import json
import os
import sys
import uuid
import time
import signal
import requests
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, TypedDict, Any
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

try:
    from supabase import create_client, Client
except ImportError:
    raise ImportError("Supabase client library not installed. Please run `pip install supabase`.")

try:
    import google.generativeai as genai
except ImportError:
    raise ImportError("Google GenAI library not installed. Please run `pip install google-generativeai`.")

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Send
except ImportError:
    raise ImportError("LangGraph not installed. Please run `pip install langgraph`.")

from app.config import settings

# --- Data Models (from test_searcher.py) ---
class Candidate(BaseModel):
    full_name: str = Field(..., description="Full name of the candidate")
    current_title: str = Field(..., description="Current job title")
    current_company: str = Field(..., description="Current company")
    source_url: str = Field(..., description="URL of the page where the candidate was found")
    evidence_snippet: Optional[str] = Field(None, description="A text snippet from the source page that supports the findings")

class SearchQuery(BaseModel):
    query: str = Field(..., description="A precise Google search query")
    description: str = Field(..., description="A brief explanation of what this query is looking for")

class OverallState(TypedDict, total=False):
    jd_id: str
    user_id: str
    input: str
    iterations: int
    max_iterations: int
    search_queries: Optional[List[dict]]
    current_query_index: int
    leads: Optional[List[dict]]
    all_time_candidates: List[dict]

