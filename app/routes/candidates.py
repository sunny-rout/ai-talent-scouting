"""
Candidate browsing, engagement page, and per-candidate notes.
GET /candidates          — ranked candidate grid (requires parsed JD in state)
GET /engage/{cid}        — candidate profile + chat UI
GET /candidates/{cid}/notes
POST /candidates/{cid}/notes
DELETE /candidates/{cid}/notes/{note_id}
"""
from __future__ import annotations

import random, string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models import ShortlistEntry
from app.state import AppState

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _color(s: float) -> str:
    return "green" if s >= 75 else ("yellow" if s >= 50 else "red")


def _note_id() -> str:
    chars = string.ascii_lowercase + string.digits
    return "n_" + "".join(random.choices(chars, k=8))


def get_state() -> AppState:
    from main import app_state  # noqa: F401 — injected by main.py lifespan
    return app_state


# ── Notes CRUD ─────────────────────────────────────────────────────────

@router.get("/{candidate_id}/notes")
async def get_notes(candidate_id: str, state: AppState = Depends(get_state)):
    from app.db import get_db
    try:
        notes = get_db().load_notes(candidate_id)
        return {"notes": notes}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{candidate_id}/notes")
async def add_note(
    candidate_id: str,
    payload: dict,
    state: AppState = Depends(get_state),
):
    """Save a new note for a candidate. Returns the saved note object."""
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Note text cannot be empty")
    if len(text) > 2000:
        raise HTTPException(status_code=422, detail="Note too long (max 2000 chars)")

    note = {
        "id":         _note_id(),
        "text":       text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from app.db import get_db
        get_db().save_note(candidate_id, note)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"note": note}


@router.delete("/{candidate_id}/notes/{note_id}")
async def delete_note(candidate_id: str, note_id: str, state: AppState = Depends(get_state)):
    try:
        from app.db import get_db
        get_db().delete_note(candidate_id, note_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}