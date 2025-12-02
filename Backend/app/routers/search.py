# backend/app/routers/search.py
import logging
import uuid
import io
import pandas as pd  # NEW: For data formatting
from typing import Any, Dict, List, Iterable, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, StreamingResponse  # NEW: StreamingResponse for downloads
from pydantic import BaseModel

# SQL helper
from sqlalchemy import text

# --- START: CELERY IMPORTS ---
from celery.result import AsyncResult
from app.worker import (
    celery_app,
    search_and_rank_pipeline_task,
    rank_resumes_task,
    apollo_search_task,
    process_single_uploaded_resume_task,  # NEW: background task to handle a single uploaded resume
    google_linkedin_task,                 # NEW: Google+LinkedIn sourcing task
)
# --- END: CELERY IMPORTS ---

# Your original dependencies (unchanged)
from ..dependencies import get_current_user, get_supabase_client
from ..models.user import User
from supabase import Client

# DB + ORM
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.candidate import RankedCandidate, RankedCandidateFromResume
from app.models.linkedin import LinkedIn  # <-- ADDED THIS IMPORT
from app.schemas.linkedin import LinkedInCandidate  # <-- ADDED THIS IMPORT

# LinkedIn finder
from ..services.linkedin_finder_service import LinkedInFinder


# --- MODELS (Unchanged) ---
class SearchRequest(BaseModel):
    jd_id: str
    prompt: str


class LinkedInRequest(BaseModel):
    profile_id: str


# --- NEW: Apollo Search Request Model ---
class ApolloSearchRequest(BaseModel):
    """
    Request body for the /apollo-search/{jd_id} endpoint.
    search_option: 1 -> apollo_only (fast), 2 -> apollo_and_web (comprehensive)
    prompt: Optional custom prompt / requirements string
    """
    search_option: int
    prompt: Optional[str] = None


# --- ROUTER SETUP ---
router = APIRouter()
logger = logging.getLogger(__name__)
linkedin_finder_agent = LinkedInFinder()


# --- HELPER: Date Sorting Key ---
def date_sort_key(item: Dict[str, Any]) -> datetime:
    """
    Helper to extract a datetime object from a dictionary for sorting.
    Handles 'created_at' as datetime object, ISO string, or missing.
    """
    val = item.get("created_at")
    if val is None:
        return datetime.min
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return datetime.min


def _extract_id_values(candidates: Iterable[Any], id_key_candidates: List[str]) -> List[str]:
    out: List[str] = []
    for c in candidates:
        val = None
        if isinstance(c, dict):
            for k in id_key_candidates:
                if k in c and c[k] is not None:
                    val = str(c[k])
                    break
        else:
            for k in id_key_candidates:
                if hasattr(c, k) and getattr(c, k) is not None:
                    val = str(getattr(c, k))
                    break
        if val:
            out.append(val)
    return out


def enrich_with_favorites(db: Session, candidates: Iterable[Any]) -> List[Dict]:
    """
    Given an iterable of candidate items (dicts or objects), query the DB to find
    favorite flags and attach a 'favorite' boolean to each candidate dict.
    Returns a list of plain dicts.
    """
    candidates_list = list(candidates)
    # Try to extract profile_ids and resume_ids (if present)
    profile_ids = set(_extract_id_values(candidates_list, ["profile_id", "id", "profileId"]))
    resume_ids = set(_extract_id_values(candidates_list, ["resume_id", "resumeId"]))

    fav_by_profile: Dict[str, bool] = {}
    fav_by_resume: Dict[str, bool] = {}

    if profile_ids:
        rows = db.query(RankedCandidate.profile_id, RankedCandidate.favorite) \
                 .filter(RankedCandidate.profile_id.in_(list(profile_ids))).all()
        fav_by_profile = {str(r[0]): bool(r[1]) for r in rows}

    if resume_ids:
        rows = db.query(RankedCandidateFromResume.resume_id, RankedCandidateFromResume.favorite) \
                 .filter(RankedCandidateFromResume.resume_id.in_(list(resume_ids))).all()
        fav_by_resume = {str(r[0]): bool(r[1]) for r in rows}

    enriched: List[Dict] = []
    for c in candidates_list:
        # produce a mutable dict representation
        if isinstance(c, dict):
            item = dict(c)  # shallow copy
        else:
            # Convert SQLAlchemy model to dict
            item = {col.name: getattr(c, col.name) for col in c.__table__.columns}

            # Handle potential __dict__ attributes if not a pure ORM model (less ideal)
            if not item and hasattr(c, "__dict__"):
                try:
                    for k, v in c.__dict__.items():
                        if k not in item and not k.startswith('_'):
                            item[k] = v
                except Exception:
                    pass

        # default favorite = False unless DB says otherwise
        fav_val = False
        if "profile_id" in item and item.get("profile_id") is not None:
            fav_val = fav_by_profile.get(str(item.get("profile_id")), False)
        elif "resume_id" in item and item.get("resume_id") is not None:
            fav_val = fav_by_resume.get(str(item.get("resume_id")), False)

        item["favorite"] = bool(fav_val)
        enriched.append(item)

    return enriched


