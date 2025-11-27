# backend/app/schemas/candidate.py

from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime


# ===========================
# Schemas for RankedCandidate
# ===========================

class RankedCandidateBase(BaseModel):
    """Base schema for a ranked candidate derived from search results."""
    user_id: UUID4
    jd_id: UUID4
    profile_id: UUID4
    rank: Optional[int] = None
    match_score: Optional[float] = None
    strengths: Optional[str] = None
    favorite: bool = False  # Changed to non-optional with default False
    save_for_future: bool = False
    send_to_recruiter: Optional[UUID4] = None
    outreached: bool = False
    linkedin_url: Optional[str] = None

    # --- NEW FIELDS ---
    contacted: bool = False
    stage: str = "In Consideration"
    # --- END NEW FIELDS ---


class RankedCandidateCreate(RankedCandidateBase):
    """Schema for creating a ranked candidate entry."""
    pass


class RankedCandidateUpdate(BaseModel):
    """Schema for updating fields of an existing ranked candidate."""
    rank: Optional[int] = None
    match_score: Optional[float] = None
    strengths: Optional[str] = None
    favorite: Optional[bool] = None
    save_for_future: Optional[bool] = None
    send_to_recruiter: Optional[UUID4] = None
    outreached: Optional[bool] = None
    linkedin_url: Optional[str] = None

    # --- NEW FIELDS ---
    contacted: Optional[bool] = None
    stage: Optional[str] = None
    # --- END NEW FIELDS ---


class RankedCandidate(RankedCandidateBase):
    """Response schema with full ranked candidate details."""
    rank_id: UUID4
    created_at: datetime

    class Config:
        from_attributes = True


# =====================================
# Schemas for RankedCandidateFromResume
# =====================================

class RankedCandidateFromResumeBase(BaseModel):
    """Base schema for ranked candidates derived from uploaded resumes."""
    user_id: UUID4
    jd_id: UUID4
    resume_id: UUID4
    rank: Optional[int] = None
    match_score: Optional[float] = None
    strengths: Optional[str] = None
    favorite: bool = False  # Changed to non-optional with default False
    save_for_future: bool = False
    send_to_recruiter: Optional[UUID4] = None
    outreached: bool = False
    linkedin_url: Optional[str] = None

    # --- NEW FIELDS ---
    contacted: bool = False
    stage: str = "In Consideration"
    # --- END NEW FIELDS ---


class RankedCandidateFromResumeCreate(RankedCandidateFromResumeBase):
    """Schema for creating a ranked candidate from a resume."""
    pass


class RankedCandidateFromResumeUpdate(BaseModel):
    """Schema for updating ranked candidate from resume."""
    rank: Optional[int] = None
    match_score: Optional[float] = None
    strengths: Optional[str] = None
    favorite: Optional[bool] = None
    save_for_future: Optional[bool] = None
    send_to_recruiter: Optional[UUID4] = None
    outreached: Optional[bool] = None
    linkedin_url: Optional[str] = None

    # --- NEW FIELDS ---
    contacted: Optional[bool] = None
    stage: Optional[str] = None
    # --- END NEW FIELDS ---


class RankedCandidateFromResume(RankedCandidateFromResumeBase):
    """Response schema with full details of a ranked candidate from resume."""
    rank_id: UUID4
    created_at: datetime

    class Config:
        from_attributes = True

# --- NEW SCHEMAS FOR UPDATES ---
class CandidateStageUpdate(BaseModel):
    stage: str

class CandidateContactedUpdate(BaseModel):
    contacted: bool
# --- END NEW SCHEMAS ---