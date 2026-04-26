"""
DB provider factory — mirrors the LLM provider pattern.

Usage in main.py:
    from app.db import get_db
    db = get_db()               # SQLite by default
    db = get_db("sqlite")       # explicit
    db = get_db("postgres")     # future provider

The returned object implements BaseDB, so every call site
is provider-agnostic.
"""
from app.db.base    import BaseDB
from app.db.sqlite_db import SQLiteDB

# Registry: add new providers here — one line each
_PROVIDERS: dict[str, type[BaseDB]] = {
    "sqlite":   SQLiteDB,
    # "postgres": PostgresDB,   ← future
    # "mongo":    MongoDB,       ← future
}

def get_db(provider: str = "sqlite", **kwargs) -> BaseDB:
    """
    Return an initialised DB provider instance.

    Args:
        provider: "sqlite" (default) or any registered key.
        **kwargs: forwarded to the provider constructor
                  e.g. get_db("sqlite", db_path="/custom/path.db")
    """
    key = provider.lower().strip()
    if key not in _PROVIDERS:
        raise ValueError(
            f"Unknown DB provider '{provider}'. "
            f"Available: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[key](**kwargs)


__all__ = ["get_db", "BaseDB"]
