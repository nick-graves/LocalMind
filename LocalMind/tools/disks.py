import psutil
from typing import Dict, Any

def disk_usage():
    out = {}
    for p in psutil.disk_partitions(all=False):
        if p.fstype and "cdrom" not in p.opts:
            du = psutil.disk_usage(p.mountpoint)
            out[p.mountpoint] = {
                "bytes_total": int(du.total),
                "bytes_used": int(du.used),
                "bytes_free": int(du.free),
                "percent_used": float(du.percent)
            }
    return out

