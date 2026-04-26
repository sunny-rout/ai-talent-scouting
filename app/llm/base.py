"""
Abstract LLMProvider — all concrete providers implement this interface.
Imported by email_draft.py and interview_questions.py.
"""
from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """Minimal interface every LLM backend must implement."""

    @abstractmethod
    def chat(
        self,
        prompt: str,
        system: str        = "",
        temperature: float = 0.7,
        timeout: int       = 60,
    ) -> str:
        """
        Send a prompt and return the model's text response.
        Raises one of the exceptions in app.llm.exceptions on failure.
        """

    @abstractmethod
    def health_check(self) -> dict:
        """
        Quickly probe the LLM backend.
        Returns:
          {"status": "ok"|"unreachable"|"timeout"|"auth_error",
           "provider": str, "model": str, "latency_ms": int|None}
        """
