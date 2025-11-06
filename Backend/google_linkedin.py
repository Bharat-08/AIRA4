
#!/usr/bin/env python3
"""
google_linkedin.py — Interactive LinkedIn Candidate Sourcer (DuckDuckGo + Gemini)

Features:
- Prompts for jd_id and validates it exists in 'jds' (lowercase) table in Supabase.
- Uses site:linkedin.com/in queries to prioritize personal profiles.
- Tries python supabase client first; falls back to Supabase REST.
- Saves collected profiles to public.linkedin, skipping duplicates by profile_link.
- Works in DRY_RUN mode if GEMINI API key / google-genai SDK is not available.
"""

import os
import time
import csv
import re
import random
import json
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# -------------------- CONFIG --------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
DRY_RUN = False if GEMINI_API_KEY else True
MODEL_TO_USE = os.getenv("MODEL_TO_USE", "gemini-2.5-pro")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_USER_ID = os.getenv("SUPABASE_USER_ID", "")

OUTPUT_CSV = os.getenv("OUTPUT_CSV", "filtered_candidates.csv")

# JD sample — adjust or replace by reading actual JD content if needed
JD = {
    "role": "AI Engineer",
    "location": "India",
    "experience_text": "5-10 years",
    "must_have_skills": ["Python", "TensorFlow", "PyTorch", "NLP"],
    "nice_to_have": ["Spark", "Docker", "Kubernetes"],
    "domains": ["LLM", "Generative AI", "Signal Processing"],
}

# Search tuning
MAX_QUERIES = 6
PAGES_PER_QUERY = int(os.getenv("PAGES_PER_QUERY", 2))  # increased to get more results
RESULTS_PER_PAGE = int(os.getenv("RESULTS_PER_PAGE", 50))  # increased
MIN_DELAY = 0.8
MAX_DELAY = 1.6

# -------------------- IMPORTS --------------------
ddg_available = False
ddg_obj_available = False
try:
    # preferred: duckduckgo_search (returns more results in one call)
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

if not DRY_RUN:
    try:
        from google import genai
    except Exception as e:
        print("⚠️ google-genai not found or unusable. Running in DRY_RUN mode.", e)
        DRY_RUN = True

# Supabase client fallback
use_supabase_client = False
supabase_client = None
try:
    from supabase import create_client  # pip install supabase
    if SUPABASE_URL and SUPABASE_KEY:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        use_supabase_client = True
except Exception:
    use_supabase_client = False

import requests

# -------------------- SUPABASE HELPERS --------------------
def supabase_get(table, filters=None, select="*"):
    """
    table: table name (no schema prefix) e.g., 'jds' or 'linkedin'
    filters: dict of column -> value (exact equality)
    """
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
                    # supabase REST filter format: col = eq.value
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
    """payload: dict or list of dicts"""
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

def check_jd_exists(jd_id):
    """Check existence in 'jds' (lowercase) table."""
    if not jd_id:
        return False
    rows = supabase_get("jds", filters={"jd_id": jd_id}, select="jd_id")
    if rows:
        return True
    # fallback raw REST
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        url = f"{SUPABASE_URL}/rest/v1/jds"
        resp = requests.get(url, headers=headers, params={"select": "jd_id", "jd_id": f"eq.{jd_id}"})
        if resp.ok and resp.json():
            return True
    except Exception:
        pass
    return False

def linkedin_exists(profile_link):
    """Check if profile_link already present in public.linkedin"""
    if not profile_link:
        return False
    rows = supabase_get("linkedin", filters={"profile_link": profile_link}, select="linkedin_profile_id")
    return bool(rows)

