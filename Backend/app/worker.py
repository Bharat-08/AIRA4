import asyncio
import os
import sys
import logging
from celery import Celery

# Try package import first (app.searcher_apollo_web) then fallback to top-level import.
try:
    from app.searcher_apollo_web import EnhancedDeepResearchAgent, SearchMode
except Exception:
    from searcher_apollo_web import EnhancedDeepResearchAgent, SearchMode

# Existing ranker imports
from ranker import ProfileRanker, Config as RankerConfig

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

    Parameters:
      - jd_id: job description id
      - custom_prompt: optional prompt string
      - user_id: the requesting user's id (used when saving profiles)
      - search_mode: "apollo_only" or "apollo_and_web"
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker: Starting APOLLO search task for JD ID: {jd_id}, mode: {search_mode}")

    try:
        mode_enum = SearchMode(search_mode)
        agent = EnhancedDeepResearchAgent(search_mode=mode_enum)

        # Run the non-interactive research (agent will run 3 iterations and save candidates)
        # New signature: run_deep_research(self, jd_id: str, search_mode: SearchMode, custom_prompt: str = "", user_id: str = None)
        logger.info("Apollo task - Step 1: Running EnhancedDeepResearchAgent.search...")
        agent.run_deep_research(jd_id=jd_id, search_mode=mode_enum, custom_prompt=custom_prompt or "", user_id=user_id)
        logger.info("Apollo task - Step 1 Complete: Search finished.")

        # Step 2: Run profile ranking (ProfileRanker) to rank saved profiles in `search` table
        logger.info("Apollo task - Step 2: Ranking saved profiles (ProfileRanker)...")
        ranker_config = RankerConfig.from_env()
        ranker_config.user_id = user_id
        ranker_agent = ProfileRanker(ranker_config)

        # run the async ranking function synchronously
        asyncio.run(ranker_agent.run_ranking_for_api(jd_id=jd_id))
        logger.info("Apollo task - Step 2 Complete: Ranking finished.")

        # Step 3: Fetch the final ranked candidates via RPC
        logger.info("Apollo task - Step 3: Fetching final ranked candidates...")
        rpc_params = {'jd_id_param': jd_id}
        try:
            ranked_response = ranker_agent.supabase.rpc('get_ranked_candidates_with_details', rpc_params).execute()
            final_results = ranked_response.data if getattr(ranked_response, 'data', None) else []
        except Exception as e:
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
    Uses the new EnhancedDeepResearchAgent but hardcodes search_mode to APOLLO_ONLY
    to preserve previous behavior.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker: Starting search and rank pipeline for JD ID: {jd_id}")
    try:
        # Use the new agent but in APOLLO_ONLY mode for backward compatibility
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
    Replaces the old subprocess-based approach to avoid blocking workers.
    This task is unchanged and will continue to be used when the frontend triggers resume-ranking.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Celery worker: Starting resume ranking for JD ID: {jd_id} user_id: {user_id}")
    try:
        # Import here to avoid import cycles during module load
        from app.services.database_ranking_service import DatabaseProfileRanker
        from app.dependencies import get_supabase_client

        # Obtain the shared supabase client (synchronous client)
        supabase = get_supabase_client()

        # Instantiate the async ranker and run it from this synchronous task
        ranker = DatabaseProfileRanker(supabase, user_id)

        # Run the async runner synchronously using asyncio.run
        results = asyncio.run(ranker.run(jd_id))

        # After the ranker has written results to DB, fetch the final detailed rows
        try:
            rpc_params = {'jd_id_param': jd_id}
            ranked_response = supabase.rpc('get_ranked_resumes_with_details', rpc_params).execute()
            final_results = ranked_response.data if getattr(ranked_response, 'data', None) else []
        except Exception as e:
            logger.exception("Failed to fetch ranked results via RPC, returning runner results as fallback.")
            final_results = results or []

        logger.info(f"Celery worker: Resume ranking finished. Found {len(final_results)} candidates.")
        return {"status": "completed", "result": final_results}
    except Exception as e:
        logger.exception(f"An error occurred during resume ranking task: {e}")
        return {"status": "failed", "error": str(e)}
