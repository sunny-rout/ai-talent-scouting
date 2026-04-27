"""
Conversation routes — legacy non-streaming and SSE streaming.
POST /run-conversation/{candidate_id}    — legacy JSON response
POST /stream-conversation/{candidate_id} — SSE streaming with live token output
"""
from __future__ import annotations

import json as _j

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.conversation import parse_turns, score_interest, simulate_conversation
from app.models import ConversationResult
from app.state import AppState

router = APIRouter(tags=["conversation"])


def get_state() -> AppState:
    from main import app_state  # noqa: F401
    return app_state


@router.post("/run-conversation/{candidate_id}")
async def run_conv(candidate_id: str, state: AppState = Depends(get_state)):
    """Legacy non-streaming conversation — used by old engage flow."""
    if not state.parsed_jd:
        raise HTTPException(status_code=400, detail="No JD")
    from main import CANDIDATE_MAP
    c = CANDIDATE_MAP.get(candidate_id)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    result = simulate_conversation(c, state.parsed_jd, state.llm())
    state.save_conversation(candidate_id, result)
    return result


@router.post("/stream-conversation/{candidate_id}")
async def stream_conversation(candidate_id: str, state: AppState = Depends(get_state)):
    """
    SSE streaming conversation — provider-agnostic.
    Phase 1 (fatal):     stream tokens via state.llm().stream_chat()
    Phase 2 (non-fatal): score interest via state.llm().chat() in executor
    Phase 3 (non-fatal): persist to STATE + DB
    """
    match_result = next(
        (r for r in state.match_results if r.candidate.id == candidate_id), None
    )
    if not match_result:
        raise HTTPException(status_code=404, detail="Candidate not found in STATE")
    if not state.parsed_jd:
        raise HTTPException(status_code=400, detail="No JD parsed yet")

    candidate = match_result.candidate
    jd = state.parsed_jd

    prompt = f"""You are an AI recruiter doing a brief realistic outreach conversation.

Role: {jd.role}
Required skills: {", ".join(jd.required_skills[:6])}

Candidate: {candidate.name}
Current title: {candidate.title} at {candidate.company}
Their skills: {", ".join(candidate.skills[:8])}
Match score: {match_result.match_score:.0f}%
Skill gaps: {", ".join(match_result.skill_gaps[:3]) if match_result.skill_gaps else "none"}

Write a 4-turn conversation. Use EXACTLY this format (no blank lines between turns):
Recruiter: [message]
Candidate: [message]
Recruiter: [message]
Candidate: [message]

Keep each turn 1-3 sentences. Sound natural, specific to this candidate's background."""

    messages = [{"role": "user", "content": prompt}]

    async def event_stream():
        full_text = ""

        # Phase 1: stream tokens (fatal — abort on error)
        try:
            yield f"data: {_j.dumps({'type': 'start'})}\n\n"
            llm = state.llm()
            async for token in llm.stream_chat(messages, temperature=0.72):
                full_text += token
                yield f"data: {_j.dumps({'type': 'token', 'text': token})}\n\n"
        except Exception as exc:
            yield f"data: {_j.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        # Phase 2: score interest (non-fatal)
        turns = parse_turns(full_text)
        interest = await score_interest(turns, jd, candidate, state.llm())

        # Phase 3: save and emit done (non-fatal)
        try:
            conv = ConversationResult(
                candidate_id=candidate_id,
                turns=turns,
                interest_analysis=interest,
                raw_text=full_text,
            )
            state.save_conversation(candidate_id, conv)
            yield f"data: {_j.dumps({'type': 'done', 'conversation': conv.model_dump()})}\n\n"
        except Exception as exc:
            yield f"data: {_j.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )
