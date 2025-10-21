# backend/app/services/database_ranking_service.py
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any

from app.config import settings
from google import genai
from google.genai import types
from supabase.client import Client  # type: ignore

logger = logging.getLogger(__name__)


def _to_dict_or_none(obj: Any) -> Optional[Dict]:
    """
    Convert various SDK return types into a plain dict (if possible).
    Returns None when conversion isn't possible.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    # pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    # pydantic v1
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    # if it's a JSON string
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except Exception:
            return {"text": obj}
    # fallback: try to json-serialize and parse
    try:
        text = json.dumps(obj)
        return json.loads(text)
    except Exception:
        return None


class DatabaseProfileRanker:
    """
    Async service that ranks profiles from the database for a given JD.
    Uses google-genai Client (async via client.aio when available),
    and wraps synchronous Supabase calls with asyncio.to_thread to avoid blocking.
    """

    def __init__(self, supabase_client: Client, user_id: str):
        self.supabase = supabase_client
        self.user_id = user_id
        self.batch_size = 3
        self.max_retries = 3

        # Default to a Gemini 2.x model unless overridden in settings
        self.model_name = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.0-flash")
        self.api_key = getattr(settings, "GEMINI_API_KEY", None)

        # Instantiate the google-genai Client; it will read GEMINI_API_KEY / GOOGLE_API_KEY
        try:
            if self.api_key:
                self.client = genai.Client(api_key=self.api_key)
            else:
                self.client = genai.Client()

            # Check which entrypoints are available on the client
            has_aio = hasattr(self.client, "aio") and hasattr(self.client.aio, "models")
            has_models = hasattr(self.client, "models") and hasattr(self.client.models, "generate_content")

            logger.info(
                "[DBRanker] Initialized genai.Client -> type=%s aio=%s models=%s",
                type(self.client).__name__,
                has_aio,
                has_models,
            )

            # Fail fast if neither async nor sync model entrypoints are present
            if not (has_aio or has_models):
                raise RuntimeError(
                    "genai.Client does not expose async (.aio.models) or sync (.models.generate_content) entrypoints. "
                    "Ensure 'google-genai' package is installed and GEMINI_API_KEY/GOOGLE_API_KEY is set."
                )

        except Exception as e:
            logger.exception("[DBRanker] Failed to initialize genai.Client: %s", e)
            raise RuntimeError(
                "Failed to initialize google-genai Client. "
                "Ensure the 'google-genai' package is installed in the worker and GEMINI_API_KEY/GOOGLE_API_KEY is set."
            ) from e

    async def _supabase_execute(self, fn, *args, **kwargs):
        """Run synchronous supabase client calls in a threadpool to avoid blocking."""
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def get_unranked_resumes(self, jd_id: str) -> List[Dict]:
        """Fetch resumes for jd_id and exclude those already ranked."""
        logger.info(f"[DBRanker] get_unranked_resumes for jd={jd_id}")

        def fetch_resumes():
            return self.supabase.table("resume").select(
                "resume_id,jd_id,user_id,json_content,person_name,role,company,profile_url"
            ).eq("jd_id", jd_id).execute()

        resumes_resp = await self._supabase_execute(fetch_resumes)
        resumes = getattr(resumes_resp, "data", None) or []
        logger.info(f"[DBRanker] Found {len(resumes)} resumes for JD {jd_id} (before filtering).")

        def fetch_ranked():
            return self.supabase.table("ranked_candidates_from_resume").select("resume_id").eq("jd_id", jd_id).execute()

        ranked_resp = await self._supabase_execute(fetch_ranked)
        ranked_ids = {r["resume_id"] for r in (getattr(ranked_resp, "data", None) or [])}
        logger.info(f"[DBRanker] Already ranked {len(ranked_ids)} resumes for JD {jd_id}")

        unranked = [r for r in resumes if r.get("resume_id") not in ranked_ids]
        logger.info(f"[DBRanker] {len(unranked)} resumes remain to be processed for JD {jd_id}")
        return unranked

    def _build_prompt(self, jd: Dict, candidate_text: str) -> str:
        """Build prompt for the LLM."""
        prompt = f"""
