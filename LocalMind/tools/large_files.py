import os, time, stat
from typing import Dict, Any, List, Tuple
from datetime import datetime

DEFAULT_EXCLUDES = {
    r"C:\Windows\WinSxS",
    r"C:\Windows\SoftwareDistribution",
    r"C:\$Recycle.Bin",
    r"C:\System Volume Information",
}

def _default_roots() -> List[str]:
    roots = []
    user = os.environ.get("USERPROFILE")
    if user:
        roots += [
            os.path.join(user, "Desktop"),
            os.path.join(user, "Documents"),
            os.path.join(user, "Downloads"),
            os.path.join(user, "Pictures"),
            user
        ]
    roots.append("C:\\")
    # dedupe + keep existing
    out, seen = [], set()
    for r in roots:
        if r and os.path.isdir(r):
            low = r.lower()
            if low not in seen:
                seen.add(low); out.append(r)
    return out

def _fmt_utc(ts: float) -> str:
    try:
        return datetime.utcfromtimestamp(ts).isoformat() + "Z"
    except Exception:
        return ""

def _largest_files(roots: List[str], top_n: int, timeout: int) -> List[Dict[str, Any]]:
    t0 = time.monotonic()
    heap: List[Tuple[int, str, float]] = []  # (size, path, mtime)
    files: List[Tuple[int, str, float]] = []

    def add(path: str, st: os.stat_result):
        files.append((int(st.st_size), path, float(st.st_mtime)))

    for root in roots:
        if time.monotonic() - t0 > timeout: break
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            if time.monotonic() - t0 > timeout: break
            # prune excluded dirs
            low = dirpath.lower()
            if any(low.startswith(ex.lower()) for ex in DEFAULT_EXCLUDES):
                dirnames[:] = []
                continue
            try:
                for name in filenames:
                    if time.monotonic() - t0 > timeout: break
                    full = os.path.join(dirpath, name)
                    try:
                        st = os.stat(full)
                        if not stat.S_ISREG(st.st_mode):
                            continue
                        add(full, st)
                    except Exception:
                        continue
            except Exception:
                continue

    # sort once at end (faster than pushing to heap repeatedly given bounded time)
    files.sort(key=lambda x: x[0], reverse=True)
    out = []
    for size, path, mtime in files[:top_n]:
        out.append({
            "path": path,
            "size_bytes": size,
            "modified_utc": _fmt_utc(mtime)
        })
    return out

def _dir_size_bounded(path: str, t0: float, timeout: int) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        if time.monotonic() - t0 > timeout: return total
        low = dirpath.lower()
        if any(low.startswith(ex.lower()) for ex in DEFAULT_EXCLUDES):
            dirnames[:] = []
            continue
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
                if stat.S_ISREG(st.st_mode):
                    total += int(st.st_size)
            except Exception:
                continue
    return total

def _largest_folders(roots: List[str], top_n: int, timeout: int) -> List[Dict[str, Any]]:
    t0 = time.monotonic()
    candidates: List[str] = []
    # Shallow discovery first (one level down per root)
    for root in roots:
        if time.monotonic() - t0 > timeout: break
        try:
            with os.scandir(root) as it:
                for e in it:
                    if time.monotonic() - t0 > timeout: break
                    if e.is_dir(follow_symlinks=False):
                        candidates.append(e.path)
        except Exception:
            continue

    # Compute sizes with global timeout
    sized: List[Tuple[int, str]] = []
    for d in candidates:
        if time.monotonic() - t0 > timeout: break
        try:
            sz = _dir_size_bounded(d, t0, timeout)
            sized.append((sz, d))
        except Exception:
            continue

    sized.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sz, d in sized[:top_n]:
        try:
            st = os.stat(d)
            out.append({
                "path": d,
                "size_bytes": int(sz),
                "modified_utc": _fmt_utc(st.st_mtime)
            })
        except Exception:
            out.append({
                "path": d, "size_bytes": int(sz)
            })
    return out

def list_large_files(top_n: int = 20,
                     include_folders: bool = False,
                     roots: List[str] = None,
                     timeout_seconds: int = 10) -> Dict[str, Any]:
    roots = roots or _default_roots()
    try:
        files = _largest_files(roots, top_n, timeout_seconds)
        folders = _largest_folders(roots, top_n, timeout_seconds) if include_folders else []
        return {
            "ok": True,
            "params": {
                "top_n": top_n,
                "include_folders": include_folders,
                "roots": roots,
                "timeout_seconds": timeout_seconds
            },
            "files": files,
            "folders": folders
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}