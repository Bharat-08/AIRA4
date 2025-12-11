# Backend/app/routers/pipeline.py
import logging
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, UUID4
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from app.db.session import get_db
from app.dependencies import get_current_user, get_supabase_client
from app.models.user import User
from app.models.candidate import RankedCandidate, RankedCandidateFromResume
from app.models.linkedin import LinkedIn
from postgrest.exceptions import APIError
from supabase import Client
import math

logger = logging.getLogger(__name__)

# --- Helper function for batching (Unchanged) ---
async def fetch_in_batches(
    supabase_client: Client,
    table_name: str,
    id_column: str,
    select_columns: str,
    ids: List[str],
    batch_size: int = 100,
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
            logger.error(
                f"Supabase APIError querying '{table_name}' (batch {i+1}/{total_batches}): {api_err}"
            )
        except Exception as ex:
            logger.exception(
                f"Unexpected error querying Supabase '{table_name}' (batch {i+1}/{total_batches}): {ex}"
            )

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
    source: Literal[
        "ranked_candidates",
        "ranked_candidates_from_resume",
        "linkedin",
    ]

    profile_name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    summary: Optional[str] = None

    jd_name: Optional[str] = None
    is_recommended: bool = False

    class Config:
        orm_mode = True


class RecommendRequest(BaseModel):
    candidate_id: UUID4
    source: str  # 'ranked_candidates', 'ranked_candidates_from_resume', or 'linkedin'
    target_jd_id: Optional[UUID4] = None  # Optional now
    target_user_id: Optional[UUID4] = None  # Added for teammate recommendation


class RecommendToUserRequest(BaseModel):
    candidate_id: UUID4
    target_user_id: UUID4


class StageUpdateRequest(BaseModel):
    stage: str


class DeleteCandidateSchema(BaseModel):
    id: UUID4
    source: str


router = APIRouter(
    prefix="/pipeline",
    tags=["Pipeline"],
    dependencies=[Depends(get_current_user)],
)


# =========================
# STATIC ROUTES FIRST
# =========================

@router.post("/recommend")
async def recommend_candidate(
    payload: RecommendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recommends a candidate to another JD (Role) OR another User (Teammate).
    If target_user_id is provided, it assigns to that user with NULL jd_id (Untagged).
    If target_jd_id is provided, it assigns to the current user (or specific user logic if needed) for that JD.
    """
    try:
        # Validate inputs
        if not payload.target_jd_id and not payload.target_user_id:
            raise HTTPException(status_code=400, detail="Must provide either target_jd_id or target_user_id")

        # Determine target owner and JD
        target_user_uuid = payload.target_user_id if payload.target_user_id else current_user.id

        # If sending to a teammate (target_user_id exists), we set jd_id to None (Untagged).
        # Otherwise, we use the provided target_jd_id.
        target_jd_uuid = payload.target_jd_id if not payload.target_user_id else None

        if payload.source == "ranked_candidates":
            existing = (
                db.query(RankedCandidate)
                .filter(
                    RankedCandidate.rank_id == payload.candidate_id,
                    RankedCandidate.user_id == str(current_user.id),
                )
                .first()
            )

            if not existing:
                raise HTTPException(status_code=404, detail="Candidate not found")

            # Check duplication
            query = db.query(RankedCandidate).filter(
                RankedCandidate.user_id == target_user_uuid,
                RankedCandidate.profile_id == existing.profile_id,
            )

            if target_jd_uuid:
                query = query.filter(RankedCandidate.jd_id == target_jd_uuid)
            else:
                query = query.filter(RankedCandidate.jd_id.is_(None))

            duplicate = query.first()

            if duplicate:
                return {"message": "Candidate already in target pipeline"}

            new_entry = RankedCandidate(
                user_id=target_user_uuid,
                jd_id=target_jd_uuid,
                profile_id=existing.profile_id,
                match_score=existing.match_score,
                strengths=existing.strengths,
                linkedin_url=existing.linkedin_url,
                # ✅ UPDATED: If sending to teammate, set is_recommended=False to avoid clash
                is_recommended=True if target_jd_uuid else False,
                stage="In Consideration",
                recommended_by=current_user.id
            )
            db.add(new_entry)

        elif payload.source == "ranked_candidates_from_resume":
            existing = (
                db.query(RankedCandidateFromResume)
                .filter(
                    RankedCandidateFromResume.rank_id == payload.candidate_id,
                    RankedCandidateFromResume.user_id == str(current_user.id),
                )
                .first()
            )

            if not existing:
                raise HTTPException(status_code=404, detail="Candidate not found")

            query = db.query(RankedCandidateFromResume).filter(
                RankedCandidateFromResume.user_id == target_user_uuid,
                RankedCandidateFromResume.resume_id == existing.resume_id,
            )

            if target_jd_uuid:
                query = query.filter(RankedCandidateFromResume.jd_id == target_jd_uuid)
            else:
                query = query.filter(RankedCandidateFromResume.jd_id.is_(None))

            duplicate = query.first()

            if duplicate:
                return {"message": "Candidate already in target pipeline"}

            new_entry = RankedCandidateFromResume(
                user_id=target_user_uuid,
                jd_id=target_jd_uuid,
                resume_id=existing.resume_id,
                match_score=existing.match_score,
                strengths=existing.strengths,
                linkedin_url=existing.linkedin_url,
                # ✅ UPDATED: False for teammate
                is_recommended=True if target_jd_uuid else False,
                stage="In Consideration",
                recommended_by=current_user.id
            )
            db.add(new_entry)

        elif payload.source == "linkedin":
            existing = (
                db.query(LinkedIn)
                .filter(
                    LinkedIn.linkedin_profile_id == payload.candidate_id,
                    LinkedIn.user_id == str(current_user.id),
                )
                .first()
            )

            if not existing:
                raise HTTPException(status_code=404, detail="Candidate not found")

            new_entry = LinkedIn(
                user_id=target_user_uuid,
                jd_id=target_jd_uuid,
                name=existing.name,
                profile_link=existing.profile_link,
                position=existing.position,
                company=existing.company,
                summary=existing.summary,
                # ✅ UPDATED: False for teammate
                is_recommended=True if target_jd_uuid else False,
                recommended_by=current_user.id
            )
            db.add(new_entry)

        else:
            raise HTTPException(status_code=400, detail="Invalid source type")

        db.commit()
        return {"message": "Candidate recommended successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error recommending candidate: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to recommend candidate")


@router.post("/recommend-to-user")
async def recommend_candidate_to_user(
    payload: RecommendToUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recommend a candidate to a teammate (target_user_id).
    """
    try:
        target_user_id = payload.target_user_id

        # 1) Try RankedCandidate
        existing_ranked = (
            db.query(RankedCandidate)
            .filter(
                RankedCandidate.rank_id == payload.candidate_id,
                RankedCandidate.user_id == str(current_user.id),
            )
            .first()
        )

        if existing_ranked:
            duplicate = (
                db.query(RankedCandidate)
                .filter(
                    RankedCandidate.user_id == str(target_user_id),
                    RankedCandidate.profile_id == existing_ranked.profile_id,
                    RankedCandidate.jd_id.is_(None),
                )
                .first()
            )

            if duplicate:
                return {
                    "message": "Candidate already recommended to this user (ranked_candidates)."
                }

            new_entry = RankedCandidate(
                user_id=str(target_user_id),
                jd_id=None,
                profile_id=existing_ranked.profile_id,
                match_score=existing_ranked.match_score,
                strengths=existing_ranked.strengths,
                linkedin_url=existing_ranked.linkedin_url,
                # ✅ FIXED: Explicitly set False to prevent clash with 'Recommend to Role'
                is_recommended=False, 
                stage="In Consideration",
                recommended_by=current_user.id
            )
            db.add(new_entry)
            db.commit()
            return {"message": "Candidate recommended to user successfully (ranked_candidates)."}

        # 2) Try RankedCandidateFromResume
        existing_resume = (
            db.query(RankedCandidateFromResume)
            .filter(
                RankedCandidateFromResume.rank_id == payload.candidate_id,
                RankedCandidateFromResume.user_id == str(current_user.id),
            )
            .first()
        )

        if existing_resume:
            duplicate = (
                db.query(RankedCandidateFromResume)
                .filter(
                    RankedCandidateFromResume.user_id == str(target_user_id),
                    RankedCandidateFromResume.resume_id == existing_resume.resume_id,
                    RankedCandidateFromResume.jd_id.is_(None),
                )
                .first()
            )

            if duplicate:
                return {
                    "message": "Candidate already recommended to this user (ranked_candidates_from_resume)."
                }

            new_entry = RankedCandidateFromResume(
                user_id=str(target_user_id),
                jd_id=None,
                resume_id=existing_resume.resume_id,
                match_score=existing_resume.match_score,
                strengths=existing_resume.strengths,
                linkedin_url=existing_resume.linkedin_url,
                # ✅ FIXED: Explicitly set False
                is_recommended=False,
                stage="In Consideration",
                recommended_by=current_user.id
            )
            db.add(new_entry)
            db.commit()
            return {"message": "Candidate recommended to user successfully (ranked_candidates_from_resume)."}

        # 3) Try LinkedIn
        existing_linkedin = (
            db.query(LinkedIn)
            .filter(
                LinkedIn.linkedin_profile_id == payload.candidate_id,
                LinkedIn.user_id == str(current_user.id),
            )
            .first()
        )

        if existing_linkedin:
            duplicate = (
                db.query(LinkedIn)
                .filter(
                    LinkedIn.user_id == str(target_user_id),
                    LinkedIn.profile_link == existing_linkedin.profile_link,
                    LinkedIn.jd_id.is_(None),
                )
                .first()
            )

            if duplicate:
                return {
                    "message": "Candidate already recommended to this user (linkedin)."
                }

            new_entry = LinkedIn(
                user_id=str(target_user_id),
                jd_id=None,
                name=existing_linkedin.name,
                profile_link=existing_linkedin.profile_link,
                position=existing_linkedin.position,
                company=existing_linkedin.company,
                summary=existing_linkedin.summary,
                # ✅ FIXED: Explicitly set False
                is_recommended=False,
                recommended_by=current_user.id
            )
            db.add(new_entry)
            db.commit()
            return {"message": "Candidate recommended to user successfully (linkedin)."}

        # If not found in any table
        raise HTTPException(status_code=404, detail="Candidate not found for current user")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error recommending candidate to user: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to recommend candidate to user")


@router.delete("/delete")
async def delete_candidates(
    payload: List[DeleteCandidateSchema],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes candidates from the pipeline.
    Accepts a list of objects with 'id' and 'source'.
    """
    try:
        if not payload:
             return {"message": "No candidates provided"}

        ids_ranked = [str(item.id) for item in payload if item.source == "ranked_candidates"]
        ids_resume = [str(item.id) for item in payload if item.source == "ranked_candidates_from_resume"]
        ids_linkedin = [str(item.id) for item in payload if item.source == "linkedin"]

        if ids_ranked:
            db.query(RankedCandidate).filter(
                RankedCandidate.rank_id.in_(ids_ranked),
                RankedCandidate.user_id == str(current_user.id)
            ).delete(synchronize_session=False)

        if ids_resume:
            db.query(RankedCandidateFromResume).filter(
                RankedCandidateFromResume.rank_id.in_(ids_resume),
                RankedCandidateFromResume.user_id == str(current_user.id)
            ).delete(synchronize_session=False)

        if ids_linkedin:
            db.query(LinkedIn).filter(
                LinkedIn.linkedin_profile_id.in_(ids_linkedin),
                LinkedIn.user_id == str(current_user.id)
            ).delete(synchronize_session=False)

        db.commit()
        return {"message": "Candidates deleted successfully"}
    except Exception as e:
        logger.exception(f"Error deleting candidates: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete candidates")


@router.get("/all/download")
async def download_all_candidates_csv(
    favorite: Optional[bool] = Query(None),
    contacted: Optional[bool] = Query(None),
    save_for_future: Optional[bool] = Query(None),
    recommended: Optional[bool] = Query(None),
    recommended_to_me: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    supabase: Client = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user),
):
    """
    Downloads all ranked candidates as CSV, applying optional filters AND search.
    """
    try:
        # 1. Build filters
        filters_ranked = [RankedCandidate.user_id == str(current_user.id)]
        filters_resume = [RankedCandidateFromResume.user_id == str(current_user.id)]
        filters_linkedin = [LinkedIn.user_id == str(current_user.id)]

        if favorite is not None:
            filters_ranked.append(RankedCandidate.favorite.is_(favorite))
            filters_resume.append(RankedCandidateFromResume.favorite.is_(favorite))
            filters_linkedin.append(LinkedIn.favourite.is_(favorite))

        if contacted is not None:
            filters_ranked.append(RankedCandidate.contacted.is_(contacted))
            filters_resume.append(RankedCandidateFromResume.contacted.is_(contacted))

        if save_for_future is not None:
            filters_ranked.append(RankedCandidate.save_for_future.is_(save_for_future))
            filters_resume.append(
                RankedCandidateFromResume.save_for_future.is_(save_for_future)
            )
            filters_linkedin.append(LinkedIn.save_for_future.is_(save_for_future))

        if recommended is not None:
            filters_ranked.append(RankedCandidate.is_recommended.is_(recommended))
            filters_resume.append(
                RankedCandidateFromResume.is_recommended.is_(recommended)
            )
            filters_linkedin.append(LinkedIn.is_recommended.is_(recommended))

        if recommended_to_me:
            # ✅ FIX: Rely ONLY on recommended_by, ignoring is_recommended flag
            filters_ranked.append(RankedCandidate.recommended_by.isnot(None))
            filters_ranked.append(RankedCandidate.recommended_by != current_user.id)
            
            filters_resume.append(RankedCandidateFromResume.recommended_by.isnot(None))
            filters_resume.append(RankedCandidateFromResume.recommended_by != current_user.id)
            
            filters_linkedin.append(LinkedIn.recommended_by.isnot(None))
            filters_linkedin.append(LinkedIn.recommended_by != current_user.id)

        # Search
        if search:
            search_term = f"%{search}%"

            # Search Web (Supabase)
            web_filter = (
                f"profile_name.ilike.{search_term},"
                f"role.ilike.{search_term},"
                f"company.ilike.{search_term}"
            )
            web_res = (
                supabase.table("search")
                .select("profile_id")
                .or_(web_filter)
                .execute()
            )
            web_ids = [x["profile_id"] for x in web_res.data] if web_res.data else []

            if web_ids:
                filters_ranked.append(RankedCandidate.profile_id.in_(web_ids))
            else:
                filters_ranked.append(text("1=0"))

            # Search Resume (Supabase)
            resume_filter = (
                f"person_name.ilike.{search_term},company.ilike.{search_term}"
            )
            resume_res = (
                supabase.table("resume")
                .select("resume_id")
                .or_(resume_filter)
                .execute()
            )
            resume_ids = [x["resume_id"] for x in resume_res.data] if resume_res.data else []

            if resume_ids:
                filters_resume.append(RankedCandidateFromResume.resume_id.in_(resume_ids))
            else:
                filters_resume.append(text("1=0"))

            # Search LinkedIn (Local SQL)
            filters_linkedin.append(
                or_(
                    LinkedIn.name.ilike(search_term),
                    LinkedIn.position.ilike(search_term),
                    LinkedIn.company.ilike(search_term),
                )
            )

        # 2. Query local DB
        ranked_rows = db.query(RankedCandidate).filter(*filters_ranked).all()
        resume_rows = db.query(RankedCandidateFromResume).filter(*filters_resume).all()

        linkedin_rows: List[LinkedIn] = []
        if not (contacted is True):
            linkedin_rows = db.query(LinkedIn).filter(*filters_linkedin).all()

        all_rows: List[Any] = ranked_rows + resume_rows + linkedin_rows

        # 3. Sort
        def get_sort_key(r: Any) -> float:
            if isinstance(r, LinkedIn):
                return -999999.0
            return r.match_score if r.match_score is not None else -999999.0

        all_rows.sort(key=get_sort_key, reverse=True)

        # 4. Collect IDs & Fetch Metadata
        profile_ids = [
            str(r.profile_id)
            for r in all_rows
            if isinstance(r, RankedCandidate) and r.profile_id
        ]
        resume_ids = [
            str(r.resume_id)
            for r in all_rows
            if isinstance(r, RankedCandidateFromResume) and r.resume_id
        ]
        jd_ids = list({str(r.jd_id) for r in all_rows if r.jd_id})

        profile_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="search",
            id_column="profile_id",
            select_columns="profile_id, profile_name, role, company, summary",
            ids=profile_ids,
        )

        resume_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="resume",
            id_column="resume_id",
            select_columns="resume_id, person_name, company",
            ids=resume_ids,
        )

        jd_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="jds",
            id_column="jd_id",
            select_columns="jd_id, role",
            ids=jd_ids,
        )

        # 5. Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Name",
                "Company",
                "Role",
                "Summary",
                "Match Score",
                "Strengths",
                "Status",
                "JD Role",
                "LinkedIn URL",
                "Recommended",
            ]
        )

        for r in all_rows:
            jd_name = jd_map.get(str(r.jd_id), {}).get("role") if r.jd_id else ""
            c_name = ""
            c_company = ""
            c_role = ""
            c_summary = ""
            c_score: Any = ""
            c_strengths = ""
            c_status = "In Pipeline"
            c_url = ""
            c_rec = False

            if isinstance(r, RankedCandidate):
                pdata = profile_map.get(str(r.profile_id), {}) if r.profile_id else {}
                c_name = pdata.get("profile_name")
                c_company = pdata.get("company")
                c_role = pdata.get("role")
                c_summary = pdata.get("summary")
                c_score = r.match_score
                c_strengths = r.strengths
                c_status = (
                    "Favourited"
                    if r.favorite
                    else ("Contacted" if r.contacted else "In Pipeline")
                )
                c_url = r.linkedin_url or ""
                c_rec = bool(r.is_recommended)

            elif isinstance(r, RankedCandidateFromResume):
                rdata = resume_map.get(str(r.resume_id), {}) if r.resume_id else {}
                c_name = rdata.get("person_name")
                c_company = rdata.get("company")
                c_score = r.match_score
                c_strengths = r.strengths
                c_status = (
                    "Favourited"
                    if r.favorite
                    else ("Contacted" if r.contacted else "In Pipeline")
                )
                c_url = r.linkedin_url or ""
                c_rec = bool(r.is_recommended)

            elif isinstance(r, LinkedIn):
                c_name = r.name
                c_company = r.company
                c_role = r.position
                c_summary = r.summary
                c_status = "Favourited" if r.favourite else "In Pipeline"
                c_url = r.profile_link or ""
                c_rec = bool(r.is_recommended)

            writer.writerow(
                [
                    c_name or "",
                    c_company or "",
                    c_role or "",
                    c_summary or "",
                    c_score or "",
                    c_strengths or "",
                    c_status,
                    jd_name,
                    c_url or "",
                    "Yes" if c_rec else "No",
                ]
            )

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=all_candidates.csv"},
        )

    except Exception as e:
        logger.exception(f"Error downloading all ranked candidates: {e}")
        raise HTTPException(
            status_code=500, detail="Could not download candidates."
        )


@router.get("/all/", response_model=Dict[str, Any])
async def get_all_ranked_candidates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    favorite: Optional[bool] = Query(None),
    contacted: Optional[bool] = Query(None),
    save_for_future: Optional[bool] = Query(None),
    recommended: Optional[bool] = Query(None),
    recommended_to_me: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    supabase: Client = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch all ranked candidates with pagination and SEARCH support.
    """
    try:
        # 1. Build filters
        filters_ranked = [RankedCandidate.user_id == str(current_user.id)]
        filters_resume = [RankedCandidateFromResume.user_id == str(current_user.id)]
        filters_linkedin = [LinkedIn.user_id == str(current_user.id)]

        if favorite is not None:
            filters_ranked.append(RankedCandidate.favorite.is_(favorite))
            filters_resume.append(RankedCandidateFromResume.favorite.is_(favorite))
            filters_linkedin.append(LinkedIn.favourite.is_(favorite))

        if contacted is not None:
            filters_ranked.append(RankedCandidate.contacted.is_(contacted))
            filters_resume.append(RankedCandidateFromResume.contacted.is_(contacted))

        if save_for_future is not None:
            filters_ranked.append(RankedCandidate.save_for_future.is_(save_for_future))
            filters_resume.append(
                RankedCandidateFromResume.save_for_future.is_(save_for_future)
            )
            filters_linkedin.append(LinkedIn.save_for_future.is_(save_for_future))

        if recommended is not None:
            filters_ranked.append(RankedCandidate.is_recommended.is_(recommended))
            filters_resume.append(
                RankedCandidateFromResume.is_recommended.is_(recommended)
            )
            filters_linkedin.append(LinkedIn.is_recommended.is_(recommended))

        if recommended_to_me:
            # ✅ FIX: Rely ONLY on recommended_by, ignoring is_recommended flag
            filters_ranked.append(RankedCandidate.recommended_by.isnot(None))
            filters_ranked.append(RankedCandidate.recommended_by != current_user.id)

            filters_resume.append(RankedCandidateFromResume.recommended_by.isnot(None))
            filters_resume.append(RankedCandidateFromResume.recommended_by != current_user.id)

            filters_linkedin.append(LinkedIn.recommended_by.isnot(None))
            filters_linkedin.append(LinkedIn.recommended_by != current_user.id)

        # Search
        if search:
            search_term = f"%{search}%"

            # Web profiles
            web_filter = (
                f"profile_name.ilike.{search_term},"
                f"role.ilike.{search_term},"
                f"company.ilike.{search_term}"
            )
            web_res = (
                supabase.table("search")
                .select("profile_id")
                .or_(web_filter)
                .execute()
            )
            web_ids = [x["profile_id"] for x in web_res.data] if web_res.data else []

            if web_ids:
                filters_ranked.append(RankedCandidate.profile_id.in_(web_ids))
            else:
                filters_ranked.append(text("1=0"))

            # Resumes
            resume_filter = (
                f"person_name.ilike.{search_term},company.ilike.{search_term}"
            )
            resume_res = (
                supabase.table("resume")
                .select("resume_id")
                .or_(resume_filter)
                .execute()
            )
            resume_ids = [x["resume_id"] for x in resume_res.data] if resume_res.data else []

            if resume_ids:
                filters_resume.append(RankedCandidateFromResume.resume_id.in_(resume_ids))
            else:
                filters_resume.append(text("1=0"))

            # LinkedIn (SQL)
            filters_linkedin.append(
                or_(
                    LinkedIn.name.ilike(search_term),
                    LinkedIn.position.ilike(search_term),
                    LinkedIn.company.ilike(search_term),
                )
            )

        # 2. Query local DB
        ranked_rows = db.query(RankedCandidate).filter(*filters_ranked).all()
        resume_rows = db.query(RankedCandidateFromResume).filter(*filters_resume).all()

        linkedin_rows: List[LinkedIn] = []
        if not (contacted is True):
            linkedin_rows = db.query(LinkedIn).filter(*filters_linkedin).all()

        all_rows: List[Any] = ranked_rows + resume_rows + linkedin_rows

        # 3. Sort
        def get_sort_key(r: Any) -> float:
            if isinstance(r, LinkedIn):
                return -999999.0
            return r.match_score if r.match_score is not None else -999999.0

        all_rows.sort(key=get_sort_key, reverse=True)

        # 4. Paginate
        total = len(all_rows)
        start = (page - 1) * limit
        end = start + limit
        paginated_rows = all_rows[start:end]
        has_more = end < total

        # 5. Collect IDs & Fetch Metadata
        profile_ids = [
            str(r.profile_id)
            for r in paginated_rows
            if isinstance(r, RankedCandidate) and r.profile_id
        ]
        resume_ids = [
            str(r.resume_id)
            for r in paginated_rows
            if isinstance(r, RankedCandidateFromResume) and r.resume_id
        ]
        jd_ids = list({str(r.jd_id) for r in paginated_rows if r.jd_id})

        profile_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="search",
            id_column="profile_id",
            select_columns="profile_id, profile_name, role, company, summary",
            ids=profile_ids,
        )

        resume_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="resume",
            id_column="resume_id",
            select_columns="resume_id, person_name, company",
            ids=resume_ids,
        )

        jd_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="jds",
            id_column="jd_id",
            select_columns="jd_id, role",
            ids=jd_ids,
        )

        # 6. Merge
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
                        match_score=float(r.match_score)
                        if r.match_score is not None
                        else None,
                        strengths=r.strengths,
                        favorite=bool(r.favorite),
                        save_for_future=bool(r.save_for_future),
                        linkedin_url=r.linkedin_url,
                        contacted=bool(r.contacted),
                        stage=r.stage,
                        source="ranked_candidates",
                        profile_name=pdata.get("profile_name"),
                        role=pdata.get("role"),
                        company=pdata.get("company"),
                        summary=pdata.get("summary"),
                        jd_name=jd_name,
                        is_recommended=bool(r.is_recommended),
                    )
                )
            elif isinstance(r, RankedCandidateFromResume):
                rdata = resume_map.get(str(r.resume_id), {}) if r.resume_id else {}
                combined.append(
                    PipelineCandidateResponse(
                        rank_id=r.rank_id,
                        profile_id=None,
                        resume_id=r.resume_id,
                        match_score=float(r.match_score)
                        if r.match_score is not None
                        else None,
                        strengths=r.strengths,
                        favorite=bool(r.favorite),
                        save_for_future=bool(r.save_for_future),
                        linkedin_url=r.linkedin_url,
                        contacted=bool(r.contacted),
                        stage=r.stage,
                        source="ranked_candidates_from_resume",
                        profile_name=rdata.get("person_name") or None,
                        role=None,
                        company=rdata.get("company") or None,
                        summary=None,
                        jd_name=jd_name,
                        is_recommended=bool(r.is_recommended),
                    )
                )
            elif isinstance(r, LinkedIn):
                combined.append(
                    PipelineCandidateResponse(
                        rank_id=r.linkedin_profile_id,
                        profile_id=r.linkedin_profile_id,
                        resume_id=None,
                        match_score=None,
                        strengths=None,
                        favorite=bool(r.favourite),
                        save_for_future=bool(r.save_for_future),
                        linkedin_url=r.profile_link,
                        contacted=False,
                        stage="Sourced",
                        source="linkedin",
                        profile_name=r.name,
                        role=r.position,
                        company=r.company,
                        summary=r.summary,
                        jd_name=jd_name,
                        is_recommended=bool(r.is_recommended),
                    )
                )

        return {
            "items": combined,
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": has_more,
        }

    except Exception as e:
        logger.exception(f"Error fetching all ranked candidates: {e}")
        raise HTTPException(
            status_code=500, detail="Could not fetch all pipeline candidates."
        )