# ----------------------------
# Base-table merge helpers (Unchanged)
# ----------------------------

def _fetch_search_base_map(db: Session, profile_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Returns { profile_id: {profile_name, role, company, profile_url} } for ids in search table.
    """
    base: Dict[str, Dict[str, Any]] = {}
    if not profile_ids:
        return base

    profile_id_list = list(set(profile_ids))
    if not profile_id_list:
        return base

    rows = db.execute(
        text("""
            SELECT profile_id, profile_name, role, company, profile_url
            FROM public.search
            WHERE profile_id = ANY(:pids)
        """),
        {"pids": profile_id_list},
    ).fetchall()

    for row in rows:
        d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        base[str(d["profile_id"])] = {
            "profile_name": d.get("profile_name"),
            "role": d.get("role"),
            "company": d.get("company"),
            "profile_url": d.get("profile_url"),
        }
    return base


def _fetch_resume_base_map(db: Session, resume_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Returns { resume_id: {person_name, role, company, profile_url} } for ids in resume table.
    """
    base: Dict[str, Dict[str, Any]] = {}
    if not resume_ids:
        return base

    resume_id_list = list(set(resume_ids))
    if not resume_id_list:
        return base

    rows = db.execute(
        text("""
            SELECT resume_id, person_name, role, company, profile_url
            FROM public.resume
            WHERE resume_id = ANY(:rids)
        """),
        {"rids": resume_id_list},
    ).fetchall()

    for row in rows:
        d = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        base[str(d["resume_id"])] = {
            "person_name": d.get("person_name"),
            "role": d.get("role"),
            "company": d.get("company"),
            "profile_url": d.get("profile_url"),
        }
    return base


def _merge_web_ranked_with_search_base(items: List[Dict], base_map: Dict[str, Dict[str, Any]]) -> List[Dict]:
    merged: List[Dict] = []
    for it in items:
        pid = str(it.get("profile_id")) if it.get("profile_id") else None
        base = base_map.get(pid or "", {})
        it["profile_name"] = base.get("profile_name") or it.get("profile_name")
        it["role"] = base.get("role") or it.get("role")
        it["company"] = base.get("company") or it.get("company")
        it["profile_url"] = base.get("profile_url") or it.get("profile_url")
        it["source"] = "web"
        merged.append(it)
    return merged


def _merge_resume_ranked_with_resume_base(items: List[Dict], base_map: Dict[str, Dict[str, Any]]) -> List[Dict]:
    merged: List[Dict] = []
    for it in items:
        rid = str(it.get("resume_id")) if it.get("resume_id") else None
        base = base_map.get(rid or "", {})
        it["person_name"] = base.get("person_name") or it.get("person_name")
        it["role"] = base.get("role") or it.get("role")
        it["company"] = base.get("company") or it.get("company")
        it["profile_url"] = base.get("profile_url") or it.get("profile_url")
        it["source"] = "resume"
        merged.append(it)
    return merged


# --- EXISTING ENDPOINTS (with fixes) ---

@router.post("/search", status_code=status.HTTP_202_ACCEPTED)
async def start_search_and_rank(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    user_id = str(current_user.id)
    task = search_and_rank_pipeline_task.delay(
        jd_id=request.jd_id,
        custom_prompt=request.prompt,
        user_id=user_id
    )
    return {"task_id": task.id, "status": "processing"}


@router.post("/apollo-search/{jd_id}", status_code=status.HTTP_202_ACCEPTED)
async def start_apollo_search(
    jd_id: str,
    body: ApolloSearchRequest,
    current_user: User = Depends(get_current_user)
):
    user_id = str(current_user.id)
    option = body.search_option
    prompt = body.prompt or ""

    if option == 1:
        search_mode_str = "apollo_only"
    elif option == 2:
        search_mode_str = "apollo_and_web"
    else:
        raise HTTPException(status_code=400, detail="search_option must be 1 or 2")

    task = apollo_search_task.delay(
        jd_id=jd_id,
        custom_prompt=prompt,
        user_id=user_id,
        search_mode=search_mode_str
    )

    return {"task_id": task.id, "status": "processing"}


@router.get("/search/results/{task_id}")
async def get_search_results(task_id: str, db: Session = Depends(get_db)):
    """
    After Celery reports completion, take the returned ranked rows (with profile_id),
    enrich with favorites, then MERGE base profile fields (name/role/company/profile_url)
    from the `public.search` table.
    """
    task_result = AsyncResult(task_id, app=celery_app)
    if not task_result.ready():
        return {"status": "processing"}

    payload = task_result.get()
    if not task_result.successful():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "failed", "error": payload.get("error", str(task_result.info))}
        )

    result_items = payload.get("result") or payload.get("results") or payload.get("data") or []

    # 1) favorites
    try:
        enriched = enrich_with_favorites(db, result_items)
    except Exception as e:
        logger.exception("Failed to enrich search results with favorites: %s", e)
        enriched = []
        for r in result_items:
            item = dict(r) if isinstance(r, dict) else {col.name: getattr(r, col.name) for col in r.__table__.columns}
            item.setdefault("favorite", False)
            enriched.append(item)

    # 2) base merge from public.search
    profile_ids = [str(x.get("profile_id")) for x in enriched if isinstance(x, dict) and x.get("profile_id")]
    base_map = _fetch_search_base_map(db, profile_ids)
    merged = _merge_web_ranked_with_search_base(enriched, base_map)

    # 3) ✅ SORT BY CREATED_AT (Newest First)
    merged_sorted = sorted(merged, key=date_sort_key, reverse=True)

    return {"status": payload.get("status", "completed"), "data": merged_sorted}


