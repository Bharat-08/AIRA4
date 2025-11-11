# backend/app/services/google_linkedin_sourcer.py
#!/usr/bin/env python3
"""
google_linkedin_sourcer.py — Service-module port of the NEW standalone google_linkedin.py

Exact logic replicated (speed & UX tweaks):
- DEFAULT: one iteration (first N queries, but here iterations=1 for backend).
- Faster config: fewer pages, capped results, early stop, fewer AI calls, lighter sleeps, tighter retries.
- Location terms quoted; query shape: site:linkedin.com/in "ROLE" "LOCATION" (Dom1 OR Dom2 ...)
- Heuristic pre-filter before AI; cap AI parses per query; early-stop after enough accepted profiles.

Integration differences:
- NO CLI, NO prompts — non-interactive.
- Uses app.supabase.supabase_client.
- Caller must pass user_id.

Environment (read if set; otherwise defaults used below):
  GEMINI_API_KEY (required; or settings.GEMINI_API_KEY)
  MODEL_TO_USE (default: gemini-2.5-pro)
"""

from __future__ import annotations

import os
import re
import time
import json
import random
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

# App wiring
from app.supabase import supabase_client
from app.config import settings

# Search
try:
    from duckduckgo_search import ddg
    _ddg_available = True
except Exception:
    _ddg_available = False
    try:
        from ddgs import DDGS
        _ddgs_available = True
    except Exception:
        _ddgs_available = False

# Gemini
from google import genai
from google.genai import errors as genai_errors

# -------------------- CONFIG (mirrors CLI defaults) --------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", settings.GEMINI_API_KEY or "").strip()
if not GEMINI_API_KEY:
    raise SystemExit("❌ GEMINI_API_KEY is required.")

PRIMARY_MODEL = os.getenv("MODEL_TO_USE", "gemini-2.5-pro").strip()
FALLBACK_MODELS: List[str] = [m for m in [PRIMARY_MODEL, "gemini-2.5-flash", "gemini-2.0-pro"] if m]

# Faster defaults from the new CLI
MAX_QUERIES = 6
PAGES_PER_QUERY_DEFAULT = 1
RESULTS_PER_PAGE_DEFAULT = 35
MIN_DELAY = 0.15
MAX_DELAY = 0.35
EARLY_STOP_GOOD_CANDIDATES = 40

MAX_AI_CALLS_PER_QUERY_DEFAULT = 25
MIN_HEURISTIC_SCORE_FOR_AI_DEFAULT = 2  # 0–10

client = genai.Client(api_key=GEMINI_API_KEY)
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}

# -------------------- Helpers shared with CLI --------------------
def _extract_first_json_block(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return m.group(0) if m else text.strip()

def genai_generate_with_retry(contents: List[Any],
                              temperature: float = 0.2,
                              max_retries: int = 1,
                              base_delay: float = 0.5) -> Optional[str]:
    """Faster retry policy (same as new CLI)."""
    for model in FALLBACK_MODELS:
        attempt = 0
        while attempt <= max_retries:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config={"temperature": temperature},
                )
                return getattr(resp, "text", None) or ""
            except genai_errors.APIError as e:
                status = getattr(e, "status_code", None) or getattr(e, "code", None)
                msg = getattr(e, "message", str(e))
                retryable = (status in RETRY_STATUS) or ("temporarily" in msg.lower()) or ("unavailable" in msg.lower())
                attempt += 1
                if retryable and attempt <= max_retries:
                    time.sleep(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.25))
                    continue
                break
            except Exception:
                attempt += 1
                if attempt <= max_retries:
                    time.sleep(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.25))
                    continue
                break
    return None

JD_FACETS_PROMPT = """
You are an expert recruiter. Given a job description record (JSON), extract concise search facets
to find candidates on LinkedIn.

Return ONLY valid JSON:
{
  "role": "string|null",
  "locations": ["string", ...],
  "skills_must": ["string", ...],
  "domains": ["string", ...],
  "extra_title_keywords": ["string", ...]
}

Keep arrays short and practical (3–8 items each). Use nulls/empty arrays if unknown.
"""

