"""
Conversation routes — legacy non-streaming and SSE streaming.
POST /run-conversation/{candidate_id}   — legacy JSON response
POST /stream-conversation/{candidate_id} — SSE streaming with live token output
"""
from __future__ import annotations

import json as _j, re, traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from app.conversation import parse_turns, score_interest, simulate_conversation
from app.models import ConversationResult, ConversationTurn, InterestAnalysis
from app.state import AppState

router = APIRouter(tags=["conversation"])

OLLAMA_MODEL_THINK = "qwen3.5"
_ollama = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


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
    SSE streaming conversation with 3-phase error handling:
      Phase 1 (fatal): Stream LLM tokens — any exception aborts with SSE error event
      Phase 2 (non-fatal): Score interest via LLM — fallback to keyword scoring
      Phase 3 (non-fatal): Save to STATE + DB — DB errors are caught and logged
    """
    print(f"[stream] >>> POST /stream-conversation/{candidate_id}")

    # ── Validate candidate ──────────────────────────────────────────
    match_result = next(
        (r for r in state.match_results if r.candidate.id == candidate_id), None
    )
    if not match_result:
        raise HTTPException(status_code=404, detail="Candidate not found in STATE")
    if not state.parsed_jd:
        raise HTTPException(status_code=400, detail="No JD parsed yet")
    candidate = match_result.candidate

    # ── Build prompt ────────────────────────────────────────────────
    prompt = f"""You are an AI recruiter doing a brief realistic outreach conversation.

Role: {state.parsed_jd.role}
Required skills: {", ".join(state.parsed_jd.required_skills[:6])}

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

    # ── SSE generator ───────────────────────────────────────────────
    async def event_stream():
        full_text = ""
        token_count = 0

        # Phase 1: Stream tokens (fatal)
        try:
            yield f"data: {_j.dumps({'type': 'start'})}\n\n"
            stream = await _ollama.chat.completions.create(
                model=state.llm_model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=700,
                temperature=0.72,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_text += delta
                    token_count += 1
                    yield f"data: {_j.dumps({'type': 'token', 'text': delta})}\n\n"
        except Exception as exc:
            yield f"data: {_j.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        # Phase 2: Score interest (non-fatal)
        turns = parse_turns(full_text)
        interest = await score_interest(
            turns, state.parsed_jd, candidate, _ollama, state.llm_model
        )

        # Phase 3: Save and send done (non-fatal)
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