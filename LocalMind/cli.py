import json, os, sys
from pathlib import Path
from rich.console import Console
from LocalMind.llm.ollama_client import Ollama
from LocalMind.mcp_server import dispatch_tool_call


VERBOSE = os.getenv("LOCALMIND_DEBUG", "1") == "1"

console = Console()

def load_system_prompt(path: str = "system_prompt.txt") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"[warning] Could not load system prompt from {path}: {e}")
        return "You are LocalMind, a read-only Windows system assistant."

SYSTEM_PROMPT = load_system_prompt()


TOOL_SPEC = [
  {
    "type": "function",
    "function": {
      "name": "get_system_overview",
      "description": "Snapshot of CPU/RAM/disk plus top processes by CPU and memory.",
      "parameters": {
        "type": "object",
        "properties": { "top_n": { "type": "integer", "minimum": 1, "maximum": 50, "default": 5 } }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "list_processes",
      "description": "List processes with cpu%, memory MB, exe path, and cmdline.",
      "parameters": {
        "type": "object",
        "properties": {
          "sort_by": { "type": "string", "enum": ["cpu","mem","name"], "default": "cpu" },
          "top_n":   { "type": "integer", "minimum": 1, "maximum": 100, "default": 10 }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "process_detail",
      "description": "Deep dive on a single process (read-only).",
      "parameters": {
        "type": "object",
        "properties": { "pid": { "type": "integer" } },
        "required": ["pid"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "disk_usage",
      "description": "Per-volume capacity, used, free, percent used.",
      "parameters": { "type": "object", "properties": {} }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "network_activity",
      "description": "List TCP/UDP connections with pid and process name.",
      "parameters": {
        "type": "object",
        "properties": {
          "only_established": { "type": "boolean", "default": True },
          "top_n": { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "startup_items",
      "description": "Read-only startup entries from registry and Startup folders.",
      "parameters": { "type": "object", "properties": {} }
    }
  },
  {
    "type": "function",
    "function": {
        "name": "find_files",
        "description": "Search for files by name/pattern on Windows (read-only). Returns matching file paths with size and modified time.",
        "parameters": {
        "type": "object",
        "properties": {
            "query": { "type": "string", "description": "Filename or pattern, e.g., 'jobs.xls' or '*.xlsx'." },
            "roots": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Optional list of root directories to search. Defaults to user profile and common libraries."
            },
            "max_results": { "type": "integer", "default": 50, "minimum": 1, "maximum": 1000 },
            "timeout_seconds": { "type": "integer", "default": 8, "minimum": 1, "maximum": 60 },
            "use_glob": { "type": "boolean", "default": True, "description": "If true, treat query like a glob (*.xlsx). If false, do substring match." }
        },
        "required": ["query"]
        }
    }  
  },
  {
    "type": "function",
    "function": {
      "name": "list_large_files",
      "description": "Find largest files and (optionally) folders under given roots. Read-only, bounded by timeout.",
      "parameters": {
        "type": "object",
        "properties": {
          "top_n": { "type": "integer", "minimum": 1, "maximum": 200, "default": 20 },
          "include_folders": { "type": "boolean", "default": False },
          "roots": { "type": "array", "items": { "type": "string" } },
          "timeout_seconds": { "type": "integer", "minimum": 2, "maximum": 60, "default": 10 }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "wifi_info",
      "description": "List nearby Wi-Fi networks with SSID, BSSID, signal percent, channel, auth and encryption.",
      "parameters": {
        "type": "object",
        "properties": {
          "timeout_seconds": { "type": "integer", "minimum": 2, "maximum": 20, "default": 6 }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_system_info",
      "description": "Windows system info: version, uptime, CPU, memory, GPU names. Read-only.",
      "parameters": { "type": "object", "properties": {} }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "list_scheduled_tasks",
      "description": "List Windows Scheduled Tasks (read-only): name, path, enabled, state, next/last run, triggers, actions.",
      "parameters": {
        "type": "object",
        "properties": {
          "name_pattern": { "type": "string", "description": "Case-insensitive substring or regex to match TaskName." },
          "include_disabled": { "type": "boolean", "default": True },
          "folder": { "type": "string", "description": "Filter by TaskPath folder, e.g. '\\\\Microsoft\\\\Windows'." },
          "max_results": { "type": "integer", "minimum": 1, "maximum": 1000, "default": 200 },
          "timeout_seconds": { "type": "integer", "minimum": 2, "maximum": 30, "default": 6 }
        }
      }
    }
  }

]

def _extract_tool_invocations(resp_json):
    """
    Return a list of {"id": str, "name": str, "arguments": str} from different response shapes.
    """
    invocations = []
    msg = (resp_json.get("choices", [{}])[0]
                  .get("message", {}))

    # 1) OpenAI multi-tool format
    tc = msg.get("tool_calls") or []
    for i, t in enumerate(tc):
        fn = t.get("function", {})
        invocations.append({
            "id": t.get("id", f"tool_{i}"),
            "name": fn.get("name"),
            "arguments": fn.get("arguments") or "{}",
        })
    if invocations:
        return invocations

    # 2) Older single function_call format
    fc = msg.get("function_call")
    if fc and isinstance(fc, dict) and fc.get("name"):
        invocations.append({
            "id": "func_0",
            "name": fc["name"],
            "arguments": fc.get("arguments") or "{}",
        })
        return invocations

    # 3) Plain-text fallback: look for {"name": "...", "parameters": {...}} in content
    content = msg.get("content") or ""
    if "{" in content and "}" in content and '"name"' in content:
        import re, json
        # very small, safe JSON sniffer (first balanced object-ish)
        match = re.search(r'(\{.*"name"\s*:\s*".*?".*\})', content, re.DOTALL)
        if match:
            blob = match.group(1)
            try:
                obj = json.loads(blob)
                name = obj.get("name")
                args = obj.get("parameters") or obj.get("arguments") or {}
                invocations.append({
                    "id": "text_0",
                    "name": name,
                    "arguments": json.dumps(args),
                })
            except Exception:
                pass
    return invocations

def _run_tool_calls(response_json, messages, client):
    """
    Keep executing tools until the model stops asking.
    """
    def _msg_from(resp):
        return (resp.get("choices", [{}])[0] or {}).get("message", {})  # safe-ish

    if VERBOSE:
        from rich.console import Console
        console = Console()
        console.rule("[bold cyan]Tool Loop Start[/bold cyan]")

    # First turn: show what the model said
    msg = _msg_from(response_json)
    if VERBOSE:
        content = msg.get("content") or ""
        console.print(f"[bold]Assistant content (pre-tools):[/bold]\n{content[:1000]}")
        console.print(f"[bold]Raw assistant message:[/bold]\n{json.dumps(msg, indent=2)[:1200]}")

    while True:
        calls = _extract_tool_invocations(response_json)

        if VERBOSE:
            if calls:
                console.print(f"[bold]Extracted tool calls ({len(calls)}):[/bold]")
                for i, tc in enumerate(calls):
                    console.print(f"  {i+1}. [yellow]{tc.get('name')}[/yellow] args={tc.get('arguments')}")
            else:
                console.print("[bold red]No tool calls found. Exiting tool loop.[/bold red]")

        if not calls:
            return response_json  # no tools requested → done

        for tc in calls:
            if VERBOSE:
                console.print(f"[yellow]→ Executing tool:[/yellow] {tc['name']}")
                console.print(f"[dim]Arguments:[/dim] {tc.get('arguments')}\n")

            out = dispatch_tool_call(tc["name"], tc.get("arguments") or "{}")

            if VERBOSE:
                console.print(f"[green]✔ Tool result (truncated):[/green] {str(out)[:500]}")

            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "name": tc["name"],
                "content": json.dumps(out)[:120000],
            }

            if VERBOSE:
                console.print("[blue]Sending tool result back to model...[/blue]\n")

            messages.append(tool_msg)

        # Ask model to continue with tool results
        response_json = client.chat_with_tools(messages, tools=TOOL_SPEC)
        new_msg = _msg_from(response_json)
        messages.append(new_msg)

        if VERBOSE:
            console.rule("[bold cyan]Model Follow-up[/bold cyan]")
            console.print(f"[bold]Assistant content:[/bold]\n{(new_msg.get('content') or '')[:1000]}")
            console.print(f"[bold]Raw assistant message:[/bold]\n{json.dumps(new_msg, indent=2)[:1200]}")




def main():
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        console.print("[bold]LocalMind[/bold] (Windows, read-only, offline). Ask a question:")
        question = input("> ").strip()

    client = Ollama()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question}
    ]

    # First turn with tool specs
    resp = client.chat_with_tools(messages, tools=TOOL_SPEC)
    messages.append(resp["choices"][0]["message"])
    resp = _run_tool_calls(resp, messages, client)

    # Final answer
    final_msg = resp["choices"][0]["message"]["content"]
    console.print("\n[bold]LocalMind:[/bold] " + (final_msg or "(no content)"))

    if VERBOSE:
        console.rule("[bold green]Conversation complete[/bold green]")
        console.print("Final messages stack:")
        for m in messages:
            role = m.get("role")
            summary = (m.get("content") or str(m)[:200])
            console.print(f"[{role}] {summary[:200]}")

if __name__ == "__main__":
    main()