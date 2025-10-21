
"""
Professional-Grade Profile Ranking Script (CLI Version)
Ranks candidates for a specific Job Description ID provided via the command line.
"""

import os
import uuid
import json
import asyncio
import logging
import re
import argparse ### CLI UPDATE ###: Import argparse for command-line arguments
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv
from supabase import create_client, Client

# Use the correct, modern imports
from google import genai
from google.genai import types

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

@dataclass
class Config:
    """Configuration management with validation."""
    supabase_url: str
    supabase_key: str
    user_id: str
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-pro-latest"
    batch_size: int = 3
    max_retries: int = 3
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables."""
        required_vars = ["SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_USER_ID", "GEMINI_API_KEY"]
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")
        
        return cls(
            supabase_url=os.environ["SUPABASE_URL"],
            supabase_key=os.environ["SUPABASE_KEY"],
            user_id=os.environ["SUPABASE_USER_ID"],
            gemini_api_key=os.environ["GEMINI_API_KEY"],
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-pro-latest")
        )


class ProfileRanker:
    """Main profile ranking class using a professional-grade evaluation process."""
    
    # Add this new method inside the ProfileRanker class in ranker.py
    async def run_ranking_for_api(self, jd_id: str):
        """
        Non-interactive version of the run method for API calls.
        """
        logger.info(f"API-triggered ranking process starting for JD ID: {jd_id}")
        
        # Step 1: Validate the JD ID exists
        jd_check = self.supabase.table("jds").select("jd_id").eq("jd_id", jd_id).execute()
        if not jd_check.data:
            error_msg = f"Validation failed for ranking: No Job Description found with ID '{jd_id}'."
            logger.error(error_msg)
            # Return an empty list or raise an exception if the JD doesn't exist
            return []

        # Step 2: Get all unranked candidates for this specific JD
        candidates = await self.get_unranked_candidates(jd_id=jd_id)
        if not candidates:
            logger.info(f"No new candidates to rank for JD ID: {jd_id}.")
            return
        
        # Step 3: Process the found candidates in batches
        results = await self.process_candidates_batch(candidates)
        
        logger.info(f"API-triggered ranking complete for JD ID: {jd_id}. Processed {len(results)} candidates.")
    
    def __init__(self, config: Config):
        self.config = config
        self.supabase = create_client(config.supabase_url, config.supabase_key)
        self.client = genai.Client(api_key=config.gemini_api_key)
        logger.info(f"Initialized Professional Ranker with model: {config.gemini_model}")

    # ### CLI UPDATE ###: Method now requires a jd_id to filter queries
    async def get_unranked_candidates(self, jd_id: str) -> List[Dict]:
        """Fetches unranked candidates for a specific jd_id."""
        try:
            logger.info(f"Fetching candidates for JD ID: {jd_id}...")
            
            # Filter all queries by the provided jd_id
            resumes_response = self.supabase.table("resume").select("...").eq("jd_id", jd_id).execute()
            searches_response = self.supabase.table("search").select("...").eq("jd_id", jd_id).execute()
            ranked_response = self.supabase.table("ranked_candidates").select("profile_id").eq("jd_id", jd_id).execute()
            
            resumes = resumes_response.data if resumes_response.data else []
            searches = searches_response.data if searches_response.data else []
            ranked_ids = {r["profile_id"] for r in ranked_response.data} if ranked_response.data else set()
            
            logger.info(f"Found {len(resumes)} resumes, {len(searches)} searches. {len(ranked_ids)} candidates are already ranked for this JD.")
            
            candidates = []
            for r in resumes:
                if r["resume_id"] not in ranked_ids:
                    candidates.append({"jd_id": r["jd_id"], "profile_id": r["resume_id"], "person_name": r.get("person_name"), "role": r.get("role"), "company": r.get("company"), "summary": r.get("json_content"), "source": "resume"})
            for s in searches:
                if s["profile_id"] not in ranked_ids:
                    candidates.append({"jd_id": s["jd_id"], "profile_id": s["profile_id"], "person_name": s.get("profile_name"), "role": s.get("role"), "company": s.get("company"), "summary": s.get("summary"), "source": "search"})
            
            logger.info(f"Found {len(candidates)} unranked candidates for this JD.")
            return candidates
        except Exception as e:
            logger.error(f"Error fetching candidates: {e}")
            return []
    
    def format_candidate_data(self, candidate: Dict) -> str:
        """Formats candidate data for the prompt."""
        # This function remains the same
        parts = []
        if candidate.get("person_name"): parts.append(f"Name: {candidate['person_name']}")
        if candidate.get("role"): parts.append(f"Role: {candidate['role']}")
        if candidate.get("company"): parts.append(f"Company: {candidate['company']}")
        
        summary_content = candidate.get("summary")
        if candidate["source"] == "resume" and summary_content:
            try:
                json_data = json.loads(summary_content) if isinstance(summary_content, str) else summary_content
                if isinstance(json_data, dict):
                    if "skills" in json_data: parts.append(f"Skills: {json_data['skills']}")
                    if "experience" in json_data:
                        exp = json_data["experience"]
                        exp_text = "; ".join([str(e) for e in exp]) if isinstance(exp, list) else str(exp)
                        parts.append(f"Experience: {exp_text}")
                    if "education" in json_data: parts.append(f"Education: {json_data['education']}")
            except (json.JSONDecodeError, TypeError):
                parts.append(f"Summary: {str(summary_content)}")
        elif summary_content:
            parts.append(f"Summary: {str(summary_content)}")
        
        return "\n".join(parts) if parts else "Limited profile information"

    def parse_llm_response(self, response_text: str) -> Tuple[float, str]:
        """Parse the detailed LLM response and format it for storage."""
        # This function remains the same
        if not response_text:
            return 0.0, "Error: No response from LLM"
        
        try:
            cleaned_text = re.sub(r'```json\n|```', '', response_text).strip()
            parsed = json.loads(cleaned_text)
            
            match_score = float(parsed.get("match_score", 0.0))
            verdict = parsed.get("verdict", "N/A")
            strengths = parsed.get("strengths", [])
            weaknesses = parsed.get("weaknesses", [])
            reasoning = parsed.get("reasoning", "No reasoning provided.")

            strengths_str = "\n".join([f"- {s}" for s in strengths]) if strengths else "None identified."
            weaknesses_str = "\n".join([f"- {w}" for w in weaknesses]) if weaknesses else "None identified."

            formatted_summary = (
                f"**Verdict:** {verdict}\n\n"
                f"**Strengths:**\n{strengths_str}\n\n"
                f"**Weaknesses/Gaps:**\n{weaknesses_str}\n\n"
                f"**Reasoning:**\n{reasoning}"
            )
            
            return max(0.0, min(100.0, match_score)), formatted_summary

        except Exception as e:
            logger.error(f"Error parsing detailed LLM response: {e}")
            return 0.0, f"Error parsing response: {str(e)}"

    async def rank_candidate(self, candidate: Dict) -> Optional[Dict]:
        """Ranks a candidate using a multi-step, chain-of-thought process."""
        # This function remains the same
        for attempt in range(self.config.max_retries):
            try:
                jd_response = self.supabase.table("jds").select("*").eq("jd_id", candidate["jd_id"]).execute()
                if not jd_response.data:
                    logger.error(f"JD not found for candidate {candidate['profile_id']}")
                    return None
                
                jd = jd_response.data[0]
                candidate_details = self.format_candidate_data(candidate)

                prompt = f"""
