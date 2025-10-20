import os, fnmatch, time, stat
from typing import List, Dict, Any, Iterable
from datetime import datetime

def _default_roots() -> List[str]:
    # Reasonable defaults: user profile + common libraries
    roots = []
    user = os.environ.get("USERPROFILE")
    if user:
        roots.extend([
            user,
            os.path.join(user, "Documents"),
            os.path.join(user, "Desktop"),
            os.path.join(user, "Downloads"),
            os.path.join(user, "Pictures"),
            os.path.join(user, "OneDrive")  # if present
        ])
    # Add fixed drives (C:\ only by default; expand if needed)
    roots.append("C:\\")
    # Deduplicate and keep existing
    out = []
    seen = set()
    for r in roots:
        if r and os.path.isdir(r) and r.lower() not in seen:
            out.append(r)
            seen.add(r.lower())
    return out

def _iter_dirs(root: str) -> Iterable[str]:
    # Robust walk: ignore reparse points & system dirs that explode traversal cost
    skip_dirs = { "$Recycle.Bin", "System Volume Information", "Windows\\WinSxS" }
    for dirpath, dirnames, _ in os.walk(root, topdown=True, followlinks=False):
        low = dirpath.lower()
        if any(s.lower() in low for s in skip_dirs):
            # prune
            dirnames[:] = []
            continue
        yield dirpath

def _match_name(name: str, query: str, use_glob: bool) -> bool:
    name_l = name.lower()
    q = query.lower()
    if use_glob:
        return fnmatch.fnmatch(name_l, q)
    return q in name_l

def _file_info(fullpath: str) -> Dict[str, Any]:
    try:
        st = os.stat(fullpath)
        # skip directories
        if stat.S_ISDIR(st.st_mode):
            return {}
        return {
            "path": fullpath,
            "size_bytes": int(st.st_size),
            "modified_utc": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z"
        }
    except Exception as e:
        return {"path": fullpath, "error": str(e)}

def _confidence(name: str, query: str, use_glob: bool) -> float:
    n, q = name.lower(), query.lower()
    if n == q: return 1.0
    if use_glob:
        # crude heuristic: exact suffix match is strong
        if q.startswith("*.") and n.endswith(q[1:]):
            return 0.9
    if q in n:
        return max(0.6, 1.0 - (len(n) - len(q)) * 0.01)
    return 0.5

def find_files(query: str, roots: List[str] = None, max_results: int = 50,
               timeout_seconds: int = 8, use_glob: bool = True) -> Dict[str, Any]:
    if not query or not isinstance(query, str):
        return {"ok": False, "error": "query must be a non-empty string"}

    roots = roots or _default_roots()
    t0 = time.monotonic()
    hits: List[Dict[str, Any]] = []
    scanned_dirs = 0

    try:
        for root in roots:
            if time.monotonic() - t0 > timeout_seconds:
                break
            if not os.path.isdir(root):
                continue
            for dirpath in _iter_dirs(root):
                scanned_dirs += 1
                if time.monotonic() - t0 > timeout_seconds:
                    break
                try:
                    with os.scandir(dirpath) as it:
                        for entry in it:
                            if time.monotonic() - t0 > timeout_seconds:
                                break
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            name = entry.name
                            if _match_name(name, query, use_glob):
                                info = _file_info(entry.path)
                                if info:
                                    info["confidence"] = _confidence(name, query, use_glob)
                                    hits.append(info)
                                    if len(hits) >= max_results:
                                        break
                        if len(hits) >= max_results:
                            break
                except PermissionError:
                    continue
                except Exception:
                    continue
                if len(hits) >= max_results:
                    break
            if len(hits) >= max_results:
                break
    except Exception as e:
        return {"ok": False, "error": str(e), "scanned_dirs": scanned_dirs, "roots": roots}

    # sort: higher confidence, then newest modified
    hits.sort(key=lambda x: (x.get("confidence", 0.0), x.get("modified_utc", "")), reverse=True)
    elapsed = round(time.monotonic() - t0, 3)
    return {
        "ok": True,
        "query": query,
        "roots": roots,
        "elapsed_seconds": elapsed,
        "scanned_dirs": scanned_dirs,
        "results_count": len(hits),
        "results": hits
    }