"""
Ollama LLM provider — wraps httpx calls to the local Ollama server.
All low-level exceptions are translated into the app.llm.exceptions hierarchy.
"""
import json, time
import httpx
from app.llm.base       import LLMProvider
from app.llm.exceptions import (
    LLMConnectionError, LLMTimeoutError, LLMModelNotFoundError, LLMParseError
)


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model    = model
        self.base_url = base_url.rstrip("/")

    # ── chat ──────────────────────────────────────────────────────────────────

    def chat(self, prompt: str, system: str = "", temperature: float = 0.7, timeout: int = 90) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self.model, "messages": messages,
                   "stream": False, "options": {"temperature": temperature}}
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.post(f"{self.base_url}/api/chat", json=payload)

            if r.status_code == 404:
                raise LLMModelNotFoundError(
                    f"Model '{self.model}' not found on Ollama.",
                    hint=f"Run: ollama pull {self.model}"
                )
            r.raise_for_status()
            return r.json()["message"]["content"]

        except LLMModelNotFoundError:
            raise
        except httpx.ConnectError:
            raise LLMConnectionError(
                "Ollama server is not running.",
                hint="Start it with: ollama serve"
            )
        except httpx.TimeoutException:
            raise LLMTimeoutError(
                f"Ollama timed out after {timeout}s. "
                "Model may still be loading — wait a moment, then retry."
            )
        except (KeyError, json.JSONDecodeError) as exc:
            raise LLMParseError(f"Unexpected Ollama response: {exc}")
        except httpx.HTTPStatusError as exc:
            raise LLMConnectionError(f"Ollama HTTP error: {exc.response.status_code} {exc.response.text[:200]}")

    # ── health_check ──────────────────────────────────────────────────────────

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
