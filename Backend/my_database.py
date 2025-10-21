#!/usr/bin/env python3
"""
my_database.py

Resume-only ranking script (CLI).
Usage:
    python my_database.py <jd_id> <user_id>

Notes:
- This script will use SUPABASE_SERVICE_ROLE_KEY (preferred) or SUPABASE_KEY (fallback)
  to communicate with Supabase/PostgREST.
- The user_id passed on the command line will be used as the 'user_id' when inserting rows
  into ranked_candidates_from_resume (so the script no longer depends on SUPABASE_USER_ID env var).
- Ensure SUPABASE_URL and a valid service key are present in environment when running.
"""

import os
import sys
import json
import asyncio
import logging
import re
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from supabase import create_client
import requests

# Load .env
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MY_DATABASE_SCRIPT")

@dataclass
class Config:
    supabase_url: str
    supabase_key: Optional[str]
    supabase_service_role_key: Optional[str]
    batch_size: int = 3
    max_retries: int = 3

    @classmethod
    def from_env(cls):
        return cls(
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_key=os.getenv("SUPABASE_KEY"),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            batch_size=int(os.getenv("BATCH_SIZE", 3)),
            max_retries=int(os.getenv("MAX_RETRIES", 3))
        )

def mask_key(k: Optional[str]) -> str:
    if not k:
        return "<NONE>"
    k = k.strip()
    if len(k) <= 12:
        return k[:3] + "..." + k[-3:]
    return k[:6] + "..." + k[-6:]

