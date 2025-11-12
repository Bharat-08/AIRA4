import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, UUID4
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.dependencies import get_current_user, get_supabase_client
from app.models.user import User
from app.models.candidate import RankedCandidate, RankedCandidateFromResume  # SQLAlchemy models
from postgrest.exceptions import APIError
from supabase import Client
import math # Import math for batching

logger = logging.getLogger(__name__)

# --- Helper function for batching ---
async def fetch_in_batches(
    supabase_client: Client,
    table_name: str,
    id_column: str,
    select_columns: str,
    ids: List[str],
    batch_size: int = 100
) -> Dict[str, Any]:
    """Fetches records from Supabase in batches to avoid URL length limits."""
    data_map: Dict[str, Any] = {}
    if not ids:
        return data_map
    
    total_batches = math.ceil(len(ids) / batch_size)
    
    for i in range(total_batches):
        start_index = i * batch_size
        end_index = (i + 1) * batch_size
        batch_ids = ids[start_index:end_index]
        
        try:
            response = (
                supabase_client.table(table_name)
                .select(select_columns)
                .in_(id_column, batch_ids)
                .execute()
            )
            if getattr(response, "data", None):
                for item in response.data:
                    data_map[str(item[id_column])] = item
        except APIError as api_err:
            logger.error(f"Supabase APIError querying '{table_name}' (batch {i+1}/{total_batches}): {api_err}")
        except Exception as ex:
            logger.exception(f"Unexpected error querying Supabase '{table_name}' (batch {i+1}/{total_batches}): {ex}")
            
    return data_map
# --- End helper function ---


class PipelineCandidateResponse(BaseModel):
    rank_id: UUID4
    profile_id: Optional[UUID4] = None
    resume_id: Optional[UUID4] = None
    match_score: Optional[float] = None
    strengths: Optional[str] = None
    favorite: bool = False
    save_for_future: bool = False
    linkedin_url: Optional[str] = None
    contacted: bool = False
    stage: Optional[str] = None
    source: Optional[str] = "ranked_candidates"

    profile_name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    
    jd_name: Optional[str] = None

    class Config:
        orm_mode = True


class StageUpdateRequest(BaseModel):
    stage: str


router = APIRouter(
    prefix="/pipeline",
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
    the SQL DB (ranks, scores, etc.) and Supabase (profile info, jd info).
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

        # 2. Extract profile_ids and jd_ids to query Supabase
        profile_ids = [str(rc.profile_id) for rc in ranked_candidates if rc.profile_id]
        jd_ids = list(set([str(rc.jd_id) for rc in ranked_candidates if rc.jd_id]))

        # 3. Fetch profile info from Supabase ("search" table) - BATCHED
        profile_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="search",
            id_column="profile_id",
            select_columns="profile_id, profile_name, role, company",
            ids=profile_ids
        )

        # 4. Fetch JD info from Supabase ("jds" table) - BATCHED
        jd_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="jds",
            id_column="jd_id",
            select_columns="jd_id, role", # Corrected: Only 'role' exists
            ids=jd_ids
        )

        # 5. Merge the data sources
        final_pipeline: List[PipelineCandidateResponse] = []
        for rc in ranked_candidates:
            profile_data = profile_map.get(str(rc.profile_id), {}) if rc.profile_id else {}
            jd_data = jd_map.get(str(rc.jd_id), {}) if rc.jd_id else {}

            candidate_data = PipelineCandidateResponse(
                rank_id=rc.rank_id,
                profile_id=rc.profile_id,
                match_score=float(rc.match_score) if rc.match_score is not None else None,
                strengths=rc.strengths,
                favorite=bool(rc.favorite),
                save_for_future=bool(rc.save_for_future),
                linkedin_url=rc.linkedin_url,
                contacted=bool(rc.contacted),
                stage=rc.stage,
                source="ranked_candidates", # Source is hardcoded as this endpoint only queries ranked_candidates
                profile_name=profile_data.get("profile_name"),
                role=profile_data.get("role"),
                company=profile_data.get("company"),
                jd_name=jd_data.get("role") if jd_data else None,
            )
            final_pipeline.append(candidate_data)

        return final_pipeline

    except Exception as e:
        logger.exception(f"Error fetching pipeline for jd {jd_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch pipeline candidates.")


