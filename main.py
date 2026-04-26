import csv, io, json
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from app.config import LLM_PROVIDER, OLLAMA_BASE_URL, OLLAMA_MODEL
from app.jd_parser import parse_jd
from app.llm import get_provider
from app.matcher import rank_candidates
from app.models import Candidate, ShortlistEntry, ParsedJD, MatchResult
from app.db import get_db

db = get_db("sqlite")

STATE = dict(jd_text=None, parsed_jd=None, match_results=[],
             conversations={}, shortlist=[], provider=LLM_PROVIDER, model=OLLAMA_MODEL)

@asynccontextmanager
async def lifespan(app):
    # ── STARTUP ──────────────────────────────────────────────────
    db.init()

    # Restore LLM settings
    s = db.load_settings()
    STATE["llm_provider"] = s["llm_provider"]
    STATE["llm_model"]    = s["llm_model"]

    # Restore parsed JD
    jd_raw = db.load_parsed_jd()
    if jd_raw:
        try:
            STATE["parsed_jd"] = ParsedJD(**jd_raw)
        except Exception as e:
            print(f"[DB] JD restore failed: {e}")

    # Restore match results
    restored_matches = []
    for r in db.load_match_results():
        try:
            r["candidate"] = Candidate(**r["candidate"])
            restored_matches.append(MatchResult(**r))
        except Exception as e:
            print(f"[DB] Match result restore failed: {e}")
    if restored_matches:
        STATE["match_results"] = restored_matches

    # Restore conversations
    STATE["conversations"] = db.load_conversations()

    print(
        f"[DB] Restored — "
        f"JD: {bool(STATE.get('parsed_jd'))}, "
        f"matches: {len(STATE.get('match_results') or [])}, "
        f"convs: {len(STATE.get('conversations') or {})}"
    )

    yield   # ← app is live here

    # ── SHUTDOWN ──────────────────────────────────────────────────
    print("[DB] Shutdown.")

app = FastAPI(title="TalentScout AI", version="1.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

with open("data/candidates.json") as f:
    CANDIDATE_POOL = [Candidate(**c) for c in json.load(f)]
CANDIDATE_MAP = {c.id: c for c in CANDIDATE_POOL}


def _llm():      return get_provider(STATE["provider"], STATE["model"])
def _color(s):   return "green" if s >= 75 else ("yellow" if s >= 50 else "red")

def persist_state():
    try:
        if STATE.get("parsed_jd"):
            db.save_parsed_jd(STATE["parsed_jd"])
        if STATE.get("match_results"):
            db.save_match_results(STATE["match_results"])
        db.save_settings(
            STATE.get("llm_provider", "ollama"),
            STATE.get("llm_model",    "llama3"),
        )
    except Exception as e:
        print(f"[DB] persist_state error: {e}")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request":request,
        "provider":STATE["provider"],"model":STATE["model"]})

@app.post("/parse-jd", response_class=HTMLResponse)
async def post_parse_jd(request: Request,
        jd_text:str=Form(...), provider:str=Form("ollama"), model:str=Form("llama3")):
    STATE.update(provider=provider, model=model, jd_text=jd_text,
                 conversations={}, shortlist=[])
    llm = _llm()
    try:
        parsed = parse_jd(jd_text, llm)
    except Exception as e:
        return templates.TemplateResponse("index.html",
            {"request":request,"error":str(e),"provider":provider,"model":model})
    STATE["parsed_jd"] = parsed
    STATE["match_results"] = rank_candidates(CANDIDATE_POOL, parsed)
    return templates.TemplateResponse("candidates.html", {
        "request":request,"parsed_jd":parsed,"results":STATE["match_results"],
        "shortlist_ids":{e.candidate.id for e in STATE["shortlist"]},
        "conv_ids":set(STATE["conversations"]), "score_color":_color})

@app.get("/candidates", response_class=HTMLResponse)
async def get_candidates(request: Request):
    if not STATE["parsed_jd"]: return RedirectResponse("/")
    return templates.TemplateResponse("candidates.html", {
        "request":request,"parsed_jd":STATE["parsed_jd"],"results":STATE["match_results"],
        "shortlist_ids":{e.candidate.id for e in STATE["shortlist"]},
        "conv_ids":set(STATE["conversations"]),"score_color":_color})

@app.get("/engage/{cid}", response_class=HTMLResponse)
async def engage(request: Request, cid: str):
    if not STATE["parsed_jd"]: return RedirectResponse("/")
    c = CANDIDATE_MAP.get(cid)
    if not c: raise HTTPException(404)
    mr  = next((r for r in STATE["match_results"] if r.candidate.id == cid), None)
    conv = STATE["conversations"].get(cid)
    return templates.TemplateResponse("conversation.html", {
        "request":request,"candidate":c,"parsed_jd":STATE["parsed_jd"],
        "match_result":mr,"conversation":conv,
        "already_in_shortlist":any(e.candidate.id==cid for e in STATE["shortlist"]),
        "score_color":_color})

