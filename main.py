from datetime import datetime, timezone
import csv, io, json
from fastapi import FastAPI, Form, HTTPException, Request, Body
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

@app.post("/shortlist/{candidate_id}")
async def add_to_shortlist(candidate_id: str):
    """
    Add a candidate to the shortlist.
    Works with OR without a prior conversation:
      - With conversation  → final = 0.6 × match + 0.4 × interest
      - Without conversation → interest_score = 0, final = match_score
    """

    # Find candidate
    candidate = CANDIDATE_MAP.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Matching must already exist
    match_result = next((r for r in STATE["match_results"] if r.candidate.id == candidate_id), None)
    if not match_result:
        raise HTTPException(status_code=400, detail="Run matching first before shortlisting")

    # Conversation may or may not exist
    conversation = STATE["conversations"].get(candidate_id)
    has_conv = conversation is not None

    if has_conv and conversation.interest_analysis:
        interest_score = round(conversation.interest_analysis.total, 1)
        interest_breakdown = conversation.interest_analysis
        interest_summary = conversation.interest_analysis.summary
        final_score = round(0.6 * match_result.match_score + 0.4 * interest_score, 1)
    else:
        interest_score = 0.0
        interest_breakdown = None
        interest_summary = "No conversation conducted — scored on match only"
        final_score = round(match_result.match_score, 1)

    # Build shortlist entry
    entry = ShortlistEntry(
        candidate=candidate,
        match_score=round(match_result.match_score, 1),
        interest_score=interest_score,
        final_score=final_score,
        skill_matches=match_result.skill_matches,
        skill_gaps=match_result.skill_gaps,
        conversation_summary = interest_summary,
        rank=0,  # to be set in re-ranking step
    )

    # Upsert
    STATE["shortlist"] = [e for e in STATE["shortlist"] if e.candidate.id != candidate_id]
    STATE["shortlist"].append(entry)

    # Re-rank
    STATE["shortlist"].sort(key=lambda e: e.final_score, reverse=True)
    for i, e in enumerate(STATE["shortlist"], 1):
        e.rank = i

    return {
        "success": True,
        "candidate_id": candidate_id,
        "match_score": entry.match_score,
        "interest_score": entry.interest_score,
        "final_score": entry.final_score,
        "has_conversation": has_conv,
        "rank": entry.rank,
    }

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

from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
import json as _j, re, traceback

# ── AsyncOpenAI client pointed at Ollama's OpenAI-compatible endpoint ──────
# WHY AsyncOpenAI (not OpenAI)?
#   FastAPI is async. If we use sync OpenAI() it blocks the event loop while
#   waiting for LLM tokens — no other requests can run. AsyncOpenAI is
#   non-blocking: the event loop handles other requests between token yields.
_ollama = AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",   # Ollama ignores the key but the SDK requires it
)
OLLAMA_MODEL_THINK = "qwen3.5"  # run `ollama list` to confirm your model name