class ProfileRanker:
    def __init__(self, cfg: Config, insert_user_id: str):
        self.cfg = cfg
        self.insert_user_id = insert_user_id

        # Choose service key if available (bypasses RLS)
        key_for_client = cfg.supabase_service_role_key or cfg.supabase_key
        if cfg.supabase_service_role_key:
            logger.info("Using SUPABASE_SERVICE_ROLE_KEY for DB access (bypasses RLS).")
        else:
            logger.warning("SUPABASE_SERVICE_ROLE_KEY not set — using SUPABASE_KEY (may be anon and subject to RLS).")

        if not key_for_client:
            raise RuntimeError("No SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY found in environment.")

        self.supabase = create_client(cfg.supabase_url, key_for_client)
        self.rest_url = cfg.supabase_url.rstrip("/") + "/rest/v1"
        self.rest_service_key = cfg.supabase_service_role_key or cfg.supabase_key

        logger.info("Supabase URL: %s", cfg.supabase_url)
        logger.info("Supabase client key (masked): %s", mask_key(key_for_client))
        logger.info("Inserting rows with user_id: %s", self.insert_user_id)

    def _log_response_debug(self, tag: str, resp_obj: Any):
        try:
            data = getattr(resp_obj, "data", None)
            error = getattr(resp_obj, "error", None)
            if error:
                logger.warning("[%s] response.error: %s", tag, error)
            else:
                if isinstance(data, list):
                    logger.info("[%s] %d rows (sample ids): %s", tag, len(data), [row.get("resume_id") for row in data[:5]])
                else:
                    logger.info("[%s] data: %s", tag, str(data)[:200])
        except Exception as e:
            logger.exception("Failed to log response debug for %s: %s", tag, e)

    def rest_fallback_check(self, jd_id: str) -> None:
        if not self.rest_service_key:
            logger.warning("No REST key for fallback check.")
            return
        url = f"{self.rest_url}/resume?select=resume_id,jd_id,person_name,role,company,profile_url&jd_id=eq.{jd_id}"
        headers = {
            "apikey": self.rest_service_key,
            "Authorization": f"Bearer {self.rest_service_key}",
            "Accept": "application/json"
        }
        try:
            logger.info("REST fallback check URL: %s", url)
            r = requests.get(url, headers=headers, timeout=10)
            logger.info("REST fallback status: %s", r.status_code)
            try:
                payload = r.json()
                if isinstance(payload, list):
                    logger.info("REST fallback returned %d rows (sample ids): %s", len(payload), [row.get("resume_id") for row in payload[:5]])
                else:
                    logger.info("REST fallback returned non-list JSON: %s", json.dumps(payload)[:400])
            except Exception:
                logger.warning("REST fallback non-JSON response (first 1000 chars): %s", r.text[:1000])
        except Exception as e:
            logger.exception("REST fallback check failed: %s", e)

    def get_unranked_resumes(self, jd_id: str) -> List[Dict[str, Any]]:
        try:
            jd_id = str(jd_id).strip()
            logger.info("Querying resume table for jd_id=%s ...", jd_id)

            resumes_resp = self.supabase.table("resume").select(
                "resume_id,jd_id,user_id,json_content,person_name,role,company,profile_url,created_at"
            ).eq("jd_id", jd_id).execute()

            self._log_response_debug("resume_query", resumes_resp)
            resumes = resumes_resp.data if getattr(resumes_resp, "data", None) else []

            if not resumes:
                logger.warning("No resumes found via supabase client for jd_id=%s. Running REST fallback check.", jd_id)
                self.rest_fallback_check(jd_id)

            ranked_resp = self.supabase.table("ranked_candidates_from_resume").select("resume_id").eq("jd_id", jd_id).execute()
            self._log_response_debug("ranked_query", ranked_resp)
            ranked_ids = {r.get("resume_id") for r in (ranked_resp.data or [])}

            candidates = []
            for r in resumes:
                rid = r.get("resume_id")
                if rid and rid not in ranked_ids:
                    candidates.append({
                        "jd_id": r.get("jd_id"),
                        "resume_id": rid,
                        "user_id": r.get("user_id"),
                        "person_name": r.get("person_name"),
                        "role": r.get("role"),
                        "company": r.get("company"),
                        "summary": r.get("json_content"),
                        "profile_url": r.get("profile_url"),
                        "created_at": r.get("created_at"),
                        "source": "resume"
                    })

            logger.info("Found %d unranked resumes for JD %s (after filtering %d ranked).", len(candidates), jd_id, len(ranked_ids))
            return candidates
        except Exception as e:
            logger.exception("Exception while fetching resumes: %s", e)
            return []

    def insert_or_update_ranked_row(self, row: Dict[str, Any]) -> None:
        try:
            resume_id = row.get("resume_id")
            if not resume_id:
                logger.warning("insert_or_update called without resume_id")
                return
            existing = self.supabase.table("ranked_candidates_from_resume").select("rank_id").eq("resume_id", resume_id).eq("jd_id", row.get("jd_id")).execute()
            if existing.data and len(existing.data) > 0:
                rank_id = existing.data[0].get("rank_id")
                update_payload = row.copy()
                update_payload.pop("user_id", None)
                self.supabase.table("ranked_candidates_from_resume").update(update_payload).eq("rank_id", rank_id).execute()
                logger.info("Updated ranked row for %s", resume_id)
            else:
                self.supabase.table("ranked_candidates_from_resume").insert(row).execute()
                logger.info("Inserted ranked row for %s", resume_id)
        except Exception as e:
            logger.exception("Failed to insert_or_update_ranked_row for %s: %s", row.get("resume_id"), e)
            raise

    def _stub_score(self, resume_id: str) -> float:
        h = 0
        for ch in str(resume_id):
            h = (h * 131 + ord(ch)) % 1000
        return round((h % 101), 2)

    async def rank_candidate_stub(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            score = self._stub_score(candidate["resume_id"])
            formatted = f"STUB evaluation, score {score}"
            row = {
                "user_id": self.insert_user_id,
                "jd_id": candidate["jd_id"],
                "resume_id": candidate["resume_id"],
                "rank": None,
                "match_score": float(score),
                "strengths": formatted
            }
            self.insert_or_update_ranked_row(row)
            return {"resume_id": candidate["resume_id"], "match_score": score}
        except Exception as e:
            logger.exception("Failed ranking candidate %s: %s", candidate.get("resume_id"), e)
            # insert error row (attempt), but use provided insert_user_id
            try:
                err_row = {
                    "user_id": self.insert_user_id,
                    "jd_id": candidate["jd_id"],
                    "resume_id": candidate["resume_id"],
                    "rank": None,
                    "match_score": 0.00,
                    "strengths": f"Evaluation failed: {str(e)[:1000]}"
                }
                self.insert_or_update_ranked_row(err_row)
            except Exception as ie:
                logger.exception("Failed to insert error row for %s: %s", candidate.get("resume_id"), ie)
            return None

    async def process_batches(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for i in range(0, len(candidates), self.cfg.batch_size):
            batch = candidates[i:i + self.cfg.batch_size]
            logger.info("Processing batch %d (%d resumes)", (i // self.cfg.batch_size) + 1, len(batch))
            tasks = [self.rank_candidate_stub(c) for c in batch]
            batch_results = await asyncio.gather(*tasks)
            for r in batch_results:
                if r:
                    results.append(r)
            if i + self.cfg.batch_size < len(candidates):
                await asyncio.sleep(1)
        return results

    async def run(self, jd_id: str):
        logger.info("Starting ranking for JD %s", jd_id)
        candidates = self.get_unranked_resumes(jd_id)
        if not candidates:
            logger.info("No unranked resumes to process.")
            return
        results = await self.process_batches(candidates)
        logger.info("Processed %d / %d resumes.", len(results), len(candidates))


def parse_args():
    parser = argparse.ArgumentParser(description="Rank resumes for a JD")
    parser.add_argument("jd_id", type=str, help="Job Description UUID to process")
    parser.add_argument("user_id", type=str, help="User UUID to use when inserting ranked rows")
    return parser.parse_args()


async def main():
    args = parse_args()
    cfg = Config.from_env()
    if not cfg.supabase_url:
        logger.error("SUPABASE_URL not set in environment.")
        sys.exit(2)
    if not (cfg.supabase_service_role_key or cfg.supabase_key):
        logger.error("No SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY found in environment.")
        sys.exit(2)

    ranker = ProfileRanker(cfg, insert_user_id=args.user_id)
    await ranker.run(args.jd_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception("Fatal error in my_database.py: %s", e)
        sys.exit(1)
