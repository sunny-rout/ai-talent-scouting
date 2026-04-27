"""
Google AI Studio provider — uses the Gemini REST API with an API key.
Requires: google-generativeai
"""
import time
from typing import List, Dict

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

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        import google.generativeai as genai
        client = self._get_client()

        # Map OpenAI-style roles to Gemini roles (user/model only)
        history = []
        last_user_msg = None
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            if role == "user":
                last_user_msg = m["content"]
            history.append({"role": role, "parts": [m["content"]]})

        # Start fresh chat each call (stateless usage matches existing pattern)
        chat = client.start_chat(history=history[:-1] if len(history) > 1 else [])
        cfg = genai.types.GenerationConfig(temperature=temperature, max_output_tokens=2048)
        resp = chat.send_message(history[-1]["parts"][0], generation_config=cfg)
        return resp.text

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
