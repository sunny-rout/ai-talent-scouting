"""
OpenAI provider — works with the official OpenAI API and any OpenAI-compatible
endpoint (e.g. Azure OpenAI, local LM Studio, Groq) via OPENAI_BASE_URL.
Requires: openai>=1.0
"""
import time
from typing import List, Dict

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or None
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        return resp.choices[0].message.content

    def health_check(self) -> dict:
        base = {"provider": "openai", "model": self.model}
        t0 = time.monotonic()
        try:
            client = self._get_client()
            models = [m.id for m in client.models.list()]
            latency = int((time.monotonic() - t0) * 1000)
            if self.model not in models:
                return {**base, "status": "model_missing", "latency_ms": latency,
                        "hint": f"Model '{self.model}' not found in your OpenAI account."}
            return {**base, "status": "ok", "latency_ms": latency}
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            msg = str(exc)
            status = "auth_error" if "401" in msg or "Incorrect API key" in msg else "unreachable"
            return {**base, "status": status, "latency_ms": latency, "hint": msg}
