import json, re
from app.models import Candidate, ParsedJD, MatchResult
from app.llm.base import LLMProvider

EMAIL_PROMPT = """You are a skilled technical recruiter. Write a SHORT, personalized outreach email to a candidate.

CANDIDATE:
- Name: {name}
- Current Role: {title} at {company}
- Experience: {years} years
- Top Skills: {skills}
- Location: {location}
- Notice Period: {notice}
- Expected CTC: {ctc}

JOB DETAILS:
- Role: {role}
- Company Type: fast-growing startup
- Key Requirements: {required}
- Salary Range: {salary}

MATCH CONTEXT:
- Match Score: {match_score}%
- Skills they have: {skill_matches}
- Skills they lack: {skill_gaps}

{conversation_context}

INSTRUCTIONS:
- Write a subject line and email body
- Keep the email under 180 words
- Be specific — mention 2-3 of their actual skills
- Sound human, not templated
- End with a clear, low-pressure CTA (15-min call)
- Return ONLY valid JSON in this exact format:
{{
  "subject": "...",
  "body": "..."
}}"""

CONV_CONTEXT_TEMPLATE = """CONVERSATION INSIGHT:
The recruiter already had a simulated conversation with this candidate.
Interest Score: {interest_score}%
Summary: {summary}
Use this context to make the email feel like a natural follow-up."""

def _extract_json(text: str) -> dict:
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
    raise ValueError("No JSON found in LLM response")

def generate_email(
    candidate: Candidate,
    jd: ParsedJD,
    match_result: MatchResult,
    llm: LLMProvider,
    interest_score: float = None,
    interest_summary: str = None,
) -> dict:
    conv_ctx = ""
    if interest_score is not None and interest_summary:
        conv_ctx = CONV_CONTEXT_TEMPLATE.format(
            interest_score=round(interest_score, 1),
            summary=interest_summary,
        )

    prompt = EMAIL_PROMPT.format(
        name=candidate.name,
        title=candidate.title,
        company=candidate.company,
        years=candidate.years_experience,
        skills=", ".join(candidate.skills[:6]),
        location=candidate.location,
        notice=candidate.notice_period,
        ctc=candidate.expected_salary,
        role=jd.role,
        required=", ".join(jd.required_skills[:5]),
        salary=jd.salary_range or "competitive",
        match_score=round(match_result.match_score, 1),
        skill_matches=", ".join(match_result.skill_matches[:4]) or "several key skills",
        skill_gaps=", ".join(match_result.skill_gaps[:2]) or "none critical",
        conversation_context=conv_ctx,
    )

    msgs = [
        {"role": "system", "content": "Return only valid JSON with subject and body keys."},
        {"role": "user",   "content": prompt},
    ]
    try:
        raw  = llm.chat(msgs, temperature=0.7)
        data = _extract_json(raw)
        return {
            "subject": data.get("subject", f"Exciting {jd.role} opportunity – would love to connect"),
            "body":    data.get("body", "Could not generate email. Please try again."),
        }
    except Exception as e:
        return _fallback_email(candidate, jd, match_result)

def _fallback_email(candidate: Candidate, jd: ParsedJD, match: MatchResult) -> dict:
    skills_str = ", ".join(match.skill_matches[:3]) if match.skill_matches else "your background"
    return {
        "subject": f"Exciting {jd.role} opportunity – {candidate.name}",
        "body": f"""Hi {candidate.name.split()[0]},

I came across your profile and was impressed by your experience with {skills_str} — exactly what we're looking for in a {jd.role} role.

We're a fast-growing startup building in the fintech space, and your {candidate.years_experience} years of experience at {candidate.company} caught my attention.

The role involves {", ".join(jd.required_skills[:3])} and offers {jd.salary_range or "a competitive package"}.

Would you be open to a quick 15-minute call this week to explore if there's a fit?

Looking forward to hearing from you.

Best regards,
[Recruiter Name]"""
    }
