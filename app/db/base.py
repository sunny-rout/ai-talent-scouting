"""
Abstract base class for TalentScout database providers.
Follows the same provider pattern as app/llm/base.py.
Swap SQLite → PostgreSQL → MongoDB by changing one line.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional


def _to_dict(obj: Any) -> Any:
    """Serialize Pydantic v1/v2 model, dict, or list to plain dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if hasattr(obj, "model_dump"):   # Pydantic v2
        return obj.model_dump()
    if hasattr(obj, "dict"):         # Pydantic v1
        return obj.dict()
    return str(obj)


class BaseDB(ABC):
    """
    Provider-agnostic persistence interface.

    Every DB backend must implement all abstract methods below.
    The in-memory app_state dict is the source of truth at runtime;
    this layer is responsible for persisting and restoring it.
    """

    # ── Lifecycle ─────────────────────────────────────────────────

    @abstractmethod
    def init(self) -> None:
        """
        Create schema / connect / run migrations.
        Called once at app startup. Must be idempotent.
        """

    @abstractmethod
    def clear_all(self) -> None:
        """
        Wipe ALL persisted data.
        Called by the /reset route.
        """

    # ── Parsed JD ─────────────────────────────────────────────────

    @abstractmethod
    def save_parsed_jd(self, jd: Any) -> None:
        """Persist the parsed JD (Pydantic model or dict)."""

    @abstractmethod
    def load_parsed_jd(self) -> Optional[dict]:
        """Return the last saved JD as a plain dict, or None."""

    # ── Match results ─────────────────────────────────────────────

    @abstractmethod
    def save_match_results(self, results: list) -> None:
        """Persist a list of MatchResult objects."""

    @abstractmethod
    def load_match_results(self) -> list[dict]:
        """Return all saved match results as plain dicts."""

    # ── Conversations ─────────────────────────────────────────────

    @abstractmethod
    def save_conversation(self, candidate_id: str, conv: Any) -> None:
        """Persist a single conversation by candidate ID."""

    @abstractmethod
    def load_conversations(self) -> dict[str, dict]:
        """Return {candidate_id: conv_dict} for all saved conversations."""

    # ── Settings ──────────────────────────────────────────────────

    @abstractmethod
    def save_settings(self, provider: str, model: str) -> None:
        """Persist LLM provider + model name."""

    @abstractmethod
    def load_settings(self) -> dict:
        """Return {llm_provider, llm_model} with sensible defaults."""
