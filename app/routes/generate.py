"""
LLM-powered content generation.
POST /generate-email/{candidate_id}     — personalised outreach email
POST /generate-questions/{candidate_id} — personalised interview questions
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.state import AppState

router = APIRouter(prefix="/generate", tags=["generate"])


def get_state() -> AppState:
    from main import app_state  # noqa: F401
    return app_state


@router.post("/email/{candidate_id}")
async def generate_email_route(candidate_id: str, state: AppState = Depends(get_state)):
    if not state.parsed_jd:
        raise HTTPException(status_code=400, detail="No JD parsed yet. Parse a JD first.")
    if not state.match_results:
        raise HTTPException(status_code=400, detail="No match results. Parse a JD first.")

    from main import CANDIDATE_MAP
    from app.email_draft import generate_email

    candidate = CANDIDATE_MAP.get(candidate_id)
    match_result = next(
        (r for r in state.match_results if r.candidate.id == candidate_id), None
    )
    if not candidate or not match_result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    interest_score = None
    interest_summary = None
    conv = state.conversations.get(candidate_id)
    if conv:
        ia = None
        if isinstance(conv, dict):
            ia = conv.get("interest_analysis")
        else:
            ia = getattr(conv, "interest_analysis", None)
        if ia:
            interest_score = getattr(ia, "total", None)
            interest_summary = getattr(ia, "summary", None)

    email = generate_email(
        candidate=candidate,
        jd=state.parsed_jd,
        match_result=match_result,
        llm=state.llm(),
        interest_score=interest_score,
        interest_summary=interest_summary,
    )
    return {"subject": email["subject"], "body": email["body"]}


@router.post("/questions/{candidate_id}")
async def generate_questions_route(candidate_id: str, state: AppState = Depends(get_state)):
    if not state.parsed_jd:
        raise HTTPException(status_code=400, detail="No JD parsed yet. Parse a JD first.")
    if not state.match_results:
        raise HTTPException(status_code=400, detail="No match results found. Parse a JD first.")

    from main import CANDIDATE_MAP
    from app.interview_questions import generate_questions

    match_result = next(
        (r for r in state.match_results if r.candidate.id == candidate_id), None
    )
    candidate = match_result.candidate if match_result else None
    if not candidate or not match_result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    interest_score = None
    interest_summary = None
    conv = state.conversations.get(candidate_id)
    if conv:
        ia = None
        if isinstance(conv, dict):
            ia = conv.get("interest_analysis")
        else:
            ia = getattr(conv, "interest_analysis", None)
        if ia:
            interest_score = getattr(ia, "total", None)
            interest_summary = getattr(ia, "summary", None)

    questions = generate_questions(
        candidate=candidate,
        jd=state.parsed_jd,
        match_result=match_result,
        llm=state.llm(),
        interest_score=interest_score,
        interest_summary=interest_summary,
    )
    return questions