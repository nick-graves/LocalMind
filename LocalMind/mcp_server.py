import json
from typing import Any, Dict, List

from LocalMind.tools.system_overview import get_system_overview
from LocalMind.tools.processes import list_processes, process_detail
from LocalMind.tools.disks import disk_usage
from LocalMind.tools.network import network_activity
from LocalMind.tools.startup import startup_items
from LocalMind.tools.file_search import find_files

TOOLS = {
    "get_system_overview": lambda args: get_system_overview(top_n=int(args.get("top_n", 5))),
    "list_processes":      lambda args: list_processes(sort_by=args.get("sort_by","cpu"), top_n=int(args.get("top_n",10))),
    "process_detail":      lambda args: process_detail(pid=int(args["pid"])),
    "disk_usage":          lambda args: disk_usage(),
    "network_activity":    lambda args: network_activity(only_established=bool(args.get("only_established", True)),
                                                         top_n=int(args.get("top_n",50))),
    "startup_items":       lambda args: startup_items(),
    "find_files": lambda args: find_files(query=args.get("query", ""), roots=args.get("roots"), max_results=int(args.get("max_results", 50)),
                                          timeout_seconds=int(args.get("timeout_seconds", 8)), use_glob=bool(args.get("use_glob", True)),),
}

def dispatch_tool_call(name: str, arguments_json: str) -> Dict[str, Any]:
    fn = TOOLS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except Exception:
        args = {}
    try:
        result = fn(args)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}