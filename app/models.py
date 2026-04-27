from pydantic import BaseModel
from typing import List, Optional, Dict

class Candidate(BaseModel):
    id: str
    name: str
    title: str
    company: str
    location: str
    years_experience: int
    skills: List[str]
    education: str
    bio: str
    expected_salary: str
    notice_period: str
    personality: str  # enthusiastic | passive | lukewarm | focused

class ParsedJD(BaseModel):
    role: str
    role_type: str
    required_skills: List[str]
    preferred_skills: List[str]
    years_experience: int
    education: Optional[str] = None
    responsibilities: List[str]
    must_haves: List[str]
    salary_range: Optional[str] = None

class MatchResult(BaseModel):
    candidate: Candidate
    match_score: float
    skill_matches: List[str]
    skill_gaps: List[str]
    experience_match: bool
    score_breakdown: Dict[str, float]
    explanation: str

class ConversationTurn(BaseModel):
    role: str
    message: str

class InterestAnalysis(BaseModel):
    enthusiasm: float
    availability: float
    compensation_fit: float
    engagement: float
    total: float
    summary: str

class ConversationResult(BaseModel):
    candidate_id: str
    turns: List[ConversationTurn]
    interest_analysis: InterestAnalysis
    raw_text: str = ""

class ShortlistEntry(BaseModel):
    rank: int
    candidate: Candidate
    match_score: float
    interest_score: float
    final_score: float
    skill_matches: List[str]
    skill_gaps: List[str]
    conversation_summary: str
    interest_analysis: Optional[InterestAnalysis] = None