import psutil, time
from typing import Dict, Any

def get_system_overview(top_n: int = 5) -> Dict[str, Any]:
    psutil.cpu_percent(None)  # prime
    time.sleep(0.3)           # short sample window
    cpu = psutil.cpu_percent(interval=0.7)
    vm = psutil.virtual_memory()
    disks = {p.mountpoint: psutil.disk_usage(p.mountpoint)._asdict()
             for p in psutil.disk_partitions(all=False)
             if p.fstype and "cdrom" not in p.opts}

    procs = []
    for p in psutil.process_iter(["pid","name","cpu_percent","memory_info","exe","username"]):
        info = p.info
        procs.append({
            "pid": info.get("pid"),
            "name": info.get("name"),
            "cpu_percent": info.get("cpu_percent", 0.0),
            "memory_mb": round((info.get("memory_info").rss if info.get("memory_info") else 0)/ (1024*1024), 1),
            "exe": info.get("exe"),
            "user": info.get("username")
        })
    top_cpu = sorted(procs, key=lambda x: x["cpu_percent"] or 0, reverse=True)[:top_n]
    top_mem = sorted(procs, key=lambda x: x["memory_mb"] or 0, reverse=True)[:top_n]
    return {
        "cpu_percent": cpu,
        "memory": {"total_mb": round(vm.total/1_048_576,1), "used_mb": round(vm.used/1_048_576,1),
                   "percent": vm.percent},
        "disks": disks,
        "top_cpu_processes": top_cpu,
        "top_mem_processes": top_mem
    }
