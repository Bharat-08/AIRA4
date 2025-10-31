import logging
from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Optional
from pydantic import BaseModel, UUID4
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.dependencies import get_current_user, get_supabase_client
from app.models.user import User
from app.models.candidate import RankedCandidate  # This is the SQLAlchemy model
from supabase import Client

logger = logging.getLogger(__name__)

# This Pydantic schema matches the frontend 'Candidate' type
# (from Frontend/src/types/candidate.ts)
class PipelineCandidateResponse(BaseModel):
    # From ranked_candidates table
    rank_id: UUID4
    profile_id: UUID4
    match_score: Optional[float] = None
    strengths: Optional[str] = None
    favorite: bool = False
    linkedin_url: Optional[str] = None
    contacted: bool = False
    stage: Optional[str] = None

    # From Supabase "search" table
    profile_name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None

    class Config:
        orm_mode = True


class StageUpdateRequest(BaseModel):
    stage: str


router = APIRouter(
    # --- THIS IS THE FIX ---
    # The prefix is now /pipeline, not /api/pipeline
    # Vite will rewrite /api/pipeline -> /pipeline
    # This router will match /pipeline/{jd_id}
    prefix="/pipeline",
    # -----------------------
    tags=["Pipeline"],
    dependencies=[Depends(get_current_user)]
)


@router.get("/{jd_id}", response_model=List[PipelineCandidateResponse])
async def get_pipeline_for_jd(
    jd_id: str,
    db: Session = Depends(get_db),
    supabase: Client = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user),
):
    """
    Fetches all ranked candidates for a specific JD, combining data from
    the SQL DB (ranks, scores, stage, favorite, etc.) and Supabase (profile info).
    """
    try:
        # 1. Fetch ranked data from PostgreSQL (SQLAlchemy)
        ranked_candidates = (
            db.query(RankedCandidate)
            .filter(
                RankedCandidate.jd_id == jd_id,
                RankedCandidate.user_id == str(current_user.id),
            )
            .order_by(RankedCandidate.match_score.desc())
            .all()
        )

        if not ranked_candidates:
            return []

        # 2. Extract profile_ids to query Supabase
        profile_ids = [str(rc.profile_id) for rc in ranked_candidates]

        # 3. Fetch profile info from Supabase ("search" table)
        PROFILE_TABLE_NAME = "search"
        profile_response = (
            supabase.table(PROFILE_TABLE_NAME)
            .select("profile_id, profile_name, role, company")
            .in_("profile_id", profile_ids)
            .execute()
        )

        profile_map = {}
        if profile_response.data:
            # Create a lookup map for fast merging
            profile_map = {str(p["profile_id"]): p for p in profile_response.data}
        else:
            logger.warning(
                f"No profile info found in Supabase 'search' table for {len(profile_ids)} profile_ids."
            )

        # 4. Merge the two data sources
        final_pipeline: List[PipelineCandidateResponse] = []
        for rc in ranked_candidates:
            profile_data = profile_map.get(str(rc.profile_id), {})

            candidate_data = PipelineCandidateResponse(
                # Data from PostgreSQL (RankedCandidate model)
                rank_id=rc.rank_id,
                profile_id=rc.profile_id,
                match_score=float(rc.match_score) if rc.match_score is not None else None,
                strengths=rc.strengths,
                favorite=bool(rc.favorite),
                linkedin_url=rc.linkedin_url,
                contacted=bool(rc.contacted),
                stage=rc.stage,

                # Data from Supabase "search" table
                profile_name=profile_data.get("profile_name"),
                role=profile_data.get("role"),
                company=profile_data.get("company"),
            )
            final_pipeline.append(candidate_data)

        return final_pipeline

    except Exception as e:
        logger.exception(f"Error fetching pipeline for jd {jd_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch pipeline candidates.")


@router.put("/stage/{rank_id}")
async def update_candidate_stage(
    rank_id: UUID4 = Path(..., description="The rank_id of the RankedCandidate to update"),
    payload: StageUpdateRequest = None,  # this must be received in the request body
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload is None or not payload.stage:
        raise HTTPException(status_code=400, detail="Missing 'stage' in request body.")

    # Find candidate
    rc = (
        db.query(RankedCandidate)
        .filter(RankedCandidate.rank_id == rank_id, RankedCandidate.user_id == str(current_user.id))
        .one_or_none()
    )

    if rc is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Update and persist
    rc.stage = payload.stage
    db.commit()
    db.refresh(rc)

    return {"rank_id": str(rank_id), "new_stage": rc.stage, "message": "Stage updated successfully"}