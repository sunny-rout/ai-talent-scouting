"""
Application state — replaces the flat STATE dict in main.py.
All routes import state from Depends() rather than closing over a module-level dict.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import LLM_PROVIDER, OLLAMA_MODEL
from app.db import get_db
from app.llm import get_provider
from app.models import (
    Candidate,
    ConversationResult,
    MatchResult,
    ParsedJD,
    ShortlistEntry,
)

if TYPE_CHECKING:
    from app.llm.base import LLMProvider


class AppState:
    """
    In-memory application state, persisted to SQLite on shutdown.

    Normalises the key naming that existed in the old STATE dict:
      - llm_provider / llm_model  (canonical names, used everywhere)
      - jd_text / parsed_jd / match_results / conversations / shortlist
    """

    def __init__(
        self,
        jd_text: str | None = None,
        parsed_jd: ParsedJD | None = None,
        match_results: list[MatchResult] | None = None,
        conversations: dict[str, ConversationResult] | None = None,
        shortlist: list[ShortlistEntry] | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        self.jd_text = jd_text
        self.parsed_jd = parsed_jd
        self.match_results: list[MatchResult] = match_results or []
        self.conversations: dict[str, ConversationResult] = conversations or {}
        self.shortlist: list[ShortlistEntry] = shortlist or []
        self.llm_provider = llm_provider or LLM_PROVIDER
        self.llm_model = llm_model or OLLAMA_MODEL

    # ── LLM accessor ───────────────────────────────────────────────

    def llm(self) -> "LLMProvider":
        return get_provider(self.llm_provider, self.llm_model)

    # ── Persistence ───────────────────────────────────────────────

    def persist(self) -> None:
        """Save current state to SQLite. Called on shutdown and after key mutations."""
        db = get_db("sqlite")
        try:
            if self.parsed_jd:
                db.save_parsed_jd(self.parsed_jd)
            if self.match_results:
                db.save_match_results(self.match_results)
            db.save_settings(self.llm_provider, self.llm_model)
        except Exception as e:
            print(f"[AppState] persist error: {e}")

    def save_conversation(self, candidate_id: str, conv: ConversationResult) -> None:
        self.conversations[candidate_id] = conv
        try:
            get_db().save_conversation(candidate_id, conv.model_dump())
        except Exception as e:
            print(f"[AppState] save_conversation error: {e}")

    # ── DB restore ─────────────────────────────────────────────────

    @classmethod
    def from_db(cls) -> "AppState":
        """Restore state from SQLite on startup."""
        db = get_db("sqlite")

        # LLM settings
        s = db.load_settings()

        # Parsed JD
        parsed_jd = None
        jd_raw = db.load_parsed_jd()
        if jd_raw:
            try:
                parsed_jd = ParsedJD(**jd_raw)
            except Exception as e:
                print(f"[AppState] JD restore failed: {e}")

        # Match results
        restored_matches: list[MatchResult] = []
        for r in db.load_match_results():
            try:
                r["candidate"] = Candidate(**r["candidate"])
                restored_matches.append(MatchResult(**r))
            except Exception as e:
                print(f"[AppState] Match result restore failed: {e}")

        # Conversations (stored as dicts, kept as dicts in memory)
        conversations_raw = db.load_conversations()
        # Convert dicts back to ConversationResult where possible
        conversations: dict[str, ConversationResult] = {}
        for cid, conv_dict in conversations_raw.items():
            try:
                conversations[cid] = ConversationResult(**conv_dict)
            except Exception:
                conversations[cid] = conv_dict  # keep raw dict on failure

        state = cls(
            parsed_jd=parsed_jd,
            match_results=restored_matches,
            conversations=conversations,
            llm_provider=s.get("llm_provider", LLM_PROVIDER),
            llm_model=s.get("llm_model", OLLAMA_MODEL),
        )

        print(
            f"[AppState] Restored — "
            f"JD: {bool(state.parsed_jd)}, "
            f"matches: {len(state.match_results)}, "
            f"convs: {len(state.conversations)}"
        )
        return state