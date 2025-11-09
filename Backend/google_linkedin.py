#!/usr/bin/env python3
"""
google_linkedin.py — LinkedIn Candidate Sourcer (DuckDuckGo + Gemini, AI-only parsing)

This version:
- Fetches JD by jd_id from public.jds.
- Uses Gemini to extract search facets AND to parse LinkedIn search results (name/position/company/summary).
- Adds robust retry/backoff for Gemini 429/5xx (incl. 503 UNAVAILABLE) and model fallback (Gemini only).
- No regex/hand parsing for profile fields (AI-only); URL normalization + query templating remain minimal.

Env:
  GEMINI_API_KEY (required)
  MODEL_TO_USE (optional; default: gemini-2.5-pro)
  SUPABASE_URL, SUPABASE_KEY, SUPABASE_USER_ID
  OUTPUT_CSV (optional)
"""

import os
import time
import csv
import re
import random
import json
from urllib.parse import urlparse
from dotenv import load_dotenv
import requests
from typing import List, Dict, Any, Optional

load_dotenv()

# -------------------- CONFIG --------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if not GEMINI_API_KEY:
    raise SystemExit("❌ GEMINI_API_KEY is required. This script uses AI-only parsing and will not run without it.")

PRIMARY_MODEL = os.getenv("MODEL_TO_USE", "gemini-2.5-pro").strip()
FALLBACK_MODELS: List[str] = [m for m in [
    PRIMARY_MODEL,
    "gemini-2.0-flash",
    "gemini-1.5-pro",
] if m]

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_USER_ID = os.getenv("SUPABASE_USER_ID", "")
OUTPUT_CSV = os.getenv("OUTPUT_CSV", "filtered_candidates.csv")

# Search tuning
MAX_QUERIES = 6
PAGES_PER_QUERY = int(os.getenv("PAGES_PER_QUERY", 2))
RESULTS_PER_PAGE = int(os.getenv("RESULTS_PER_PAGE", 50))
MIN_DELAY = 0.8
MAX_DELAY = 1.6

# -------------------- SEARCH LIBS --------------------
try:
    from duckduckgo_search import ddg  # pip install duckduckgo_search
    ddg_available = True
except Exception:
    ddg_available = False

if not ddg_available:
    try:
        from ddgs import DDGS  # pip install ddgs
        ddg_obj_available = True
    except Exception:
        ddg_obj_available = False
else:
    ddg_obj_available = False

# -------------------- GEMINI --------------------
from google import genai  # pip install google-genai
from google.genai import errors as genai_errors

client = genai.Client(api_key=GEMINI_API_KEY)

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}

def _extract_first_json_block(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return m.group(0) if m else text.strip()

def genai_generate_with_retry(contents: List[Any], temperature: float = 0.2,
                              max_retries: int = 6, base_delay: float = 1.0) -> Optional[str]:
    """
    Call Gemini with retries + fallback models. Returns .text (str) or None on failure.
    Retries on 429/5xx and network-ish errors with exponential backoff + jitter.
    """
    attempt = 0
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
                    print(f"⚠️ Gemini {model} error ({status}): {msg}. Retry {attempt}/{max_retries} in {sleep_s:.1f}s ...")
                    time.sleep(sleep_s)
                    continue
                else:
                    print(f"❌ Gemini {model} failed (non-retryable or retries exhausted): {msg}")
                    break
            except Exception as e:
                attempt += 1
                if attempt <= max_retries:
                    sleep_s = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    print(f"⚠️ Gemini {model} exception: {e}. Retry {attempt}/{max_retries} in {sleep_s:.1f}s ...")
                    time.sleep(sleep_s)
                    continue
                print(f"❌ Gemini {model} exception (retries exhausted): {e}")
                break
        print(f"➡️ Trying fallback model… (was {model})")
    return None

# --- AI: Extract JD facets for search (AI-only; no manual parsing) ---
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
        print("❌ Could not extract JD facets from AI.")
        return {"role": None, "locations": [], "skills_must": [], "domains": [], "extra_title_keywords": []}
    raw = _extract_first_json_block(resp_text)
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    # normalize
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

# --- AI: Parse LinkedIn search result (AI-only; no manual parsing rules) ---
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

# -------------------- SUPABASE --------------------
use_supabase_client = False
supabase_client = None
try:
    from supabase import create_client  # pip install supabase
    if SUPABASE_URL and SUPABASE_KEY:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        use_supabase_client = True
except Exception:
    use_supabase_client = False

def supabase_get(table, filters=None, select="*"):
    if use_supabase_client:
        try:
            q = supabase_client.table(table).select(select)
            if filters:
                for k, v in filters.items():
                    q = q.eq(k, v)
            res = q.execute()
            return res.data or []
        except Exception as e:
            print("supabase client GET error:", e)
            return []
    else:
        try:
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            url = f"{SUPABASE_URL}/rest/v1/{table}"
            params = {"select": select}
            if filters:
                for k, v in filters.items():
                    params[k] = f"eq.{v}"
            resp = requests.get(url, headers=headers, params=params)
            if resp.ok:
                return resp.json()
            else:
                print("supabase REST GET failed:", resp.status_code, resp.text)
                return []
        except Exception as e:
            print("supabase REST GET error:", e)
            return []

def supabase_insert(table, payload):
    if use_supabase_client:
        try:
            res = supabase_client.table(table).insert(payload).execute()
            return res.data
        except Exception as e:
            print("supabase client INSERT error:", e)
            return None
    else:
        try:
            headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }
            url = f"{SUPABASE_URL}/rest/v1/{table}"
            resp = requests.post(url, headers=headers, data=json.dumps(payload))
            if resp.ok:
                return resp.json()
            else:
                print("supabase REST INSERT failed:", resp.status_code, resp.text)
                return None
        except Exception as e:
            print("supabase REST INSERT error:", e)
            return None

