import logging
from typing import Any, Dict, List, Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --- START: CELERY IMPORTS ---
# These are the necessary components to interact with your background tasks
from celery.result import AsyncResult
from app.worker import (
    celery_app,
    search_and_rank_pipeline_task,
    rank_resumes_task,
    apollo_search_task,  # NEW: apollo search task
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
    prompt: optional custom prompt / requirements string
    """
    search_option: int
    prompt: Optional[str] = None

# --- ROUTER SETUP ---
router = APIRouter()
logger = logging.getLogger(__name__)
linkedin_finder_agent = LinkedInFinder()


def _extract_id_values(candidates: Iterable[Any], id_key_candidates: List[str]) -> List[str]:
    """
    Utility to extract id strings from a list of candidate items.
    id_key_candidates: list of possible keys/attrs to try (e.g. ['profile_id', 'id'])
    Supports both dict-like and object-like candidate items.
    """
    out = []
    for c in candidates:
        val = None
        if isinstance(c, dict):
            for k in id_key_candidates:
                if k in c and c[k] is not None:
                    val = str(c[k])
                    break
        else:
            # object-like
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
            # attempt to include common fields if present
            for attr in ("profile_id", "resume_id", "profile_name", "name", "role", "company", "match_score", "strengths", "linkedin_url"):
                if hasattr(c, attr):
                    item[attr] = getattr(c, attr)

            # include any extra attributes by trying __dict__ if available
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


# --- NEW ASYNCHRONOUS ENDPOINTS ---

@router.post("/search", status_code=status.HTTP_202_ACCEPTED)
async def start_search_and_rank(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Starts the full search and rank pipeline as a background task.
    This endpoint is now non-blocking and returns a task ID immediately.
    All the heavy lifting is now done by the 'search_and_rank_pipeline_task' in worker.py.
    """
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
    """
    Starts an Apollo-backed search (Fast or Web+Apollo) as a background Celery job.
    Frontend sends `search_option` (1 or 2) and optional `prompt`.

    Mapping:
      1 -> "apollo_only"        (Fast search)
      2 -> "apollo_and_web"     (Web search + Apollo)
    """
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
    Polls for the results of the main search and rank pipeline. The frontend
    will call this endpoint to check if the background job is complete.
    This endpoint now enriches returned candidate objects with their `favorite` status
    from the ranked_candidates / ranked_candidates_from_resume tables.
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

    # payload is expected to be a dict with 'status' and 'result' keys (result is iterable)
    result_items = payload.get("result") or payload.get("results") or payload.get("data") or []
    try:
        enriched = enrich_with_favorites(db, result_items)
    except Exception as e:
        logger.exception("Failed to enrich search results with favorites: %s", e)
        # fallback to returning original results but ensure they include favorite=False
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
    """
    Starts the resume ranking process as a background task.
    The logic for this is now handled by the 'rank_resumes_task' in worker.py.
    """
    user_id = str(current_user.id)
    task = rank_resumes_task.delay(jd_id=request.jd_id, user_id=user_id)
    return {"task_id": task.id, "status": "processing"}


@router.get("/rank-resumes/results/{task_id}")
async def get_rank_resumes_results(task_id: str, db: Session = Depends(get_db)):
    """
    Polls for the results of the resume ranking task and enriches results with favorites.
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


# --- PRESERVED ENDPOINTS (Functionality Unchanged) ---

@router.post("/cancel/{task_id}")
async def cancel_task(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Cancels a running Celery task using its built-in revoke feature.
    """
    celery_app.control.revoke(task_id, terminate=True)
    logger.info(f"Cancellation request for task: {task_id} by user: {current_user.id}")
    return {"message": "Task cancellation requested."}


@router.post("/generate-linkedin-url")
async def generate_linkedin_url(
    request: LinkedInRequest,
    supabase: Client = Depends(get_supabase_client)
):
    """
    Generates a LinkedIn URL for a specific candidate. (Unchanged).
    """
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
