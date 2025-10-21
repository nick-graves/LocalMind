import ast, json, os
from typing import Any, Dict, List

def _coerce_bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true","1","yes","on"): return True
        if s in ("false","0","no","off"): return False
    return v

def _parse_array_messy(v):
    # Accept: real list, JSON string, Python repr string, comma string
    if isinstance(v, list): return v
    if isinstance(v, str):
        s = v.strip()
        # try json
        try:
            out = json.loads(s)
            if isinstance(out, list): return out
        except Exception:
            pass
        # try python literal
        try:
            out = ast.literal_eval(s)
            if isinstance(out, list): return out
        except Exception:
            pass
        # try comma-split
        if "," in s:
            return [x.strip() for x in s.split(",") if x.strip()]
        # handle quoted drives like "'C:\\'"
        if s.startswith("'") and s.endswith("'"):
            return [s[1:-1]]
        return [s]
    return [v]

def _clean_roots(roots: List[str]):
    out = []
    seen = set()
    for r in roots:
        r = r.strip().strip('"').strip("'")
        # Normalize common mistakes
        if r == "\\Users\\" or r == "/Users/":
            r = os.path.join(os.environ.get("SystemDrive","C:"), "Users")
        if r in ("C:", "D:", "E:"): r += "\\"
        if not os.path.isabs(r):
            # best effort: anchor to system drive
            r = os.path.join(os.environ.get("SystemDrive","C:"), r.lstrip("\\/"))
        r = os.path.normpath(r)
        if r.lower() not in seen and os.path.isdir(r):
            seen.add(r.lower()); out.append(r)
    return out

def normalize_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    a = dict(args or {})
    # Common coercions
    for k in list(a.keys()):
        if k in ("top_n","timeout_seconds","max_results"):
            try: a[k] = int(a[k])
            except Exception: pass
        if k in ("only_established","include_folders","include_disabled"):
            a[k] = _coerce_bool(a[k])

    if tool_name == "list_large_files":
        roots = _parse_array_messy(a.get("roots") or [])
        roots = _clean_roots(roots)
        a["roots"] = roots
        # reasonable safety nets
        a["top_n"] = max(1, min(int(a.get("top_n", 20)), 200))
        a["timeout_seconds"] = max(5, min(int(a.get("timeout_seconds", 15)), 120))
        if "include_folders" not in a:
            a["include_folders"] = False

    if tool_name == "find_files":
        roots = _parse_array_messy(a.get("roots") or [])
        a["roots"] = _clean_roots(roots)

    if tool_name == "network_activity":
        a["top_n"] = max(1, min(int(a.get("top_n", 50)), 200))
        a["only_established"] = _coerce_bool(a.get("only_established", True))

    if tool_name == "list_scheduled_tasks":
        a["max_results"] = max(1, min(int(a.get("max_results", 200)), 1000))

    return a