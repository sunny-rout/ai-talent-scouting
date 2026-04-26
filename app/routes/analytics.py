"""
Analytics dashboard route — delegates to app/analytics.py.
GET /analytics
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.analytics import compute_analytics
from app.state import AppState

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_state() -> AppState:
    from main import app_state  # noqa: F401
    return app_state


@router.get("", response_class=HTMLResponse)
async def analytics_dashboard(request: Request, state: AppState = Depends(get_state)):
    data = compute_analytics(state)
    if data.get("no_data"):
        from fastapi import templating
        from main import templates
        return templates.TemplateResponse("analytics.html", {
            "request": request, "no_data": True
        })
    data["request"] = request
    from main import templates
    return templates.TemplateResponse("analytics.html", data)