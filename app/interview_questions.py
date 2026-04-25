import json, re
from app.models import Candidate, ParsedJD, MatchResult
from app.llm.base import LLMProvider

IQ_PROMPT = """You are a senior technical interviewer. Generate targeted interview questions for this candidate.

CANDIDATE:
- Name: {name}
- Title: {title} at {company}
- Years of experience: {years}
- Skills: {skills}
- Education: {education}

JOB REQUIREMENTS:
- Role: {role}
- Required skills: {required}
- Preferred skills: {preferred}
- Min experience: {min_exp} years

MATCH ANALYSIS:
- Match Score: {match_score}%
- Skills they HAVE: {skill_matches}
- Skills they LACK: {skill_gaps}

{interest_context}

Generate exactly this JSON structure — no markdown fences, pure JSON:
{{
  "technical": [
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}},
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}},
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}}
  ],
  "gap_probe": [
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}},
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}}
  ],
  "behavioral": [
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}},
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}},
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}}
  ],
  "motivation": [
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}},
    {{"question": "...", "rationale": "...", "difficulty": "Easy|Medium|Hard"}}
  ]
}}

RULES:
- technical: 3 questions probing their claimed skills deeply
- gap_probe: 2 questions specifically on their MISSING skills (be direct but fair)
- behavioral: 3 STAR-format questions (Situation/Task/Action/Result)
- motivation: 2 questions uncovering why they want THIS role
- rationale: 1 sentence explaining WHY you ask this specific candidate this question
- Make questions specific to {name}'s background, not generic templates
- difficulty: Easy=foundational, Medium=practical, Hard=architectural/leadership"""

INTEREST_CTX = """CONVERSATION INSIGHT:
Interest Score: {score}%
Summary: {summary}
Tailor 1-2 motivation questions around these interest signals."""

def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    for attempt in [raw, re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()]:
        try:
            return json.loads(attempt)
        except Exception:
            pass
    m = re.search(r"\{[\s\S]+\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    raise ValueError("Could not parse JSON from LLM response")

def _fallback(candidate: Candidate, jd: ParsedJD, match: MatchResult) -> dict:
    skill = match.skill_matches[0] if match.skill_matches else "your primary skill"
    gap   = match.skill_gaps[0]    if match.skill_gaps    else "a new technology"
    return {
        "technical": [
            {"question": f"Walk me through the most complex {skill} system you've built end-to-end.",
             "rationale": f"Validates depth of {skill} claim on their profile.", "difficulty": "Hard"},
            {"question": f"How do you approach debugging a production issue in a {skill} service at 2am?",
             "rationale": "Tests operational mindset and real-world ownership.", "difficulty": "Medium"},
            {"question": f"What's a {skill} anti-pattern you've seen in production and how did you fix it?",
             "rationale": "Distinguishes experienced practitioners from beginners.", "difficulty": "Medium"},
        ],
        "gap_probe": [
            {"question": f"You haven't listed {gap} on your profile — how quickly could you get productive with it, and what's your plan?",
             "rationale": f"Directly addresses the {gap} gap in their match profile.", "difficulty": "Easy"},
            {"question": f"Describe a time you had to learn a completely new technology stack under deadline pressure.",
             "rationale": "Assesses learning agility which is critical given skill gaps.", "difficulty": "Medium"},
        ],
        "behavioral": [
            {"question": "Tell me about a time you disagreed with a technical decision. What did you do?",
             "rationale": "Tests communication and professional maturity.", "difficulty": "Medium"},
            {"question": "Describe the most impactful project you've owned. What made it successful?",
             "rationale": "Surfaces ownership, scope, and measurable impact.", "difficulty": "Medium"},
            {"question": "Tell me about a time a project failed. What would you do differently?",
             "rationale": "Evaluates self-awareness and growth mindset.", "difficulty": "Easy"},
        ],
        "motivation": [
            {"question": f"Why are you looking to move from {candidate.company} right now?",
             "rationale": "Uncovers push vs pull motivation — critical for retention.", "difficulty": "Easy"},
            {"question": f"What specifically excites you about a {jd.role} role at a startup vs your current setup?",
             "rationale": "Tests whether this is a deliberate move or just any job.", "difficulty": "Easy"},
        ],
    }

def generate_questions(
    candidate: Candidate,
    jd: ParsedJD,
    match_result: MatchResult,
    llm: LLMProvider,
    interest_score: float = None,
    interest_summary: str = None,
) -> dict:
    interest_ctx = ""
    if interest_score is not None and interest_summary:
        interest_ctx = INTEREST_CTX.format(
            score=round(interest_score, 1),
            summary=interest_summary,
        )

    prompt = IQ_PROMPT.format(
        name=candidate.name,
        title=candidate.title,
        company=candidate.company,
        years=candidate.years_experience,
        skills=", ".join(candidate.skills[:8]),
        education=getattr(candidate, "education", "Not specified"),
        role=jd.role,
        required=", ".join(jd.required_skills[:6]),
        preferred=", ".join(getattr(jd, "preferred_skills", [])[:4]),
        min_exp=getattr(jd, "min_experience", 0),
        match_score=round(match_result.match_score, 1),
        skill_matches=", ".join(match_result.skill_matches[:5]) or "several skills",
        skill_gaps=", ".join(match_result.skill_gaps[:3]) or "none critical",
        interest_context=interest_ctx,
    )

    msgs = [
        {"role": "system", "content": "Return only valid JSON. No markdown fences."},
        {"role": "user",   "content": prompt},
    ]
    try:
        raw  = llm.chat(msgs, temperature=0.6)
        data = _parse_json(raw)
        # Ensure all four keys exist
        for key in ("technical", "gap_probe", "behavioral", "motivation"):
            if key not in data or not isinstance(data[key], list):
                data[key] = []
        return data
    except Exception:
        return _fallback(candidate, jd, match_result)
