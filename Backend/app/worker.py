# backend/app/worker.py
import asyncio
import os
import sys
import logging
import tempfile
from pathlib import Path
from celery import Celery

# Try package import first (app.searcher_apollo_web) then fallback to top-level import.
try:
    from app.searcher_apollo_web import EnhancedDeepResearchAgent, SearchMode
except Exception:
    from searcher_apollo_web import EnhancedDeepResearchAgent, SearchMode

# Existing ranker imports
from ranker import ProfileRanker, Config as RankerConfig

# ✅ Import the non-interactive Google+LinkedIn sourcer (now exports run_sourcing alias)
try:
    from app.services.google_linkedin_sourcer import run_sourcing as run_google_linkedin_sourcing
except Exception:
    # Avoid bad fallback like "from services..." – keep package-qualified import only.
    raise

celery_app = Celery(
    "tasks",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)


@celery_app.task
def apollo_search_task(jd_id: str, custom_prompt: str, user_id: str, search_mode: str):
    """
    Celery task to run the EnhancedDeepResearchAgent in the requested search_mode.
    After the search completes and candidates are saved to the 'search' table,
    this task will run the ProfileRanker to rank those saved profiles and return
    the ranked candidates as the task result.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker: Starting APOLLO search task for JD ID: {jd_id}, mode: {search_mode}")

    try:
        mode_enum = SearchMode(search_mode)
        agent = EnhancedDeepResearchAgent(search_mode=mode_enum)

        logger.info("Apollo task - Step 1: Running EnhancedDeepResearchAgent.search...")
        agent.run_deep_research(jd_id=jd_id, search_mode=mode_enum, custom_prompt=custom_prompt or "", user_id=user_id)
        logger.info("Apollo task - Step 1 Complete: Search finished.")

        logger.info("Apollo task - Step 2: Ranking saved profiles (ProfileRanker)...")
        ranker_config = RankerConfig.from_env()
        ranker_config.user_id = user_id
        ranker_agent = ProfileRanker(ranker_config)

        asyncio.run(ranker_agent.run_ranking_for_api(jd_id=jd_id))
        logger.info("Apollo task - Step 2 Complete: Ranking finished.")

        logger.info("Apollo task - Step 3: Fetching final ranked candidates...")
        rpc_params = {'jd_id_param': jd_id}
        try:
            ranked_response = ranker_agent.supabase.rpc('get_ranked_candidates_with_details', rpc_params).execute()
            final_results = ranked_response.data if getattr(ranked_response, 'data', None) else []
        except Exception:
            logger.exception("Failed to fetch ranked candidates via RPC; returning empty results.")
            final_results = []

        logger.info(f"Apollo task: pipeline finished. Found {len(final_results)} ranked candidates.")
        return {"status": "completed", "result": final_results}
    except Exception as e:
        logger.exception(f"An error occurred in apollo_search_task: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def search_and_rank_pipeline_task(jd_id: str, custom_prompt: str, user_id: str):
    """
    Legacy compatibility task: full search + ranking pipeline.
    Uses the new EnhancedDeepResearchAgent but hardcodes search_mode to APOLLO_ONLY.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker: Starting search and rank pipeline for JD ID: {jd_id}")
    try:
        agent = EnhancedDeepResearchAgent(search_mode=SearchMode.APOLLO_ONLY)
        ranker_config = RankerConfig.from_env()
        ranker_config.user_id = user_id
        ranker_agent = ProfileRanker(ranker_config)

        logger.info(f"Worker - Step 1: Searching for candidates...")
        agent.run_deep_research(jd_id=jd_id, search_mode=SearchMode.APOLLO_ONLY, custom_prompt=custom_prompt or "", user_id=user_id)
        logger.info(f"Worker - Step 1 Complete: Search finished.")

        logger.info(f"Worker - Step 2: Ranking candidates...")
        asyncio.run(ranker_agent.run_ranking_for_api(jd_id=jd_id))
        logger.info("Worker - Step 2 Complete: Ranking finished.")

        logger.info("Worker - Step 3: Fetching final ranked candidates...")
        rpc_params = {'jd_id_param': jd_id}
        ranked_response = ranker_agent.supabase.rpc('get_ranked_candidates_with_details', rpc_params).execute()
        final_results = ranked_response.data if ranked_response.data else []

        logger.info(f"Celery worker: Pipeline finished. Found {len(final_results)} ranked candidates.")
        return {"status": "completed", "result": final_results}
    except Exception as e:
        logger.exception(f"An error occurred in search_and_rank_pipeline_task: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def rank_resumes_task(jd_id: str, user_id: str):
    """
    Celery task to rank resumes using the in-app async DatabaseProfileRanker service.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker: Starting resume ranking for JD ID: {jd_id} user_id: {user_id}")
    try:
        from app.services.database_ranking_service import DatabaseProfileRanker
        from app.dependencies import get_supabase_client

        supabase = get_supabase_client()
        ranker = DatabaseProfileRanker(supabase, user_id)
        results = asyncio.run(ranker.run(jd_id))

        try:
            rpc_params = {'jd_id_param': jd_id}
            ranked_response = supabase.rpc('get_ranked_resumes_with_details', rpc_params).execute()
            final_results = ranked_response.data if getattr(ranked_response, 'data', None) else []
        except Exception:
            logger.exception("Failed to fetch ranked results via RPC, returning runner results as fallback.")
            final_results = results or []

        logger.info(f"Celery worker: Resume ranking finished. Found {len(final_results)} candidates.")
        return {"status": "completed", "result": final_results}
    except Exception as e:
        logger.exception(f"An error occurred during resume ranking task: {e}")
        return {"status": "failed", "error": str(e)}


# =============================
# NEW TASK: process_single_uploaded_resume_task
# =============================

@celery_app.task
def process_single_uploaded_resume_task(jd_id: str, file_contents: bytes, user_id: str):
    """
    Celery task to process a single uploaded resume file (bytes), parse it,
    insert into the `resume` table and then kick off the resume-ranking task.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"process_single_uploaded_resume_task: start jd_id={jd_id} user_id={user_id}")

    try:
        from app.services.resume_parsing_service import process_resume_file
        from app.dependencies import get_supabase_client
    except Exception as e:
        logger.exception("Required modules for resume processing are not available: %s", e)
        return {"status": "failed", "error": f"missing modules: {e}"}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_contents)
            tmp.flush()
            tmp_path = tmp.name

        tmp_path_obj = Path(tmp_path)
        supabase = get_supabase_client()

        inserted = process_resume_file(supabase=supabase, file_path=tmp_path_obj, user_id=user_id, jd_id=jd_id)
        resume_id = inserted.get("resume_id") if isinstance(inserted, dict) else None
        logger.info(f"process_single_uploaded_resume_task: parsed and inserted resume_id={resume_id}")

        try:
            logger.info(f"process_single_uploaded_resume_task: enqueueing rank_resumes_task for jd_id={jd_id}")
            rank_resumes_task.delay(jd_id=jd_id, user_id=user_id)
        except Exception as e:
            logger.exception("Failed to enqueue rank_resumes_task: %s", e)
            return {"status": "parsed", "resume_id": resume_id, "warning": f"failed to enqueue ranking: {e}"}

        return {"status": "processed", "resume_id": resume_id}
    except Exception as e:
        logger.exception("Error in process_single_uploaded_resume_task: %s", e)
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            if tmp_path and Path(tmp_path).exists():
                Path(tmp_path).unlink()
        except Exception as e:
            logging.getLogger(__name__).debug("Could not remove temp file %s: %s", tmp_path, e)


# =============================
# NEW TASK: google_linkedin_task (non-interactive, one-iteration)
# =============================

@celery_app.task
def google_linkedin_task(jd_id: str, user_id: str, custom_prompt: str = ""):
    """
    Kick off one non-interactive iteration of Google+LinkedIn sourcing.
    Uses app.services.google_linkedin_sourcer.run_sourcing (alias of run_once).
    """
    logger = logging.getLogger(__name__)
    logger.info(f"google_linkedin_task: start jd_id={jd_id} user_id={user_id}")
    try:
        result = run_google_linkedin_sourcing(jd_id=jd_id, user_id=user_id, custom_prompt=custom_prompt or "")
        # Ensure a normalized response
        if isinstance(result, dict):
            return {"status": result.get("status", "completed"), **result}
        return {"status": "completed", "result": result}
    except Exception as e:
        logger.exception("google_linkedin_task failed: %s", e)
        return {"status": "failed", "error": str(e)}