@router.get("/all/")
async def get_all_ranked_candidates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    favorite: Optional[bool] = Query(None),
    contacted: Optional[bool] = Query(None),
    save_for_future: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    supabase: Client = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch all ranked candidates (both from `ranked_candidates` and
    `ranked_candidates_from_resume`) for the current user, with pagination
    and optional boolean filters. Merges data from Supabase.
    """
    try:
        # 1. Build filters for local DB query
        filters = [RankedCandidate.user_id == str(current_user.id)]
        filters_resume = [RankedCandidateFromResume.user_id == str(current_user.id)]

        if favorite is not None:
            filters.append(RankedCandidate.favorite.is_(favorite))
            filters_resume.append(RankedCandidateFromResume.favorite.is_(favorite))

        if contacted is not None:
            filters.append(RankedCandidate.contacted.is_(contacted))
            filters_resume.append(RankedCandidateFromResume.contacted.is_(contacted))

        if save_for_future is not None:
            filters.append(RankedCandidate.save_for_future.is_(save_for_future))
            filters_resume.append(RankedCandidateFromResume.save_for_future.is_(save_for_future))

        # 2. Query local DB
        # TODO: This logic queries ALL rows then paginates.
        # This is inefficient but reflects the previous logic.
        # A future optimization would be to paginate the SQL query itself.
        ranked_rows = db.query(RankedCandidate).filter(*filters).all()
        resume_rows = db.query(RankedCandidateFromResume).filter(*filters_resume).all()
        
        all_rows = ranked_rows + resume_rows

        # 3. Sort before paginating
        all_rows.sort(
            key=lambda r: r.match_score if r.match_score is not None else -999999.0,
            reverse=True
        )

        # 4. Paginate the combined list
        total = len(all_rows)
        start = (page - 1) * limit
        end = start + limit
        paginated_rows = all_rows[start:end]
        has_more = end < total

        # 5. Collect IDs *from the paginated list only*
        profile_ids = [str(r.profile_id) for r in paginated_rows if isinstance(r, RankedCandidate) and r.profile_id]
        resume_ids = [str(r.resume_id) for r in paginated_rows if isinstance(r, RankedCandidateFromResume) and r.resume_id]
        jd_ids = list(set([str(r.jd_id) for r in paginated_rows if r.jd_id]))

        # 6. Query Supabase 'search' table - BATCHED
        profile_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="search",
            id_column="profile_id",
            select_columns="profile_id, profile_name, role, company",
            ids=profile_ids
        )

        # 7. Query Supabase 'resumes' table - BATCHED
        # Note: The log showed 'resumes' does not exist. Let's try 'resume' (singular)
        # If this also fails, the helper will log the error but not crash.
        resume_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="resume", # Trying 'resume' (singular) based on log
            id_column="resume_id",
            select_columns="resume_id, person_name, organization",
            ids=resume_ids
        )

        # 8. Query Supabase 'jds' table - BATCHED
        jd_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="jds",
            id_column="jd_id",
            select_columns="jd_id, role", # Corrected: Only 'role' exists
            ids=jd_ids
        )
        
        # 9. Merge all data
        combined: List[PipelineCandidateResponse] = []

        for r in paginated_rows:
            jd_name = None
            if r.jd_id and str(r.jd_id) in jd_map:
                jd_name = jd_map[str(r.jd_id)].get("role")
            
            if isinstance(r, RankedCandidate):
                pdata = profile_map.get(str(r.profile_id), {}) if r.profile_id else {}
                combined.append(
                    PipelineCandidateResponse(
                        rank_id=r.rank_id,
                        profile_id=r.profile_id,
                        resume_id=None,
                        match_score=float(r.match_score) if r.match_score is not None else None,
                        strengths=r.strengths,
                        favorite=bool(r.favorite),
                        save_for_future=bool(r.save_for_future),
                        linkedin_url=r.linkedin_url,
                        contacted=bool(r.contacted),
                        stage=r.stage,
                        source="ranked_candidates", # Set correct source
                        profile_name=pdata.get("profile_name"),
                        role=pdata.get("role"),
                        company=pdata.get("company"),
                        jd_name=jd_name,
                    )
                )
            elif isinstance(r, RankedCandidateFromResume):
                rdata = resume_map.get(str(r.resume_id), {}) if r.resume_id else {}
                combined.append(
                    PipelineCandidateResponse(
                        rank_id=r.rank_id,
                        profile_id=None,
                        resume_id=r.resume_id,
                        match_score=float(r.match_score) if r.match_score is not None else None,
                        strengths=r.strengths,
                        favorite=bool(r.favorite),
                        save_for_future=bool(r.save_for_future),
                        linkedin_url=r.linkedin_url,
                        contacted=bool(r.contacted),
                        stage=r.stage,
                        source="ranked_candidates_from_resume", # Set correct source
                        profile_name=rdata.get("person_name") or None,
                        role=None, 
                        company=rdata.get("organization") or None,
                        jd_name=jd_name,
                    )
                )

        # 10. Return paginated result
        return {
            "items": combined,
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": has_more,
        }

    except Exception as e:
        logger.exception(f"Error fetching all ranked candidates: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch all pipeline candidates.")


@router.put("/stage/{rank_id}")
async def update_candidate_stage(
    rank_id: UUID4 = Path(..., description="The rank_id of the RankedCandidate to update"),
    payload: StageUpdateRequest = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # This function is unchanged
    if payload is None or not payload.stage:
        raise HTTPException(status_code=400, detail="Missing 'stage' in request body.")

    rc = (
        db.query(RankedCandidate)
        .filter(RankedCandidate.rank_id == rank_id, RankedCandidate.user_id == str(current_user.id))
        .one_or_none()
    )

    if rc is None:
        rc_resume = (
            db.query(RankedCandidateFromResume)
            .filter(RankedCandidateFromResume.rank_id == rank_id, RankedCandidateFromResume.user_id == str(current_user.id))
            .one_or_none()
        )
        if rc_resume is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        rc_resume.stage = payload.stage
        db.commit()
        db.refresh(rc_resume)
        return {"rank_id": str(rank_id), "new_stage": rc_resume.stage, "message": "Stage updated successfully (resume-sourced)"}

    rc.stage = payload.stage
    db.commit()
    db.refresh(rc)

    return {"rank_id": str(rank_id), "new_stage": rc.stage, "message": "Stage updated successfully"}