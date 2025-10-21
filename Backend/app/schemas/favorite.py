
# In backend/app/schemas/favorite.py

from pydantic import BaseModel, HttpUrl
from typing import List, Optional

# This defines the detailed ranking data we expect to receive
class RankingData(BaseModel):
    rank: int
    candidate_name: str
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    linkedin_url: Optional[HttpUrl] = None
    overall_score: float
    technical_skills: float
    experience_relevance: float
    seniority_match: float
    education_fit: float
    industry_experience: float
    location_compatibility: float
    confidence_level: str
    strengths: List[str]
    concerns: List[str]
    recommendations: List[str]
    match_explanation: str
    key_differentiators: List[str]
    interview_focus_areas: List[str]
    source: str

# This is the main object the frontend will send to our POST endpoint
class FavoriteCreate(BaseModel):
    job_id: str
    candidate_id: str
    ranking_data: RankingData