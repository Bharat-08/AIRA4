"""
Core data models for the recruitment system using Pydantic.

This module defines all the data structures used throughout the recruitment
workflow.

"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


class ExperienceLevel(str, Enum):
    """Experience level enumeration."""
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"


class EmploymentType(str, Enum):
    """Employment type enumeration."""
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"


class CompanySize(str, Enum):
    """Company size enumeration."""
    STARTUP = "startup"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    ENTERPRISE = "enterprise"


class ConfidenceLevel(str, Enum):
    """Confidence level for candidate rankings."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Location(BaseModel):
    """Location information model."""
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    remote_allowed: bool = False
    
    class Config:
        extra = "forbid"


class ExperienceYears(BaseModel):
    """Experience years range model."""
    minimum: Optional[int] = Field(None, ge=0, le=50)
    maximum: Optional[int] = Field(None, ge=0, le=50)
    
    @validator('maximum')
    def validate_max_greater_than_min(cls, v, values):
        if v is not None and values.get('minimum') is not None:
            if v < values['minimum']:
                raise ValueError('Maximum years must be greater than or equal to minimum years')
        return v
    
    class Config:
        extra = "forbid"


class JobDescription(BaseModel):
    """Comprehensive job description model."""
    title: str = Field(..., min_length=1, max_length=200)
    company: Optional[str] = Field(None, max_length=100)
    location: Optional[Location] = None
    experience_level: Optional[ExperienceLevel] = None
    experience_years: Optional[ExperienceYears] = None
    required_skills: List[str] = Field(default_factory=list, max_items=50)
    preferred_skills: List[str] = Field(default_factory=list, max_items=30)
    responsibilities: List[str] = Field(default_factory=list, max_items=20)
    requirements: List[str] = Field(default_factory=list, max_items=20)
    benefits: List[str] = Field(default_factory=list, max_items=15)
    salary_range: Optional[str] = Field(None, max_length=100)
    employment_type: Optional[EmploymentType] = None
    industry: Optional[str] = Field(None, max_length=50)
    company_size: Optional[CompanySize] = None
    education_requirements: List[str] = Field(default_factory=list, max_items=10)
    certifications: List[str] = Field(default_factory=list, max_items=10)
    
    @validator('required_skills', 'preferred_skills')
    def validate_skills_not_empty(cls, v):
        return [skill.strip() for skill in v if skill.strip()]
    
    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                "title": "Senior Python Developer",
                "company": "TechCorp Inc.",
                "location": {
                    "city": "San Francisco",
                    "state": "CA",
                    "country": "USA",
                    "remote_allowed": True
                },
                "experience_level": "senior",
                "experience_years": {"minimum": 5, "maximum": 10},
                "required_skills": ["Python", "Django", "PostgreSQL", "AWS"],
                "preferred_skills": ["React", "Docker", "Kubernetes"],
                "employment_type": "full_time"
            }
        }


class CandidateProfile(BaseModel):
    """Comprehensive candidate profile model."""
    candidate_id: str = Field(..., min_length=1)
    full_name: str = Field(..., min_length=1, max_length=100)
    current_title: Optional[str] = Field(None, max_length=150)
    current_company: Optional[str] = Field(None, max_length=100)
    location: Optional[Location] = None
    linkedin_url: Optional[str] = Field(None, pattern=r'^https?://.*linkedin\.com.*')
    email: Optional[str] = Field(None, pattern=r'^[^@]+@[^@]+\.[^@]+$')
    phone: Optional[str] = Field(None, max_length=20)
    skills: List[str] = Field(default_factory=list, max_items=100)
    experience_years: Optional[int] = Field(None, ge=0, le=50)
    education: List[str] = Field(default_factory=list, max_items=10)
    previous_companies: List[str] = Field(default_factory=list, max_items=20)
    industries: List[str] = Field(default_factory=list, max_items=10)
    candidate_description: Optional[str] = None
    
    class Config:
        extra = "forbid"
        json_schema_extra = {
            "example": {
                "candidate_id": "pdl_12345",
                "full_name": "John Doe",
                "current_title": "Senior Software Engineer",
                "current_company": "Google",
                "location": {
                    "city": "Mountain View",
                    "state": "CA",
                    "country": "USA"
                },
                "linkedin_url": "https://linkedin.com/in/johndoe",
                "email": "john.doe@email.com",
                "skills": ["Python", "JavaScript", "AWS", "Docker"],
                "experience_years": 7
            }
        }


