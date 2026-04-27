"""
Google AI Studio provider — uses the Gemini REST API with an API key.
Requires: google-generativeai
"""
import asyncio
import time
from typing import AsyncGenerator, List, Dict

from .base import LLMProvider


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)
        return self._client

    def _build_history(self, messages: List[Dict[str, str]]):
        """Convert OpenAI-style messages to Gemini history + last message."""
        history = []
        for m in messages[:-1]:
            role = "model" if m["role"] == "assistant" else "user"
            history.append({"role": role, "parts": [m["content"]]})
        last = messages[-1]["parts"][0] if isinstance(messages[-1].get("parts"), list) \
            else messages[-1]["content"]
        return history, last

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        import google.generativeai as genai
        client = self._get_client()
        history, last_msg = self._build_history(messages)
        chat = client.start_chat(history=history)
        cfg = genai.types.GenerationConfig(temperature=temperature, max_output_tokens=2048)
        resp = chat.send_message(last_msg, generation_config=cfg)
        return resp.text

    async def stream_chat(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        import google.generativeai as genai
        client = self._get_client()
        history, last_msg = self._build_history(messages)
        cfg = genai.types.GenerationConfig(temperature=temperature, max_output_tokens=2048)
        chat = client.start_chat(history=history)

        # google-generativeai streaming is synchronous — run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: chat.send_message(last_msg, generation_config=cfg, stream=True),
        )
        for chunk in response:
            text = getattr(chunk, "text", "") or ""
            if text:
                yield text

    def health_check(self) -> dict:
        base = {"provider": "gemini", "model": self.model}
        t0 = time.monotonic()
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            models = [m.name for m in genai.list_models()]
            latency = int((time.monotonic() - t0) * 1000)
            if not any(self.model in m for m in models):
                return {**base, "status": "model_missing", "latency_ms": latency,
                        "hint": f"Model '{self.model}' not found in your Gemini account."}
            return {**base, "status": "ok", "latency_ms": latency}
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            msg = str(exc)
            status = "auth_error" if "API_KEY" in msg.upper() or "403" in msg else "unreachable"
            return {**base, "status": status, "latency_ms": latency, "hint": msg}