def ai_extract_jd_facets(jd_row: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "role": jd_row.get("role"),
        "location": jd_row.get("location"),
        "experience_required": jd_row.get("experience_required"),
        "key_requirements": jd_row.get("key_requirements"),
        "jd_parsed_summary": jd_row.get("jd_parsed_summary"),
        "jd_text": jd_row.get("jd_text"),
        "job_type": jd_row.get("job_type"),
    }
    text = json.dumps(payload, ensure_ascii=False)
    resp_text = genai_generate_with_retry([JD_FACETS_PROMPT, text], temperature=0.1)
    if not resp_text:
        return {"role": None, "locations": [], "skills_must": [], "domains": [], "extra_title_keywords": []}
    raw = _extract_first_json_block(resp_text)
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    def as_list(x):
        if isinstance(x, list):
            return [i for i in x if i]
        return [x] if x else []
    return {
        "role": data.get("role"),
        "locations": as_list(data.get("locations")),
        "skills_must": as_list(data.get("skills_must")),
        "domains": as_list(data.get("domains")),
        "extra_title_keywords": as_list(data.get("extra_title_keywords")),
    }

AI_PARSE_PROMPT = """
You are an expert sourcer. Given a DuckDuckGo result's TITLE, SNIPPET, and URL
for a LinkedIn page, extract clean structured fields.

Return ONLY valid JSON:
{
  "is_candidate": true/false,
  "name": "string|null",
  "position": "string|null",
  "company": "string|null",
  "summary": "string|null"
}

Rules:
- True only if it's likely a person's LinkedIn profile (not company/job page).
- Do not include the word "LinkedIn" in any field.
- If unsure, use nulls. Do not invent details.
"""

def ai_parse_profile(title: str, snippet: str, url: str) -> Dict[str, Any]:
    payload = f"TITLE:\n{title}\n\nSNIPPET:\n{snippet}\n\nURL:\n{url}\n"
    resp_text = genai_generate_with_retry([AI_PARSE_PROMPT, payload], temperature=0.2)
    if not resp_text:
        return {"is_candidate": False, "name": None, "position": None, "company": None, "summary": None}
    raw = _extract_first_json_block(resp_text)
    try:
        data = json.loads(raw)
    except Exception:
        return {"is_candidate": False, "name": None, "position": None, "company": None, "summary": None}
    return {
        "is_candidate": bool(data.get("is_candidate", False)),
        "name": data.get("name"),
        "position": data.get("position"),
        "company": data.get("company"),
        "summary": data.get("summary"),
    }

# -------------------- Supabase helpers --------------------
def sb_get_jd_row(jd_id: str) -> Optional[Dict[str, Any]]:
    try:
        res = supabase_client.table("jds").select(
            "jd_id,user_id,file_url,location,job_type,experience_required,jd_parsed_summary,role,key_requirements,status,jd_text"
        ).eq("jd_id", jd_id).limit(1).execute()
        rows = getattr(res, "data", None) or []
        return rows[0] if rows else None
    except Exception:
        return None

def sb_linkedin_exists(profile_link: str) -> bool:
    if not profile_link:
        return False
    try:
        res = supabase_client.table("linkedin").select("linkedin_profile_id").eq("profile_link", profile_link).limit(1).execute()
        rows = getattr(res, "data", None) or []
        return bool(rows)
    except Exception:
        return False

