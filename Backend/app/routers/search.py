# backend/app/routers/search.py
import logging
import uuid
from typing import Any, Dict, List, Iterable, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
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
)
# --- END: CELERY IMPORTS ---

# Your original dependencies (unchanged)
from ..dependencies import get_current_user, get_supabase_client
from ..models.user import User
from supabase import Client
from ..services.linkedin_finder_service import LinkedInFinder

# DB + ORM
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.candidate import RankedCandidate, RankedCandidateFromResume

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


def _extract_id_values(candidates: Iterable[Any], id_key_candidates: List[str]) -> List[str]:
    out = []
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

    fav_by_profile = {}
    fav_by_resume = {}

    if profile_ids:
        rows = db.query(RankedCandidate.profile_id, RankedCandidate.favorite).filter(RankedCandidate.profile_id.in_(list(profile_ids))).all()
        fav_by_profile = {str(r[0]): bool(r[1]) for r in rows}

    if resume_ids:
        rows = db.query(RankedCandidateFromResume.resume_id, RankedCandidateFromResume.favorite).filter(RankedCandidateFromResume.resume_id.in_(list(resume_ids))).all()
        fav_by_resume = {str(r[0]): bool(r[1]) for r in rows}

    enriched = []
    for c in candidates_list:
        # produce a mutable dict representation
        if isinstance(c, dict):
            item = dict(c)  # shallow copy
        else:
            # convert object to dict by pulling attributes commonly used
            item = {}
            for attr in ("profile_id", "resume_id", "profile_name", "name", "role", "company", "match_score", "strengths", "linkedin_url"):
                if hasattr(c, attr):
                    item[attr] = getattr(c, attr)
            if hasattr(c, "__dict__"):
                try:
                    for k, v in c.__dict__.items():
                        if k not in item:
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


# --- EXISTING ENDPOINTS (unchanged) ---

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
    try:
        enriched = enrich_with_favorites(db, result_items)
    except Exception as e:
        logger.exception("Failed to enrich search results with favorites: %s", e)
        enriched = []
        for r in result_items:
            if isinstance(r, dict):
                item = dict(r)
                item.setdefault("favorite", False)
            else:
                item = {"favorite": False}
            enriched.append(item)

    return {"status": payload.get("status", "completed"), "data": enriched}


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
    try:
        enriched = enrich_with_favorites(db, result_items)
    except Exception as e:
        logger.exception("Failed to enrich rank-resumes results with favorites: %s", e)
        enriched = []
        for r in result_items:
            if isinstance(r, dict):
                item = dict(r)
                item.setdefault("favorite", False)
            else:
                item = {"favorite": False}
            enriched.append(item)

    return {"status": payload.get("status", "completed"), "data": enriched}


