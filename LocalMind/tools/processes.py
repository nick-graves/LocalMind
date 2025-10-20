import psutil
from typing import List, Dict, Any

def list_processes(sort_by: str = "cpu", top_n: int = 200) -> List[Dict[str, Any]]:
    rows = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_info","exe","username","cmdline"]):
        info = p.info
        rows.append({
            "pid": info.get("pid"),
            "name": info.get("name"),
            "cpu_percent": info.get("cpu_percent", 0.0),
            "memory_mb": round((info.get("memory_info").rss if info.get("memory_info") else 0)/ (1024*1024), 1),
            "exe": info.get("exe"),
            "user": info.get("username"),
            "cmdline": " ".join(info.get("cmdline") or [])[:400]
        })
    key = {"cpu": "cpu_percent", "mem": "memory_mb", "name": "name"}[sort_by]
    rows.sort(key=lambda x: (x[key] or 0) if key != "name" else (x[key] or ""), reverse=(key!="name"))
    return rows[:top_n]

def process_detail(pid: int) -> Dict[str, Any]:
    import datetime
    p = psutil.Process(pid)
    with p.oneshot():
        open_files = [{"path": f.path, "fd": f.fd} for f in (p.open_files() or [])][:50]
        conns = [{"laddr": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None,
                  "raddr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
                  "status": c.status} for c in (p.connections(kind="inet") or [])][:50]
        info = {
            "pid": pid,
            "name": p.name(),
            "exe": p.exe() if p.exe() else None,
            "username": p.username(),
            "create_time": datetime.datetime.fromtimestamp(p.create_time()).isoformat(),
            "cpu_percent": p.cpu_percent(interval=0.3),
            "memory_mb": round(p.memory_info().rss/ (1024*1024), 1),
            "num_threads": p.num_threads(),
            "parent_pid": (p.parent().pid if p.parent() else None),
            "children_pids": [c.pid for c in p.children(recursive=False)],
            "open_files": open_files,
            "connections": conns,
            "cmdline": " ".join(p.cmdline())[:800]
        }
    return info