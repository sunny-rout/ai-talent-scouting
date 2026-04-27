"""
Google Vertex AI provider — uses Application Default Credentials (ADC).
Requires: google-cloud-aiplatform
"""
import time
from typing import List, Dict

from .base import LLMProvider


class VertexProvider(LLMProvider):
    def __init__(self, project: str, location: str = "us-central1", model: str = "gemini-2.0-flash"):
        self.project = project
        self.location = location
        self.model_name = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(project=self.project, location=self.location)
            self._client = GenerativeModel(self.model_name)
        return self._client

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        from vertexai.generative_models import GenerationConfig
        model = self._get_client()
        prompt = "\n\n".join(
            f"[{m['role'].capitalize()}]: {m['content']}" for m in messages
        )
        cfg = GenerationConfig(temperature=temperature, max_output_tokens=2048)
        return model.generate_content(prompt, generation_config=cfg).text

    def health_check(self) -> dict:
        base = {"provider": "vertex", "model": self.model_name}
        t0 = time.monotonic()
        try:
            self._get_client()
            latency = int((time.monotonic() - t0) * 1000)
            return {**base, "status": "ok", "latency_ms": latency}
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            msg = str(exc)
            status = "auth_error" if "credentials" in msg.lower() or "403" in msg else "unreachable"
            return {**base, "status": status, "latency_ms": latency, "hint": msg}
