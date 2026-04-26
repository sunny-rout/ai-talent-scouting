"""
Export and session reset routes.
GET /export-csv  — download shortlist as CSV
GET /reset       — clear all state and redirect to /
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.state import AppState

router = APIRouter(tags=["export"])


def get_state() -> AppState:
    from main import app_state  # noqa: F401
    return app_state


@router.get("/export-csv")
async def export_csv(state: AppState = Depends(get_state)):
    if not state.shortlist:
        raise HTTPException(status_code=400, detail="Empty shortlist")

    buf = io.StringIO()
    w = __import__("csv").writer(buf)
    w.writerow([
        "Rank", "Name", "Title", "Company", "Location", "Yrs Exp",
        "Match Score", "Interest Score", "Final Score",
        "Skill Matches", "Skill Gaps", "Notice Period", "Expected Salary", "Summary",
    ])
    for e in state.shortlist:
        w.writerow([
            e.rank, e.candidate.name, e.candidate.title, e.candidate.company,
            e.candidate.location, e.candidate.years_experience,
            e.match_score, e.interest_score, e.final_score,
            "; ".join(e.skill_matches), "; ".join(e.skill_gaps),
            e.candidate.notice_period, e.candidate.expected_salary,
            e.conversation_summary,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=shortlist.csv"},
    )


@router.get("/reset")
async def reset(state: AppState = Depends(get_state)):
    state.jd_text = None
    state.parsed_jd = None
    state.match_results = []
    state.conversations = {}
    state.shortlist = []
    state.persist()
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/")