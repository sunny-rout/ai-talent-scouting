"""
Router registry — import individual routers from this module.
"""
from app.routes import (
    analytics,
    candidates,
    conversation,
    export,
    generate,
    shortlist,
)

__all__ = [
    "analytics",
    "candidates",
    "conversation",
    "export",
    "generate",
    "shortlist",
]