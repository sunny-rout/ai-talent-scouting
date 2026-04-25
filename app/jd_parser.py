import json, re
from app.models import ParsedJD
from app.llm.base import LLMProvider

PARSE_PROMPT = """Parse this Job Description and return ONLY valid JSON. No markdown, no explanation.

Schema:
{{
  "role": "exact job title",
  "role_type": "Software Engineer or Data Scientist or Product Manager",
  "required_skills": ["skill1"],
  "preferred_skills": ["skill1"],
  "years_experience": 3,
  "education": "degree requirement",
  "responsibilities": ["resp1"],
  "must_haves": ["req1"],
  "salary_range": "range or null"
}}

JOB DESCRIPTION:
{jd_text}"""

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

def _detect_role_type(jd: str) -> str:
    jd = jd.lower()
    if any(k in jd for k in ["data scientist","machine learning","ml engineer"]): return "Data Scientist"
    if any(k in jd for k in ["product manager","product owner","pm "]): return "Product Manager"
    return "Software Engineer"

def parse_jd(jd_text: str, llm: LLMProvider) -> ParsedJD:
    msgs = [
        {"role": "system", "content": "Return only valid JSON."},
        {"role": "user",   "content": PARSE_PROMPT.format(jd_text=jd_text)},
    ]
    try:
        raw  = llm.chat(msgs, temperature=0.2)
        data = _extract_json(raw)
        valid = {"Software Engineer","Data Scientist","Product Manager"}
        if data.get("role_type") not in valid:
            data["role_type"] = _detect_role_type(jd_text)
        return ParsedJD(**data)
    except Exception:
        return _fallback_parse(jd_text)

def _fallback_parse(jd_text: str) -> ParsedJD:
    keywords = ["Python","Java","JavaScript","React","Node.js","FastAPI","Docker",
                "Kubernetes","AWS","PostgreSQL","SQL","TensorFlow","PyTorch"]
    found = [k for k in keywords if k.lower() in jd_text.lower()]
    m = re.search(r"(\d+)\+?\s*years?", jd_text, re.IGNORECASE)
    return ParsedJD(
        role="Software Engineer", role_type=_detect_role_type(jd_text),
        required_skills=found[:6], preferred_skills=found[6:10],
        years_experience=int(m.group(1)) if m else 3,
        education="B.Tech/B.E. in CS or equivalent",
        responsibilities=["Build scalable software systems"],
        must_haves=found[:3] or ["Programming skills"],
    )