@app.post("/stream-conversation/{candidate_id}")
async def stream_conversation(candidate_id: str):
    print(f"[stream] >>> POST /stream-conversation/{candidate_id}")

    # ── validate ──
    print(f"[stream] Validating candidate_id={candidate_id}")
    match_result = next(
        (r for r in STATE.get("match_results", [])
         if r.candidate.id == candidate_id), None
    )
    if not match_result:
        print(f"[stream] ERROR: Candidate {candidate_id} not found in STATE")
        print(f"[stream] Available candidates: {[r.candidate.id for r in STATE.get('match_results', [])]}")
        raise HTTPException(status_code=404, detail="Candidate not found in STATE")
    print(f"[stream] OK: Found candidate {match_result.candidate.name}")

    parsed_jd = STATE.get("parsed_jd")
    if not parsed_jd:
        print(f"[stream] ERROR: No parsed JD in STATE")
        raise HTTPException(status_code=400, detail="No JD parsed yet — run JD parsing first")
    print(f"[stream] OK: JD role={parsed_jd.role}")

    candidate = match_result.candidate
    print(f"[stream] Starting conversation for {candidate.name} ({candidate.title} at {candidate.company})")

    # ── conversation prompt ──
    prompt = f"""You are an AI recruiter doing a brief realistic outreach conversation.

Role: {parsed_jd.role}
Required skills: {", ".join(parsed_jd.required_skills[:6])}

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

    # ── SSE generator (async generator function) ──────────────────────────
    # WHY an inner generator?
    #   StreamingResponse needs an iterator/generator. By making it async,
    #   we can `await` the Ollama stream and `yield` each chunk to the browser
    #   without blocking. The browser receives each `yield` immediately.
    async def event_stream():
        full_text = ""
        token_count = 0

        # ════════════════════════════════════════════════════════════════
        # PHASE 1: Stream conversation tokens  (FATAL — if this fails,
        #          we abort with an error event so the frontend can show it)
        # ════════════════════════════════════════════════════════════════
        try:
            print(f"[stream] Phase 1: Starting LLM stream with model={OLLAMA_MODEL}")
            # Tell frontend streaming has started
            yield f"data: {_j.dumps({'type': 'start'})}\n\n"

            # stream=True → AsyncOpenAI returns an async iterator of chunks
            print(f"[stream] Calling _ollama.chat.completions.create(stream=True)...")
            stream = await _ollama.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                stream=True,        # ← streaming: yields tokens as they arrive
                max_tokens=700,
                temperature=0.72,
            )
            print(f"[stream] Stream object received, iterating...")
            async for chunk in stream:
                # Each chunk has one small piece of text (sometimes empty)
                delta = chunk.choices[0].delta.content
                if delta:
                    full_text += delta
                    token_count += 1
                    # Send this token to the browser right now
                    yield f"data: {_j.dumps({'type': 'token', 'text': delta})}\n\n"
            print(f"[stream] Phase 1 complete: received {token_count} tokens")

        except Exception as exc:
            print(f"[stream] Phase 1 failed:\n{traceback.format_exc()}")
            yield f"data: {_j.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return  # stop the generator — no point scoring an empty conversation

        # ════════════════════════════════════════════════════════════════
        # PHASE 2: Score interest  (NON-FATAL — has keyword fallback)
        # Runs AFTER all tokens are received. Never crashes the response.
        # ════════════════════════════════════════════════════════════════
        print(f"[stream] Phase 2: Parsing turns from {len(full_text)} chars")
        turns    = _parse_turns(full_text)
        print(f"[stream] Parsed {len(turns)} turns: {[t.role for t in turns]}")
        print(f"[stream] Calling _score_interest...")
        interest = await _score_interest(turns, parsed_jd, candidate)
        print(f"[stream] Interest score: total={interest.total}, enthusiasm={interest.enthusiasm}")

        # ════════════════════════════════════════════════════════════════
        # PHASE 3: Save to STATE + DB, send the final "done" event
        # The "done" payload contains the full conversation object.
        # Frontend uses this to render proper chat bubbles & score panel.
        # ════════════════════════════════════════════════════════════════
        try:
            print(f"[stream] Phase 3: Saving conversation to STATE and DB")
            from app.models import ConversationResult
            conv = ConversationResult(
                candidate_id=candidate_id,
                turns=turns,
                interest_analysis=interest,
                raw_text=full_text,
            )
            STATE.setdefault("conversations", {})[candidate_id] = conv
            print(f"[stream] Saved to STATE[candidate_id]")
            try:                          # DB save is best-effort
                get_db().save_conversation(candidate_id, conv.model_dump())
                print(f"[stream] Saved to DB")
            except Exception as db_exc:
                print(f"[stream] DB save failed: {db_exc}")
            yield f"data: {_j.dumps({'type': 'done', 'conversation': conv.model_dump()})}\n\n"
            print(f"[stream] Phase 3 complete: sent 'done' event to client")

        except Exception as exc:
            print(f"[stream] Phase 3 failed:\n{traceback.format_exc()}")
            yield f"data: {_j.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    # ── return a StreamingResponse — NOT a regular JSONResponse ──────────
    # WHY these headers?
    #   Cache-Control: no-cache  → browser must not buffer or cache SSE
    #   X-Accel-Buffering: no    → tells Nginx NOT to buffer (critical for live streaming)
    #   Connection: keep-alive   → keep the HTTP connection open until generator ends
    print(f"[stream] <<< Returning StreamingResponse")
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ── helper: parse raw LLM text into ConversationTurn objects ───────────────
# WHY parse at all?  The LLM returns plain text like "Recruiter: Hello\n..."
# We need structured objects so the frontend can render proper chat bubbles
# and the scorer can look at just the candidate's words.
def _parse_turns(raw: str) -> list:
    from app.models import ConversationTurn
    turns = []
    for line in raw.strip().splitlines():
        s = line.strip()
        if s.lower().startswith("recruiter:"):
            turns.append(ConversationTurn(role="recruiter", message=s[10:].strip()))
        elif s.lower().startswith("candidate:"):
            turns.append(ConversationTurn(role="candidate", message=s[10:].strip()))
    return turns

# ── helper: score interest from conversation using Ollama ──────────────────
# WHY a SEPARATE non-streaming call for scoring?
#   We need the COMPLETE candidate text before we can score it.
#   Can't score mid-stream. So we wait for Phase 1 to finish, then
#   make a second, non-streaming call (stream=False) to get JSON scores.
# WHY a fallback?
#   If the LLM returns malformed JSON or fails, we still need a score.
#   Rule-based keyword matching always works, costs nothing, never crashes.
async def _score_interest(turns, parsed_jd, candidate):
    from app.models import InterestAnalysis

    candidate_lines = "\n".join(
        f"  {t.message}" for t in turns if t.role == "candidate"
    ) or "(no candidate responses)"

    prompt = f"""Analyze this candidate's interest in a job offer from their replies.

