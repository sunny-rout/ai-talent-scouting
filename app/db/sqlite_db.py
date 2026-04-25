"""
SQLite implementation of BaseDB.
Uses Python's built-in sqlite3 — zero extra dependencies.
"""
import json, os, sqlite3
from typing import Any, Optional

from app.db.base import BaseDB, _to_dict

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DB_PATH  = os.path.join(_BASE_DIR, "data", "talent_scout.db")


class SQLiteDB(BaseDB):

    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # ── Connection ────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    # ── Lifecycle ─────────────────────────────────────────────────

    def init(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS match_results (
                    candidate_id TEXT PRIMARY KEY,
                    data         TEXT NOT NULL,
                    updated_at   TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    candidate_id TEXT PRIMARY KEY,
                    data         TEXT NOT NULL,
                    updated_at   TEXT DEFAULT (datetime('now'))
                );
            """)

    def clear_all(self) -> None:
        with self._conn() as c:
            c.executescript("""
                DELETE FROM kv_store;
                DELETE FROM match_results;
                DELETE FROM conversations;
            """)

    # ── KV helper (private) ───────────────────────────────────────

    def _set(self, key: str, value: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, updated_at) "
                "VALUES (?, ?, datetime('now'))",
                (key, json.dumps(value, default=str))
            )

    def _get(self, key: str, default: Any = None) -> Any:
        with self._conn() as c:
            row = c.execute("SELECT value FROM kv_store WHERE key=?", (key,)).fetchone()
            return json.loads(row["value"]) if row else default

    # ── Parsed JD ─────────────────────────────────────────────────

    def save_parsed_jd(self, jd: Any) -> None:
        self._set("parsed_jd", _to_dict(jd))

    def load_parsed_jd(self) -> Optional[dict]:
        return self._get("parsed_jd")

    # ── Match results ─────────────────────────────────────────────

    def save_match_results(self, results: list) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM match_results")
            for r in results:
                d = _to_dict(r)
                cid = d.get("candidate", {}).get("id", "unknown")
                c.execute(
                    "INSERT OR REPLACE INTO match_results "
                    "(candidate_id, data, updated_at) VALUES (?, ?, datetime('now'))",
                    (cid, json.dumps(d, default=str))
                )

    def load_match_results(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT data FROM match_results ORDER BY rowid").fetchall()
            return [json.loads(r["data"]) for r in rows]

    # ── Conversations ─────────────────────────────────────────────

    def save_conversation(self, candidate_id: str, conv: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO conversations "
                "(candidate_id, data, updated_at) VALUES (?, ?, datetime('now'))",
                (candidate_id, json.dumps(_to_dict(conv), default=str))
            )

    def load_conversations(self) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT candidate_id, data FROM conversations").fetchall()
            return {r["candidate_id"]: json.loads(r["data"]) for r in rows}

    # ── Settings ──────────────────────────────────────────────────

    def save_settings(self, provider: str, model: str) -> None:
        self._set("llm_provider", provider)
        self._set("llm_model",    model)

    def load_settings(self) -> dict:
        return {
            "llm_provider": self._get("llm_provider", "ollama"),
            "llm_model":    self._get("llm_model",    "llama3"),
        }
