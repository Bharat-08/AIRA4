# Backend/app/schemas/linkedin.py
from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime


class LinkedInCandidate(BaseModel):
    """Response schema for rows from public.linkedin."""
    linkedin_profile_id: UUID4
    jd_id: UUID4
    user_id: UUID4

    name: Optional[str] = None
    profile_link: Optional[str] = None
    position: Optional[str] = None
    company: Optional[str] = None
    summary: Optional[str] = None

    created_at: datetime

    # --- ADD THESE TWO LINES ---
    save_for_future: bool
    favourite: bool
    # ---------------------------

    class Config:
        from_attributes = True