Candidate: {candidate.name}
Role offered: {parsed_jd.role}

Candidate's replies:
{candidate_lines}

Return ONLY valid JSON. No explanation, no markdown, just the JSON object:
{{
  "enthusiasm":       <integer 0-100>,
  "availability":     <integer 0-100>,
  "compensation_fit": <integer 0-100>,
  "engagement":       <integer 0-100>,
  "summary":          "<one short sentence>"
}}"""

    try:
        # stream=False → wait for the complete response, then parse JSON
        resp = await _ollama.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,       # ← non-streaming: we need full text to parse JSON
            temperature=0.2,    # ← low temp: we want consistent structured output
            max_tokens=150,
        )
        text = resp.choices[0].message.content or ""
        m    = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in response: {text[:120]}")
        d = _j.loads(m.group())
        e  = float(d.get("enthusiasm",       60))
        av = float(d.get("availability",     60))
        cf = float(d.get("compensation_fit", 60))
        eq = float(d.get("engagement",       60))
        total = round((e + av + cf + eq) / 4, 1)
        return InterestAnalysis(
            total=total, enthusiasm=e, availability=av,
            compensation_fit=cf, engagement=eq,
            summary=str(d.get("summary", "Interest assessed via LLM.")),
        )
    except Exception as exc:
        # NEVER let scoring crash the whole response — use fallback
        print(f"[_score_interest] LLM failed → using keyword fallback. Reason: {exc}")
        return _keyword_interest(turns)

def _keyword_interest(turns):
    from app.models import InterestAnalysis
    text = " ".join(t.message.lower() for t in turns if t.role == "candidate")
    pos  = ["interested","love to","sounds great","excited","open to",
            "definitely","would love","happy to","yes","great opportunity","keen"]
    neg  = ["not interested","not looking","not a good fit","no thanks","decline"]
    base = min(95, max(20, 50 + sum(10 for w in pos if w in text)
                              - sum(18 for w in neg if w in text)))
    return InterestAnalysis(
        total=float(base), enthusiasm=float(min(100, base+8)),
        availability=float(min(100, base+2)), compensation_fit=60.0,
        engagement=float(min(100, base+5)),
        summary="Interest assessed from conversation keywords.",
    )


@app.get("/candidates/{candidate_id}/notes")
async def get_notes(candidate_id: str):
    """Return all notes for a candidate, newest first."""
    try:
        notes = get_db().load_notes(candidate_id)
        return {"notes": notes}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/candidates/{candidate_id}/notes")
async def add_note(
    candidate_id: str,
    payload: dict = Body(...),   # expects {"text": "..."}
):
    """
    Save a new note for a candidate.
    Returns the saved note object (with id + timestamp) so the
    frontend can prepend it immediately without a full page reload.
    """
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
        get_db().save_note(candidate_id, note)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"note": note}


@app.delete("/candidates/{candidate_id}/notes/{note_id}")
async def delete_note(candidate_id: str, note_id: str):
    """Delete a single note by its ID."""
    try:
        get_db().delete_note(candidate_id, note_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True}


def _note_id() -> str:
    """Generate a short unique ID  e.g. 'n_1a2b3c4d'"""
    import random, string
    chars = string.ascii_lowercase + string.digits
    return "n_" + "".join(random.choices(chars, k=8))

from app.explain_score import explain as _explain_score
# In-process cache: key = "{candidate_id}_{score_type}"  value = explanation str
_explain_cache: dict[str, str] = {}

@app.post("/explain-score")
async def explain_score(payload: dict = Body(...)):
    """
    Accepts a rich context payload and returns a plain-English score explanation.

    Body keys (all optional except score_type + score_value):
      score_type        : "match" | "interest" | "final"
      score_value       : float  (the numeric score to explain)
      candidate_id      : str    (used as cache key)
      candidate_name    : str
      candidate_title   : str
      candidate_company : str
      years_experience  : int
      jd_role           : str
      jd_required_skills: list[str]
      jd_years_required : int
      breakdown         : {req_skills, pref_skills, experience, role_fit, education}
      skill_matches     : list[str]
      skill_gaps        : list[str]
      interest_analysis : {enthusiasm, availability, compensation_fit, engagement, summary}
      match_score       : float  (needed for "final" type)
      interest_score    : float  (needed for "final" type)
    """
    cache_key = payload.get("candidate_id", "?") + "_" + payload.get("score_type", "match")

    # Return cached explanation immediately (same click = instant)
    if cache_key in _explain_cache:
        return {"explanation": _explain_cache[cache_key], "cached": True}

    # Generate via LLM — raises LLMError on failure (handled globally)
    explanation = _explain_score(payload, _llm())

    _explain_cache[cache_key] = explanation
    return {"explanation": explanation, "cached": False}