# --- The Complete, Unabridged Agent Class ---
class DeepSearchAgent:
    def __init__(self):
        self.supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        genai.configure(api_key=settings.GEMINI_API_KEY)

        self.llm = genai.GenerativeModel(
            model_name="gemini-2.5-pro",
            generation_config={"response_mime_type": "application/json", "temperature": 0.3},
        )
        
        self.llm_with_search = genai.GenerativeModel(
            model_name="gemini-2.5-pro",
            tools=['google_search_retrieval'],
            generation_config={"temperature": 0.5},
        )

    def _log(self, message: str, **kwargs):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", kwargs if kwargs else "")

    def _extract_json_from_text(self, text: str, expected_type: str = "array"):
        text = text.strip()
        
        if expected_type == "array":
            json_start_index = text.find('[')
            json_end_index = text.rfind(']')
        else:
            json_start_index = text.find('{')
            json_end_index = text.rfind('}')

        if json_start_index == -1 or json_end_index == -1:
            return [] if expected_type == "array" else {}

        json_str = text[json_start_index : json_end_index + 1]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            self._log(f"JSON decoding failed: {e}. Raw text: '{text}'")
            return [] if expected_type == "array" else {}


    def fetch_jd_from_supabase(self, jd_id: str) -> str:
        res = self.supabase.table("jds").select("jd_parsed_summary").eq("jd_id", jd_id).single().execute()
        if not res.data or not res.data.get("jd_parsed_summary"):
            raise ValueError(f"Could not find a parsed summary for JD with id {jd_id}.")
        return res.data["jd_parsed_summary"]

    def url_ok(self, url: str) -> bool:
        EXCLUDED_DOMAINS = [
            "linkedin.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com",
            "tiktok.com", "pinterest.com", "reddit.com", "wikipedia.org", "google.com",
            "github.com", "gitlab.com", "medium.com", "docs.google.com", "drive.google.com"
        ]
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and parsed.netloc and parsed.netloc not in EXCLUDED_DOMAINS
        except:
            return False

    def page_contains(self, text: str, needle: str, min_ratio: int = 85) -> bool:
        return fuzz.partial_ratio(needle.lower(), text.lower()) >= min_ratio

    def validate_candidate_evidence(self, candidate: Candidate) -> Optional[Candidate]:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(candidate.source_url, timeout=15, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            page_text = soup.get_text()

            name_found = self.page_contains(page_text, candidate.full_name)
            role_found = self.page_contains(page_text, candidate.current_title)
            company_found = self.page_contains(page_text, candidate.current_company)

            if name_found and (role_found or company_found):
                sentences = re.split(r'(?<=[.!?])\s+', page_text)
                for sentence in sentences:
                    if self.page_contains(sentence, candidate.full_name):
                         candidate.evidence_snippet = sentence.strip()
                         return candidate
                return candidate
        except requests.RequestException as e:
            self._log(f"Validation request failed for {candidate.full_name} at {candidate.source_url}: {e}")
        except Exception as e:
            self._log(f"General validation failed for {candidate.full_name}: {e}")
        return None

    def is_valid_lead(self, lead_data: dict) -> bool:
        return all(isinstance(lead_data.get(key), str) and lead_data.get(key) for key in ["full_name", "current_title", "current_company", "source_url"])

    def generate_queries(self, state: OverallState) -> dict:
        jd_summary = self.fetch_jd_from_supabase(state['jd_id'])
        prompt = f"""
        Based on the job description and user input, generate 5 diverse, creative, and precise Google search queries to find qualified candidates.

        Job Summary: {jd_summary}
        User Input: {state['input']}
        Previously found candidates to avoid: {', '.join([c.get('full_name', 'N/A') for c in state['all_time_candidates']])}
        
        Focus on queries uncovering personal websites, portfolios, conference speaker lists, or niche professional communities. AVOID LINKEDIN.
        Return a JSON array of objects, each with "query" and "description".
        """
        response = self.llm.generate_content(prompt)
        queries = self._extract_json_from_text(response.text)
        self._log(f"Generated {len(queries)} new search queries.")
        return {"search_queries": queries or [], "current_query_index": 0}

    def web_research(self, state: OverallState) -> dict:
        query_info = state["search_queries"][state["current_query_index"]]
        self._log(f"Researching query: '{query_info['query']}'")
        
        prompt = f"""
        Execute a web search for the query: '{query_info['query']}'.
        Thoroughly analyze the top 5-7 search results to identify potential candidates.
        Extract a list of individuals with their full name, current job title, current company, and the exact source URL where they were found.
        Exclude anyone with titles like 'Co-founder', 'Owner', 'Founder', 'CEO', or 'President'.
        Return ONLY a JSON array of candidate objects.
        """
        response = self.llm_with_search.generate_content(prompt)
        leads = self._extract_json_from_text(response.text)
        return {"leads": leads, "current_query_index": state["current_query_index"] + 1}

    def validate_and_aggregate(self, state: OverallState) -> dict:
        validated_candidates = []
        leads_to_process = state.get("leads", [])
        if not leads_to_process:
            self._log("No new leads to validate in this step.")
            # Important: still need to pass the existing candidates forward
            return {"all_time_candidates": state.get("all_time_candidates", [])}

        for lead in leads_to_process:
            if self.is_valid_lead(lead) and self.url_ok(lead['source_url']):
                candidate_obj = Candidate(**lead)
                validated = self.validate_candidate_evidence(candidate_obj)
                if validated:
                    validated_candidates.append(validated.model_dump())
        
        self._log(f"Validated {len(validated_candidates)} new candidates from this research step.")
        
        all_time_candidates = state.get("all_time_candidates", []) + validated_candidates
        return {"all_time_candidates": all_time_candidates}

    def deduplicate_candidates(self, candidates: List[dict]) -> List[dict]:
        unique_candidates = {}
        for candidate in candidates:
            key = (candidate['full_name'].lower().strip(), candidate['current_company'].lower().strip())
            if key not in unique_candidates:
                unique_candidates[key] = candidate
        return list(unique_candidates.values())

    def should_continue(self, state: OverallState) -> str:
        if state.get("current_query_index", 0) >= len(state.get("search_queries", [])):
            return "end"
        return "continue"

    def save_candidates_to_supabase(self, candidates: List[dict], jd_id: str, user_id: str):
        if not candidates:
            self._log("No candidates to save.")
            return
        
        unique_candidates = self.deduplicate_candidates(candidates)
        rows_to_insert = [
            {
                "profile_id": str(uuid.uuid4()),
                "jd_id": jd_id,
                "user_id": user_id,
                "profile_name": c['full_name'],
                "role": c['current_title'],
                "company": c['current_company'],
                "profile_url": c['source_url'],
                "summary": c.get('evidence_snippet', ''),
                "raw_profile_data": c
            } for c in unique_candidates
        ]
        
        try:
            self.supabase.table("search").insert(rows_to_insert).execute()
            self._log(f"Successfully saved {len(rows_to_insert)} unique candidates to the database.")
        except Exception as e:
            self._log(f"Error saving candidates to Supabase: {e}")

    def build_graph(self) -> StateGraph:
        graph = StateGraph(OverallState)
        graph.add_node("generate_queries", self.generate_queries)
        graph.add_node("web_research", self.web_research)
        graph.add_node("validate", self.validate_and_aggregate)

        graph.add_edge(START, "generate_queries")
        graph.add_edge("generate_queries", "web_research")
        graph.add_edge("web_research", "validate")
        
        graph.add_conditional_edges(
            "validate",
            self.should_continue,
            {"continue": "web_research", "end": END}
        )
        return graph

# --- Entry Point Function ---
def run_agent_for_jd(jd_id: str, user_id: str, custom_prompt: str):
    try:
        print(f"Starting deep search for JD: {jd_id} with prompt: '{custom_prompt}'")
        agent = DeepSearchAgent()
        initial_state = {
            "jd_id": jd_id, "user_id": user_id, "input": custom_prompt,
            "iterations": 0, "all_time_candidates": []
        }
        graph = agent.build_graph()
        app = graph.compile()
        
        final_state = app.invoke(initial_state, {"recursion_limit": 100})
        
        if final_state and final_state.get("all_time_candidates"):
            agent.save_candidates_to_supabase(final_state["all_time_candidates"], jd_id, user_id)
        
        print(f"Deep search for JD {jd_id} completed successfully.")
    except Exception as e:
        print(f"--- Deep Search Agent CRASHED for JD {jd_id} ---")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print("--- End of Agent Crash Report ---")