def sb_insert_linkedin(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        res = supabase_client.table("linkedin").insert(payload).execute()
        rows = getattr(res, "data", None) or []
        return rows[0] if rows else None
    except Exception:
        return None

# -------------------- URL helpers (fixed regex quoting) --------------------
def normalize_link(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        # Use single-quoted raw string; escape single quotes inside the class
        m = re.search(r'https?://[^\s\'"]*linkedin\.com/[^\s\'"]+', url)
        if m:
            return m.group(0).split("?")[0].rstrip("/")
        p = urlparse(url)
        if "linkedin.com" in p.netloc:
            return f"https://{p.netloc}{p.path.rstrip('/')}"
    except Exception:
        return None

def extract_linkedin_from_result_item(item: Dict[str, Any]) -> Optional[str]:
    url = item.get("href") or item.get("url") or item.get("link") or ""
    if not url:
        body = item.get("body") or item.get("snippet") or ""
        # Same fixed quoting here
        m = re.search(r'https?://[^\s\'"]*linkedin\.com/[^\s\'"]+', body or "")
        if m:
            url = m.group(0)
    return normalize_link(url)

def likely_profile_url(url: Optional[str]) -> bool:
    if not url:
        return False
    low = url.lower()
    bad = ["/pulse/", "/posts/", "/jobs/", "/company/", "/school/", "/groups/", "/events/"]
    if any(b in low for b in bad):
        return False
    return "/in/" in low or "/pub/" in low or re.search(r"/profile/view", low) is not None

# -------------------- Query & scoring (with quoted location) --------------------
def _q(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s
    return f'"{s}"'

def build_queries_from_facets(fx: dict, max_q: int = MAX_QUERIES) -> List[str]:
    role_raw = (fx.get("role") or "").strip()
    role = _q(role_raw) if role_raw else ""

    locs = fx.get("locations", [])
    skills = fx.get("skills_must", [])
    domains = fx.get("domains", [])
    extras = fx.get("extra_title_keywords", [])

    buckets = []
    if domains: buckets.append(" OR ".join(domains[:3]))
    if skills:  buckets.append(" OR ".join(skills[:3]))
    if extras:  buckets.append(" OR ".join(extras[:3]))

    loc_list = locs[:2] if locs else [""]
    focus = [b for b in buckets if b][:2] or [""]

    queries: List[str] = []
    for loc in loc_list:
        loc_q = _q(loc) if loc else ""
        for f in focus:
            core_parts = [role, loc_q]
            core = " ".join([p for p in core_parts if p]).strip()
            q = f'site:linkedin.com/in {core} ({f})' if f else f'site:linkedin.com/in {core}'
            q = re.sub(r"\s+", " ", q).strip()
            if q and q not in queries:
                queries.append(q)
            if len(queries) >= max_q:
                break
        if len(queries) >= max_q:
            break

    if len(queries) < max_q:
        base = f'site:linkedin.com/in {role}'.strip()
        if locs:
            for loc in loc_list:
                loc_q = _q(loc)
                q = f"{base} {loc_q}".strip()
                q = re.sub(r"\s+", " ", q)
                if q not in queries:
                    queries.append(q)
                if len(queries) >= max_q:
                    break
        if len(queries) < max_q and base not in queries:
            queries.append(base)

    return queries[:max_q]

def jd_match_score_from_text(skills, domains, title, snippet):
    text = (title or "") + " " + (snippet or "")
    text = text.lower()
    score = 0
    for s in (skills or []):
        if s and s.lower() in text:
            score += 4
    for d in (domains or []):
        if d and d.lower() in text:
            score += 2
    # Title/keyword bonus (as in new CLI)
    if any(k in text for k in ["head of inventory", "inventory head", "inventory manager", "supply chain", "warehouse"]):
        score += 2
    return min(10, score)

# -------------------- PUBLIC: run_once (non-interactive) --------------------
def run_once(
    jd_id: str,
    user_id: str,
    *,
    pages_per_query: int = PAGES_PER_QUERY_DEFAULT,
    results_per_page: int = RESULTS_PER_PAGE_DEFAULT,
    max_ai_calls_per_query: int = MAX_AI_CALLS_PER_QUERY_DEFAULT,
    min_heuristic_score_for_ai: int = MIN_HEURISTIC_SCORE_FOR_AI_DEFAULT,
    early_stop_good_candidates: int = EARLY_STOP_GOOD_CANDIDATES,
    iterations: int = 1,  # keep 1 to mirror default CLI behavior
) -> Dict[str, Any]:
    """
    Non-interactive run with the same fast logic as the new CLI.
    - iterations: how many queries to run (default 1)
    """
    jd_row = sb_get_jd_row(jd_id)
    if not jd_row:
        return {"status": "failed", "error": f"JD not found for jd_id={jd_id}"}

    facets = ai_extract_jd_facets(jd_row)
    queries = build_queries_from_facets(facets, max_q=MAX_QUERIES)
    if not queries:
        return {"status": "completed", "attempted": 0, "inserted_count": 0, "queries": [], "sample": []}

    iterations_to_run = max(1, min(iterations, len(queries)))

    collected: Dict[str, Dict[str, Any]] = {}
    ran_queries: List[str] = []

    try:
        for qidx in range(iterations_to_run):
            q = queries[qidx]
            ran_queries.append(q)

            total = max(1, pages_per_query) * max(10, results_per_page)
            results = []
            if _ddg_available:
                try:
                    results = ddg(q, region="wt-wt", safesearch="Off", time=None, max_results=total)
                except Exception:
                    results = []
            elif '_ddgs_available' in globals() and globals()['_ddgs_available']:
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(q, safesearch="Off", timelimit=None, max_results=total))
                except Exception:
                    results = []
            else:
                return {"status": "failed", "error": "No DuckDuckGo client available"}

            ai_calls = 0
            for item in results or []:
                if len(collected) >= early_stop_good_candidates:
                    break

                title = item.get("title") or ""
                snippet = item.get("body") or item.get("snippet") or ""
                linkedin = extract_linkedin_from_result_item(item)
                if not linkedin or "linkedin.com" not in linkedin:
                    continue
                if not likely_profile_url(linkedin):
                    continue

                canonical = linkedin.split("?")[0]
                if canonical in collected:
                    continue

                # Heuristic pre-filter
                score = jd_match_score_from_text(facets.get("skills_must", []), facets.get("domains", []), title, snippet)
                if score < min_heuristic_score_for_ai and not any(
                    k in (title + " " + snippet).lower() for k in
                    ["inventory", "supply", "warehouse", "fmcg", "retail", "e-commerce", "ecommerce"]
                ):
                    continue

                if ai_calls >= max_ai_calls_per_query:
                    # record minimal info when AI cap reached
                    collected[canonical] = {
                        "url": canonical,
                        "title": title,
                        "snippet": snippet,
                        "score": score,
                        "reason": "heuristic-cap",
                        "source_query": q,
                        "ai_name": None,
                        "ai_position": None,
                        "ai_company": None,
                        "ai_summary": None,
                    }
                    continue

                parsed = ai_parse_profile(title, snippet, canonical)
                ai_calls += 1

                if parsed.get("is_candidate", False):
                    collected[canonical] = {
                        "url": canonical,
                        "title": title,
                        "snippet": snippet,
                        "score": score,
                        "reason": "ai-parse",
                        "source_query": q,
                        "ai_name": parsed.get("name"),
                        "ai_position": parsed.get("position"),
                        "ai_company": parsed.get("company"),
                        "ai_summary": parsed.get("summary"),
                    }

                time.sleep(0.05)  # lighter throttle

            # polite pause between queries (even if iterations==1)
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

            if len(collected) >= early_stop_good_candidates:
                break

    except KeyboardInterrupt:
        pass

    # Insert into DB (skip duplicates)
    attempted = len(collected)
    inserted_rows: List[Dict[str, Any]] = []
    for c in sorted(collected.values(), key=lambda x: x["score"], reverse=True):
        url = c.get("url")
        if not url:
            continue
        if sb_linkedin_exists(url):
            continue
        payload = {
            "jd_id": jd_id,
            "user_id": user_id,
            "name": c.get("ai_name"),
            "profile_link": url,
            "position": c.get("ai_position"),
            "company": c.get("ai_company"),
            "summary": c.get("ai_summary") or "",
        }
        row = sb_insert_linkedin(payload)
        if row:
            inserted_rows.append(row)

    sample = [
        {
            "name": i.get("name"),
            "profile_link": i.get("profile_link"),
            "position": i.get("position"),
            "company": i.get("company"),
        } for i in inserted_rows[:10]
    ]

    return {
        "status": "completed",
        "attempted": attempted,
        "inserted_count": len(inserted_rows),
        "queries": ran_queries,
        "sample": sample,
    }

# Back-compat entry used by Celery task
from typing import Optional as _Optional
def run_sourcing(jd_id: str, user_id: str, custom_prompt: _Optional[str] = "") -> Dict[str, Any]:
    # Non-interactive single-iteration run with the new fast logic.
    return run_once(
        jd_id,
        user_id,
        pages_per_query=PAGES_PER_QUERY_DEFAULT,
        results_per_page=RESULTS_PER_PAGE_DEFAULT,
        max_ai_calls_per_query=MAX_AI_CALLS_PER_QUERY_DEFAULT,
        min_heuristic_score_for_ai=MIN_HEURISTIC_SCORE_FOR_AI_DEFAULT,
        early_stop_good_candidates=EARLY_STOP_GOOD_CANDIDATES,
        iterations=1,
    )

__all__ = ["run_once", "run_sourcing"]
