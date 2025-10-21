import os, json, ast
from typing import Any, Dict, List

from LocalMind.utils.arg_normalize import normalize_args

from LocalMind.tools.system_overview import get_system_overview
from LocalMind.tools.processes import list_processes, process_detail
from LocalMind.tools.disks import disk_usage
from LocalMind.tools.network import network_activity
from LocalMind.tools.startup import startup_items
from LocalMind.tools.file_search import find_files
from LocalMind.tools.large_files import list_large_files
from LocalMind.tools.wifi import wifi_info
from LocalMind.tools.system_info import get_system_info
from LocalMind.tools.scheduled_tasks import list_scheduled_tasks


TOOLS = {
    "get_system_overview": lambda args: get_system_overview(**args),
    "list_processes":      lambda args: list_processes(**args),
    "process_detail":      lambda args: process_detail(**args),
    "disk_usage":          lambda args: disk_usage(**args),
    "network_activity":    lambda args: network_activity(**args),
    "startup_items":       lambda args: startup_items(**args),
    "find_files":          lambda args: find_files(**args),
    "list_large_files":    lambda args: list_large_files(**args),
    "wifi_info":           lambda args: wifi_info(**args),
    "get_system_info":     lambda args: get_system_info(**args),
    "list_scheduled_tasks":lambda args: list_scheduled_tasks(**args),
}

def dispatch_tool_call(name: str, arguments_json_or_dict: Any) -> Dict[str, Any]:
    fn = TOOLS.get(name)
    if not fn:
        return {"ok": False, "error": f"unknown tool: {name}"}

    # 1) Parse arguments from various shapes the model may emit
    args: Dict[str, Any] = {}
    if isinstance(arguments_json_or_dict, dict):
        args = arguments_json_or_dict
    elif isinstance(arguments_json_or_dict, str):
        # try JSON first
        try:
            args = json.loads(arguments_json_or_dict)
        except Exception:
            # then a safe Python literal (handles "['C:\\\\','D:\\\\']" cases)
            try:
                val = ast.literal_eval(arguments_json_or_dict)
                if isinstance(val, dict):
                    args = val
                else:
                    # if it's not a dict, wrap it (rare)
                    args = {"value": val}
            except Exception:
                args = {}
    else:
        args = {}

    # 2) Normalize/coerce types & clean paths (roots, booleans, ints, etc.)
    try:
        args = normalize_args(name, args)
    except Exception as e:
        return {"ok": False, "error": f"arg normalization failed: {e}"}

    # Optional debug
    if os.getenv("LOCALMIND_DEBUG", "0") == "1":
        print(f"[dispatch] {name} <- {args}")

    # 3) Call the tool
    try:
        out = fn(args)

        # If tool already returns a dict with ok/result/error, pass it through
        if isinstance(out, dict) and ("ok" in out or "result" in out or "error" in out):
            return out

        # Otherwise, wrap the raw return
        return {"ok": True, "result": out}
    except Exception as e:
        return {"ok": False, "error": f"{name} failed: {e.__class__.__name__}: {e}"}