# -------------------- SEARCH HELPERS --------------------
def generate_simple_queries(jd, max_q=MAX_QUERIES):
    role = jd.get("role", "")
    loc = jd.get("location", "")
    exp = jd.get("experience_text", "")
    domains = jd.get("domains", [])
    must = jd.get("must_have_skills", [])
    domain_chunk = " OR ".join(domains[:3]) if domains else ""
    skill_chunk = " OR ".join(must[:4]) if must else ""

    templates = [
        'site:linkedin.com/in "{role}" {loc} {exp} ({domain_or_skills})',
        'site:linkedin.com/in "{role}" {loc} {exp} ({skill_chunk})',
        'site:linkedin.com/in {role} {loc} {domain_or_skills}',
        'site:linkedin.com/in {role} {loc} {skill_chunk}',
        'site:linkedin.com/in "{role}" {loc} ({skill_chunk})',
    ]

    qlist = []
    for t in templates:
        q = t.format(
            role=role,
            loc=loc,
            exp=exp,
            domain_or_skills=(domain_chunk or skill_chunk),
            skill_chunk=skill_chunk,
        ).strip()
        if q not in qlist:
            qlist.append(q)
        if len(qlist) >= max_q:
            break
    return qlist

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
        m = re.search(r"https?://[^\s'\"]*linkedin\.com/[^\s'\"]+", body)
        if m:
            url = m.group(0)
    return normalize_link(url)

def jd_match_score(jd, title, snippet):
    text = (title or "") + " " + (snippet or "")
    text = text.lower()
    score = 0
    for s in jd.get("must_have_skills", []):
        if s.lower() in text:
            score += 4
    for d in jd.get("domains", []):
        if d.lower() in text:
            score += 2
    return min(10, score)

def pretty_print_result(idx, title, snippet, url):
    print(f"\n{idx}. {title}")
    short_snip = (snippet[:220] + "...") if snippet and len(snippet) > 220 else snippet
    print(f"   {short_snip}\n   {url}")
    print("-" * 100)

def likely_profile_url(url):
    """Quick early filter to reject obvious non-profile LinkedIn URLs."""
    if not url:
        return False
    low = url.lower()
    bad = ["/pulse/", "/posts/", "/jobs/", "/company/", "/school/", "/groups/", "/events/"]
    if any(b in low for b in bad):
        return False
    # profile paths commonly contain /in/ or /pub/
    return "/in/" in low or "/pub/" in low or re.search(r"/profile/view", low)

# -------------------- GEMINI HELPERS --------------------
def _extract_text_from_genai_response(resp):
    if hasattr(resp, "text") and resp.text:
        return resp.text
    try:
        if hasattr(resp, "candidates"):
            cands = resp.candidates
            if cands and hasattr(cands[0], "content"):
                parts = getattr(cands[0].content[0], "text", None)
                if parts:
                    return parts
        if hasattr(resp, "output") and resp.output:
            out = resp.output
            if isinstance(out, list) and len(out) > 0:
                item = out[0]
                if hasattr(item, "text"):
                    return item.text
    except Exception:
        pass
    return str(resp)

def classify_with_gemini(client, model_name, title, snippet, url):
    prompt = f"""
You are an expert recruiter. Given a LinkedIn result's title, snippet, and URL,
decide if it is an individual's LinkedIn profile (a person) or NOT (company, blog, job post, etc).
Return ONLY JSON:
{{"is_candidate": true/false, "reason": "one sentence"}}.

Title: {title}
Snippet: {snippet}
URL: {url}
"""
    try:
        resp = client.models.generate_content(model=model_name, contents=prompt)
        text = _extract_text_from_genai_response(resp)
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        parsed = json.loads(m.group(0)) if m else json.loads(text)
        return {"is_candidate": bool(parsed.get("is_candidate", False)), "reason": parsed.get("reason", "")}
    except Exception as e:
        return {"is_candidate": False, "reason": f"gemini error: {e}"}

def is_likely_candidate_heuristic(title, snippet, url):
    text = (title or "") + (snippet or "") + (url or "")
    text = text.lower()
    bad_words = ["jobs", "careers", "blog", "company", "services", "products", "press", "apply"]
    if any(w in text for w in bad_words):
        return False
    if "linkedin.com/in" in text or "linkedin.com/pub" in text:
        return True
    return any(k in text for k in ["engineer", "scientist", "developer", "researcher", "data", "ml", "ai"])

def ask_user_continue():
    while True:
        ans = input("Do you want to continue to the next query? (y/n): ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer y/n.")

