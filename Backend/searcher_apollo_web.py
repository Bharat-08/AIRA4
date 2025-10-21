#!/usr/bin/env python3
"""
Enhanced Deep Research Agent with Apollo API Integration

Changes:
- fanout_followup passes numeric indices (fixes int() errors)
- apollo_search robustly handles query_index formats and rotates pages per loop
- reflection parsing tolerant to list/dict outputs
- user can choose search mode on every iteration
- defensive payload construction and APOLLO_DEBUG support

Refactored to be non-interactive:
- run_deep_research(self, jd_id: str, search_mode: SearchMode, custom_prompt: str = "", user_id: str = None)
- Removed all input() calls and interactive prompts
- Fixed 3-iteration loop with visible iteration completion logs
"""
import json
import os
import sys
import uuid
import time
import signal
import requests
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, TypedDict, Annotated, Any
from dataclasses import dataclass
from urllib.parse import urlparse
from pydantic import BaseModel, Field
from enum import Enum

from dotenv import load_dotenv
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

try:
    from supabase import create_client, Client
except ImportError as exc:
    raise ImportError(
        "Supabase client library not installed. Please run `pip install supabase`"
    ) from exc

try:
    from google import genai
    from google.genai.types import GenerateContentConfig, Tool
except ImportError as exc:
    raise ImportError(
        "Google Gen AI SDK not installed. Please run `pip install google-genai`"
    ) from exc

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Send
except ImportError as exc:
    raise ImportError(
        "LangGraph not installed. Please run `pip install langgraph`"
    ) from exc


# Load environment
load_dotenv()

# Apollo API Configuration
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "").strip()
APOLLO_BASE_URL = os.getenv("APOLLO_BASE_URL", "https://api.apollo.io/v1").rstrip("/")
APOLLO_RATE_LIMIT_DELAY = float(os.getenv("APOLLO_RATE_LIMIT_DELAY", "1.0"))
# Hard cap Apollo search results (cap to small number for interactive runs)
_env_apollo_max = int(os.getenv("APOLLO_MAX_RESULTS_PER_SEARCH", "25"))
APOLLO_MAX_RESULTS_PER_SEARCH = min(_env_apollo_max, 7)  # keep at most 7 by default
APOLLO_REQUEST_TIMEOUT = float(os.getenv("APOLLO_REQUEST_TIMEOUT", "10"))
# Enable extra Apollo debug prints when troubleshooting (true/false)
APOLLO_DEBUG = os.getenv("APOLLO_DEBUG", "false").lower() in ("1", "true", "yes")

# Model Configuration
DEFAULT_MODEL = os.getenv("DR_MODEL", "gemini-2.5-pro")
MODEL_PRIORITY_ENV = os.getenv("DR_MODEL_PRIORITY", "")
if MODEL_PRIORITY_ENV:
    MODEL_PRIORITY = [m.strip() for m in MODEL_PRIORITY_ENV.split(",") if m.strip()]
else:
    MODEL_PRIORITY = [DEFAULT_MODEL, "gemini-2.5-flash", "gemini-1.5-pro"]

TEMPERATURE = float(os.getenv("DR_TEMPERATURE", "0.2"))
TOP_K = int(os.getenv("DR_TOP_K", "40"))
TOP_P = float(os.getenv("DR_TOP_P", "0.8"))

# Search Configuration
TARGET_COUNT = int(os.getenv("DR_TARGET_COUNT", "15"))
MAX_LOOPS = int(os.getenv("DR_MAX_LOOPS", "8"))
PER_QUERY_MAX = int(os.getenv("DR_PER_QUERY_MAX", "10"))
TIME_BUDGET_SEC = int(os.getenv("DR_TIME_BUDGET_SEC", "300"))
INITIAL_QUERY_COUNT = int(os.getenv("DR_INITIAL_QUERY_COUNT", "10"))

# Validation Configuration
EXCLUDE_DOMAINS = set(os.getenv("DR_EXCLUDE_DOMAINS", "linkedin.com,lnkd.in,facebook.com,twitter.com,instagram.com").split(","))
REQUEST_TIMEOUT = float(os.getenv("DR_HTTP_TIMEOUT", "8"))
REQUEST_DELAY = float(os.getenv("DR_REQUEST_DELAY", "0.2"))
MIN_NAME_MATCH = int(os.getenv("DR_MIN_NAME_MATCH", "85"))
MIN_ROLE_MATCH = int(os.getenv("DR_MIN_ROLE_MATCH", "70"))
MIN_COMPANY_MATCH = int(os.getenv("DR_MIN_COMPANY_MATCH", "70"))
MIN_ROLE_KEYWORD_SIMILARITY = int(os.getenv("DR_MIN_ROLE_KEYWORD_SIMILARITY", "80"))

# Location Configuration
DEFAULT_LOCATION = os.getenv("DR_DEFAULT_LOCATION", "India")
LOCATION_INDICATORS = os.getenv("DR_LOCATION_INDICATORS", "india,mumbai,bangalore,bengaluru,delhi,hyderabad,chennai,pune,kolkata").split(",")

# Logging Configuration
LOG_LEVEL = os.getenv("DR_LOG_LEVEL", "INFO")
ENABLE_AUDIT_TRAIL = os.getenv("DR_ENABLE_AUDIT_TRAIL", "true").lower() == "true"

# Fallback behavior
MAX_MODEL_FALLBACKS = int(os.getenv("DR_MAX_MODEL_FALLBACKS", "3"))
FALLBACK_BACKOFF_SEC = float(os.getenv("DR_FALLBACK_BACKOFF_SEC", "1.0"))


class SearchMode(str, Enum):
    """Search mode selection."""
    APOLLO_ONLY = "apollo_only"
    APOLLO_AND_WEB = "apollo_and_web"


class Candidate(BaseModel):
    """Structured candidate schema with evidence tracking."""
    full_name: str = Field(description="Full name of the candidate")
    current_title: str = Field(description="Current job title/role")
    current_company: str = Field(description="Current company name")
    location: str = Field(description="Geographic location")
    notes: str = Field(description="Professional background and experience summary")
    other_contacts: List[str] = Field(default_factory=list, description="Additional contact information")
    sources: List[str] = Field(default_factory=list, description="Source URLs or API identifiers")
    
    # Evidence tracking
    evidence_snippet: Optional[str] = Field(default=None, description="Text snippet validating the candidate")
    validated_url: Optional[str] = Field(default=None, description="URL that was validated")
    validated_at: Optional[str] = Field(default=None, description="Validation timestamp")
    discovered_by_query: Optional[str] = Field(default=None, description="Search query that found this candidate")
    source_type: Optional[str] = Field(default="web", description="Source type: 'apollo' or 'web'")
    
    # Apollo-specific fields
    apollo_id: Optional[str] = Field(default=None, description="Apollo person ID")
    email: Optional[str] = Field(default=None, description="Email address from Apollo")
    phone: Optional[str] = Field(default=None, description="Phone number from Apollo")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn URL from Apollo")