# =========================
# DYNAMIC JD ROUTES AFTER
# =========================

@router.get("/{jd_id}", response_model=List[PipelineCandidateResponse])
async def get_pipeline_for_jd(
    jd_id: str,
    db: Session = Depends(get_db),
    supabase: Client = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user),
):
    """
    Fetches all ranked AND sourced candidates for a specific JD.
    """
    try:
        final_pipeline: List[PipelineCandidateResponse] = []

        # 1. Fetch ranked data
        ranked_candidates = (
            db.query(RankedCandidate)
            .filter(
                RankedCandidate.jd_id == jd_id,
                RankedCandidate.user_id == str(current_user.id),
            )
            .order_by(RankedCandidate.match_score.desc())
            .all()
        )

        # 2. Extract IDs
        profile_ids = [str(rc.profile_id) for rc in ranked_candidates if rc.profile_id]
        jd_ids = list({str(rc.jd_id) for rc in ranked_candidates if rc.jd_id})

        # Fetch Sourced LinkedIn Candidates
        linkedin_candidates = (
            db.query(LinkedIn)
            .filter(LinkedIn.jd_id == jd_id, LinkedIn.user_id == str(current_user.id))
            .all()
        )

        if not jd_ids and linkedin_candidates:
            jd_ids = list({str(lc.jd_id) for lc in linkedin_candidates if lc.jd_id})

        if not ranked_candidates and not linkedin_candidates:
            return []

        # 3. Fetch profile info (Added 'summary')
        profile_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="search",
            id_column="profile_id",
            select_columns="profile_id, profile_name, role, company, summary",
            ids=profile_ids,
        )

        # 4. Fetch JD info
        jd_map = await fetch_in_batches(
            supabase_client=supabase,
            table_name="jds",
            id_column="jd_id",
            select_columns="jd_id, role",
            ids=jd_ids,
        )

        # 5. Merge Ranked
        for rc in ranked_candidates:
            profile_data = (
                profile_map.get(str(rc.profile_id), {}) if rc.profile_id else {}
            )
            jd_data = jd_map.get(str(rc.jd_id), {}) if rc.jd_id else {}

            candidate_data = PipelineCandidateResponse(
                rank_id=rc.rank_id,
                profile_id=rc.profile_id,
                match_score=float(rc.match_score)
                if rc.match_score is not None
                else None,
                strengths=rc.strengths,
                favorite=bool(rc.favorite),
                save_for_future=bool(rc.save_for_future),
                linkedin_url=rc.linkedin_url,
                contacted=bool(rc.contacted),
                stage=rc.stage,
                source="ranked_candidates",
                profile_name=profile_data.get("profile_name"),
                role=profile_data.get("role"),
                company=profile_data.get("company"),
                summary=profile_data.get("summary"),
                jd_name=jd_data.get("role") if jd_data else None,
                is_recommended=bool(rc.is_recommended),
            )
            final_pipeline.append(candidate_data)

        # 6. Merge LinkedIn
        for lc in linkedin_candidates:
            jd_data = jd_map.get(str(lc.jd_id), {}) if lc.jd_id else {}

            linkedin_candidate_data = PipelineCandidateResponse(
                rank_id=lc.linkedin_profile_id,
                profile_id=lc.linkedin_profile_id,
                resume_id=None,
                match_score=None,
                strengths=None,
                favorite=bool(lc.favourite),
                save_for_future=bool(lc.save_for_future),
                linkedin_url=lc.profile_link,
                contacted=False,
                stage="Sourced",
                source="linkedin",
                profile_name=lc.name,
                role=lc.position,
                company=lc.company,
                summary=lc.summary,
                jd_name=jd_data.get("role") if jd_data else None,
                is_recommended=bool(lc.is_recommended),
            )
            final_pipeline.append(linkedin_candidate_data)

        return final_pipeline

    except Exception as e:
        logger.exception(f"Error fetching pipeline for jd {jd_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Could not fetch pipeline candidates."
        )