You are a talent intelligence assistant. Evaluate the candidate profile vs the job description.

JD Summary: {jd.get('jd_parsed_summary', 'Not available')}

Candidate Profile:
{candidate_text}

Return a single JSON object only with the schema:
{{
  "match_score": <float 0.0-100.0>,
  "verdict": "<one-line verdict>",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "reasoning": "<detailed reasoning>"
}}
"""
        return prompt

    async def _call_gemini(self, prompt: str) -> Optional[Dict]:
        """
        Use the new Google GenAI SDK:
         - Preferred: await client.aio.models.generate_content(...)
         - Fallback: client.models.generate_content(...) executed in a thread
         Returns a plain dict (if possible) or None on failure.
        """
        try:
            cfg = types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2048,
                response_mime_type="application/json"
            )

            # Preferred async path
            if getattr(self.client, "aio", None) and getattr(self.client.aio, "models", None):
                logger.debug("[DBRanker] Calling client.aio.models.generate_content (async)")
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=cfg
                )

                # Prefer parsed (pydantic) then fallback to text/dump
                parsed_obj = getattr(response, "parsed", None)
                if parsed_obj is not None:
                    parsed_dict = _to_dict_or_none(parsed_obj)
                    if parsed_dict is not None:
                        return parsed_dict

                text = getattr(response, "text", None)
                if text:
                    try:
                        return json.loads(text)
                    except Exception:
                        return {"text": text}

                try:
                    dump = response.model_dump_json(exclude_none=True)
                    return json.loads(dump)
                except Exception:
                    logger.debug("[DBRanker] Could not parse response.model_dump_json()")

                return None

            # Fallback: sync client.models.generate_content in thread
            elif getattr(self.client, "models", None) and getattr(self.client.models, "generate_content", None):
                logger.debug("[DBRanker] Using sync client.models.generate_content wrapped in thread")

                def sync_call():
                    return self.client.models.generate_content(model=self.model_name, contents=prompt, config=cfg)

                resp = await asyncio.to_thread(sync_call)

                parsed_obj = getattr(resp, "parsed", None)
                if parsed_obj is not None:
                    parsed_dict = _to_dict_or_none(parsed_obj)
                    if parsed_dict is not None:
                        return parsed_dict

                text = getattr(resp, "text", None)
                if text:
                    try:
                        return json.loads(text)
                    except Exception:
                        return {"text": text}

                try:
                    return json.loads(resp.model_dump_json(exclude_none=True))
                except Exception:
                    logger.debug("[DBRanker] Could not parse resp.model_dump_json()")

                return None

            else:
                raise RuntimeError("No supported client.models.generate_content entrypoint found on genai.Client")
        except Exception as e:
            logger.exception("[DBRanker] Gemini call failed: %s", e)
            return None

    async def _insert_ranked_row(self, row: Dict):
        """Insert the ranked row into DB via thread-wrapped supabase call."""
        def insert():
            return self.supabase.table("ranked_candidates_from_resume").insert(row).execute()
        return await self._supabase_execute(insert)

    async def _insert_error_row(self, candidate: Dict, jd: Dict, error_message: str):
        """Inserts a row indicating an error during processing."""
        err_row = {
            "user_id": self.user_id,
            "jd_id": jd.get("jd_id"),
            "resume_id": candidate.get("resume_id"),
            "match_score": 0.00,
            "strengths": f"Evaluation failed: {error_message[:1000]}",
        }
        try:
            await self._insert_ranked_row(err_row)
            logger.info(f"[DBRanker] Inserted error row for resume {candidate.get('resume_id')}")
        except Exception as db_e:
            logger.error(f"[DBRanker] Failed to insert error row for resume {candidate.get('resume_id')}: {db_e}")

    async def process_single(self, candidate: Dict, jd: Dict) -> Optional[Dict]:
        """Process a single candidate: call LLM, parse result, insert ranked row."""
        resume_id = candidate.get("resume_id")
        candidate_text = candidate.get("json_content") or candidate.get("person_name") or ""
        prompt = self._build_prompt(jd, candidate_text)

        for attempt in range(1, self.max_retries + 1):
            logger.debug(f"[DBRanker] Generating content for resume {resume_id}, attempt {attempt}")
            parsed = await self._call_gemini(prompt)
            if parsed is None:
                logger.warning(f"[DBRanker] Gemini returned no parse on attempt {attempt} for resume {resume_id}")
                await asyncio.sleep(1 * attempt)
                continue

            # parsed should be a plain dict (see _call_gemini), but be defensive
            if not isinstance(parsed, dict):
                parsed = _to_dict_or_none(parsed) or {}
            match_score = parsed.get("match_score")
            strengths = parsed.get("strengths")
            weaknesses = parsed.get("weaknesses")
            verdict = parsed.get("verdict")
            reasoning = parsed.get("reasoning", "No specific reasoning provided.")

            if match_score is None:
                logger.warning(f"[DBRanker] No match_score in Gemini response for resume {resume_id}")
                await asyncio.sleep(1 * attempt)
                continue

            # Format strengths/weaknesses and summary
            strengths_text = "\n".join(f"- {s}" for s in strengths) if strengths else "None identified."
            weaknesses_text = "\n".join(f"- {w}" for w in weaknesses) if weaknesses else "None identified."

            formatted_summary = (
                f"**Verdict:** {verdict or 'N/A'}\n\n"
                f"**Strengths:**\n{strengths_text}\n\n"
                f"**Weaknesses/Gaps:**\n{weaknesses_text}\n\n"
                f"**Reasoning:**\n{reasoning}"
            )

            # convert score to float safely
            try:
                score_float = float(match_score)
            except Exception:
                logger.exception("[DBRanker] match_score parse error")
                await asyncio.sleep(1 * attempt)
                continue

            score_rounded = round(score_float, 2)

            row = {
                "user_id": self.user_id,
                "jd_id": jd.get("jd_id"),
                "resume_id": candidate.get("resume_id"),
                "rank": None,
                "match_score": score_rounded,
                "strengths": formatted_summary,
            }

            try:
                await self._insert_ranked_row(row)
                logger.info(f"[DBRanker] Inserted ranked row for resume {resume_id} (score={score_rounded})")
                return {"resume_id": resume_id, "match_score": score_rounded}
            except Exception as e:
                logger.exception(f"[DBRanker] Failed to insert ranked row for resume {resume_id}: {e}")
                await asyncio.sleep(1 * attempt)

        logger.error(f"[DBRanker] Exhausted retries for resume {resume_id}. Inserting error row.")
        await self._insert_error_row(candidate, jd, "Exhausted all retries processing with Gemini.")
        return None

    async def process_batches(self, candidates: List[Dict], jd: Dict) -> List[Dict]:
        results: List[Dict] = []
        for i in range(0, len(candidates), self.batch_size):
            batch = candidates[i:i + self.batch_size]
            tasks = [self.process_single(c, jd) for c in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=False)
            results.extend([r for r in batch_results if r])
            if i + self.batch_size < len(candidates):
                await asyncio.sleep(2)
        return results

    async def run(self, jd_id: str) -> List[Dict]:
        """
        Top-level async runner for ranking resumes for a given JD ID.
        Writes rows into `ranked_candidates_from_resume` table and returns
        the processed results summary (list of dicts).
        """
        logger.info(f"[DBRanker] run start for jd={jd_id}")

        def fetch_jd():
            return self.supabase.table("jds").select("jd_id,jd_parsed_summary").eq("jd_id", jd_id).single().execute()

        jd_resp = await self._supabase_execute(fetch_jd)
        if not getattr(jd_resp, "data", None):
            msg = f"No JD found with id {jd_id}. Aborting ranking."
            logger.error(f"[DBRanker] {msg}")
            raise RuntimeError(msg)

        jd = jd_resp.data
        candidates = await self.get_unranked_resumes(jd_id)
        if not candidates:
            logger.info(f"[DBRanker] No unranked resumes to process for JD {jd_id}.")
            return []

        logger.info(f"[DBRanker] Found {len(candidates)} unranked resumes. Starting ranking...")
        results = await self.process_batches(candidates, jd)
        logger.info(f"[DBRanker] Finished database ranking workflow for JD {jd_id}. Processed {len(results)} resumes.")
        return results