You are an expert technical recruiter with 20 years of experience. Your task is to provide a highly accurate and professional evaluation of a candidate for a job opening.

**Evaluation Process (Follow these steps meticulously):**

**Step 1: Detailed Analysis**
First, conduct a thorough, step-by-step analysis of the candidate's profile against the job description. Do not produce the final JSON yet. Mentally evaluate the following:
- Core skills alignment: How well do the candidate's listed skills match the required skills?
- Experience relevance: Is their work experience directly relevant to the role? Consider titles, companies, and responsibilities.
- Seniority match: Does the candidate's experience level (e.g., years, project complexity) align with the job's requirements?
- Educational background: Is their education relevant or noteworthy?

**Step 2: Synthesize Findings and Produce JSON Output**
Based on your detailed analysis from Step 1, now create a single JSON object with the following precise structure. Do not include any text outside of this JSON object.

**Job Description:**
- **Title:** {jd.get('title', 'N/A')}
- **Experience Required:** {jd.get('experience_required', 'N/A')}
- **Full Summary:** {jd.get('jd_parsed_summary', 'Not available')}

**Candidate Profile:**
{candidate_details}

**Required JSON Output Schema:**
{{
  "match_score": <A float between 0.0 and 100.0, representing the overall match quality. Be critical and precise.>,
  "verdict": "<A very short, one-sentence summary like 'Strong contender', 'Potential fit with gaps', or 'Poor fit'.>",
  "strengths": [
    "<A list of specific, evidence-based strengths, e.g., 'Direct experience with Python and AWS as required.'>",
    "<Another strength...>"
  ],
  "weaknesses": [
    "<A list of specific, evidence-based weaknesses or gaps, e.g., 'Lacks the required 5 years of management experience.'>",
    "<Another weakness...>"
  ],
  "reasoning": "<A detailed paragraph explaining *why* you arrived at the match_score, referencing the strengths and weaknesses you identified. Justify your conclusion logically.>"
}}
"""
                
                response = await self.client.aio.models.generate_content(
                    model=self.config.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.4,
                        max_output_tokens=4096,
                        response_mime_type="application/json"
                    )
                )

                if not response.candidates or response.candidates[0].finish_reason.name != 'STOP':
                    finish_reason_name = response.candidates[0].finish_reason.name if response.candidates else "UNKNOWN"
                    logger.warning(f"Skipping candidate {candidate['profile_id']} due to non-standard finish reason: {finish_reason_name}.")
                    return None
                
                response_text = response.text
                if not response_text:
                    raise Exception("Empty response from LLM despite successful generation")
                
                match_score, formatted_summary = self.parse_llm_response(response_text)
                
                if "Error" in formatted_summary:
                    raise Exception(formatted_summary)

                ranking_data = {"user_id": self.config.user_id, "jd_id": candidate["jd_id"], "profile_id": candidate["profile_id"], "rank": None, "match_score": match_score, "strengths": formatted_summary}
                
                self.supabase.table("ranked_candidates").insert(ranking_data).execute()
                logger.info(f"Professionally ranked {candidate['profile_id']}: {match_score:.1f}%")
                
                return {"profile_id": candidate["profile_id"], "match_score": match_score, "strengths": formatted_summary}
                
            except Exception as e:
                error_str = str(e)
                logger.warning(f"Attempt {attempt + 1} failed for {candidate['profile_id']}: {error_str}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(5)
                else:
                    logger.error(f"Failed to rank candidate {candidate['profile_id']} after {self.config.max_retries} attempts.")
                    try:
                        error_ranking = {"user_id": self.config.user_id, "jd_id": candidate["jd_id"], "profile_id": candidate["profile_id"], "rank": None, "match_score": 0.0, "strengths": f"Evaluation failed: {error_str[:500]}"}
                        self.supabase.table("ranked_candidates").insert(error_ranking).execute()
                    except Exception as db_error:
                        logger.error(f"Failed to save error ranking: {db_error}")
                    return None

    async def process_candidates_batch(self, candidates: List[Dict]) -> List[Dict]:
        """Processes candidates in smaller batches suitable for the powerful model."""
        # This function remains the same
        results = []
        for i in range(0, len(candidates), self.config.batch_size):
            batch = candidates[i:i + self.config.batch_size]
            logger.info(f"Processing batch {i//self.config.batch_size + 1} ({len(batch)} candidates)")
            tasks = [self.rank_candidate(candidate) for candidate in batch]
            batch_results = await asyncio.gather(*tasks)
            for result in batch_results:
                if result:
                    results.append(result)
            if i + self.config.batch_size < len(candidates):
                logger.info("Waiting 5s before next batch...")
                await asyncio.sleep(5)
        return results
    
    # ### CLI UPDATE ###: Run method now accepts a jd_id and validates it
    async def run(self, jd_id: str):
        """Main execution method for a specific jd_id."""
        try:
            logger.info(f"Starting professional ranking process for JD ID: {jd_id}")
            
            # Step 1: Validate the JD ID
            logger.info("Validating JD ID...")
            jd_check = self.supabase.table("jds").select("jd_id").eq("jd_id", jd_id).execute()
            if not jd_check.data:
                logger.error(f"Validation failed: No Job Description found with ID '{jd_id}'.")
                return

            logger.info("JD ID validated successfully.")
            
            # Step 2: Get unranked candidates for this specific JD
            candidates = await self.get_unranked_candidates(jd_id=jd_id)
            
            if not candidates:
                logger.info("No new candidates to process for this JD.")
                return
            
            # Step 3: Process the found candidates
            results = await self.process_candidates_batch(candidates)
            
            logger.info(f"Successfully processed {len(results)} out of {len(candidates)} candidates.")
            
            if results:
                avg_score = sum(r["match_score"] for r in results) / len(results)
                logger.info(f"Average match score for this batch: {avg_score:.1f}%")
            
        except Exception as e:
            logger.error(f"Fatal error in main process: {e}", exc_info=True)
            raise


async def main():
    """Main entry point: parses CLI arguments and runs the ranker."""
    # ### CLI UPDATE ###: Set up the command-line argument parser
    parser = argparse.ArgumentParser(description="Rank candidates for a specific Job Description.")
    parser.add_argument("jd_id", type=str, help="The UUID of the Job Description to process.")
    args = parser.parse_args()

    try:
        config = Config.from_env()
        ranker = ProfileRanker(config)
        # Pass the jd_id from the command line to the run method
        await ranker.run(jd_id=args.jd_id)
    except Exception as e:
        logger.error(f"Application failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)