import csv, io, json
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import LLM_PROVIDER, OLLAMA_MODEL, VERTEX_MODEL
from app.conversation import simulate_conversation
from app.jd_parser import parse_jd
from app.llm import get_provider
from app.matcher import rank_candidates
from app.models import Candidate, ShortlistEntry

app = FastAPI(title="TalentScout AI", version="1.0.0")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

with open("data/candidates.json") as f:
    CANDIDATE_POOL = [Candidate(**c) for c in json.load(f)]
CANDIDATE_MAP = {c.id: c for c in CANDIDATE_POOL}

STATE = dict(jd_text=None, parsed_jd=None, match_results=[],
             conversations={}, shortlist=[], provider=LLM_PROVIDER, model=OLLAMA_MODEL)

def _llm():      return get_provider(STATE["provider"], STATE["model"])
def _color(s):   return "green" if s >= 75 else ("yellow" if s >= 50 else "red")

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
    """Generate a personalized recruiter outreach email via LLM."""
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
