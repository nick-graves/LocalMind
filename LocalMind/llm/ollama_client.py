import json, os, requests
from typing import Any, Dict, List, Optional

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("LOCALMIND_MODEL", "llama3.1:8b-instruct-q8_0")

class Ollama:
    def __init__(self, model: str = MODEL):
        self.model = model

    def chat_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Returns the raw Ollama response. If tool calls are present, you'll see them in response['message']['tool_calls'].
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "required",
            "temperature": 0.0,
            "stream": False
        }

        if os.getenv("LOCALMIND_DEBUG", "1") == "1":
            print("\n================= OLLAMA REQUEST =================")
            import json
            print(json.dumps(payload, indent=2)[:2000])
            print("==================================================\n")

        r = requests.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload, timeout=120)
        r.raise_for_status()
        resp = r.json()

        if os.getenv("LOCALMIND_DEBUG", "1") == "1":
            print("\n================= OLLAMA RESPONSE =================")
            print(json.dumps(resp, indent=2)[:4000])
            print("===================================================\n")

        return resp