class SearchQuery(BaseModel):
    """Structured search query with metadata."""
    query: str = Field(description="Search query string")
    intent: str = Field(description="Intent behind this query")
    expected_sources: List[str] = Field(default_factory=list, description="Expected source types")
    search_mode: str = Field(default="web", description="Search mode: 'apollo' or 'web'")

def add_leads(left: List[dict], right: List[dict]) -> List[dict]:
    """Custom reducer for aggregating leads."""
    if not left:
        return right
    if not right:
        return left
    return left + right

class OverallState(TypedDict, total=False):
    """Complete state for the research workflow."""
    # Input data
    jd_data: dict
    custom_prompt: str
    user_id: str
    jd_id: str
    search_mode: str
    
    # Dynamic prompts and queries
    dynamic_prompt: str
    search_queries: List[dict]
    
    # Research results
    leads: Annotated[List[dict], add_leads]
    validated_candidates: List[dict]
    final_candidates: List[dict]
    
    # Loop control
    research_loop_count: int
    max_research_loops: int
    is_sufficient: bool
    start_time: float
    
    # Follow-up and reflection
    follow_up_queries: List[dict]
    coverage_gaps: List[str]
    reflection_notes: str
    
    # Configuration
    per_query_max: int
    target_count: int
    role_keyword: str
    
    # Iteration tracking
    iteration_count: int
    exclusion_names: List[str]
    exclusion_companies: List[str]
    query_index: Any


