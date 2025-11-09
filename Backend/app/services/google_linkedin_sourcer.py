# backend/app/services/google_linkedin_sourcer.py
#!/usr/bin/env python3
"""
google_linkedin_sourcer.py — Non-interactive port of google_linkedin.py

Behavior parity with the original CLI:
- Fetch JD by jd_id from public.jds
- Use Gemini to extract search facets (AI-only)
- Build queries the same way
- Search DuckDuckGo (duckduckgo_search.ddg, fallback to ddgs.DDGS)
- For each result: normalize LinkedIn URL, filter to likely profiles, AI-parse (name/position/company/summary)
- Score with jd_match_score_from_text (signal only)
- Insert into public.linkedin (skip duplicates by profile_link)

Differences (on purpose for backend use):
- NO interactive prompts; runs EXACTLY ONE query (first query only), simulating user answering "no" thereafter
- Does NOT read SUPABASE_USER_ID from .env — user_id must be passed to run_once/run_sourcing
- Uses the app’s shared Supabase client (app.supabase.supabase_client)
"""

from __future__ import annotations

import os
import re
import time
import json
import random
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

# --- App wiring (shared Supabase client & settings) ---
from app.supabase import supabase_client
from app.config import settings

# --- DuckDuckGo search ---
try:
    from duckduckgo_search import ddg  # pip install duckduckgo_search
    _ddg_available = True
except Exception:
    _ddg_available = False
    try:
        from ddgs import DDGS  # pip install ddgs
        _ddgs_available = True
    except Exception:
        _ddgs_available = False

# --- Gemini (AI) ---
from google import genai  # pip install google-genai
from google.genai import errors as genai_errors

# -------------------- CONFIG --------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", getattr(settings, "GEMINI_API_KEY", "") or "").strip()
if not GEMINI_API_KEY:
    raise SystemExit("❌ GEMINI_API_KEY is required.")

PRIMARY_MODEL = os.getenv("MODEL_TO_USE", "gemini-2.5-pro").strip()
FALLBACK_MODELS: List[str] = [m for m in [
    PRIMARY_MODEL,
    "gemini-2.0-flash",
    "gemini-1.5-pro",
] if m]

PAGES_PER_QUERY = int(os.getenv("PAGES_PER_QUERY", 2))
RESULTS_PER_PAGE = int(os.getenv("RESULTS_PER_PAGE", 50))
MIN_DELAY = 0.8
MAX_DELAY = 1.6

client = genai.Client(api_key=GEMINI_API_KEY)
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}

