import subprocess, json, csv, io, re
from typing import Any, Dict, List, Optional

def _run_ps(cmd: str, timeout: int) -> str:
    cp = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or "powershell returned non-zero")
    return cp.stdout

def _ps_list_tasks(name_pattern: Optional[str], include_disabled: bool,
                   folder: Optional[str], max_results: int, timeout: int) -> List[Dict[str, Any]]:
    # Build PS filters
    filters = []
    if name_pattern:
        # do case-insensitive match on TaskName
        filters.append(f"$_.TaskName -match '{_escape_ps_regex(name_pattern)}'")
    if folder:
        # TaskPath looks like "\Microsoft\Windows\Defrag\"
        filters.append(f"$_.TaskPath -like '{_escape_ps_like(folder)}*'")
    if not include_disabled:
        filters.append("$_.Enabled -eq $true")

    where_clause = ""
    if filters:
        where_clause = " | Where-Object { " + " -and ".join(filters) + " }"

    ps = rf"""
$tasks = Get-ScheduledTask {where_clause} | Select-Object -First {max_results}
$tasks | ForEach-Object {{
  $t = $_
  try {{
    $info = $t | Get-ScheduledTaskInfo
  }} catch {{
    $info = $null
  }}
  [PSCustomObject]@{{
    TaskName       = $t.TaskName
    TaskPath       = $t.TaskPath
    State          = $t.State
    Enabled        = $t.Enabled
    Author         = $t.Author
    Description    = $t.Description
    LastRunTime    = if ($info) {{ $info.LastRunTime }} else {{ $null }}
    NextRunTime    = if ($info) {{ $info.NextRunTime }} else {{ $null }}
    LastTaskResult = if ($info) {{ $info.LastTaskResult }} else {{ $null }}
    Triggers       = @($t.Triggers | ForEach-Object {{ $_.ToString() }})
    Actions        = @($t.Actions  | ForEach-Object {{ $_.Execute }})
  }}
}} | ConvertTo-Json -Depth 5
""".strip()

    out = _run_ps(ps, timeout)
    out = out.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def _escape_ps_like(s: str) -> str:
    # Escape PS wildcard chars for -like; keep simple
    return s.replace("'", "''").replace("[", "`[").replace("]", "`]").replace("`", "``")

def _escape_ps_regex(s: str) -> str:
    # rough escape for -match regex
    specials = r"\.^$|?*+()[]{}"
    out = []
    for ch in s:
        if ch in specials:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out).replace("'", "''")

def _fallback_schtasks(name_pattern: Optional[str], folder: Optional[str],
                       include_disabled: bool, max_results: int, timeout: int) -> List[Dict[str, Any]]:
    # CSV gives many columns; we’ll map the important ones
    cp = subprocess.run(
        ["schtasks", "/Query", "/V", "/FO", "CSV"],
        capture_output=True, text=True, timeout=timeout
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or "schtasks returned non-zero")

    text = cp.stdout
    # schtasks emits UTF-16LE sometimes; handle BOM/encoding if needed
    try:
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
    except Exception:
        pass

    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        name = (row.get("TaskName") or row.get("TaskName ") or "").strip()
        path = (row.get("Task To Run") or "").strip()  # schtasks different semantics; use as action hint
        status = (row.get("Status") or "").strip()
        next_run = (row.get("Next Run Time") or "").strip()
        last_run = (row.get("Last Run Time") or "").strip()
        last_res = (row.get("Last Result") or "").strip()
        enabled = (row.get("Enabled") or "").strip().lower() in ("yes", "true", "1")

        # Filters
        if name_pattern and name_pattern.lower() not in name.lower():
            continue
        if folder and not name.lower().startswith("\\" + folder.strip("\\").lower()):
            continue
        if not include_disabled and not enabled:
            continue

        rows.append({
            "TaskName": name,
            "TaskPath": None,  # not provided directly by schtasks CSV
            "State": status or None,
            "Enabled": enabled,
            "Author": None,
            "Description": None,
            "LastRunTime": last_run or None,
            "NextRunTime": next_run or None,
            "LastTaskResult": last_res or None,
            "Triggers": [],  # not easily available from CSV
            "Actions": [path] if path else [],
        })
        if len(rows) >= max_results:
            break
    return rows

def list_scheduled_tasks(name_pattern: Optional[str] = None,
                         include_disabled: bool = True,
                         folder: Optional[str] = None,
                         max_results: int = 200,
                         timeout_seconds: int = 6) -> Dict[str, Any]:
    """
    Read-only enumeration of Windows Scheduled Tasks with key fields.
    Tries PowerShell (rich), falls back to 'schtasks' (CSV).
    """
    try:
        results = _ps_list_tasks(name_pattern, include_disabled, folder, max_results, timeout_seconds)
        return {
            "ok": True,
            "source": "powershell",
            "params": {
                "name_pattern": name_pattern,
                "include_disabled": include_disabled,
                "folder": folder,
                "max_results": max_results,
                "timeout_seconds": timeout_seconds
            },
            "results_count": len(results),
            "tasks": results
        }
    except Exception as ps_err:
        try:
            results = _fallback_schtasks(name_pattern, folder, include_disabled, max_results, timeout_seconds)
            return {
                "ok": True,
                "source": "schtasks",
                "params": {
                    "name_pattern": name_pattern,
                    "include_disabled": include_disabled,
                    "folder": folder,
                    "max_results": max_results,
                    "timeout_seconds": timeout_seconds
                },
                "results_count": len(results),
                "tasks": results,
                "note": f"powershell failed: {str(ps_err)[:200]}"
            }
        except Exception as sh_err:
            return {"ok": False, "error": f"powershell failed: {ps_err}; schtasks failed: {sh_err}"}