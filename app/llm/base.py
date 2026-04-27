from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """Send a chat request and return the full response string."""

    @abstractmethod
    async def stream_chat(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Yield response tokens one at a time as an async generator.
        Each yielded value is a plain string fragment (never None/empty).
        Implementations must be async generators (use `yield`).
        """

    @abstractmethod
    def health_check(self) -> dict:
        """
        Quickly probe the LLM backend.
        Returns:
          {"status": "ok"|"unreachable"|"timeout"|"auth_error",
           "provider": str, "model": str, "latency_ms": int|None}
        """
