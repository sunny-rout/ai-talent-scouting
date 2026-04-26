"""
D2 — Score Explanation
Generates plain-English explanations for Match, Interest, and Final scores
using the LLM. Used by POST /explain-score in main.py.
"""
import json, re
from app.llm.base import LLMProvider

# ─────────────────────────────────────────────────────────────────────────────
SYSTEM = (
    "You are a senior talent analyst helping a recruiter understand AI-generated "
    "scores. Write concise, plain-English explanations that a non-technical recruiter "
    "can act on. Be specific — reference actual skills, experience, and gaps. "
    "Never use jargon. Output only the explanation text, no markdown headers."
)

MATCH_PROMPT = """A candidate scored {score}% on Match Score for a {role} role.

CANDIDATE: {name} — {title} at {company}, {years} years experience
REQUIRED SKILLS (40 pts): {req_skills_list}
  → Candidate earned {req_pts}/40 pts (has: {skill_matches}; missing: {skill_gaps})
PREFERRED SKILLS (15 pts): earned {pref_pts}/15
EXPERIENCE FIT (20 pts): earned {exp_pts}/20 (need {yrs_req}+ yrs, has {years})
ROLE FIT (10 pts): earned {role_pts}/10
EDUCATION (10 pts): earned {edu_pts}/10

Explain in 3–5 bullet points WHY this candidate scored {score}%.
Start with the biggest driver (positive or negative), then explain each dimension briefly.
End with one sentence a recruiter can act on (e.g. "Consider them if X is trainable").
Keep it under 130 words."""

INTEREST_PROMPT = """A candidate scored {score}% on Interest Score after a recruiter conversation.

CANDIDATE: {name} — {title} at {company}
INTEREST BREAKDOWN:
  Enthusiasm        : {enthusiasm}/25
  Availability      : {availability}/25
  Compensation Fit  : {comp_fit}/25
  Engagement Quality: {engagement}/25
AI SUMMARY: "{summary}"

Explain in 3–5 bullet points WHY this candidate scored {score}% on interest.
Highlight what signals were strong and what raised doubts.
End with one actionable sentence for the recruiter.
Keep it under 130 words."""

FINAL_PROMPT = """A candidate received a Final Score of {score}% (= 0.6 × Match + 0.4 × Interest).

CANDIDATE: {name} — {title} at {company}, {years} years experience
MATCH SCORE : {match}% — skill matches: {skill_matches}; gaps: {skill_gaps}
INTEREST SCORE: {interest}% — "{summary}"
ROLE: {role}

Explain in 3–5 bullet points what this combined score means and why the candidate
ranked where they did. Be honest about trade-offs.
End with a clear hire / consider / pass recommendation with the single main reason.
Keep it under 140 words."""

# ─────────────────────────────────────────────────────────────────────────────

def explain(payload: dict, llm: LLMProvider) -> str:
    """
    Build and run the correct prompt based on payload['score_type'].
    Returns a plain-text explanation string.
    Raises LLMError subclass on failure (caught by FastAPI handler).
    """
    t = payload.get("score_type", "match")

    if t == "match":
        prompt = MATCH_PROMPT.format(
            score        = round(payload.get("score_value", 0), 1),
            name         = payload.get("candidate_name", "Candidate"),
            title        = payload.get("candidate_title", ""),
            company      = payload.get("candidate_company", ""),
            years        = payload.get("years_experience", "?"),
            yrs_req      = payload.get("jd_years_required", "?"),
            role         = payload.get("jd_role", "the role"),
            req_skills_list = ", ".join(payload.get("jd_required_skills", [])),
            req_pts      = round(payload.get("breakdown", {}).get("req_skills", 0), 1),
            pref_pts     = round(payload.get("breakdown", {}).get("pref_skills", 0), 1),
            exp_pts      = round(payload.get("breakdown", {}).get("experience",  0), 1),
            role_pts     = round(payload.get("breakdown", {}).get("role_fit",    0), 1),
            edu_pts      = round(payload.get("breakdown", {}).get("education",   0), 1),
            skill_matches = ", ".join(payload.get("skill_matches", [])[:5]) or "none",
            skill_gaps    = ", ".join(payload.get("skill_gaps",    [])[:4]) or "none",
        )

    elif t == "interest":
        ia = payload.get("interest_analysis", {})
        prompt = INTEREST_PROMPT.format(
            score        = round(payload.get("score_value", 0), 1),
            name         = payload.get("candidate_name", "Candidate"),
            title        = payload.get("candidate_title", ""),
            company      = payload.get("candidate_company", ""),
            enthusiasm   = round(ia.get("enthusiasm",    0), 1),
            availability = round(ia.get("availability",  0), 1),
            comp_fit     = round(ia.get("compensation_fit", 0), 1),
            engagement   = round(ia.get("engagement",    0), 1),
            summary      = ia.get("summary", ""),
        )

    else:  # "final" or anything else
        ia = payload.get("interest_analysis", {})
        prompt = FINAL_PROMPT.format(
            score         = round(payload.get("score_value", 0), 1),
            match         = round(payload.get("match_score",    0), 1),
            interest      = round(payload.get("interest_score", 0), 1),
            name          = payload.get("candidate_name", "Candidate"),
            title         = payload.get("candidate_title", ""),
            company       = payload.get("candidate_company", ""),
            years         = payload.get("years_experience", "?"),
            role          = payload.get("jd_role", "the role"),
            skill_matches = ", ".join(payload.get("skill_matches", [])[:4]) or "none",
            skill_gaps    = ", ".join(payload.get("skill_gaps",    [])[:3]) or "none",
            summary       = ia.get("summary", ""),
        )

    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": prompt},
    ]
    raw = llm.chat(msgs, temperature=0.4)
    return raw.strip()
