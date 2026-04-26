from abc import ABC, abstractmethod
from typing import List, Dict

class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """
        Send a chat message to the LLM and return the response.
        """
    
    @abstractmethod
    def health_check(self) -> dict:
        """
        Quickly probe the LLM backend.
        Returns:
          {"status": "ok"|"unreachable"|"timeout"|"auth_error",
           "provider": str, "model": str, "latency_ms": int|None}
        """