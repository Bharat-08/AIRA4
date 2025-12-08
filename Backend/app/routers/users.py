# backend/app/routers/users.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
from pydantic import BaseModel

# ✅ CORRECTED IMPORTS based on your project structure
from ..db.session import get_db

# Attempt to import User model and Auth dependency
try:
    # Standard structure based on 'db.session' existence
    from ..db.models import User
except ImportError:
    # Fallback
    from ..models import User

try:
    # Try finding get_current_user in common locations
    from ..services.auth import get_current_user
except ImportError:
    try:
        from ..dependencies import get_current_user
    except ImportError:
        # If we can't find it, we import from the 'me' router which MUST have it
        from .me import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])

class TeammateResponse(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str

    class Config:
        from_attributes = True

@router.get("/teammates", response_model=List[TeammateResponse])
def get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch ALL users (excluding the current logged-in user).
    """
    # Fetch all users except the one making the request
    users = db.query(User).filter(User.id != current_user.id).all()

    results = []
    for u in users:
        # Use name if available, otherwise email
        display_name = u.name if u.name and u.name.strip() else u.email
        
        results.append({
            "user_id": u.id,
            "name": display_name,
            "email": u.email
        })

    return results