class DimensionScores(BaseModel):
    """Candidate evaluation dimension scores."""
    technical_skills: float = Field(..., ge=0.0, le=1.0)
    experience_relevance: float = Field(..., ge=0.0, le=1.0)
    seniority_match: float = Field(..., ge=0.0, le=1.0)
    education_fit: float = Field(..., ge=0.0, le=1.0)
    industry_experience: float = Field(..., ge=0.0, le=1.0)
    location_compatibility: float = Field(..., ge=0.0, le=1.0)
    
    class Config:
        extra = "forbid"


class CandidateRanking(BaseModel):
    """Comprehensive candidate ranking and analysis."""
    candidate_id: str = Field(..., min_length=1)
    candidate_name: str = Field(..., min_length=1)
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    linkedin_url: Optional[str] = None
    overall_score: float = Field(..., ge=0.0, le=1.0)
    dimension_scores: DimensionScores
    strengths: List[str] = Field(default_factory=list, max_items=10)
    concerns: List[str] = Field(default_factory=list, max_items=10)
    recommendations: List[str] = Field(default_factory=list, max_items=10)
    confidence_level: ConfidenceLevel
    match_explanation: str = Field(..., min_length=10, max_length=1000)
    key_differentiators: List[str] = Field(default_factory=list, max_items=10)
    interview_focus_areas: List[str] = Field(default_factory=list, max_items=10)
    candidate_description: Optional[str] = None
    
    class Config:
        extra = "forbid"


class SearchMetadata(BaseModel):
    """Metadata for candidate search operations."""
    processing_time_seconds: float = Field(..., ge=0.0)
    candidates_found: int = Field(..., ge=0)
    candidates_ranked: int = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=datetime.now)
    workflow_version: str = Field(default="2.0.0")
    search_queries_used: List[str] = Field(default_factory=list)
    api_calls_made: int = Field(default=0, ge=0)
    
    class Config:
        extra = "forbid"


class WorkflowResult(BaseModel):
    """Complete workflow result containing all data."""
    job_data: JobDescription
    candidates: List[CandidateProfile]
    rankings: List[CandidateRanking]
    metadata: SearchMetadata
    
    @validator('rankings')
    def validate_rankings_sorted(cls, v):
        """Ensure rankings are sorted by overall_score in descending order."""
        if len(v) > 1:
            scores = [ranking.overall_score for ranking in v]
            if scores != sorted(scores, reverse=True):
                raise ValueError('Rankings must be sorted by overall_score in descending order')
        return v
    
    class Config:
        extra = "forbid"


class PDLSearchQuery(BaseModel):
    """People Data Labs search query model."""
    sql_query: Optional[str] = None
    elasticsearch_query: Optional[Dict[str, Any]] = None
    max_results: int = Field(default=10, ge=1, le=100)
    
    class Config:
        extra = "forbid"


class APIResponse(BaseModel):
    """Generic API response model."""
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    
    class Config:
        extra = "forbid"


class SystemConfiguration(BaseModel):
    """System configuration model."""
    openai_api_key: str = Field(..., min_length=1)
    pdl_api_key: str = Field(..., min_length=1)
    log_level: str = Field(default="INFO")
    max_candidates_default: int = Field(default=10, ge=1, le=100)
    output_directory: str = Field(default="./results")
    
    class Config:
        extra = "forbid"


# Export all models for easy importing
__all__ = [
    'ExperienceLevel',
    'EmploymentType', 
    'CompanySize',
    'ConfidenceLevel',
    'Location',
    'ExperienceYears',
    'JobDescription',
    'CandidateProfile',
    'DimensionScores',
    'CandidateRanking',
    'SearchMetadata',
    'WorkflowResult',
    'PDLSearchQuery',
    'APIResponse',
    'SystemConfiguration'
]