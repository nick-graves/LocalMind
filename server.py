from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List
import json
import os

# ---- import your existing logic ----
# Adjust these if your package name casing differs
from LocalMind.llm.ollama_client import Ollama
from LocalMind.mcp_server import dispatch_tool_call
from LocalMind.cli import SYSTEM_PROMPT, TOOL_SPEC  # reuse your prompt/spec

app = FastAPI(title="LocalMind API")

# CORS for local dev (frontend on file:// or localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # narrow this later if you like
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]

class ChatResponse(BaseModel):
    messages: List[Dict[str, Any]]
    answer_markdown: str

def _extract_tool_invocations(resp_json: Dict[str, Any]):
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
    if "{" in content and "}" in content and '''"name"''' in content:
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

def run_localmind_chat(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    client = Ollama()
    messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    # First assistant turn
    resp = client.chat_with_tools(messages, tools=TOOL_SPEC)
    msg = (resp.get("choices", [{}])[0] or {}).get("message", {})
    messages.append(msg)

    # Tool loop
    while True:
        calls = _extract_tool_invocations(resp)
        if not calls:
            break
        for tc in calls:
            out = dispatch_tool_call(tc["name"], tc.get("arguments") or "{}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "content": json.dumps(out)[:120000],
            })
        resp = client.chat_with_tools(messages, tools=TOOL_SPEC)
        msg = (resp.get("choices", [{}])[0] or {}).get("message", {})
        messages.append(msg)

    final_text = (messages[-1].get("content") or "").strip()
    return {"messages": messages, "answer_markdown": final_text}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = run_localmind_chat(req.messages)
    return ChatResponse(**result)