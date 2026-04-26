"""
OpenAI LLM provider — wraps the openai Python SDK.
All SDK exceptions are translated into app.llm.exceptions.
"""
import json, time
from app.llm.base       import LLMProvider
from app.llm.exceptions import (
    LLMConnectionError, LLMTimeoutError, LLMAuthError,
    LLMRateLimitError, LLMParseError
)


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", api_key: str = ""):
        self.model   = model
        self.api_key = api_key
        self._client = None  # lazy-init so import works without openai installed

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise LLMConnectionError(
                    "openai package not installed.",
                    hint="Run: pip install openai"
                )
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    # ── chat ──────────────────────────────────────────────────────────────────

    def chat(self, prompt: str, system: str = "", temperature: float = 0.7, timeout: int = 60) -> str:
        import openai as _oai

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = self._get_client().chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                timeout=timeout,
            )
            return resp.choices[0].message.content

        except _oai.AuthenticationError:
            raise LLMAuthError("Invalid OpenAI API key.")
        except _oai.RateLimitError:
            raise LLMRateLimitError("OpenAI rate limit exceeded.")
        except _oai.APITimeoutError:
            raise LLMTimeoutError(f"OpenAI timed out after {timeout}s.")
        except _oai.APIConnectionError as exc:
            raise LLMConnectionError(f"Cannot reach OpenAI API: {exc}")
        except (KeyError, IndexError, AttributeError) as exc:
            raise LLMParseError(f"Unexpected OpenAI response structure: {exc}")

    # ── health_check ──────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        import openai as _oai
        base = {"provider": "openai", "model": self.model}
        t0 = time.monotonic()
        try:
            self._get_client().models.retrieve(self.model)
            latency = int((time.monotonic() - t0) * 1000)
            return {**base, "status": "ok", "latency_ms": latency}
        except _oai.AuthenticationError:
            return {**base, "status": "auth_error", "latency_ms": None,
                    "hint": "Check OPENAI_API_KEY in your .env file."}
        except _oai.RateLimitError:
            return {**base, "status": "rate_limited", "latency_ms": None,
                    "hint": "OpenAI rate limit hit — wait a minute."}
        except _oai.APIConnectionError:
            return {**base, "status": "unreachable", "latency_ms": None,
                    "hint": "Cannot reach api.openai.com — check your internet connection."}
        except Exception as exc:
            return {**base, "status": "error", "latency_ms": None, "hint": str(exc)}