# --- NEW ENDPOINT: Combined Search (start tasks) ---
@router.post("/combined-search", status_code=status.HTTP_202_ACCEPTED)
async def trigger_combined_search(
    jd_id: str = Form(...),
    prompt: Optional[str] = Form(None),
    search_option: int = Form(2),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
):
    """
    Starts an Apollo/web search plus optionally processes a single uploaded resume.
    This endpoint should return immediately with HTTP 202. It enqueues:
      - apollo_search_task.delay(...)
      - process_single_uploaded_resume_task.delay(...)  (only if a file was provided)
    """
    user_id = str(current_user.id)
    launched = {}
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

        # If a file was provided, read bytes and enqueue the resume processing task
        if file is not None:
            try:
                file_bytes = await file.read()
                resume_task = process_single_uploaded_resume_task.delay(
                    jd_id=jd_id,
                    file_contents=file_bytes,
                    user_id=user_id
                )
                launched["resume_task_id"] = resume_task.id
            except Exception as fe:
                logger.exception("Failed to enqueue resume processing task: %s", fe)
                # Return 500 because we couldn't enqueue the resume task after accepting the request
                raise HTTPException(status_code=500, detail=f"Failed to enqueue resume processing task: {fe}")

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

    Each item includes: profile_name/person_name, role, company, profile_url, match_score, favorite, source, etc.
    Sorted by match_score desc.
    """
    from app.models.candidate import RankedCandidate, RankedCandidateFromResume
    # Import your ORM models that map to the "search" and "resume" tables
    # If they live elsewhere, adjust these imports accordingly.
    from app.models.search import Search          # <-- must exist as ORM model
    from app.models.resume import Resume          # <-- must exist as ORM model

    try:
        try:
            jd_uuid = uuid.UUID(str(jd_id))
        except Exception:
            # If your DB uses UUID type, SQLAlchemy will usually coerce string UUID fine.
            jd_uuid = jd_id

        # ---- WEB RESULTS: ranked_candidates ⨝ search ----
        web_join = (
            db.query(RankedCandidate, Search)
            .join(
                Search,
                (Search.profile_id == RankedCandidate.profile_id) &
                (Search.jd_id == RankedCandidate.jd_id)
            )
            .filter(
                RankedCandidate.jd_id == jd_uuid,
                RankedCandidate.created_at > since
            )
            .all()
        )

        web_items = []
        for rc, s in web_join:
            item = {
                "rank_id": str(rc.rank_id),
                "user_id": str(rc.user_id) if rc.user_id else None,
                "jd_id": str(rc.jd_id) if rc.jd_id else None,
                "profile_id": str(rc.profile_id) if rc.profile_id else None,
                "rank": rc.rank,
                "match_score": float(rc.match_score) if rc.match_score is not None else None,
                "strengths": rc.strengths,
                "favorite": bool(rc.favorite),
                "save_for_future": bool(rc.save_for_future),
                "send_to_recruiter": str(rc.send_to_recruiter) if rc.send_to_recruiter else None,
                "outreached": bool(rc.outreached),
                "created_at": rc.created_at.isoformat() if rc.created_at else None,
                "linkedin_url": rc.linkedin_url,
                "contacted": bool(rc.contacted),
                "stage": rc.stage,
                "source": "web",

                # From SEARCH table (names/role/company/profile_url)
                "profile_name": s.profile_name,
                "role": s.role,
                "company": s.company,
                "profile_url": s.profile_url,
            }
            web_items.append(item)

        # ---- RESUME RESULTS: ranked_candidates_from_resume ⨝ resume ----
        resume_join = (
            db.query(RankedCandidateFromResume, Resume)
            .join(
                Resume,
                (Resume.resume_id == RankedCandidateFromResume.resume_id) &
                (Resume.jd_id == RankedCandidateFromResume.jd_id)
            )
            .filter(
                RankedCandidateFromResume.jd_id == jd_uuid,
                RankedCandidateFromResume.created_at > since
            )
            .all()
        )

        resume_items = []
        for rr, r in resume_join:
            item = {
                "rank_id": str(rr.rank_id),
                "user_id": str(rr.user_id) if rr.user_id else None,
                "jd_id": str(rr.jd_id) if rr.jd_id else None,
                "resume_id": str(rr.resume_id) if rr.resume_id else None,
                "rank": rr.rank,
                "match_score": float(rr.match_score) if rr.match_score is not None else None,
                "strengths": rr.strengths,
                "favorite": bool(rr.favorite),
                "save_for_future": bool(rr.save_for_future),
                "send_to_recruiter": str(rr.send_to_recruiter) if rr.send_to_recruiter else None,
                "outreached": bool(rr.outreached),
                "created_at": rr.created_at.isoformat() if rr.created_at else None,
                "linkedin_url": rr.linkedin_url,
                "contacted": bool(rr.contacted),
                "stage": rr.stage,
                "source": "resume",

                # From RESUME table (person_name/role/company/profile_url)
                "profile_name": r.person_name,
                "role": r.role,
                "company": r.company,
                "profile_url": r.profile_url,
            }
            resume_items.append(item)

        combined = web_items + resume_items

        # Re-enrich favorites defensively (no harm if already present)
        try:
            enriched = enrich_with_favorites(db, combined)
        except Exception as e:
            logger.exception("Failed to enrich combined results with favorites: %s", e)
            enriched = []
            for it in combined:
                it = dict(it)
                it.setdefault("favorite", False)
                enriched.append(it)

        # Sort by match_score desc (missing scores last)
        def score_val(x):
            ms = x.get("match_score")
            try:
                return float(ms) if ms is not None else -9999.0
            except Exception:
                return -9999.0

        enriched_sorted = sorted(enriched, key=score_val, reverse=True)
        return enriched_sorted

    except Exception as e:
        logger.exception("Error while fetching combined results: %s", e)
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