@router.post("/rank-resumes", status_code=status.HTTP_202_ACCEPTED)
async def start_rank_resumes(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    user_id = str(current_user.id)
    task = rank_resumes_task.delay(jd_id=request.jd_id, user_id=user_id)
    return {"task_id": task.id, "status": "processing"}


@router.get("/rank-resumes/results/{task_id}")
async def get_rank_resumes_results(task_id: str, db: Session = Depends(get_db)):
    """
    After Celery reports completion, take the returned ranked rows (with resume_id),
    enrich with favorites, then MERGE base fields (person_name/role/company/profile_url)
    from the `public.resume` table.
    """
    task_result = AsyncResult(task_id, app=celery_app)
    if not task_result.ready():
        return {"status": "processing"}

    payload = task_result.get()
    if not task_result.successful():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "failed", "error": payload.get("error", str(task_result.info))}
        )

    result_items = payload.get("result") or payload.get("results") or payload.get("data") or []

    # 1) favorites
    try:
        enriched = enrich_with_favorites(db, result_items)
    except Exception as e:
        logger.exception("Failed to enrich rank-resumes results with favorites: %s", e)
        enriched = []
        for r in result_items:
            item = dict(r) if isinstance(r, dict) else {col.name: getattr(r, col.name) for col in r.__table__.columns}
            item.setdefault("favorite", False)
            enriched.append(item)

    # 2) base merge from public.resume
    resume_ids = [str(x.get("resume_id")) for x in enriched if isinstance(x, dict) and x.get("resume_id")]
    base_map = _fetch_resume_base_map(db, resume_ids)
    merged = _merge_resume_ranked_with_resume_base(enriched, base_map)

    # 3) ✅ SORT BY CREATED_AT (Newest First)
    merged_sorted = sorted(merged, key=date_sort_key, reverse=True)

    return {"status": payload.get("status", "completed"), "data": merged_sorted}


