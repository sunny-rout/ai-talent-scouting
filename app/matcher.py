from typing import List
from app.models import Candidate, ParsedJD, MatchResult

def _norm(s): return s.lower().strip().replace("-","").replace(" ","")

def _overlap(cand_skills, jd_skills):
    norm_c = {_norm(s): s for s in cand_skills}
    matches = []
    for js in jd_skills:
        nj = _norm(js)
        if any(nj in nc or nc in nj for nc in norm_c):
            matches.append(js)
    return matches

def _exp_score(candidate_yrs, required_yrs):
    diff = candidate_yrs - required_yrs
    if diff >= 0: return min(20.0, 20.0 - diff * 0.5)
    return max(0.0, 20.0 + diff * 3)

def compute_match_score(candidate: Candidate, jd: ParsedJD) -> MatchResult:
    req_m  = _overlap(candidate.skills, jd.required_skills)
    pref_m = _overlap(candidate.skills, jd.preferred_skills)
    req_s  = (len(req_m)  / max(len(jd.required_skills),  1)) * 40
    pref_s = (len(pref_m) / max(len(jd.preferred_skills), 1)) * 15
    exp_s  = _exp_score(candidate.years_experience, jd.years_experience)
    exp_ok = candidate.years_experience >= jd.years_experience
    role_s = 10.0 if jd.role_type.lower() in candidate.title.lower() else (
             5.0  if any(w in candidate.title.lower() for w in jd.role_type.lower().split()) else 0.0)
    edu_s  = 10.0 if any(k in candidate.education.lower() for k in
                         ["b.tech","b.e","m.tech","ms","phd","bachelor","master"]) else 5.0
    must_m = _overlap(candidate.skills, jd.must_haves)
    must_s = (len(must_m) / max(len(jd.must_haves), 1)) * 5
    total  = min(100.0, req_s + pref_s + exp_s + role_s + edu_s + must_s)
    gaps   = [s for s in jd.required_skills if s not in req_m]

    return MatchResult(
        candidate=candidate, match_score=round(total, 1),
        skill_matches=req_m + pref_m, skill_gaps=gaps,
        experience_match=exp_ok,
        score_breakdown={
            "required_skills": round(req_s, 1),
            "preferred_skills": round(pref_s, 1),
            "experience": round(exp_s, 1),
            "role_fit": round(role_s, 1),
            "education": round(edu_s, 1),
            "must_haves": round(must_s, 1),
        },
        explanation=(
            f"{candidate.name} matches {len(req_m)}/{len(jd.required_skills)} required skills "
            f"with {candidate.years_experience} years exp "
            f"({'meets' if exp_ok else 'below'} {jd.years_experience}yr requirement)."
        ),
    )

def rank_candidates(candidates: List[Candidate], jd: ParsedJD) -> List[MatchResult]:
    results = [compute_match_score(c, jd) for c in candidates]
    results.sort(key=lambda r: r.match_score, reverse=True)
    return results