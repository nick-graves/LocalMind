from typing import List, Dict, Any
import os, winreg, pathlib

HKLM_RUN = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
HKCU_RUN = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"

def _read_run_key(root, path) -> List[Dict[str, Any]]:
    out = []
    try:
        key = winreg.OpenKey(root, path)
    except OSError:
        return out
    i = 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
            out.append({"name": name, "command": value, "location": f"{root}\\{path}"})
            i += 1
        except OSError:
            break
    return out

def _startup_folders() -> List[str]:
    # Common + Current user Startup folders
    folders = [
        os.path.join(os.environ.get("ProgramData","C:\\ProgramData"),
                     r"Microsoft\Windows\Start Menu\Programs\StartUp"),
        os.path.join(os.environ.get("APPDATA",""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    ]
    return [f for f in folders if f and os.path.isdir(f)]

def startup_items() -> List[Dict[str, Any]]:
    items = []
    items += _read_run_key(winreg.HKEY_LOCAL_MACHINE, HKLM_RUN)
    items += _read_run_key(winreg.HKEY_CURRENT_USER, HKCU_RUN)
    for folder in _startup_folders():
        for p in pathlib.Path(folder).glob("*"):
            items.append({"name": p.name, "command": str(p), "location": folder})
    return items