# --- NEW ENDPOINT: Combined Search (start tasks) ---
@router.post("/combined-search", status_code=status.HTTP_202_ACCEPTED)
async def trigger_combined_search(
    jd_id: str = Form(...),
    prompt: Optional[str] = Form(None),
    search_option: int = Form(2),
    files: List[UploadFile] = File(None),  # CHANGED: Accepts list of files
    current_user: User = Depends(get_current_user),
):
    """
    Starts an Apollo/web search plus optionally processes multiple uploaded resumes.
    This endpoint should return immediately with HTTP 202. It enqueues:
      - apollo_search_task.delay(...)
      - process_single_uploaded_resume_task.delay(...)  (for each file provided)
    """
    user_id = str(current_user.id)
    launched: Dict[str, Any] = {}
    try:
        # Map search_option to search_mode string
        if search_option == 1:
            search_mode_str = "apollo_only"
        elif search_option == 2:
            search_mode_str = "apollo_and_web"
        else:
            raise HTTPException(status_code=400, detail="search_option must be 1 or 2")

        # Launch the apollo search task
        apollo_task = apollo_search_task.delay(
            jd_id=jd_id,
            custom_prompt=prompt or "",
            user_id=user_id,
            search_mode=search_mode_str
        )
        launched["apollo_task_id"] = apollo_task.id

        # If files were provided, read bytes and enqueue the resume processing task for each
        if files:
            resume_task_ids = []
            for file in files:
                try:
                    file_bytes = await file.read()
                    # We reuse the "single" task for each file in the loop
                    resume_task = process_single_uploaded_resume_task.delay(
                        jd_id=jd_id,
                        file_contents=file_bytes,
                        user_id=user_id
                    )
                    resume_task_ids.append(resume_task.id)
                except Exception as fe:
                    logger.exception(f"Failed to enqueue resume processing task for file {file.filename}: {fe}")
                    # We continue processing other files even if one fails
            
            if resume_task_ids:
                launched["resume_task_ids"] = resume_task_ids

        return {"status": "processing", **launched}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to start combined search tasks: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# --- NEW ENDPOINT: Combined Results (polling) ---