# -------------------- Helpers (same as CLI) --------------------
def _extract_first_json_block(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return m.group(0) if m else text.strip()

def genai_generate_with_retry(contents: List[Any], temperature: float = 0.2,
                              max_retries: int = 6, base_delay: float = 1.0) -> Optional[str]:
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
                    sleep_s = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    time.sleep(sleep_s)
                    continue
                break
            except Exception:
                attempt += 1
                if attempt <= max_retries:
                    sleep_s = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    time.sleep(sleep_s)
                    continue
                break
    return None

# --- AI: Extract JD facets (same prompt as CLI) ---
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

# --- AI: Parse a LinkedIn result (same prompt as CLI) ---
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

# --- Supabase helpers (shared client) ---
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

# --- URL helpers (same as CLI) ---
def normalize_link(url):
    if not url:
        return None
    try:
        # FIX: escape quotes in regex character classes
        m = re.search(r'https?://[^\s\'"]*linkedin\.com/[^\s\'"]+', url)
        if m:
            return m.group(0).split("?")[0].rstrip("/")
        p = urlparse(url)
        if "linkedin.com" in p.netloc:
            return f"https://{p.netloc}{p.path.rstrip('/')}"
    except Exception:
        return None

def extract_linkedin_from_result_item(item):
    url = item.get("href") or item.get("url") or item.get("link") or ""
    if not url:
        body = item.get("body") or item.get("snippet") or ""
        # FIX: escape quotes in regex character classes
        m = re.search(r'https?://[^\s\'"]*linkedin\.com/[^\s\'"]+', body or "")
        if m:
            url = m.group(0)
    return normalize_link(url)

def likely_profile_url(url):
    if not url:
        return False
    low = url.lower()
    bad = ["/pulse/", "/posts/", "/jobs/", "/company/", "/school/", "/groups/", "/events/"]
    if any(b in low for b in bad):
        return False
    return "/in/" in low or "/pub/" in low or re.search(r"/profile/view", low) is not None

# --- Query generation & scoring (same) ---
MAX_QUERIES = 6

def build_queries_from_facets(fx: dict, max_q=MAX_QUERIES):
    role = (fx.get("role") or "").strip()
    locs = fx.get("locations", [])
    skills = fx.get("skills_must", [])
    domains = fx.get("domains", [])
    extras = fx.get("extra_title_keywords", [])

    buckets = []
    if domains: buckets.append(" OR ".join(domains[:3]))
    if skills:  buckets.append(" OR ".join(skills[:4]))
    if extras:  buckets.append(" OR ".join(extras[:3]))

    loc_list = locs[:2] if locs else [""]
    focus = [b for b in buckets if b][:2] or [""]

    queries = []
    for loc in loc_list:
        for f in focus:
            core = f' "{role}" {loc}'.strip()
            q = f'site:linkedin.com/in {core} ({f})' if f else f'site:linkedin.com/in {core}'
            q = re.sub(r"\s+", " ", q).strip()
            if q and q not in queries:
                queries.append(q)
            if len(queries) >= max_q:
                break
        if len(queries) >= max_q:
            break

    if len(queries) < max_q:
        base = f'site:linkedin.com/in "{role}"'
        if locs:
            for loc in loc_list:
                q = f"{base} {loc}".strip()
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
    return min(10, score)

# -------------------- PUBLIC: run ONCE (first query only) --------------------
def run_once(jd_id: str, user_id: str) -> Dict[str, Any]:
    """
    Perform ONE iteration of the original sourcing loop (first built query).
    Inserts all parsed candidates into public.linkedin (skips duplicates).
    Returns a compact summary dict.
    """
    jd_row = sb_get_jd_row(jd_id)
    if not jd_row:
        return {"status": "failed", "error": f"JD not found for jd_id={jd_id}"}

    facets = ai_extract_jd_facets(jd_row)
    queries = build_queries_from_facets(facets, max_q=MAX_QUERIES)
    if not queries:
        return {"status": "completed", "attempted": 0, "inserted_count": 0, "queries": [], "sample": []}

    # FIRST query only (simulate user answering "no" for the rest)
    q = queries[0]
    total_to_fetch = PAGES_PER_QUERY * RESULTS_PER_PAGE

    results = []
    if _ddg_available:
        try:
            results = ddg(q, region="wt-wt", safesearch="Off", time=None, max_results=total_to_fetch)
        except Exception:
            results = []
    elif '_ddgs_available' in globals() and globals()['_ddgs_available']:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(q, safesearch="Off", timelimit=None, max_results=total_to_fetch))
        except Exception:
            results = []
    else:
        return {"status": "failed", "error": "No DuckDuckGo client available"}

    collected: Dict[str, Dict[str, Any]] = {}
    if results:
        for item in results:
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

            parsed = ai_parse_profile(title, snippet, canonical)
            if parsed.get("is_candidate", False):
                score = jd_match_score_from_text(
                    facets.get("skills_must", []),
                    facets.get("domains", []),
                    title,
                    snippet
                )
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
            # small per-result delay to mimic original pacing
            time.sleep(0.25)

    # polite delay for the (single) query
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    # Insert into DB (skip duplicates)
    attempted = len(collected)
    inserted: List[Dict[str, Any]] = []
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
            inserted.append(row)

    sample = [
        {
            "name": i.get("name"),
            "profile_link": i.get("profile_link"),
            "position": i.get("position"),
            "company": i.get("company"),
        } for i in inserted[:10]
    ]

    return {
        "status": "completed",
        "attempted": attempted,
        "inserted_count": len(inserted),
        "queries": [q],
        "sample": sample,
    }

# Optional: local debug runner
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m app.services.google_linkedin_sourcer <jd_id> <user_id>")
        raise SystemExit(1)
    jd_id_arg, user_id_arg = sys.argv[1], sys.argv[2]
    out = run_once(jd_id_arg, user_id_arg)
    print(json.dumps(out, ensure_ascii=False, indent=2))

# Back-compat for Celery worker imports
from typing import Optional as _Optional
def run_sourcing(jd_id: str, user_id: str, custom_prompt: _Optional[str] = ""):
    """
    Celery entrypoint. Non-interactive single-iteration run.
    """
    return run_once(jd_id, user_id)

__all__ = ["run_once", "run_sourcing"]
