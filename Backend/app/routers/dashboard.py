# Backend/app/routers/dashboard.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.db.session import get_db
from app.security.deps import require_user
from app.models.user import User
from app.models.jd import JD
from app.models.candidate import RankedCandidate

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)

@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    ctx: dict = Depends(require_user) # Use the correct auth dependency
):
    """
    Returns statistics for the user's landing page:
    - Open Roles: Count of JDs with status 'Open' (case-insensitive)
    - Contacted Candidates: Count of RankedCandidates with contacted=True
    - Favorited Candidates: Count of RankedCandidates with favorite=True
    - Recommendations Received: Count of candidates recommended by others
    """
    try:
        user = ctx["user"]
        user_id = user.id

        # 1. Count Open Roles
        # Using func.lower() to match 'open', 'Open', 'OPEN'
        open_roles_count = db.query(JD).filter(
            JD.user_id == user_id,
            func.lower(JD.status) == "open" 
        ).count()

        # 2. Count Contacted Candidates
        contacted_candidates_count = db.query(RankedCandidate).filter(
            RankedCandidate.user_id == user_id,
            RankedCandidate.contacted == True
        ).count()

        # 3. Count Favorited Candidates
        favorited_candidates_count = db.query(RankedCandidate).filter(
            RankedCandidate.user_id == user_id,
            RankedCandidate.favorite == True
        ).count()

        # 4. Count Recommendations Received
        # Logic: Check if recommended_by exists and is NOT the current user
        # We ignore is_recommended flag because we set it to False for teammate recommendations now.
        recommendations_received_count = db.query(RankedCandidate).filter(
            RankedCandidate.user_id == user_id,
            RankedCandidate.recommended_by != None,
            RankedCandidate.recommended_by != user_id
        ).count()

        return {
            "open_roles": open_roles_count,
            "contacted_candidates": contacted_candidates_count,
            "favorited_candidates": favorited_candidates_count,
            "recommendations_received": recommendations_received_count
        }

    except Exception as e:
        print(f"Error fetching dashboard stats for user: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch dashboard statistics.")