@app.post("/run-conversation/{cid}")
async def run_conv(cid: str):
    if not STATE["parsed_jd"]: raise HTTPException(400,"No JD")
    c = CANDIDATE_MAP.get(cid)
    if not c: raise HTTPException(404)
    result = simulate_conversation(c, STATE["parsed_jd"], _llm())
    STATE["conversations"][cid] = result
    return result

@app.post("/shortlist/{cid}")
async def add_shortlist(cid: str):
    c  = CANDIDATE_MAP.get(cid)
    if not c: raise HTTPException(404)
    STATE["shortlist"] = [e for e in STATE["shortlist"] if e.candidate.id != cid]
    mr   = next((r for r in STATE["match_results"] if r.candidate.id == cid), None)
    conv = STATE["conversations"].get(cid)
    ms   = mr.match_score if mr else 50.0
    is_  = conv.interest_analysis.total if conv else 0.0
    fs   = round(0.6*ms + 0.4*is_, 1)
    STATE["shortlist"].append(ShortlistEntry(
        rank=0, candidate=c, match_score=ms, interest_score=is_, final_score=fs,
        skill_matches=mr.skill_matches if mr else [],
        skill_gaps=mr.skill_gaps if mr else [],
        conversation_summary=conv.interest_analysis.summary if conv else "Not engaged",
        interest_analysis=conv.interest_analysis if conv else None,
    ))
    STATE["shortlist"].sort(key=lambda e: e.final_score, reverse=True)
    for i, e in enumerate(STATE["shortlist"], 1): e.rank = i
    return {"status":"added","final_score":fs}

@app.delete("/shortlist/{cid}")
async def del_shortlist(cid: str):
    STATE["shortlist"] = [e for e in STATE["shortlist"] if e.candidate.id != cid]
    for i, e in enumerate(STATE["shortlist"], 1): e.rank = i
    return {"status":"removed"}

@app.get("/shortlist", response_class=HTMLResponse)
async def view_shortlist(request: Request):
    return templates.TemplateResponse("shortlist.html", {
        "request":request,"shortlist":STATE["shortlist"],
        "parsed_jd":STATE["parsed_jd"],"score_color":_color})

@app.get("/export-csv")
async def export_csv():
    if not STATE["shortlist"]: raise HTTPException(400,"Empty shortlist")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Rank","Name","Title","Company","Location","Yrs Exp",
                "Match Score","Interest Score","Final Score",
                "Skill Matches","Skill Gaps","Notice Period","Expected Salary","Summary"])
    for e in STATE["shortlist"]:
        w.writerow([e.rank,e.candidate.name,e.candidate.title,e.candidate.company,
                    e.candidate.location,e.candidate.years_experience,
                    e.match_score,e.interest_score,e.final_score,
                    "; ".join(e.skill_matches),"; ".join(e.skill_gaps),
                    e.candidate.notice_period,e.candidate.expected_salary,
                    e.conversation_summary])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition":"attachment; filename=shortlist.csv"})

@app.get("/reset")
async def reset():
    STATE.update(jd_text=None,parsed_jd=None,match_results=[],conversations={},shortlist=[])
    return RedirectResponse("/")

@app.get("/architecture", response_class=HTMLResponse)
async def architecture(request: Request):
    """Interactive architecture diagram page."""
    return templates.TemplateResponse(
        "architecture.html",
        {"request": request}
    )

from app.email_draft import generate_email
@app.post("/generate-email/{candidate_id}")
async def generate_email_route(candidate_id: str):
    """Generate a personalised recruiter outreach email via LLM."""
    if not STATE.get("parsed_jd"):
        raise HTTPException(status_code=400, detail="No JD parsed yet. Go to / and parse a JD first.")
    if not STATE.get("match_results"):
        raise HTTPException(status_code=400, detail="No match results. Parse a JD first.")

    # Find candidate + match result
    candidate  = CANDIDATE_MAP.get(candidate_id)
    match_result = next((r for r in STATE["match_results"] if r.candidate.id == candidate_id), None)
    if not candidate or not match_result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Pull optional interest data from conversation
    interest_score   = None
    interest_summary = None
    conv = STATE.get("conversations", {}).get(candidate_id)
    if conv:
        interest_score   = conv.interest_analysis.total
        interest_summary = conv.interest_analysis.summary

    provider = STATE.get("provider", "ollama")
    model    = STATE.get("model", "llama3")
    llm      = get_provider(provider, model)

    email = generate_email(
        candidate=candidate,
        jd=STATE["parsed_jd"],
        match_result=match_result,
        llm=llm,
        interest_score=interest_score,
        interest_summary=interest_summary,
    )
    return {"subject": email["subject"], "body": email["body"]}

