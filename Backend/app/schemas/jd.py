# schemas/jd.py file
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JdBase(BaseModel):
    role: str
    location: Optional[str] = None
    experience_required: Optional[str] = None
    jd_parsed_summary: Optional[str] = None
    
    # --- NEW FIELD ADDED: Full, editable JD content ---
    jd_text: Optional[str] = None
    
    key_requirements: Optional[str] = None
    status: Optional[str] = 'open'

class JdCreate(JdBase):
    pass

class Jd(JdBase):
    jd_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class JdSummary(BaseModel):
    jd_id: str
    role: str
    location: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    jd_parsed_summary: Optional[str] = None
    
    # --- NEW FIELD ADDED: Full JD content for detailed view (from JD model) ---
    jd_text: Optional[str] = None
    
    experience_required: Optional[str] = None
    key_requirements: Optional[str] = None
    candidates_liked: int = 0
    candidates_contacted: int = 0
    status: Optional[str] = 'open'

    class Config:
        orm_mode = True
        
# --- NEW SCHEMA: Used for the PATCH endpoint to allow editing the JD content ---
class JdUpdateContent(BaseModel):
    """Schema for updating the JD's full text content."""
    # This is the only field the user should be allowed to update via the new endpoint
    jd_text: str