class ApolloClient:
    """Apollo.io API client with rate limiting and error handling."""
    
    def __init__(self, api_key: str = None, oauth_token: str = None):
        # supply oauth_token param only if you actually have an OAuth access token
        self.api_key = (api_key or "").strip()
        self.oauth_token = (oauth_token or "").strip()
        self.base_url = APOLLO_BASE_URL
        self.session = requests.Session()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        if self.oauth_token:
            headers["Authorization"] = f"Bearer {self.oauth_token}"
        self.session.headers.update(headers)
        self.last_request_time = 0

        
    def _rate_limit(self):
        """Implement rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < APOLLO_RATE_LIMIT_DELAY:
            time.sleep(APOLLO_RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def _debug_dump(self, payload: dict, response: Optional[requests.Response] = None):
        """Optional debug print for Apollo requests/responses if APOLLO_DEBUG enabled."""
        if not APOLLO_DEBUG:
            return
        try:
            print("=== APOLLO DEBUG DUMP ===")
            print("Request URL:", f"{self.base_url}/mixed_people/search")
            print("Request headers:", json.dumps(dict(self.session.headers), indent=2))
            print("Request payload:", json.dumps(payload, indent=2))
            if response is not None:
                print("Response status:", response.status_code)
                try:
                    print("Response body:", json.dumps(response.json(), indent=2))
                except Exception:
                    print("Response body (text):", response.text)
            print("=========================")
        except Exception as e:
            print("Apollo debug dump failed:", e)
    
    def search_people(self, 
                     titles: List[str] = None,
                     organization_locations: List[str] = None,
                     person_locations: List[str] = None,
                     q_keywords: str = None,
                     page: int = 1,
                     per_page: int = 25) -> dict:
        """
        Search for people using Apollo API.
        """
        self._rate_limit()

        url = f"{self.base_url}/mixed_people/search"

        # enforce hard cap
        per_page = max(1, min(int(per_page or 1), APOLLO_MAX_RESULTS_PER_SEARCH))

        # Build payload only with non-empty fields to avoid 422
        payload = {
            "page": int(page or 1),
            "per_page": per_page
        }

        if titles:
            clean_titles = [t.strip() for t in titles if isinstance(t, str) and t.strip()]
            if clean_titles:
                # Apollo docs accept person_titles[]; JSON key often person_titles
                payload["person_titles"] = clean_titles

        if organization_locations:
            clean_org_locs = [l.strip() for l in organization_locations if isinstance(l, str) and l.strip()]
            if clean_org_locs:
                payload["organization_locations"] = clean_org_locs

        if person_locations:
            clean_person_locs = [l.strip() for l in person_locations if isinstance(l, str) and l.strip()]
            if clean_person_locs:
                payload["person_locations"] = clean_person_locs

        if q_keywords and isinstance(q_keywords, str) and q_keywords.strip():
            payload["q_keywords"] = q_keywords.strip()

        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=APOLLO_REQUEST_TIMEOUT
            )

            # If error, attempt to show helpful info
            if response.status_code >= 400:
                # capture body
                try:
                    err_body = response.json()
                except ValueError:
                    err_body = response.text

                # debug dump if requested
                self._debug_dump(payload, response)

                # Provide clear error message
                raise requests.exceptions.HTTPError(f"{response.status_code} {response.reason}: {err_body}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as he:
            raise Exception(f"Apollo API request failed: {he}")
        except requests.exceptions.RequestException as e:
            # optionally debug
            try:
                self._debug_dump(payload)
            except Exception:
                pass
            raise Exception(f"Apollo API request failed: {e}")
    
    def enrich_person(self, person_id: str = None, email: str = None) -> dict:
        """
        Enrich person data using Apollo API.
        """
        self._rate_limit()
        
        url = f"{self.base_url}/people/match"
        
        payload = {}
        
        if person_id:
            payload["id"] = person_id
        elif email:
            payload["email"] = email
        else:
            raise ValueError("Either person_id or email must be provided")
        
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=APOLLO_REQUEST_TIMEOUT
            )

            if response.status_code >= 400:
                try:
                    err_body = response.json()
                except ValueError:
                    err_body = response.text
                if APOLLO_DEBUG:
                    print("APOLLO ENRICH DEBUG: payload:", json.dumps(payload), "status:", response.status_code, "body:", err_body)
                raise requests.exceptions.HTTPError(f"{response.status_code} {response.reason}: {err_body}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Apollo enrichment failed: {e}")


class EnhancedDeepResearchAgent:
    """Enhanced Deep Research Agent with Apollo API integration."""

    def __init__(self, search_mode: SearchMode = SearchMode.APOLLO_AND_WEB):
        # Initialize Supabase
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if not supabase_url or not supabase_key:
            raise EnvironmentError("SUPABASE_URL and SUPABASE_KEY must be set")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Initialize Gemini
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise EnvironmentError("GEMINI_API_KEY must be set")
        
        self.gemini_client = genai.Client(api_key=gemini_api_key)
        
        # Initialize Apollo (if API key available)
        self.apollo_client = None
        if APOLLO_API_KEY:
            self.apollo_client = ApolloClient(APOLLO_API_KEY)
            self._log("INFO", "✅ Apollo API client initialized")
        else:
            if search_mode == SearchMode.APOLLO_ONLY:
                raise EnvironmentError("APOLLO_API_KEY required for Apollo-only mode")
            self._log("WARNING", "⚠️ Apollo API key not found, web search only")
        
        # Initialize tools
        self.google_search_tool = Tool(google_search={})
        self.url_context_tool = Tool(url_context={})
        
        # State tracking
        self.search_mode = search_mode
        self.continue_running = True
        self.processed_urls: Set[str] = set()
        self.processed_apollo_ids: Set[str] = set()
        
        # Model fallback
        self.model_priority = list(MODEL_PRIORITY)
        if not self.model_priority:
            self.model_priority = [DEFAULT_MODEL]
        self.current_model_index = 0
        
        self._log("INFO", f"🔍 Search mode: {search_mode.value}")
        self._log("INFO", f"📋 Model priority: {self.model_priority}")
        
        # Setup signal handling
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle SIGINT gracefully."""
        print("\n🛑 Received interrupt signal. Finishing current iteration...")
        self.continue_running = False

    def _log(self, level: str, message: str, **kwargs):
        """Configurable logging."""
        if LOG_LEVEL in ["DEBUG"] or (LOG_LEVEL == "INFO" and level in ["INFO", "WARNING", "ERROR"]):
            timestamp = datetime.utcnow().isoformat()
            print(f"[{timestamp}] {level}: {message}")
            if kwargs and ENABLE_AUDIT_TRAIL:
                print(f"  Details: {json.dumps(kwargs, indent=2)}")

    def _extract_json_from_text(self, text: str, expected_type: str = "array") -> any:
        """Extract JSON from text response with fallback parsing."""
        if not text:
            return [] if expected_type == "array" else {}
        
        text = text.strip()
        
        # Try to find JSON blocks
        json_patterns = [
            (r'```json\s*(.*?)\s*```', re.DOTALL),
            (r'```\s*(.*?)\s*```', re.DOTALL),
            (r'(\[.*\])', re.DOTALL),
            (r'(\{.*\})', re.DOTALL)
        ]
        
        for pattern, flags in json_patterns:
            match = re.search(pattern, text, flags)
            if match:
                json_str = match.group(1)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue
        
        # Fallback: try entire text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            self._log("WARNING", f"Could not extract JSON from: {text[:200]}...")
            return [] if expected_type == "array" else {}

    def _get_current_model(self) -> str:
        """Get current model name."""
        return self.model_priority[self.current_model_index]

    def _advance_model(self) -> bool:
        """Advance to next model. Return True if advanced, False if exhausted."""
        if self.current_model_index + 1 < len(self.model_priority):
            self.current_model_index += 1
            self._log("WARNING", f"Switching to: {self._get_current_model()}")
            return True
        return False

    def _generate_content_with_fallback(self, *, contents: str, config: GenerateContentConfig, 
                                       max_fallbacks: int = MAX_MODEL_FALLBACKS):
        """Gemini API call with automatic model fallback on overload."""
        attempts = 0
        tried_models = set()
        last_exception = None

        while attempts <= max_fallbacks:
            model_name = self._get_current_model()
            if model_name in tried_models and not self._advance_model():
                break
            tried_models.add(model_name)
            attempts += 1

            try:
                self._log("DEBUG", f"Calling '{model_name}' (attempt {attempts})")
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                response_text = response.text if hasattr(response, "text") else str(response)
                if isinstance(response_text, str) and ("model is overloaded" in response_text.lower() or 
                                                       "503" in response_text or 
                                                       "unavailable" in response_text.lower()):
                    raise RuntimeError(f"Model overloaded: {response_text[:200]}")
                
                self._log("INFO", f"✅ '{model_name}' succeeded")
                return response
            except Exception as e:
                last_exception = e
                err_str = str(e).lower()
                is_overload = ("model is overloaded" in err_str or "503" in err_str or 
                              "unavailable" in err_str or "status: 'unavailable'" in err_str)

                if is_overload and self._advance_model():
                    self._log("WARNING", f"Overload detected, retrying with '{self._get_current_model()}'")
                    time.sleep(FALLBACK_BACKOFF_SEC)
                    continue
                else:
                    self._log("ERROR", f"Call failed for '{model_name}': {e}")
                    raise

        raise last_exception if last_exception else RuntimeError("Gemini call failed")

    def fetch_jd_from_supabase(self, jd_id: str) -> dict:
        """Fetch job description from Supabase."""
        try:
            response = (
                self.supabase.table("jds")
                .select("*")
                .eq("jd_id", jd_id)
                .single()
                .execute()
            )
            return response.data or {}
        except Exception as err:
            self._log("ERROR", f"Error fetching JD {jd_id}: {err}")
            return {}

    def apollo_search(self, state: OverallState) -> dict:
        """Perform Apollo API search. Handles both string queries and structured dict queries."""
        if not self.apollo_client:
            self._log("WARNING", "Apollo client not available")
            return {"leads": []}

        query_data = state.get("query_data", {}) or {}
        raw_query = query_data.get("query", "")
        jd_data = state.get("jd_data", {}) or {}
        exclusion_names = state.get("exclusion_names", [])

        # Normalize and prepare for logging / discovered_by_query
        query_str = ""
        # defaults for apollo call
        titles = None
        person_locations = None
        q_keywords = None
        organization_locations = None
        person_seniorities = None

        # If the model produced a structured query (dict), map common fields to Apollo params
        if isinstance(raw_query, dict):
            # create a human readable query string for discovered_by_query
            parts = []
            # jobTitles / job_titles
            jt = raw_query.get("jobTitles") or raw_query.get("job_titles") or raw_query.get("titles") or raw_query.get("job_titles[]")
            if isinstance(jt, (list, tuple)):
                titles = [str(x).strip() for x in jt if x]
                parts.append("titles: " + ", ".join(titles))
            elif isinstance(jt, str) and jt.strip():
                titles = [jt.strip()]
                parts.append("titles: " + jt.strip())

            # locations / location lists
            locs = raw_query.get("locations") or raw_query.get("location") or raw_query.get("person_locations")
            if isinstance(locs, (list, tuple)):
                person_locations = [str(x).strip() for x in locs if x]
                parts.append("locations: " + ", ".join(person_locations))
            elif isinstance(locs, str) and locs.strip():
                person_locations = [locs.strip()]
                parts.append("locations: " + locs.strip())

            # keywords / q_keywords
            keys = raw_query.get("keywords") or raw_query.get("q_keywords") or raw_query.get("keywords_list")
            if isinstance(keys, (list, tuple)):
                q_keywords = " ".join([str(x).strip() for x in keys if x])
                parts.append("keywords: " + ", ".join([str(x) for x in keys if x]))
            elif isinstance(keys, str) and keys.strip():
                q_keywords = keys.strip()
                parts.append("keywords: " + keys.strip())

            # seniority
            senior = raw_query.get("seniorities") or raw_query.get("person_seniorities") or raw_query.get("seniority")
            if isinstance(senior, (list, tuple)):
                person_seniorities = [str(x).strip() for x in senior if x]
                parts.append("seniorities: " + ", ".join(person_seniorities))
            elif isinstance(senior, str) and senior.strip():
                person_seniorities = [senior.strip()]
                parts.append("seniorities: " + senior.strip())

            # maybe company names or organization filters
            past_companies = raw_query.get("pastCompanyNames") or raw_query.get("past_companies") or raw_query.get("company") or raw_query.get("company_names")
            if isinstance(past_companies, (list, tuple)):
                organization_locations = [str(x).strip() for x in past_companies if x]
                parts.append("past_companies: " + ", ".join(organization_locations))
            elif isinstance(past_companies, str) and past_companies.strip():
                organization_locations = [past_companies.strip()]
                parts.append("past_companies: " + past_companies.strip())

            # fallback: if the dict is something else, use its JSON as string
            if not parts:
                try:
                    query_str = json.dumps(raw_query, ensure_ascii=False)
                except Exception:
                    query_str = str(raw_query)
            else:
                query_str = " | ".join(parts)

        else:
            # raw_query is string or something else: coerce to string
            query_str = str(raw_query or "").strip()
            # set q_keywords to the string if no structured mapping
            if query_str:
                q_keywords = query_str

        self._log("INFO", f"🔍 Apollo search: {raw_query if not isinstance(raw_query, dict) else json.dumps(raw_query, ensure_ascii=False) }")

        try:
            # Extract search parameters from JD as fallbacks
            role = jd_data.get("role") or jd_data.get("title", "")
            location = jd_data.get("location", DEFAULT_LOCATION)

            # If no titles were found from query dict, consider JD role as a title
            if not titles and role:
                titles = [role]

            # If person_locations is empty, fallback to location
            if not person_locations and location:
                person_locations = [location]

            # Defensive per_page: never exceed APOLLO_MAX_RESULTS_PER_SEARCH
            desired_per_page = int(state.get("per_query_max", PER_QUERY_MAX) or PER_QUERY_MAX)
            per_page = min(desired_per_page, APOLLO_MAX_RESULTS_PER_SEARCH)

            # Determine page rotation so each loop pulls different pages.
            # Handle query_index values that might be int, numeric string, or strings like "followup_2".
            raw_qindex = state.get("query_index", 0) or 0
            try:
                if isinstance(raw_qindex, int):
                    query_index = raw_qindex
                else:
                    query_index = int(str(raw_qindex))
            except Exception:
                m = re.search(r"(\d+)$", str(raw_qindex))
                if m:
                    query_index = int(m.group(1))
                else:
                    # deterministic small hash fallback
                    s = str(raw_qindex)
                    query_index = sum(ord(ch) for ch in s) % 50

            loop_count = int(state.get("research_loop_count", 0) or 0)
            # rotate within 50 pages window (Apollo display limit); keep page >=1
            page = 1 + ((loop_count) + query_index) % 50

            # Call Apollo client with the mapped parameters
            results = self.apollo_client.search_people(
                titles=titles if titles else None,
                organization_locations=organization_locations if organization_locations else None,
                person_locations=person_locations if person_locations else None,
                q_keywords=q_keywords if q_keywords else None,
                page=page,
                per_page=per_page
            )

            # Process Apollo results
            candidates = []
            people = results.get("people", []) or results.get("data", {}).get("people", []) or results.get("results", []) or results.get("profiles", [])

            # Normalize shapes
            if isinstance(people, dict):
                # maybe returned wrapped object
                # try to find a list value inside
                found_list = None
                for v in people.values():
                    if isinstance(v, list):
                        found_list = v
                        break
                people = found_list or []

            if not isinstance(people, list):
                people = []

            self._log("INFO", f"Apollo returned {len(people)} results (page={page})")

            for person in people:
                # Skip if already processed or excluded
                person_id = person.get("id") or person.get("person_id") or person.get("apollo_id")
                if not person_id:
                    continue
                if person_id in self.processed_apollo_ids:
                    continue

                name = (person.get("name") or person.get("full_name") or (person.get("first_name","") + " " + person.get("last_name",""))).strip()
                if not name:
                    continue
                if name.lower() in exclusion_names:
                    continue

                # Extract candidate data
                title = person.get("title") or person.get("headline") or ""
                company = ""
                org = person.get("organization") or person.get("company") or {}
                if isinstance(org, dict):
                    company = org.get("name") or org.get("company_name") or ""
                else:
                    company = str(org or "")

                # prefer city/state/country fields if present
                person_location = person.get("city", "") or person.get("state", "") or person.get("country", "") or (person_locations[0] if person_locations else location)

                # Skip excluded roles
                excluded_roles = ["co-founder", "founder", "owner", "entrepreneur", "ceo", "chairman"]
                if any(role_str in (title or "").lower() for role_str in excluded_roles):
                    continue

                candidate_data = {
                    "full_name": name,
                    "current_title": title,
                    "current_company": company,
                    "location": person_location or (location or DEFAULT_LOCATION),
                    "notes": f"Found via Apollo API. {person.get('headline', '') or person.get('summary','')}",
                    # store a string summary of the query that discovered this record
                    "discovered_by_query": query_str,
                    "sources": [f"apollo:{person_id}"],
                    "source_type": "apollo",
                    "apollo_id": person_id,
                    "email": person.get("email"),
                    "phone": person.get("phone_number") or person.get("phone"),
                    "linkedin_url": person.get("linkedin_url"),
                    "validated_at": datetime.utcnow().isoformat(),
                    "evidence_snippet": f"Apollo verified profile: {title} at {company}"
                }

                candidates.append(candidate_data)
                self.processed_apollo_ids.add(person_id)

            self._log("INFO", f"✅ Apollo: {len(candidates)} valid candidates")
            return {"leads": candidates}

        except Exception as err:
            self._log("ERROR", f"Apollo search failed: {err}")
            return {"leads": []}


    def url_ok(self, url: str) -> bool:
        """Validate URL format and domain exclusions."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return False
            domain = parsed.netloc.lower()
            return not any(excluded in domain for excluded in EXCLUDE_DOMAINS)
        except:
            return False

    def page_contains(self, text: str, needle: str, min_ratio: int) -> bool:
        """Fuzzy text matching."""
        return fuzz.partial_ratio(needle.lower(), text.lower()) >= min_ratio

    def validate_candidate_evidence(self, candidate: Candidate) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate candidate with evidence."""
        # Apollo candidates are pre-validated
        if candidate.source_type == "apollo":
            return True, candidate.sources[0] if candidate.sources else None, candidate.evidence_snippet
        
        self._log("DEBUG", f"Validating: {candidate.full_name}")
        
        for source_url in candidate.sources:
            if not self.url_ok(source_url):
                continue
            
            try:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; DeepResearchBot/1.0)"}
                response = requests.get(source_url, timeout=REQUEST_TIMEOUT, headers=headers)
                
                if response.status_code != 200:
                    continue
                
                content_type = response.headers.get("Content-Type", "")
                if "text" not in content_type:
                    continue
                
                soup = BeautifulSoup(response.text, "html.parser")
                page_text = soup.get_text(separator=" ", strip=True)[:200000]
                
                name_match = self.page_contains(page_text, candidate.full_name, MIN_NAME_MATCH)
                role_match = self.page_contains(page_text, candidate.current_title, MIN_ROLE_MATCH)
                company_match = self.page_contains(page_text, candidate.current_company, MIN_COMPANY_MATCH)
                
                if name_match and (role_match or company_match):
                    name_pos = page_text.lower().find(candidate.full_name.lower())
                    if name_pos >= 0:
                        start = max(0, name_pos - 100)
                        end = min(len(page_text), name_pos + 300)
                        evidence = page_text[start:end].strip()
                        
                        self._log("INFO", f"✅ Validated: {candidate.full_name}")
                        return True, source_url, evidence
                
            except requests.RequestException as e:
                self._log("DEBUG", f"Request failed for {source_url}: {e}")
                continue
            
            time.sleep(REQUEST_DELAY)
        
        self._log("WARNING", f"❌ No evidence: {candidate.full_name}")
        return False, None, None

    def is_valid_lead(self, lead_data: dict) -> bool:
        """Validate lead structure."""
        required = ["full_name", "current_title", "current_company", "location", "sources"]
        
        if not all(field in lead_data and lead_data[field] for field in required):
            return False
        
        # Apollo sources are always valid
        if lead_data.get("source_type") == "apollo":
            return True
        
        valid_sources = [url for url in lead_data["sources"] if self.url_ok(url)]
        lead_data["sources"] = valid_sources
        
        return len(valid_sources) > 0

    def generate_queries(self, state: OverallState) -> OverallState:
        """Generate search queries based on mode."""
        jd_data = state["jd_data"]
        custom_prompt = state.get("custom_prompt", "")
        iteration_count = state.get("iteration_count", 1)
        exclusion_names = state.get("exclusion_names", [])
        exclusion_companies = state.get("exclusion_companies", [])
        search_mode = state.get("search_mode", SearchMode.APOLLO_AND_WEB.value)

        jd_summary = jd_data.get("jd_parsed_summary", "")
        if isinstance(jd_summary, (dict, list)):
            jd_summary = json.dumps(jd_summary)

        location = jd_data.get("location", DEFAULT_LOCATION)

        # Extract role keyword
        role_keyword = ""
        if jd_data.get("role"):
            role_keyword = str(jd_data["role"]).strip().lower()
        elif jd_data.get("title"):
            role_keyword = str(jd_data["title"]).strip().lower()
        state["role_keyword"] = role_keyword
        
        self._log("INFO", f"Role keyword: '{role_keyword}'")

        # Build exclusion context
        exclusion_context = ""
        if exclusion_names or exclusion_companies:
            exclusion_context = f"""
            CRITICAL EXCLUSIONS:
            - Do NOT include: {', '.join(exclusion_names[:20])}
            - Avoid companies: {', '.join(exclusion_companies[:10])}
            - Find NEW candidates only
            """

        # Determine query generation strategy based on mode
        mode_instructions = ""
        if search_mode == SearchMode.APOLLO_ONLY.value:
            mode_instructions = """
            SEARCH MODE: Apollo API Only
            - Generate queries optimized for Apollo.io people search
            - Focus on job titles, locations, and keywords
            - Queries will use Apollo's structured search
            - No need for site: operators or web-specific techniques
            """
        else:  # APOLLO_AND_WEB
            mode_instructions = """
            SEARCH MODE: Apollo + Web Search
            - Generate diverse queries for both Apollo API and web search
            - Apollo queries: job titles, locations, keywords
            - Web queries: company sites, directories, professional pages
            - Use site: operators and search techniques for web
            """

        query_prompt = f"""
        Expert research strategist. Iteration {iteration_count}. Generate {INITIAL_QUERY_COUNT} queries.

        Job Description:
        {jd_summary}

        Role: {role_keyword or 'None'}
        Location: {location}
        Requirements: {custom_prompt or "None"}
        
        {mode_instructions}
        {exclusion_context}

        REQUIREMENTS:
        1. Find corporate employees at established companies
        2. Target {location}-based professionals
        3. Exclude founders, owners, CEOs of small companies
        4. Focus on Directors, VPs, Managers, Team Leads
        5. Each query should target different angles
        
        Return JSON array:
        [
            {{
                "query": "search query",
                "intent": "intent",
                "expected_sources": ["source_type"],
                "search_mode": "apollo" or "web"
            }}
        ]
        
        ONLY JSON array, no other text.
        """

        try:
            config = GenerateContentConfig(
                tools=[self.google_search_tool],
                temperature=TEMPERATURE,
                top_k=TOP_K,
                top_p=TOP_P
            )

            response = self._generate_content_with_fallback(contents=query_prompt, config=config)
            response_text = response.text if hasattr(response, 'text') else str(response)
            queries_data = self._extract_json_from_text(response_text, "array")

            if not queries_data:
                raise ValueError("No queries generated")

            # Filter queries based on search mode
            if search_mode == SearchMode.APOLLO_ONLY.value:
                queries_data = [q for q in queries_data if q.get("search_mode") == "apollo"]
            
            self._log("INFO", f"Generated {len(queries_data)} queries")
            state["search_queries"] = queries_data
            state["dynamic_prompt"] = query_prompt

        except Exception as err:
            self._log("ERROR", f"Query generation failed: {err}")
            # Fallback queries based on mode
            if search_mode == SearchMode.APOLLO_ONLY.value:
                state["search_queries"] = [
                    {"query": {"job_titles": [role_keyword]}, "intent": "find_professionals", 
                     "expected_sources": ["apollo"], "search_mode": "apollo"},
                    {"query": {"job_titles": ["director", "manager"], "locations": [location]}, "intent": "find_leadership", 
                     "expected_sources": ["apollo"], "search_mode": "apollo"}
                ]
            else:
                state["search_queries"] = [
                    {"query": f"{role_keyword} {location}", "intent": "apollo_search", 
                     "expected_sources": ["apollo"], "search_mode": "apollo"},
                    {"query": f"\"director\" {location} company website", "intent": "web_search", 
                     "expected_sources": ["websites"], "search_mode": "web"}
                ]

        return state

    def web_research(self, state: OverallState) -> dict:
        """Perform web research with Gemini tools."""
        query_data = state.get("query_data", {})
        query = query_data.get("query", "")
        search_mode = query_data.get("search_mode", "web")
        per_query_max = state.get("per_query_max", PER_QUERY_MAX)
        exclusion_names = state.get("exclusion_names", [])
        exclusion_companies = state.get("exclusion_companies", [])
        
        self._log("INFO", f"🔎 Web research: {query}")
        
        exclusion_context = ""
        if exclusion_names:
            exclusion_context = f"""
            CRITICAL EXCLUSIONS:
            - NEVER include: {', '.join(exclusion_names[:15])}
            - AVOID companies: {', '.join(exclusion_companies[:8])}
            - Find ONLY NEW candidates
            """

        research_prompt = f"""
        Expert candidate researcher. Find up to {per_query_max} real professionals.
        Use Google Search and URL Context tools.

        Query: {query}
        Intent: {query_data.get("intent", "")}
        Expected: {query_data.get("expected_sources", [])}
        
        Context: {state.get("dynamic_prompt", "")}
        {exclusion_context}

        REQUIREMENTS:
        1. Use Google Search to find pages
        2. Use URL Context to extract information
        3. Only verifiable candidates
        4. Focus on {DEFAULT_LOCATION} professionals
        5. Exclude LinkedIn, social media
        6. Include source URLs
        7. Quote validation text

        EXCLUDE ROLES:
        - Founder, Owner, Entrepreneur, CEO of small companies

        INCLUDE ROLES:
        - Director, VP, Manager, Team Lead at corporations

        Extract for each:
        - full_name, current_title, current_company, location
        - notes, sources (URLs)

        Return JSON array:
        [
            {{

                "full_name": "Name",
                "current_title": "Title",
                "current_company": "Company",
                "location": "Location",
                "notes": "Summary",
                "sources": ["url1"]
            }}
        ]
        
        ONLY JSON array. Empty [] if none found.
        """

        try:
            config = GenerateContentConfig(
                tools=[self.google_search_tool, self.url_context_tool],
                temperature=TEMPERATURE,
                top_k=TOP_K,
                top_p=TOP_P
            )
            
            response = self._generate_content_with_fallback(contents=research_prompt, config=config)
            response_text = response.text if hasattr(response, 'text') else str(response)
            candidates_data = self._extract_json_from_text(response_text, "array")
            
            # Filter results
            filtered = []
            excluded_roles = ["co-founder", "founder", "owner", "entrepreneur", "ceo", "chairman"]
            
            for candidate_data in candidates_data:
                title = candidate_data.get("current_title", "").lower()
                if any(role in title for role in excluded_roles):
                    continue
                
                name = candidate_data.get("full_name", "").lower()
                if name in exclusion_names:
                    continue
                
                candidate_data["discovered_by_query"] = query
                candidate_data["source_type"] = "web"
                filtered.append(candidate_data)
            
            self._log("INFO", f"✅ Web: {len(filtered)} candidates")
            if len(candidates_data) > len(filtered):
                self._log("INFO", f"Filtered {len(candidates_data) - len(filtered)} invalid")
            
            return {"leads": filtered}
            
        except Exception as err:
            self._log("ERROR", f"Web research failed: {err}")
            return {"leads": []}

    def route_search(self, state: OverallState) -> dict:
        """Route to appropriate search method based on query mode."""
        query_data = state.get("query_data", {})
        search_mode = query_data.get("search_mode", "web")
        
        if search_mode == "apollo" and self.apollo_client:
            return self.apollo_search(state)
        else:
            return self.web_research(state)

    def validate_and_aggregate(self, state: OverallState) -> OverallState:
        """
        Validate candidates with evidence and aggregate results.

        This implementation mirrors the original CLI agent logic:
        - Use is_valid_lead to perform structural checks and filter invalid leads
        - For each valid lead, run deterministic evidence validation via validate_candidate_evidence()
        - If evidence validation succeeds, enrich candidate with validated_url, evidence_snippet, validated_at
        - Deduplicate validated candidates and update state["validated_candidates"]
        - Set state["is_sufficient"] based on target_count and return the state
        """
        # Get all leads from the state (custom reducer will aggregate them)
        all_leads = state.get("leads", []) or []
        self._log("INFO", f"Aggregated {len(all_leads)} total leads")

        validated_candidates = []

        for lead_data in all_leads:
            try:
                # Structural validation: ensure required fields exist and sources are valid
                if not self.is_valid_lead(lead_data):
                    self._log("DEBUG", f"Skipping invalid lead (failed structural checks): {lead_data.get('full_name', 'Unknown')}")
                    continue

                # Construct Candidate model (keeps the same fields as in CLI)
                candidate = Candidate(**lead_data)

                # Deterministic evidence validation - core anti-hallucination mechanism
                is_valid, validated_url, evidence_snippet = self.validate_candidate_evidence(candidate)

                if is_valid:
                    # Update the candidate with validation results
                    candidate.validated_url = validated_url
                    candidate.evidence_snippet = evidence_snippet
                    candidate.validated_at = datetime.utcnow().isoformat()

                    # Keep the candidate (use dict representation like CLI)
                    validated_candidates.append(candidate.model_dump())
                    self._log("INFO", f"✅ Validated: {candidate.full_name} - {candidate.current_title}")
                else:
                    self._log("WARNING", f"❌ Evidence validation failed: {candidate.full_name}")
                    # do not add to validated list; continue to next lead
                    continue

            except Exception as err:
                # Keep iterating on errors; log them for debugging
                self._log("ERROR", f"Error validating candidate: {err}")
                continue

        # Deduplicate candidates (same logic as CLI: name + company)
        deduplicated = self.deduplicate_candidates(validated_candidates)

        # Update state with validated results and reflect sufficiency
        state["validated_candidates"] = deduplicated
        state["is_sufficient"] = len(deduplicated) >= state.get("target_count", TARGET_COUNT)

        self._log("INFO", f"Validated {len(deduplicated)} unique candidates")

        return state


    def deduplicate_candidates(self, candidates: List[dict]) -> List[dict]:
        """Remove duplicates by name and company."""
        seen = set()
        unique = []
        
        for candidate in candidates:
            key = (candidate["full_name"].lower(), candidate["current_company"].lower())
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        
        return unique

    def reflect_and_plan_followup(self, state: OverallState) -> OverallState:
        """Reflect and plan follow-up queries."""
        validated = state.get("validated_candidates", [])
        target = state.get("target_count", TARGET_COUNT)
        
        if len(validated) >= target:
            state["is_sufficient"] = True
            return state
        
        reflection_prompt = f"""
        Research strategist reviewing results.

        Results: {len(validated)}/{target} validated candidates
        
        Found:
        {json.dumps([{
            "name": c["full_name"], 
            "title": c["current_title"], 
            "company": c["current_company"],
            "source": c.get("source_type", "unknown")
        } for c in validated[:10]], indent=2)}

        Requirements: {state.get("dynamic_prompt", "")}

        Analyze:
        1. Gaps in candidate pool
        2. New search strategies
        3. Specific follow-up queries

        Return JSON:
        {{
            "coverage_gaps": ["gap1", "gap2"],
            "follow_up_queries": [
                {{
                    "query": "query",
                    "intent": "intent",
                    "expected_sources": ["type"],
                    "search_mode": "apollo" or "web"
                }}
            ],
            "reflection_notes": "analysis"
        }}
        
        ONLY JSON object.
        """

        try:
            config = GenerateContentConfig(
                temperature=TEMPERATURE + 0.1,
                top_k=TOP_K,
                top_p=TOP_P
            )
            
            response = self._generate_content_with_fallback(contents=reflection_prompt, config=config)
            response_text = response.text if hasattr(response, 'text') else str(response)
            reflection = self._extract_json_from_text(response_text, "object")
            
            # Defensive: model might return a list; handle gracefully
            if isinstance(reflection, list):
                reflection = reflection[0] if reflection else {}
            if not isinstance(reflection, dict):
                reflection = {}

            state["coverage_gaps"] = reflection.get("coverage_gaps", [])
            state["follow_up_queries"] = reflection.get("follow_up_queries", [])
            state["reflection_notes"] = reflection.get("reflection_notes", "")
            
            self._log("INFO", f"Reflection: {len(state['coverage_gaps'])} gaps identified")
            
        except Exception as err:
            self._log("ERROR", f"Reflection failed: {err}")
            state["coverage_gaps"] = []
            state["follow_up_queries"] = []
            state["reflection_notes"] = "Failed"
        
        return state

    def should_continue(self, state: OverallState) -> str:
        """Check if research should continue."""
        if not self.continue_running:
            return "finalize"
        
        if state.get("is_sufficient", False):
            return "finalize"
        
        if state.get("research_loop_count", 0) >= state.get("max_research_loops", MAX_LOOPS):
            return "finalize"
        
        elapsed = time.time() - state.get("start_time", time.time())
        if elapsed > TIME_BUDGET_SEC:
            return "finalize"
        
        # If there are no follow-up queries and we haven't reached targets, stop.
        if not state.get("follow_up_queries", []):
            return "finalize"
        
        return "continue_research"

    def save_candidates_to_supabase(self, candidates: List[dict], jd_id: str, user_id: str) -> bool:
        """Save validated candidates to Supabase."""
        if not candidates:
            self._log("WARNING", "No candidates to save")
            return True
        
        self._log("INFO", f"Saving {len(candidates)} candidates")
        
        rows = []
        now = datetime.utcnow().isoformat()
        
        for candidate in candidates:
            # Build summary with source type
            source_type = candidate.get("source_type", "web")
            summary_parts = [
                f"Source Type: {source_type.upper()}",
                f"Location: {candidate['location']}"
            ]
            
            if source_type == "apollo":
                if candidate.get("apollo_id"):
                    summary_parts.append(f"Apollo ID: {candidate['apollo_id']}")
                if candidate.get("linkedin_url"):
                    summary_parts.append(f"LinkedIn: {candidate['linkedin_url']}")
            else:
                summary_parts.append(f"Source URL: {candidate.get('validated_url', 'N/A')}")
            
            summary_parts.extend([
                f"Discovered by: {candidate.get('discovered_by_query', 'N/A')}",
                f"Validated at: {candidate.get('validated_at', 'N/A')}",
                "",
                candidate['notes'],
                "",
                f"Evidence: {candidate.get('evidence_snippet', 'N/A')}"
            ])
            
            row = {
                "profile_id": str(uuid.uuid4()),
                "user_id": user_id,
                "jd_id": jd_id,
                "profile_name": candidate["full_name"],
                "company": candidate["current_company"],
                "role": candidate["current_title"],
                "profile_url": candidate.get("validated_url") or candidate.get("linkedin_url"),
                "email": candidate.get("email"),
                "phone": candidate.get("phone"),
                "summary": "\n".join(summary_parts),
                "created_at": now,
            }
            rows.append(row)
        
        try:
            result = self.supabase.table("search").insert(rows).execute()
            
            if result.data:
                self._log("INFO", f"✅ Saved {len(result.data)} candidates")
                for i, c in enumerate(candidates, 1):
                    source = c.get('source_type', 'unknown').upper()
                    self._log("INFO", f"   {i}. {c['full_name']} ({source})")
                return True
            else:
                self._log("ERROR", "No data returned")
                return False
            
        except Exception as err:
            self._log("ERROR", f"Save failed: {err}")
            
            # Try individual saves
            self._log("INFO", "Trying individual saves...")
            saved = 0
            
            for row in rows:
                try:
                    individual = self.supabase.table("search").insert([row]).execute()
                    if individual.data:
                        saved += 1
                        self._log("INFO", f"✅ Saved: {row['profile_name']}")
                except Exception as e:
                    self._log("ERROR", f"❌ Failed: {row['profile_name']}")
            
            if saved > 0:
                self._log("INFO", f"✅ Saved {saved}/{len(rows)} individually")
                return True
            else:
                self._log("ERROR", "❌ Failed to save any")
                return False

    def build_graph(self) -> StateGraph:
        """Build the research workflow graph."""
        graph = StateGraph(OverallState)
        
        def fanout_research(state: OverallState):
            """Fan out to multiple research queries."""
            queries = state.get("search_queries", [])
            sends = []
            
            for i, query_data in enumerate(queries):
                sends.append(Send("route_search", {
                    **state,
                    "query_data": query_data,
                    "query_index": i  # numeric index
                }))
            
            return sends
        
        def fanout_followup(state: OverallState):
            """Fan out to follow-up queries (pass numeric indices)."""
            follow_ups = state.get("follow_up_queries", [])
            sends = []
            
            for i, query_data in enumerate(follow_ups):
                sends.append(Send("route_search", {
                    **state,
                    "query_data": query_data,
                    "query_index": i  # pass integer index, not "followup_{i}"
                }))
            
            return sends
        
        def increment_loop(state: OverallState) -> OverallState:
            """Increment loop counter."""
            state["research_loop_count"] = state.get("research_loop_count", 0) + 1
            return state
        
        def finalize_results(state: OverallState) -> OverallState:
            """Finalize results."""
            state["final_candidates"] = state.get("validated_candidates", [])
            return state
        
        # Add nodes
        graph.add_node("generate_queries", self.generate_queries)
        graph.add_node("route_search", self.route_search)
        graph.add_node("validate_and_aggregate", self.validate_and_aggregate)
        graph.add_node("reflect_and_plan_followup", self.reflect_and_plan_followup)
        graph.add_node("increment_loop", increment_loop)
        graph.add_node("finalize_results", finalize_results)
        
        # Add edges
        graph.add_edge(START, "generate_queries")
        graph.add_conditional_edges("generate_queries", fanout_research, ["route_search"])
        graph.add_edge("route_search", "validate_and_aggregate")
        graph.add_edge("validate_and_aggregate", "reflect_and_plan_followup")
        graph.add_conditional_edges("reflect_and_plan_followup", self.should_continue, {
            "continue_research": "increment_loop",
            "finalize": "finalize_results"
        })
        graph.add_conditional_edges("increment_loop", fanout_followup, ["route_search"])
        graph.add_edge("finalize_results", END)
        
        return graph

    def run_deep_research(self, jd_id: str, search_mode: SearchMode, custom_prompt: str = "", user_id: str = None) -> None:
        """Non-interactive main execution loop.

        Parameters:
        - jd_id: job description identifier (string)
        - search_mode: SearchMode enum value
        - custom_prompt: optional prompt for the search
        - user_id: optional user identifier (falls back to SUPABASE_USER_ID env var)
        """
        print("=" * 70)
        print("🚀 ENHANCED DEEP RESEARCH AGENT WITH APOLLO INTEGRATION (NON-INTERACTIVE)")
        print("=" * 70)
        print("🎯 Gemini 2.5 Pro Quality")
        print("🔍 Evidence-based validation")
        print("🌐 Apollo API + Web Search")
        print("🔄 Fixed 3 iterations (non-interactive)")
        print("🚫 Excludes founders, owners, duplicates")
        print("✅ Apollo max results per search:", APOLLO_MAX_RESULTS_PER_SEARCH)
        print()

        # Validate Apollo availability for APOLLO_ONLY mode
        if search_mode == SearchMode.APOLLO_ONLY and not self.apollo_client:
            self._log("ERROR", "APOLLO_API_KEY required for Apollo-only mode")
            print("❌ Apollo API key required for Apollo-only mode")
            return

        # Validate/resolve user_id
        resolved_user_id = user_id or os.getenv("SUPABASE_USER_ID")
        if not resolved_user_id:
            self._log("ERROR", "SUPABASE_USER_ID must be provided either as an argument or environment variable")
            print("❌ SUPABASE_USER_ID must be set (or passed as user_id argument)")
            return

        # Fetch JD from Supabase
        jd_data = self.fetch_jd_from_supabase(jd_id)
        if not jd_data:
            self._log("ERROR", f"Could not retrieve JD for id: {jd_id}")
            print("❌ Could not retrieve JD")
            return

        print(f"\n📋 JD: {str(jd_data.get('jd_parsed_summary', ''))[:200]}...")

        # Initialize tracking
        all_saved = []
        total_found = 0
        apollo_count = 0
        web_count = 0

        # Run exactly 3 iterations
        for iteration in range(1, 4):
            if not self.continue_running:
                self._log("INFO", f"Stopping before iteration {iteration} due to signal")
                break

            print(f"\n{'=' * 70}")
            print(f"🔄 ITERATION {iteration} - Mode: {search_mode.value.upper()}")
            print(f"{'=' * 70}")

            # For non-interactive runs we use the provided search_mode for all iterations.
            per_iteration_custom_prompt = custom_prompt or ""

            # Build exclusions based on already saved candidates
            exclusion_names = [c["full_name"].lower() for c in all_saved]
            exclusion_companies = [c["current_company"].lower() for c in all_saved]

            self._log("INFO", f"🚫 Excluding {len(exclusion_names)} previous candidates")
            self._log("INFO", f"🎯 Starting iteration {iteration}...")

            # Initialize state
            initial_state: OverallState = {
                "jd_data": jd_data,
                "custom_prompt": per_iteration_custom_prompt,
                "user_id": resolved_user_id,
                "jd_id": jd_id,
                "search_mode": search_mode.value,
                "research_loop_count": 0,
                "max_research_loops": MAX_LOOPS,
                "is_sufficient": False,
                "start_time": time.time(),
                "per_query_max": PER_QUERY_MAX,
                "target_count": TARGET_COUNT,
                "leads": [],
                "validated_candidates": [],
                "final_candidates": [],
                "iteration_count": iteration,
                "exclusion_names": exclusion_names,
                "exclusion_companies": exclusion_companies
            }

            try:
                # Reset model selection for the iteration
                self.current_model_index = 0
                self._log("INFO", f"Using model: {self._get_current_model()}")

                # Build and run graph
                graph = self.build_graph()
                compiled = graph.compile()

                self._log("INFO", f"🚀 Starting iteration {iteration}")
                final_state = compiled.invoke(initial_state)

                # Get results
                iteration_candidates = final_state.get("final_candidates", [])

                if iteration_candidates:
                    iter_apollo = sum(1 for c in iteration_candidates if c.get("source_type") == "apollo")
                    iter_web = len(iteration_candidates) - iter_apollo

                    # Save to Supabase
                    success = self.save_candidates_to_supabase(iteration_candidates, jd_id, resolved_user_id)
                    if success:
                        all_saved.extend(iteration_candidates)
                        total_found += len(iteration_candidates)
                        apollo_count += iter_apollo
                        web_count += iter_web
                        print(f"\n✅ Iteration {iteration}: {len(iteration_candidates)} new (Apollo: {iter_apollo}, Web: {iter_web})")
                    else:
                        print(f"\n❌ Iteration {iteration}: Save failed")
                else:
                    print(f"\n⚠️ Iteration {iteration}: No new candidates")

                # Summary for iteration
                elapsed = time.time() - initial_state["start_time"]
                print(f"\n📊 ITERATION {iteration} COMPLETED")
                print(f"{'=' * 60}")
                print(f"New this iteration: {len(iteration_candidates)}")
                print(f"Total all iterations: {total_found}")
                print(f"  • Apollo: {apollo_count}")
                print(f"  • Web: {web_count}")
                print(f"Loops: {final_state.get('research_loop_count', 0)}")
                print(f"Time: {elapsed:.1f}s")

                if iteration_candidates:
                    print(f"\n👥 New candidates (iteration {iteration}):")
                    for i, c in enumerate(iteration_candidates[:10], 1):
                        source = c.get('source_type', 'unknown').upper()
                        print(f"   {i}. {c['full_name']} - {c['current_title']} [{source}]")
                        print(f"      {c['current_company']}")

                # Highly visible iteration completion log (required)
                print("="*25 + f" ITERATION {iteration} DONE " + "="*25)

                # small pause to avoid hammering APIs immediately
                time.sleep(1)

            except KeyboardInterrupt:
                self._log("INFO", f"Interrupted during iteration {iteration}")
                break
            except Exception as err:
                self._log("ERROR", f"Iteration {iteration} error: {err}")
                print(f"\n❌ Iteration {iteration} failed: {err}")
                # In non-interactive mode, do not prompt — log and continue to next iteration
                continue

        # Final summary
        print(f"\n🎉 FINAL SUMMARY")
        print(f"{'=' * 70}")
        print(f"Mode: {search_mode.value.upper()}")
        print(f"Iterations: {min(3, max(0, iteration))}")
        print(f"Total candidates: {total_found}")
        if total_found > 0:
            print(f"  • Apollo: {apollo_count} ({apollo_count/max(1, total_found)*100:.1f}%)")
            print(f"  • Web: {web_count} ({web_count/max(1, total_found)*100:.1f}%)")
            print(f"Avg per iteration: {total_found/max(1, min(3, iteration)):.1f}")
        else:
            print("No candidates found in the 3 iterations.")

        if all_saved:
            print(f"\n👥 All unique candidates:")
            for i, c in enumerate(all_saved[:20], 1):
                source = c.get('source_type', 'unknown').upper()
                print(f"   {i}. {c['full_name']} - {c['current_title']} [{source}]")
                print(f"      {c['current_company']}")
            if len(all_saved) > 20:
                print(f"   ... and {len(all_saved) - 20} more")

        print(f"\n✅ Research completed!")
        print(f"📊 {total_found} candidates saved to Supabase")
        print(f"🚫 Zero duplicates, founders, or owners (filtered)")
        print(f"✅ Evidence-validated profiles")

def main() -> None:
    """Entry point for non-interactive execution via environment variables."""
    try:
        # Read parameters from environment for non-interactive runs.
        jd_id = os.getenv("RUN_JD_ID") or os.getenv("JD_ID")
        smode = (os.getenv("RUN_SEARCH_MODE") or os.getenv("SEARCH_MODE") or "apollo_and_web").lower()
        custom_prompt = os.getenv("RUN_CUSTOM_PROMPT") or os.getenv("CUSTOM_PROMPT") or ""
        user_id = os.getenv("SUPABASE_USER_ID") or os.getenv("RUN_USER_ID")

        if not jd_id:
            print("❌ RUN_JD_ID (or JD_ID) environment variable is required for non-interactive execution.")
            sys.exit(1)

        # Map smode to SearchMode
        if smode in ("1", "apollo_only", "apollo-only"):
            search_mode = SearchMode.APOLLO_ONLY
        else:
            search_mode = SearchMode.APOLLO_AND_WEB

        agent = EnhancedDeepResearchAgent(search_mode=search_mode)
        agent.run_deep_research(jd_id=jd_id, search_mode=search_mode, custom_prompt=custom_prompt, user_id=user_id)
    except Exception as exc:
        print(f"❌ Configuration error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