@router.get("/combined-results")
async def get_combined_results(
    jd_id: str = Query(..., description="JD id to fetch results for"),
    since: datetime = Query(..., description="ISO datetime; return candidates created after this timestamp"),
    db: Session = Depends(get_db)
):
    """
    Returns combined results from:
      - ranked_candidates (web)  JOIN search on (profile_id, jd_id)
      - ranked_candidates_from_resume (uploaded resumes) JOIN resume on (resume_id, jd_id)
    """
    try:
        try:
            jd_uuid = uuid.UUID(str(jd_id))
        except Exception:
            jd_uuid = jd_id  # let SQLAlchemy coerce if already UUID

        # ---- 1. FETCH WEB RESULTS ----
        web_ranked_rows = (
            db.query(RankedCandidate)
            .filter(
                RankedCandidate.jd_id == jd_uuid,
                RankedCandidate.created_at > since
            )
            .all()
        )
        web_items = [
            {col.name: getattr(rc, col.name) for col in rc.__table__.columns}
            for rc in web_ranked_rows
        ]

        # ---- 2. FETCH RESUME RESULTS ----
        resume_ranked_rows = (
            db.query(RankedCandidateFromResume)
            .filter(
                RankedCandidateFromResume.jd_id == jd_uuid,
                RankedCandidateFromResume.created_at > since
            )
            .all()
        )
        resume_items = [
            {col.name: getattr(rr, col.name) for col in rr.__table__.columns}
            for rr in resume_ranked_rows
        ]

        # ---- 3. MERGE BASE DATA (Name, Role, etc.) ----
        profile_ids = [str(x.get("profile_id")) for x in web_items if x.get("profile_id")]
        web_base_map = _fetch_search_base_map(db, profile_ids)
        merged_web_items = _merge_web_ranked_with_search_base(web_items, web_base_map)

        resume_ids = [str(x.get("resume_id")) for x in resume_items if x.get("resume_id")]
        resume_base_map = _fetch_resume_base_map(db, resume_ids)
        merged_resume_items = _merge_resume_ranked_with_resume_base(resume_items, resume_base_map)

        # ---- 4. COMBINE AND ENRICH ----
        combined = merged_web_items + merged_resume_items

        # Re-enrich favorites
        try:
            enriched = enrich_with_favorites(db, combined)
        except Exception as e:
            logger.exception("Failed to enrich combined results with favorites: %s", e)
            enriched = []
            for it in combined:
                it = dict(it)
                it.setdefault("favorite", False)
                enriched.append(it)

        # ---- 5. SORT AND RETURN ----
        # ✅ UPDATED: Sort by Newest to Oldest (created_at desc)
        enriched_sorted = sorted(enriched, key=date_sort_key, reverse=True)

        # JSON-serializable datetimes
        for item in enriched_sorted:
            for key, val in item.items():
                if isinstance(val, datetime):
                    item[key] = val.isoformat()

        return enriched_sorted

    except Exception as e:
        logger.exception("Error while fetching combined results: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# --- NEW ENDPOINT: Download Results ---
@router.get("/download-results")
async def download_results(
    jd_id: str = Query(..., description="JD ID to fetch results for"),
    format: str = Query("csv", description="File format: 'csv' or 'xlsx'"),
    db: Session = Depends(get_db)
):
    """
    Downloads search results (Web, Resume, LinkedIn) for a given JD in CSV or Excel format.
    Columns: Name, Company, Role, Summary, Match Score, Strengths, Source.
    """
    try:
        try:
            jd_uuid = uuid.UUID(str(jd_id))
        except Exception:
            jd_uuid = jd_id

        # 1. Fetch Web Candidates (ranked_candidates + public.search)
        web_query = text("""
            SELECT 
                s.profile_name as name,
                s.company,
                s.role,
                s.summary,
                rc.match_score,
                rc.strengths,
                'Web Search' as source
            FROM ranked_candidates rc
            JOIN public.search s ON rc.profile_id = s.profile_id
            WHERE rc.jd_id = :jd_id
        """)
        web_rows = db.execute(web_query, {"jd_id": jd_uuid}).fetchall()
        web_data = [dict(row._mapping) for row in web_rows]

        # 2. Fetch Resume Candidates (ranked_candidates_from_resume + public.resume)
        # Using fallback for summary if it doesn't exist in public.resume, 
        # but prioritizing extracting it if available.
        try:
            resume_query = text("""
                SELECT 
                    r.person_name as name,
                    r.company,
                    r.role,
                    r.summary, 
                    rcr.match_score,
                    rcr.strengths,
                    'Uploaded Resume' as source
                FROM ranked_candidates_from_resume rcr
                JOIN public.resume r ON rcr.resume_id = r.resume_id
                WHERE rcr.jd_id = :jd_id
            """)
            resume_rows = db.execute(resume_query, {"jd_id": jd_uuid}).fetchall()
            resume_data = [dict(row._mapping) for row in resume_rows]
        except Exception as e:
            logger.warning(f"Could not fetch resume details with summary: {e}. Rolling back and trying fallback.")
            # IMPORTANT: Rollback the failed transaction before proceeding!
            db.rollback()
            
            resume_fallback = text("""
                SELECT 
                    r.person_name as name,
                    r.company,
                    r.role,
                    '' as summary, 
                    rcr.match_score,
                    rcr.strengths,
                    'Uploaded Resume' as source
                FROM ranked_candidates_from_resume rcr
                JOIN public.resume r ON rcr.resume_id = r.resume_id
                WHERE rcr.jd_id = :jd_id
            """)
            resume_rows = db.execute(resume_fallback, {"jd_id": jd_uuid}).fetchall()
            resume_data = [dict(row._mapping) for row in resume_rows]

        # 3. Fetch LinkedIn Candidates (public.linkedin)
        linkedin_query = text("""
            SELECT 
                l.name,
                l.company,
                l.position as role,
                l.summary,
                NULL as match_score,
                NULL as strengths,
                'LinkedIn Sourcing' as source
            FROM public.linkedin l
            WHERE l.jd_id = :jd_id
        """)
        linkedin_rows = db.execute(linkedin_query, {"jd_id": jd_uuid}).fetchall()
        linkedin_data = [dict(row._mapping) for row in linkedin_rows]

        # Combine all data
        all_data = web_data + resume_data + linkedin_data

        if not all_data:
            # Return empty file with headers
            df = pd.DataFrame(columns=["name", "company", "role", "summary", "match_score", "strengths", "source"])
        else:
            df = pd.DataFrame(all_data)

        # Rename columns for nicer export
        df.rename(columns={
            "name": "Candidate Name",
            "company": "Company",
            "role": "Role",
            "summary": "Summary",
            "match_score": "Match Score",
            "strengths": "Strengths",
            "source": "Source"
        }, inplace=True)

        # Generate File
        stream = io.BytesIO()
        if format.lower() == 'xlsx':
            # Excel
            with pd.ExcelWriter(stream, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Candidates')
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"candidates_{jd_id}.xlsx"
        else:
            # CSV (Default)
            df.to_csv(stream, index=False)
            media_type = "text/csv"
            filename = f"candidates_{jd_id}.csv"

        stream.seek(0)
        
        return StreamingResponse(
            stream,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.exception("Export failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# --- PRESERVED ENDPOINTS (Functionality Unchanged) ---

@router.post("/cancel/{task_id}")
async def cancel_task(task_id: str, current_user: User = Depends(get_current_user)):
    celery_app.control.revoke(task_id, terminate=True)
    logger.info(f"Cancellation request for task: {task_id} by user: {current_user.id}")
    return {"message": "Task cancellation requested."}


@router.post("/generate-linkedin-url")
async def generate_linkedin_url(
    request: LinkedInRequest,
    supabase: Client = Depends(get_supabase_client)
):
    try:
        generated_url = linkedin_finder_agent.find_and_update_url(
            profile_id=request.profile_id,
            supabase=supabase
        )
        if not generated_url:
            raise HTTPException(status_code=404, detail=f"Could not find LinkedIn URL for candidate {request.profile_id}.")
        return {"linkedin_url": generated_url}
    except Exception as e:
        logger.exception("An error occurred during LinkedIn URL generation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# NEW ENDPOINTS: GOOGLE + LINKEDIN SOURCING
# (Top-level, no extra indentation)
# =============================

@router.post("/google-linkedin/{jd_id}", status_code=status.HTTP_202_ACCEPTED)
async def start_google_linkedin_sourcing(
    jd_id: str,
    prompt: Optional[str] = Form(""),
    current_user: User = Depends(get_current_user),
):
    """
    Start the new Google+LinkedIn sourcing process using Celery.

    - Fetches the JD from public.jds
    - Uses Gemini to extract search facets
    - Searches DuckDuckGo for LinkedIn profiles
    - Inserts results into public.linkedin table
    - Returns task_id for tracking

    This endpoint:
      - Does NOT use user_id from .env
      - Uses the logged-in user (via get_current_user)
      - Enqueues the Celery task google_linkedin_task
    """
    try:
        user_id = str(current_user.id)
        task = google_linkedin_task.delay(
            jd_id=jd_id,
            user_id=user_id,
            custom_prompt=prompt or ""
        )
        return {"task_id": task.id, "status": "processing"}
    except Exception as e:
        logger.exception("Failed to start google_linkedin_task: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google-linkedin/results/{task_id}")
async def get_google_linkedin_results(task_id: str):
    """
    Retrieve the results of the Google+LinkedIn sourcing task.
    """
    task_result = AsyncResult(task_id, app=celery_app)

    if not task_result.ready():
        return {"status": "processing"}

    payload = task_result.get()

    if not task_result.successful():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "failed", "error": str(payload)}
        )

    return payload