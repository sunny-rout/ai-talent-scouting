"""
LLM provider factory.

Supported providers (set LLM_PROVIDER in .env):
  ollama  — local Ollama server (default)
  gemini  — Google AI Studio via API key
  vertex  — Google Vertex AI via ADC
  openai  — OpenAI (or any OpenAI-compatible endpoint)
  auto    — tries ollama → gemini → openai → vertex, returns first healthy one
"""
import logging
from typing import Optional

from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .gemini_provider import GeminiProvider
from .vertex_provider import VertexProvider
from .openai_provider import OpenAIProvider
import app.config as cfg

logger = logging.getLogger("talentscout.llm")


def _build(name: str, model: Optional[str] = None) -> LLMProvider:
    """Construct a provider instance by name."""
    name = name.lower()
    if name == "ollama":
        return OllamaProvider(base_url=cfg.OLLAMA_BASE_URL, model=model or cfg.OLLAMA_MODEL)
    if name == "gemini":
        if not cfg.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")
        return GeminiProvider(api_key=cfg.GEMINI_API_KEY, model=model or cfg.GEMINI_MODEL)
    if name == "vertex":
        if not cfg.VERTEX_PROJECT:
            raise ValueError("VERTEX_PROJECT is not set")
        return VertexProvider(project=cfg.VERTEX_PROJECT, location=cfg.VERTEX_LOCATION,
                              model=model or cfg.VERTEX_MODEL)
    if name == "openai":
        if not cfg.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
        return OpenAIProvider(api_key=cfg.OPENAI_API_KEY, model=model or cfg.OPENAI_MODEL,
                              base_url=cfg.OPENAI_BASE_URL)
    raise ValueError(f"Unknown LLM provider: '{name}'. "
                     "Valid options: ollama, gemini, vertex, openai, auto")


def _auto_provider() -> LLMProvider:
    """
    Try providers in priority order and return the first one that is healthy.
    Priority: ollama → gemini → openai → vertex
    """
    candidates = [
        ("ollama",  lambda: bool(cfg.OLLAMA_BASE_URL)),
        ("gemini",  lambda: bool(cfg.GEMINI_API_KEY)),
        ("openai",  lambda: bool(cfg.OPENAI_API_KEY)),
        ("vertex",  lambda: bool(cfg.VERTEX_PROJECT)),
    ]
    for name, is_configured in candidates:
        if not is_configured():
            logger.debug("auto: skipping %s (not configured)", name)
            continue
        try:
            provider = _build(name)
            result = provider.health_check()
            if result.get("status") == "ok":
                logger.info("auto: selected provider=%s model=%s", name, result.get("model"))
                return provider
            logger.warning("auto: %s unhealthy (%s), trying next", name, result.get("status"))
        except Exception as exc:
            logger.warning("auto: %s failed (%s), trying next", name, exc)

    raise RuntimeError(
        "auto mode: no healthy LLM provider found. "
        "Configure at least one of: OLLAMA (running locally), "
        "GEMINI_API_KEY, OPENAI_API_KEY, or VERTEX_PROJECT."
    )


def get_provider(provider_name: Optional[str] = None, model: Optional[str] = None) -> LLMProvider:
    """
    Return an LLMProvider instance.

    provider_name — overrides LLM_PROVIDER from .env (used by AppState per-session switching)
    model         — overrides the default model for the chosen provider
    """
    name = (provider_name or cfg.LLM_PROVIDER).lower()
    if name == "auto":
        return _auto_provider()
    return _build(name, model)