def get_jd_row(jd_id: str):
    rows = supabase_get(
        "jds",
        filters={"jd_id": jd_id},
        select="jd_id,user_id,file_url,location,job_type,experience_required,jd_parsed_summary,role,key_requirements,status,jd_text"
    )
    return rows[0] if rows else None

def linkedin_exists(profile_link):
    if not profile_link:
        return False
    rows = supabase_get("linkedin", filters={"profile_link": profile_link}, select="linkedin_profile_id")
    return bool(rows)

# -------------------- URL HELPERS --------------------
def normalize_link(url):
    if not url:
        return None
    try:
        m = re.search(r"https?://[^\s'\"]*linkedin\.com/[^\s'\"]+", url)
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
        m = re.search(r"https?://[^\s'\"]*linkedin\.com/[^\s'\"]+", body or "")
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
    return "/in/" in low or "/pub/" in low or re.search(r"/profile/view", low)

# -------------------- QUERY GENERATION --------------------
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

# -------------------- RANKING (signal only) --------------------
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

def pretty_print_result(idx, title, snippet, url):
    print(f"\n{idx}. {title}")
    short_snip = (snippet[:220] + "...") if snippet and len(snippet) > 220 else snippet
    print(f"   {short_snip}\n   {url}")
    print("-" * 100)

def ask_user_continue():
    while True:
        ans = input("Do you want to continue to the next query? (y/n): ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer y/n.")

# -------------------- SAVE --------------------
def save_linkedin_rows(jd_id, user_id, candidates):
    inserted = []
    for c in candidates:
        profile_link = c.get("url")
        if not profile_link:
            continue
        if linkedin_exists(profile_link):
            print("Skipping existing profile:", profile_link)
            continue

        payload = {
            "jd_id": jd_id,
            "user_id": user_id,
            "name": c.get("ai_name"),
            "profile_link": profile_link,
            "position": c.get("ai_position"),
            "company": c.get("ai_company"),
            "summary": c.get("ai_summary") or "",
        }
        res = supabase_insert("linkedin", payload)
        if res:
            inserted.append(res)
            print("Inserted:", profile_link, "|", payload["name"], "|", payload["position"], "|", payload["company"])
        else:
            print("Failed to insert:", profile_link)
    return inserted

# -------------------- MAIN --------------------
def run():
    jd_id = input("Enter jd_id (uuid) to attach results to: ").strip()
    if not jd_id:
        print("No jd_id provided. Exiting.")
        return

    print("Fetching JD from 'public.jds'...")
    jd_row = get_jd_row(jd_id)
    if not jd_row:
        print("JD not found in 'jds'. Please confirm jd_id and try again.")
        return

    print("Asking AI to extract JD facets (role, locations, skills, domains, keywords)...")
    facets = ai_extract_jd_facets(jd_row)
    print("Facets:", json.dumps(facets, ensure_ascii=False))

    queries = build_queries_from_facets(facets, max_q=MAX_QUERIES)
    print(f"[+] Built {len(queries)} queries from AI facets.")
    for i, q in enumerate(queries, 1):
        print(f"  {i}. {q}")

    user_id = SUPABASE_USER_ID or input("SUPABASE_USER_ID not set in .env — enter your user_id: ").strip()
    if not user_id:
        print("No user id. Exiting.")
        return

    print(f"[+] ddg_available={ddg_available} | ddgs_available={ddg_obj_available}")

    collected: Dict[str, Dict[str, Any]] = {}

    try:
        for qidx, q in enumerate(queries, start=1):
            print(f"\n[Query {qidx}/{len(queries)}] {q}")
            total = PAGES_PER_QUERY * RESULTS_PER_PAGE

            results = []
            if ddg_available:
                try:
                    results = ddg(q, region="wt-wt", safesearch="Off", time=None, max_results=total)
                except Exception as e:
                    print("ddg() error:", e)
            elif ddg_obj_available:
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(q, safesearch="Off", timelimit=None, max_results=total))
                except Exception as e:
                    print("DDGS error:", e)
            else:
                print("No DuckDuckGo search library available. Please install 'duckduckgo_search' or 'ddgs'.")
                break

            if not results:
                print("No results found.")
                if not ask_user_continue():
                    break
                continue

            idx = 0
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

                idx += 1
                pretty_print_result(idx, title, snippet, canonical)

                parsed = ai_parse_profile(title, snippet, canonical)
                print(f"    → AI is_candidate={parsed['is_candidate']} | name={parsed.get('name')} | pos={parsed.get('position')} | company={parsed.get('company')}")

                if parsed.get("is_candidate", False):
                    score = jd_match_score_from_text(facets.get("skills_must", []), facets.get("domains", []), title, snippet)
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
                time.sleep(0.25)

            print(f"  → Query done. {len(collected)} total candidates so far.")
            if not ask_user_continue():
                break
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    except KeyboardInterrupt:
        print("\n⏹️ Interrupted by user.")

    if collected:
        ranked = sorted(collected.values(), key=lambda x: x["score"], reverse=True)
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "score","title","url","reason","snippet","source_query",
                    "ai_name","ai_position","ai_company","ai_summary"
                ]
            )
            writer.writeheader()
            for r in ranked:
                writer.writerow(r)
        print(f"\n✅ Saved {len(ranked)} candidates to {OUTPUT_CSV}")

        print("\nSaving candidates into Supabase table public.linkedin ...")
        inserted = save_linkedin_rows(jd_id, user_id, ranked)
        print(f"Inserted {len(inserted)} records (duplicates skipped).")
    else:
        print("\n⚠️ No candidates collected.")

if __name__ == "__main__":
    run()
