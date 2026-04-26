"""
TalentScout AI — FastAPI application entry point.

Handles app bootstrap, lifespan, static/template mounting, and the routes
that need direct access to CANDIDATE_MAP or templates:
  GET  /                  — JD input form
  POST /parse-jd          — parse JD, run matching, render candidates
  GET  /candidates        — ranked candidate grid
  GET  /engage/{cid}      — candidate profile + engagement page
  GET  /shortlist         — ranked shortlist view
  GET  /architecture      — architecture diagram page
  POST /explain-score     — LLM score explanation (cached)
  GET  /health/llm        — LLM provider health check

All other routes live in app/routes/ and receive shared state via Depends().
"""
from contextlib import asynccontextmanager
import json

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import LLM_PROVIDER, OLLAMA_MODEL
from app.jd_parser import parse_jd
from app.llm import get_provider
from app.matcher import rank_candidates
from app.models import Candidate, ShortlistEntry, ParsedJD, MatchResult
from app.db import get_db
from app.state import AppState
from app.routes import analytics, candidates, conversation, export, generate, shortlist


# ── Global state (lifespan-managed) ──────────────────────────────────
app_state: AppState = AppState()


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db("sqlite")
    db.init()

    # Restore state from SQLite
    global app_state
    app_state = AppState.from_db()

    yield  # app is live here

    # Persist on shutdown
    app_state.persist()
    print("[DB] Shutdown.")


# ── App setup ────────────────────────────────────────────────────────

app = FastAPI(title="TalentScout AI", version="1.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Load candidate pool once at startup
with open("data/candidates.json") as f:
    CANDIDATE_POOL = [Candidate(**c) for c in json.load(f)]
CANDIDATE_MAP = {c.id: c for c in CANDIDATE_POOL}


# ── Helpers ───────────────────────────────────────────────────────────

def _color(s: float) -> str:
    return "green" if s >= 75 else ("yellow" if s >= 50 else "red")


def _get_state() -> AppState:
    return app_state


# ── UI routes that must stay in main.py ──────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, state: AppState = Depends(_get_state)):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "provider": state.llm_provider,
        "model": state.llm_model,
    })


@app.post("/parse-jd", response_class=HTMLResponse)
async def post_parse_jd(
    request: Request,
    jd_text: str = Form(...),
    provider: str = Form("ollama"),
    model: str = Form("llama3"),
    state: AppState = Depends(_get_state),
):
    state.llm_provider = provider
    state.llm_model = model
    state.jd_text = jd_text
    state.conversations = {}
    state.shortlist = []

    try:
        parsed = parse_jd(jd_text, state.llm())
    except Exception as e:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": str(e),
            "provider": provider,
            "model": model,
        })

    state.parsed_jd = parsed
    state.match_results = rank_candidates(CANDIDATE_POOL, parsed)
    return templates.TemplateResponse("candidates.html", {
        "request": request,
        "parsed_jd": parsed,
        "results": state.match_results,
        "shortlist_ids": {e.candidate.id for e in state.shortlist},
        "conv_ids": set(state.conversations),
        "score_color": _color,
    })


@app.get("/candidates", response_class=HTMLResponse)
async def get_candidates(request: Request, state: AppState = Depends(_get_state)):
    if not state.parsed_jd:
        return RedirectResponse("/")
    return templates.TemplateResponse("candidates.html", {
        "request": request,
        "parsed_jd": state.parsed_jd,
        "results": state.match_results,
        "shortlist_ids": {e.candidate.id for e in state.shortlist},
        "conv_ids": set(state.conversations),
        "score_color": _color,
    })


@app.get("/engage/{cid}", response_class=HTMLResponse)
async def engage(request: Request, cid: str, state: AppState = Depends(_get_state)):
    if not state.parsed_jd:
        return RedirectResponse("/")
    c = CANDIDATE_MAP.get(cid)
    if not c:
        from fastapi import HTTPException
        raise HTTPException(404)
    mr = next((r for r in state.match_results if r.candidate.id == cid), None)
    conv = state.conversations.get(cid)
    return templates.TemplateResponse("conversation.html", {
        "request": request,
        "candidate": c,
        "parsed_jd": state.parsed_jd,
        "match_result": mr,
        "conversation": conv,
        "already_in_shortlist": any(e.candidate.id == cid for e in state.shortlist),
        "score_color": _color,
    })


@app.get("/shortlist", response_class=HTMLResponse)
async def view_shortlist(request: Request, state: AppState = Depends(_get_state)):
    return templates.TemplateResponse("shortlist.html", {
        "request": request,
        "shortlist": state.shortlist,
        "parsed_jd": state.parsed_jd,
        "score_color": _color,
    })


@app.get("/architecture", response_class=HTMLResponse)
async def architecture(request: Request):
    return templates.TemplateResponse("architecture.html", {"request": request})


# ── Score explanation (stays here — very small endpoint) ─────────────

_explain_cache: dict[str, str] = {}


@app.post("/explain-score")
async def explain_score(payload: dict, state: AppState = Depends(_get_state)):
    from app.explain_score import explain as _explain_score

    cache_key = payload.get("candidate_id", "?") + "_" + payload.get("score_type", "match")
    if cache_key in _explain_cache:
        return {"explanation": _explain_cache[cache_key], "cached": True}

    explanation = _explain_score(payload, state.llm())
    _explain_cache[cache_key] = explanation
    return {"explanation": explanation, "cached": False}


@app.get("/health/llm")
async def health_llm(state: AppState = Depends(_get_state)):
    try:
        result = state.llm().health_check()
    except Exception as exc:
        result = {
            "status":     "error",
            "provider":   "unknown",
            "model":      "unknown",
            "hint":       str(exc),
            "latency_ms": None,
        }
    return result


# ── Router registration ──────────────────────────────────────────────

app.include_router(candidates.router)
app.include_router(shortlist.router)
app.include_router(conversation.router)
app.include_router(generate.router)
app.include_router(analytics.router)
app.include_router(export.router)