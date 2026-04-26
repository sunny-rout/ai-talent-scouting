"""LLM package — import helpers."""
from .base import LLMProvider
from .exceptions import (
    LLMError, LLMConnectionError, LLMTimeoutError,
    LLMAuthError, LLMRateLimitError, LLMParseError, LLMModelNotFoundError,
)
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .vertex_provider import VertexProvider
from app.config import LLM_PROVIDER, OLLAMA_MODEL, OLLAMA_BASE_URL, VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_MODEL

def get_provider(provider_name=None, model=None) -> LLMProvider:
    name = (provider_name or LLM_PROVIDER).lower()
    if name == "vertex":
        return VertexProvider(project=VERTEX_PROJECT, location=VERTEX_LOCATION, model=model or VERTEX_MODEL)
    return OllamaProvider(base_url=OLLAMA_BASE_URL, model=model or OLLAMA_MODEL)

__all__ = [
    "LLMProvider",
    "OllamaProvider", "OpenAIProvider", "VertexProvider",
    "get_provider",
    "LLMError", "LLMConnectionError", "LLMTimeoutError",
    "LLMAuthError", "LLMRateLimitError", "LLMParseError", "LLMModelNotFoundError",
]
