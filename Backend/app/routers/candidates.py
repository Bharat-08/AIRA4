# Backend/app/routers/candidates.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import UUID4
from app.dependencies import get_current_user, get_supabase_client
from app.models.user import User
from app.schemas.candidate import (
    CandidateStageUpdate, 
    CandidateContactedUpdate, 
    RankedCandidate, 
    RankedCandidateFromResume
)
from app.schemas.jd import JdSummary # Importing JdSummary as it seems to be an expected response model in some cases
from typing import Union

router = APIRouter(
    prefix="/candidates",
    tags=["Candidates"],
)

@router.patch("/{rank_id}/stage", response_model=Union[RankedCandidate, RankedCandidateFromResume])
async def update_candidate_stage(
    rank_id: UUID4,
    stage_update: CandidateStageUpdate,
    current_user: User = Depends(get_current_user),
    supabase = Depends(get_supabase_client),
):
    """
    Update the pipeline stage for a specific ranked candidate.
    """
    # Try updating in ranked_candidates table
    try:
        response = supabase.table("ranked_candidates").update(
            {"stage": stage_update.stage}
        ).eq("rank_id", str(rank_id)).eq("user_id", str(current_user.id)).select("*").execute()
        
        if response.data:
            return RankedCandidate(**response.data[0])

        # If not found, try updating in ranked_candidates_from_resume
        response = supabase.table("ranked_candidates_from_resume").update(
            {"stage": stage_update.stage}
        ).eq("rank_id", str(rank_id)).eq("user_id", str(current_user.id)).select("*").execute()

        if response.data:
            return RankedCandidateFromResume(**response.data[0])
            
        # If no data in either, candidate not found or doesn't belong to user
        raise HTTPException(status_code=404, detail="Candidate not found or unauthorized")

    except Exception as e:
        print(f"Error updating stage for rank_id {rank_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error updating candidate stage.")

@router.patch("/{rank_id}/contact", response_model=Union[RankedCandidate, RankedCandidateFromResume])
async def update_candidate_contacted_status(
    rank_id: UUID4,
    contacted_update: CandidateContactedUpdate,
    current_user: User = Depends(get_current_user),
    supabase = Depends(get_supabase_client),
):
    """
    Update the contacted status for a specific ranked candidate.
    """
    # Try updating in ranked_candidates table
    try:
        response = supabase.table("ranked_candidates").update(
            {"contacted": contacted_update.contacted}
        ).eq("rank_id", str(rank_id)).eq("user_id", str(current_user.id)).select("*").execute()
        
        if response.data:
            return RankedCandidate(**response.data[0])

        # If not found, try updating in ranked_candidates_from_resume
        response = supabase.table("ranked_candidates_from_resume").update(
            {"contacted": contacted_update.contacted}
        ).eq("rank_id", str(rank_id)).eq("user_id", str(current_user.id)).select("*").execute()

        if response.data:
            return RankedCandidateFromResume(**response.data[0])
            
        # If no data in either, candidate not found or doesn't belong to user
        raise HTTPException(status_code=404, detail="Candidate not found or unauthorized")

    except Exception as e:
        print(f"Error updating contacted status for rank_id {rank_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error updating candidate status.")