@router.get("/{jd_id}/download")
async def download_pipeline_for_jd_csv(
    jd_id: str,
    stage: Optional[str] = Query(None),
    favorite: Optional[bool] = Query(None),
    contacted: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    supabase: Client = Depends(get_supabase_client),
    current_user: User = Depends(get_current_user),
):
    """
    Downloads the pipeline for a JD as a CSV file, with optional filtering.
    """
    candidates = await get_pipeline_for_jd(jd_id, db, supabase, current_user)

    filtered: List[PipelineCandidateResponse] = []
    search_lower = search.lower() if search else None

    for c in candidates:
        if favorite is True and not c.favorite:
            continue
        if contacted is True and not c.contacted:
            continue

        if stage and stage != "all" and c.stage != stage:
            continue

        if search_lower:
            name = (c.profile_name or "").lower()
            role = (c.role or "").lower()
            company = (c.company or "").lower()
            if (
                search_lower not in name
                and search_lower not in role
                and search_lower not in company
            ):
                continue

        filtered.append(c)

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Profile Name",
            "Company",
            "Role",
            "Summary",
            "Match Score",
            "Strengths",
            "Stage",
            "Status",
            "LinkedIn URL",
            "Recommended",
        ]
    )

    for c in filtered:
        status_label = (
            "Favourited"
            if c.favorite
            else ("Contacted" if c.contacted else "In Pipeline")
        )
        writer.writerow(
            [
                c.profile_name or "",
                c.company or "",
                c.role or "",
                c.summary or "",
                c.match_score if c.match_score is not None else "",
                c.strengths or "",
                c.stage or "",
                status_label,
                c.linkedin_url or "",
                "Yes" if c.is_recommended else "No",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=pipeline_jd_{jd_id}.csv"},
    )


@router.put("/stage/{rank_id}")
async def update_candidate_stage(
    rank_id: UUID4 = Path(..., description="The rank_id of the RankedCandidate to update"),
    payload: StageUpdateRequest = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload is None or not payload.stage:
        raise HTTPException(status_code=400, detail="Missing 'stage' in request body.")

    rc = (
        db.query(RankedCandidate)
        .filter(
            RankedCandidate.rank_id == rank_id,
            RankedCandidate.user_id == str(current_user.id),
        )
        .one_or_none()
    )

    if rc is None:
        rc_resume = (
            db.query(RankedCandidateFromResume)
            .filter(
                RankedCandidateFromResume.rank_id == rank_id,
                RankedCandidateFromResume.user_id == str(current_user.id),
            )
            .one_or_none()
        )
        if rc_resume is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        rc_resume.stage = payload.stage
        db.commit()
        db.refresh(rc_resume)
        return {
            "rank_id": str(rank_id),
            "new_stage": rc_resume.stage,
            "message": "Stage updated successfully (resume-sourced)",
        }

    rc.stage = payload.stage
    db.commit()
    db.refresh(rc)

    return {
        "rank_id": str(rank_id),
        "new_stage": rc.stage,
        "message": "Stage updated successfully",
    }