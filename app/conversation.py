import json, re
from app.models import Candidate, ParsedJD, ConversationResult, ConversationTurn, InterestAnalysis
from app.llm.base import LLMProvider

PROMPT = """Simulate a 4-turn recruitment conversation (recruiter → candidate → recruiter → candidate).

JOB: {role} | Skills needed: {required_skills} | {years_experience}+ yrs | Salary: {salary_range}
CANDIDATE: {name}, {title} at {company}, {cand_years} yrs exp
Skills: {skills} | Expects: {expected_salary} | Notice: {notice_period} | Personality: {personality}

Personality guide:
- enthusiastic: excited, asks questions, very positive
- passive: polite, not actively looking, needs convincing
- lukewarm: mild interest, mentions other offers
- focused: asks specific technical/comp questions before committing

Return ONLY this JSON (no markdown):
{{
  "turns": [
    {{"role":"recruiter","message":"..."}},
    {{"role":"candidate","message":"..."}},
    {{"role":"recruiter","message":"..."}},
    {{"role":"candidate","message":"..."}}
  ],
  "interest_analysis": {{
    "enthusiasm": 20,
    "availability": 18,
    "compensation_fit": 15,
    "engagement": 22,
    "summary": "One sentence summary of candidate interest."
  }}
}}"""

def _extract_json(text):
    text = text.strip()
    try: return json.loads(text)
    except: pass
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        try: return json.loads(m.group(1).strip())
        except: pass
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    raise ValueError("No JSON found")

def _fallback(candidate, jd):
    turns = [
        ConversationTurn(role="recruiter", message=f"Hi {candidate.name}! I came across your profile and believe you'd be a strong fit for a {jd.role} role. Would you be open to a quick chat?"),
        ConversationTurn(role="candidate", message=f"Thanks for reaching out! I'm currently at {candidate.company} and things are going well, but I'm always open to interesting opportunities. Tell me more about the role?"),
        ConversationTurn(role="recruiter",  message=f"Great! The role involves {', '.join(jd.required_skills[:3])}. Your background in {', '.join(candidate.skills[:3])} is a strong match. What's your notice period and expected CTC?"),
        ConversationTurn(role="candidate", message=f"My notice period is {candidate.notice_period} and I'm targeting around {candidate.expected_salary}. The tech stack sounds solid — what does the team look like?"),
    ]
    ia = InterestAnalysis(enthusiasm=16, availability=15, compensation_fit=14, engagement=15, total=60.0, summary="Candidate showed moderate professional interest.")
    return ConversationResult(candidate_id=candidate.id, turns=turns, interest_analysis=ia)

def simulate_conversation(candidate: Candidate, jd: ParsedJD, llm: LLMProvider) -> ConversationResult:
    prompt = PROMPT.format(
        role=jd.role, required_skills=", ".join(jd.required_skills),
        years_experience=jd.years_experience, salary_range=jd.salary_range or "Competitive",
        name=candidate.name, title=candidate.title, company=candidate.company,
        cand_years=candidate.years_experience, skills=", ".join(candidate.skills),
        expected_salary=candidate.expected_salary, notice_period=candidate.notice_period,
        personality=candidate.personality,
    )
    try:
        raw  = llm.chat([
            {"role":"system","content":"Generate realistic recruitment conversations. Return only valid JSON."},
            {"role":"user","content":prompt}
        ], temperature=0.75)
        data = _extract_json(raw)
        turns = [ConversationTurn(**t) for t in data["turns"][:4]]
        ia    = data["interest_analysis"]
        e, a, c, en = float(ia.get("enthusiasm",15)), float(ia.get("availability",15)), float(ia.get("compensation_fit",15)), float(ia.get("engagement",15))
        return ConversationResult(
            candidate_id=candidate.id, turns=turns,
            interest_analysis=InterestAnalysis(
                enthusiasm=e, availability=a, compensation_fit=c, engagement=en,
                total=round(min(100.0, e+a+c+en), 1),
                summary=ia.get("summary",""),
            )
        )
    except Exception:
        return _fallback(candidate, jd)