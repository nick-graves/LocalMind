import psutil
from typing import List, Dict, Any

def network_activity(only_established: bool = True, top_n: int = 50) -> List[Dict[str, Any]]:
    states_ok = {"ESTABLISHED"} if only_established else None
    rows = []
    proc_name_cache = {}
    for c in psutil.net_connections(kind="inet"):
        if states_ok and c.status not in states_ok:
            continue
        pid = c.pid
        name = None
        if pid:
            if pid in proc_name_cache:
                name = proc_name_cache[pid]
            else:
                try:
                    name = psutil.Process(pid).name()
                except Exception:
                    name = None
                proc_name_cache[pid] = name
        rows.append({
            "pid": pid,
            "process_name": name,
            "laddr": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None,
            "raddr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
            "status": c.status
        })
        if len(rows) >= top_n:
            break
    return rows


print(network_activity(True, 10))