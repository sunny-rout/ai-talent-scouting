"""
Shortlist management.
GET /shortlist            — view ranked shortlist
POST /shortlist/{candidate_id}  — add or upsert a candidate
DELETE /shortlist/{candidate_id} — remove from shortlist
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.models import ShortlistEntry
from app.state import AppState

router = APIRouter(prefix="/shortlist", tags=["shortlist"])


def get_state() -> AppState:
    from main import app_state  # noqa: F401
    return app_state


@router.post("/{candidate_id}")
async def add_to_shortlist(candidate_id: str, state: AppState = Depends(get_state)):
    """
    Add a candidate to the shortlist.
    Works with OR without a prior conversation:
      - With conversation  → final = 0.6 × match + 0.4 × interest
      - Without conversation → interest_score = 0, final = match_score
    """
    # Find candidate
    candidate = None
    for c in state.match_results:
        if c.candidate.id == candidate_id:
            candidate = c.candidate
            break

    if not candidate:
        # Try to find from candidate pool loaded in main.py
        from main import CANDIDATE_MAP
        candidate = CANDIDATE_MAP.get(candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

    # Find matching result
    match_result = next(
        (r for r in state.match_results if r.candidate.id == candidate_id), None
    )
    if not match_result:
        raise HTTPException(
            status_code=400, detail="Run matching first before shortlisting"
        )

    # Conversation may or may not exist
    conversation = state.conversations.get(candidate_id)
    has_conv = conversation is not None

    if has_conv:
        ia = None
        if isinstance(conversation, dict):
            ia = conversation.get("interest_analysis")
        else:
            ia = getattr(conversation, "interest_analysis", None)

        if ia:
            interest_score = round(getattr(ia, "total", 0.0), 1)
            interest_summary = getattr(ia, "summary", "")
        else:
            interest_score = 0.0
            interest_summary = "No conversation conducted — scored on match only"
    else:
        interest_score = 0.0
        interest_summary = "No conversation conducted — scored on match only"

    final_score = round(0.6 * match_result.match_score + 0.4 * interest_score, 1)

    entry = ShortlistEntry(
        candidate=candidate,
        match_score=round(match_result.match_score, 1),
        interest_score=interest_score,
        final_score=final_score,
        skill_matches=match_result.skill_matches,
        skill_gaps=match_result.skill_gaps,
        conversation_summary=interest_summary,
        rank=0,
    )

    # Upsert: remove if already present, then append
    state.shortlist = [e for e in state.shortlist if e.candidate.id != candidate_id]
    state.shortlist.append(entry)

    # Re-rank
    state.shortlist.sort(key=lambda e: e.final_score, reverse=True)
    for i, e in enumerate(state.shortlist, 1):
        e.rank = i

    state.persist()

    return {
        "success": True,
        "candidate_id": candidate_id,
        "match_score": entry.match_score,
        "interest_score": entry.interest_score,
        "final_score": entry.final_score,
        "has_conversation": has_conv,
        "rank": entry.rank,
    }


@router.delete("/{candidate_id}")
async def del_shortlist(candidate_id: str, state: AppState = Depends(get_state)):
    state.shortlist = [e for e in state.shortlist if e.candidate.id != candidate_id]
    for i, e in enumerate(state.shortlist, 1):
        e.rank = i
    state.persist()
    return {"status": "removed"}