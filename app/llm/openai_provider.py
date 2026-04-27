"""
OpenAI provider — works with the official OpenAI API and any OpenAI-compatible
endpoint (e.g. Azure OpenAI, local LM Studio, Groq) via OPENAI_BASE_URL.
Requires: openai>=1.0
"""
import time
from typing import AsyncGenerator, List, Dict

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or None
        self._sync_client = None
        self._async_client = None

    def _get_sync_client(self):
        if self._sync_client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._sync_client = OpenAI(**kwargs)
        return self._sync_client

    def _get_async_client(self):
        if self._async_client is None:
            from openai import AsyncOpenAI
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._async_client = AsyncOpenAI(**kwargs)
        return self._async_client

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        client = self._get_sync_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        return resp.choices[0].message.content

    async def stream_chat(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        client = self._get_async_client()
        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=700,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def health_check(self) -> dict:
        base = {"provider": "openai", "model": self.model}
        t0 = time.monotonic()
        try:
            client = self._get_sync_client()
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
