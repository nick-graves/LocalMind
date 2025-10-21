import platform, psutil, time, subprocess, json
from datetime import datetime

def _fmt_utc(ts: float) -> str:
    try:
        return datetime.utcfromtimestamp(ts).isoformat() + "Z"
    except Exception:
        return ""

def _ps_once(cmd: str, timeout: int = 4) -> str:
    cp = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    if cp.returncode != 0:
        return ""
    return cp.stdout.strip()

def _cpu_name() -> str:
    out = _ps_once('Get-CimInstance -ClassName Win32_Processor | Select-Object -ExpandProperty Name')
    return out.splitlines()[0].strip() if out else (platform.processor() or "")

def _gpu_names() -> list:
    out = _ps_once('Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name')
    names = [l.strip() for l in out.splitlines() if l.strip()] if out else []
    return names

def get_system_info():
    try:
        uname = platform.uname()
        win_ver = platform.win32_ver()
        boot_ts = psutil.boot_time()
        vm = psutil.virtual_memory()

        info = {
            "ok": True,
            "os": {
                "system": uname.system,
                "release": uname.release,
                "version": uname.version,
                "win32_ver": {
                    "release": win_ver[0],
                    "version": win_ver[1],
                    "csd": win_ver[2],
                    "ptype": win_ver[3],
                }
            },
            "machine": {
                "node": uname.node,
                "architecture": platform.machine(),
                "cpu_name": _cpu_name(),
                "cpu_physical_cores": psutil.cpu_count(logical=False) or 0,
                "cpu_logical_cores": psutil.cpu_count(logical=True) or 0,
                "gpus": _gpu_names(),
            },
            "memory": {
                "total_bytes": int(vm.total),
                "available_bytes": int(vm.available),
                "used_bytes": int(vm.used),
                "percent_used": float(vm.percent)
            },
            "uptime": {
                "boot_time_utc": _fmt_utc(boot_ts),
                "uptime_seconds": int(time.time() - boot_ts)
            }
        }
        return info
    except Exception as e:
        return {"ok": False, "error": str(e)}