# -------------------- SAVE HELPERS --------------------
def save_linkedin_rows(jd_id, user_id, candidates):
    """
    candidates: list of dicts with keys: url, title, snippet, score, reason, source_query
    """
    inserted = []
    for c in candidates:
        profile_link = c.get("url")
        if not profile_link:
            continue
        if linkedin_exists(profile_link):
            print("Skipping existing profile:", profile_link)
            continue

        name_guess = c.get("title") or ""
        title_text = c.get("title") or ""
        position = None
        company = None

        # Heuristic extraction: "Name - Position at Company" or "Position at Company - Name"
        # We'll try to extract "Position at Company" if present
        t = title_text
        # search for " at <Company>"
        m = re.search(r"(.+?) at ([^\|–\-]{2,80})", t, flags=re.IGNORECASE)
        if m:
            position = m.group(1).strip(" -|—")
            company = m.group(2).strip()
        else:
            # fallback: use entire title as position
            position = title_text

        payload = {
            "jd_id": jd_id,
            "user_id": user_id,
            "name": name_guess,
            "profile_link": profile_link,
            "position": position,
            "company": company,
            "summary": c.get("snippet") or "",
        }
        res = supabase_insert("linkedin", payload)
        if res:
            inserted.append(res)
            print("Inserted:", profile_link)
        else:
            print("Failed to insert:", profile_link)
    return inserted

# -------------------- MAIN --------------------
def run():
    global DRY_RUN

    jd_id = input("Enter jd_id (uuid) to attach results to: ").strip()
    if not jd_id:
        print("No jd_id provided. Exiting.")
        return

    print("Checking JD exists in database (table 'jds')...")
    if not check_jd_exists(jd_id):
        print("JD not found in 'jds'. Please confirm jd_id and try again.")
        return
    print("JD found. Continuing...")

    user_id = SUPABASE_USER_ID or input("SUPABASE_USER_ID not set in .env — enter your user_id: ").strip()
    if not user_id:
        print("No user id. Exiting.")
        return

    queries = generate_simple_queries(JD)
    print(f"[+] Will run {len(queries)} queries one by one.")
    print(f"[+] DRY_RUN={DRY_RUN} | ddg_available={ddg_available} | ddgs_available={ddg_obj_available}")

    client = None
    if not DRY_RUN:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
        except Exception as e:
            print("Gemini init failed:", e)
            DRY_RUN = True

    collected = {}

    for qidx, q in enumerate(queries, start=1):
        print(f"\n[Query {qidx}/{len(queries)}] {q}")
        total = PAGES_PER_QUERY * RESULTS_PER_PAGE
        results = []

        if ddg_available:
            try:
                # ddg returns list of dicts
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
            # quick early URL filter
            if not likely_profile_url(linkedin):
                # still allow some candidates if ddg returns /in/ but flagged earlier
                continue

            canonical = linkedin.split("?")[0]
            if canonical in collected:
                continue
            idx += 1
            pretty_print_result(idx, title, snippet, canonical)

            # CLASSIFY
            if not DRY_RUN and client:
                cls = classify_with_gemini(client, MODEL_TO_USE, title, snippet, canonical)
                is_cand, reason = cls["is_candidate"], cls["reason"]
            else:
                is_cand = is_likely_candidate_heuristic(title, snippet, canonical)
                reason = "heuristic"

            print(f"    → Classification: {is_cand} | reason: {reason}")

            if is_cand:
                score = jd_match_score(JD, title, snippet)
                collected[canonical] = {
                    "url": canonical,
                    "title": title,
                    "snippet": snippet,
                    "score": score,
                    "reason": reason,
                    "source_query": q,
                }
            time.sleep(0.25)

        print(f"  → Query done. {len(collected)} total candidates so far.")
        if not ask_user_continue():
            break
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    if collected:
        ranked = sorted(collected.values(), key=lambda x: x["score"], reverse=True)
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["score", "title", "url", "reason", "snippet", "source_query"]
            )
            writer.writeheader()
            for r in ranked:
                writer.writerow({
                    "score": r.get("score"),
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "reason": r.get("reason"),
                    "snippet": r.get("snippet"),
                    "source_query": r.get("source_query"),
                })
        print(f"\n✅ Saved {len(ranked)} candidates to {OUTPUT_CSV}")

        print("\nSaving candidates into Supabase table public.linkedin ...")
        inserted = save_linkedin_rows(jd_id, user_id, ranked)
        print(f"Inserted {len(inserted)} records (duplicates skipped).")
    else:
        print("\n⚠️ No candidates collected.")

if __name__ == "__main__":
    run()
