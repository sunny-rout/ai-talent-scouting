import time
import json
from typing import AsyncGenerator, List, Dict

import httpx
import requests

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    async def stream_chat(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break

    def health_check(self) -> dict:
        base = {"provider": "ollama", "model": self.model}
        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=5) as client:
                r = client.get(f"{self.base_url}/api/tags")
            latency = int((time.monotonic() - t0) * 1000)
            if r.status_code != 200:
                return {**base, "status": "unreachable", "latency_ms": latency,
                        "hint": "Ollama returned an unexpected status code."}
            models = [m["name"] for m in r.json().get("models", [])]
            if self.model not in models and not any(self.model in m for m in models):
                return {**base, "status": "model_missing", "latency_ms": latency,
                        "available_models": models,
                        "hint": f"Run: ollama pull {self.model}"}
            return {**base, "status": "ok", "latency_ms": latency}
        except httpx.ConnectError:
            return {**base, "status": "unreachable", "latency_ms": None,
                    "hint": "Ollama is not running. Start it with: ollama serve"}
        except httpx.TimeoutException:
            return {**base, "status": "timeout", "latency_ms": None,
                    "hint": "Ollama health check timed out."}