from app.interview_questions import generate_questions
@app.post("/generate-questions/{candidate_id}")
async def generate_questions_route(candidate_id: str):
    """Generate personalised interview questions via LLM."""
    if not STATE.get("parsed_jd"):
        raise HTTPException(status_code=400, detail="No JD parsed yet. Parse a JD first.")
    if not STATE.get("match_results"):
        raise HTTPException(status_code=400, detail="No match results found. Parse a JD first.")

    match_result = next((r for r in STATE["match_results"] if r.candidate.id == candidate_id), None)
    candidate    = match_result.candidate 
    if not candidate or not match_result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    interest_score   = None
    interest_summary = None
    conv = STATE.get("conversations", {}).get(candidate_id)
    if conv:
        interest_score   = conv.interest_analysis.total
        interest_summary = conv.interest_analysis.summary

    provider = STATE.get("llm_provider", "ollama")
    model    = STATE.get("llm_model",    "llama3")
    llm      = get_provider(provider, model)

    questions = generate_questions(
        candidate=candidate,
        jd=STATE["parsed_jd"],
        match_result=match_result,
        llm=llm,
        interest_score=interest_score,
        interest_summary=interest_summary,
    )
    return questions

import json as _json

@app.get("/analytics")
async def analytics_dashboard(request: Request):
    match_results = STATE.get("match_results", [])
    conversations = STATE.get("conversations", {})

    if not match_results:
        return templates.TemplateResponse("analytics.html", {
            "request": request, "no_data": True
        })

    # ── Helper: get interest score from conv (Pydantic obj or raw dict) ──
    def _interest(candidate_id):
        conv = conversations.get(candidate_id)
        if not conv:
            return 0
        if isinstance(conv, dict):
            return conv.get("interest_analysis", {}).get("total", 0)
        return getattr(getattr(conv, "interest_analysis", None), "total", 0)

    # ── KPIs ──────────────────────────────────────────────────────────
    match_scores    = [r.match_score for r in match_results]
    interest_scores = [_interest(r.candidate.id) for r in match_results]
    engaged_ids     = [cid for cid, c in conversations.items() if c]

    avg_match    = round(sum(match_scores)    / len(match_scores), 1)
    avg_interest = round(sum(interest_scores) / len(match_scores), 1)
    shortlisted  = sum(1 for s in match_scores if s >= 70)

    # ── Score-bucket histogram (match scores) ─────────────────────────
    buckets = [0, 0, 0, 0, 0]   # 0-20, 21-40, 41-60, 61-80, 81-100
    for s in match_scores:
        buckets[min(int(s // 20), 4)] += 1

    # ── Tier breakdown (doughnut) ─────────────────────────────────────
    tiers = [0, 0, 0, 0]        # Excellent, Good, Fair, Low
    for s in match_scores:
        if   s >= 80: tiers[0] += 1
        elif s >= 60: tiers[1] += 1
        elif s >= 40: tiers[2] += 1
        else:         tiers[3] += 1

    # ── Scatter: match vs interest ────────────────────────────────────
    scatter = [
        {"x": round(r.match_score, 1),
         "y": round(_interest(r.candidate.id), 1),
         "label": r.candidate.name}
        for r in match_results
    ]

    # ── Top skill gaps ────────────────────────────────────────────────
    gap_counts: dict = {}
    for r in match_results:
        for g in (r.skill_gaps or []):
            gap_counts[g] = gap_counts.get(g, 0) + 1
    top_gaps = sorted(gap_counts.items(), key=lambda x: -x[1])[:8]

    # ── Funnel ────────────────────────────────────────────────────────
    funnel = [
        {"label": "Evaluated",    "count": len(match_results)},
        {"label": "Match ≥ 60%",  "count": sum(1 for s in match_scores if s >= 60)},
        {"label": "Engaged",      "count": len(engaged_ids)},
        {"label": "Interest ≥ 70","count": sum(1 for s in interest_scores if s >= 70)},
        {"label": "Shortlisted",  "count": shortlisted},
    ]

    # ── Top candidates table ──────────────────────────────────────────
    top_candidates = sorted(
        [{"name":     r.candidate.name,
          "title":    r.candidate.title,
          "company":  r.candidate.company,
          "match":    round(r.match_score, 1),
          "interest": round(_interest(r.candidate.id), 1),
          "combined": round((r.match_score * 0.6 + _interest(r.candidate.id) * 0.4), 1),
          "engaged":  r.candidate.id in conversations,
         } for r in match_results],
        key=lambda x: -x["combined"]
    )[:10]

    return templates.TemplateResponse("analytics.html", {
        "request":         request,
        "no_data":         False,
        "total":           len(match_results),
        "avg_match":       avg_match,
        "avg_interest":    avg_interest,
        "engaged_count":   len(engaged_ids),
        "shortlisted":     shortlisted,
        "bucket_data":     _json.dumps(buckets),
        "tier_data":       _json.dumps(tiers),
        "scatter_data":    _json.dumps(scatter),
        "gap_labels":      _json.dumps([g[0] for g in top_gaps]),
        "gap_counts":      _json.dumps([g[1] for g in top_gaps]),
        "funnel":          funnel,
        "top_candidates":  top_candidates,
    })
