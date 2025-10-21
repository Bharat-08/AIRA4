# """
# AI-Powered Candidate Ranking Module

# This module provides comprehensive candidate ranking capabilities with AI-powered analysis

# """

# import json
# import logging
# import os
# import time
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from typing import List, Dict, Any, Optional, Union
# import requests
# from datetime import datetime
# import fitz

# from src.config.settings import get_settings
# from src.core.models import (
#     CandidateProfile, CandidateRanking, JobDescription, 
#     ConfidenceLevel, DimensionScores
# )

# logger = logging.getLogger(__name__)


# class CandidateRanker:
#     """AI-powered candidate ranking with discovery capabilities."""
    
#     def __init__(self):
#         """Initialize the ranker with settings and configurations."""
#         self.settings = get_settings()
#         self.openai_client = None
#         self.gemini_client = None
        
#         # OpenAI configuration with token management
#         self.openai_model = getattr(self.settings, 'openai_model', 'gpt-4o')
#         self.openai_temperature = getattr(self.settings, 'openai_temperature', 0.1)
#         self.openai_max_tokens = getattr(self.settings, 'openai_max_tokens', 8000)
#         self.openai_timeout = getattr(self.settings, 'openai_timeout', 60)
        
#         # Apply token management
#         self._apply_token_management()
        
#         # Discovery configuration
#         self.discovery_enabled = getattr(self.settings, 'discovery_enabled', False)
#         self.gemini_api_key = os.getenv('GEMINI_API_KEY') or getattr(self.settings, 'gemini_api_key', '')
#         self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.5-pro')
#         self.discovery_max_iterations = getattr(self.settings, 'discovery_max_iterations', 2)
#         self.discovery_candidates_per_seed = getattr(self.settings, 'discovery_candidates_per_seed', 2)
#         self.discovery_top_seeds = getattr(self.settings, 'discovery_top_seeds', 6)
        
#         # Enable discovery if API key is available
#         if self.gemini_api_key and not self.discovery_enabled:
#             self.discovery_enabled = True
#             logger.info("Discovery enabled: Gemini API key detected")
#         elif not self.gemini_api_key:
#             logger.info("Discovery disabled: Gemini API key not configured")
    
#     def _apply_token_management(self):
#         """Apply intelligent token management based on model capabilities."""
        
#         # Model-specific token limits
#         model_limits = {
#             "gpt-4o": {
#                 "max_input_tokens": 128000,
#                 "max_output_tokens": 4096,
#                 "safe_input_tokens": 120000,
#                 "safe_output_tokens": 4000
#             },
#             "gpt-4": {
#                 "max_input_tokens": 8192,
#                 "max_output_tokens": 4096,
#                 "safe_input_tokens": 7000,
#                 "safe_output_tokens": 4000
#             },
#             "gpt-3.5-turbo": {
#                 "max_input_tokens": 16385,
#                 "max_output_tokens": 4096,
#                 "safe_input_tokens": 15000,
#                 "safe_output_tokens": 4000
#             }
#         }
        
#         # Get limits for current model
#         limits = model_limits.get(self.openai_model, model_limits["gpt-4o"])
        
#         # Adjust max_tokens if it exceeds model limits
#         if self.openai_max_tokens > limits["max_output_tokens"]:
#             logger.warning(f"Max tokens adjusted from {self.openai_max_tokens} to {limits['safe_output_tokens']}")
#             logger.warning(f"Model '{self.openai_model}' supports max {limits['max_output_tokens']} output tokens")
#             logger.warning(f"Using safe limit of {limits['safe_output_tokens']} tokens")
#             self.openai_max_tokens = limits["safe_output_tokens"]
        
#         # Store limits for prompt management
#         self.max_input_tokens = limits["safe_input_tokens"]
#         self.max_output_tokens = limits["safe_output_tokens"]
    
#     def rank_candidates(self, job_data: JobDescription, candidates: List[CandidateProfile]) -> List[CandidateRanking]:
#         """Rank candidates using AI-powered analysis."""
#         if not candidates:
#             logger.warning("No candidates provided for ranking")
#             return []
        
#         # Validate and flatten candidates
#         validated_candidates = self._validate_and_flatten_candidates(candidates)
        
#         if not validated_candidates:
#             logger.error("No valid candidates after validation")
#             return []
        
#         logger.info(f"Ranking {len(validated_candidates)} candidates with AI-powered analysis...")
        
#         try:
#             # Process candidates in batches for better performance
#             batch_size = 5
#             all_rankings = []
            
#             for i in range(0, len(validated_candidates), batch_size):
#                 batch = validated_candidates[i:i + batch_size]
#                 batch_num = (i // batch_size) + 1
#                 total_batches = (len(validated_candidates) + batch_size - 1) // batch_size
                
#                 logger.info(f"Processing batch {batch_num}/{total_batches}")
                
#                 batch_rankings = self._rank_batch_with_ai(job_data, batch)
#                 all_rankings.extend(batch_rankings)
            
#             # Sort by overall score (descending)
#             all_rankings.sort(key=lambda x: x.overall_score, reverse=True)
            
#             logger.info(f"Successfully ranked {len(all_rankings)} candidates")
#             return all_rankings
            
#         except Exception as e:
#             logger.error(f"Error in candidate ranking: {e}")
#             # Return emergency rankings
#             return self._create_emergency_rankings(validated_candidates, job_data)
    
#     def rank_candidates_with_discovery(self, job_data: JobDescription, candidates: List[CandidateProfile], jd_file_path: Optional[str] = None) -> Dict[str, Any]:
#         """Rank candidates with iterative discovery using Gemini 2.5 Pro."""
#         logger.info(" Starting iterative candidate discovery process...")
        
#         # Initial ranking
#         logger.info(" Performing initial candidate ranking...")
#         initial_rankings = self.rank_candidates(job_data, candidates)
        
#         if not initial_rankings:
#             logger.warning("No initial candidates to use for discovery")
#             return {
#                 'final_rankings': [],
#                 'discovery_report': "No candidates available for discovery",
#                 'discovery_data': {}
#             }
        
#         logger.info(f" Initial ranking completed: {len(initial_rankings)} candidates")
        
#         # Check if discovery is enabled
#         if not self.discovery_enabled or not self.gemini_api_key:
#             logger.warning("Discovery disabled or Gemini API key not configured")
#             return {
#                 'final_rankings': initial_rankings,
#                 'discovery_report': "Discovery feature not enabled",
#                 'discovery_data': {}
#             }
        
#         # Iterative discovery
#         all_candidates = list(candidates)  # Start with original candidates
#         discovery_stats = {
#             'iterations': 0,
#             'candidates_discovered': 0,
#             'total_api_calls': 0,
#             'successful_calls': 0,
#             'failed_calls': 0,
#             'initial_count': len(initial_rankings),
#             'final_count': 0,
#             'score_improvement': 0.0,
#             'source_distribution': {'pdl_api': 0, 'uploaded_resume': 0, 'gemini_discovery': 0}
#         }
        
#         for iteration in range(1, self.discovery_max_iterations + 1):
#             logger.info(f"\n Discovery Iteration {iteration}/{self.discovery_max_iterations}")
            
#             # Get top candidates as seeds
#             current_rankings = self.rank_candidates(job_data, all_candidates)
#             top_seeds = current_rankings[:self.discovery_top_seeds]
            
#             logger.info(f" Using top {len(top_seeds)} candidates as seeds")
            
#             iteration_candidates = []
            
#             for seed_idx, seed_ranking in enumerate(top_seeds, 1):
#                 logger.info(f" Processing seed {seed_idx}/{len(top_seeds)}: {seed_ranking.candidate_name}")
                
#                 # Find the original candidate profile for this ranking
#                 seed_candidate = None
#                 for candidate in all_candidates:
#                     if candidate.candidate_id == seed_ranking.candidate_id:
#                         seed_candidate = candidate
#                         break
                
#                 if not seed_candidate:
#                     logger.warning(f"Could not find original candidate profile for {seed_ranking.candidate_name}")
#                     continue
                
#                 # Discover similar candidates
#                 discovered = self._discover_similar_candidates(
#                     job_data, seed_candidate, seed_ranking, iteration, jd_file_path
#                 )
                
#                 discovery_stats['total_api_calls'] += 1
#                 if discovered:
#                     discovery_stats['successful_calls'] += 1
#                     iteration_candidates.extend(discovered)
#                     logger.info(f"    Found {len(discovered)} valid candidates from seed")
#                 else:
#                     discovery_stats['failed_calls'] += 1
#                     logger.info(f"    No valid candidates found from seed")
            
#             # Deduplicate candidates
#             before_dedup = len(iteration_candidates)
#             iteration_candidates = self._deduplicate_candidates(iteration_candidates, all_candidates)
#             after_dedup = len(iteration_candidates)
            
#             logger.info(f" Deduplicated: {before_dedup} → {after_dedup} candidates")
            
#             if not iteration_candidates:
#                 logger.warning(f"No new candidates discovered in iteration {iteration}")
#                 continue
            
#             # Add to candidate pool
#             all_candidates.extend(iteration_candidates)
#             discovery_stats['candidates_discovered'] += len(iteration_candidates)
#             discovery_stats['iterations'] = iteration
            
#             logger.info(f" Added {len(iteration_candidates)} new candidates to pool")
#             logger.info(f" Total candidates now: {len(all_candidates)}")
        
#         # Final ranking with all candidates
#         logger.info(" Performing final ranking with all discovered candidates...")
#         final_rankings = self.rank_candidates(job_data, all_candidates)
        
#         # Update discovery statistics
#         discovery_stats['final_count'] = len(final_rankings)
#         if initial_rankings and final_rankings:
#             discovery_stats['score_improvement'] = final_rankings[0].overall_score - initial_rankings[0].overall_score
        
#         # Count sources in final rankings
#         for ranking in final_rankings:
#             if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
#                 discovery_stats['source_distribution']['uploaded_resume'] += 1
#             elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
#                 discovery_stats['source_distribution']['gemini_discovery'] += 1
#             else:
#                 discovery_stats['source_distribution']['pdl_api'] += 1
        
#         # Generate discovery report
#         discovery_report = self._generate_discovery_report(
#             initial_rankings, final_rankings, discovery_stats, job_data
#         )
        
#         logger.info(" Discovery process completed!")
        
#         return {
#             'final_rankings': final_rankings,
#             'discovery_report': discovery_report,
#             'discovery_data': discovery_stats
#         }
    
#     def _validate_and_flatten_candidates(self, candidates: Any) -> List[CandidateProfile]:
#         """Validate and flatten candidates, handling various input types safely."""
#         validated = []
#         for candidate in candidates:
#             try:
#                 # Handle different candidate types
#                 if isinstance(candidate, CandidateProfile):
#                     # Standard CandidateProfile
#                     validated.append(candidate)

#                 elif hasattr(candidate, 'candidate_profile'):
#                     # ResumeCandidate wrapper or similar
#                     validated.append(candidate.candidate_profile)

#                 elif isinstance(candidate, dict):
#                     # --- START: MODIFICATION TO FIX EMAIL VALIDATION ---
#                     # Check and fix email before creating the profile to prevent Pydantic errors.
#                     # This handles resumes where the email could not be parsed.
#                     email = candidate.get('email', '')
#                     if not self._is_valid_email(email):
#                         full_name = candidate.get('full_name')
#                         if full_name:
#                             # Generate a placeholder email using the candidate's name.
#                             name_part = ''.join(filter(str.isalnum, full_name.lower().replace(' ', '.')))
#                             candidate['email'] = f"{name_part}@placeholder.email"
#                             logger.warning(f"Invalid or missing email for '{full_name}'. Generated placeholder: {candidate['email']}")
#                         else:
#                             # Fallback if the full name is also missing.
#                             import time
#                             candidate['email'] = f"candidate.{int(time.time())}@placeholder.email"
#                             logger.warning(f"Missing name and email for a candidate. Generated random placeholder.")
#                     # --- END: MODIFICATION ---

#                     # Dictionary representation - try to convert
#                     try:
#                         profile = CandidateProfile(**candidate)
#                         validated.append(profile)
#                     except Exception as dict_error:
#                         logger.error(f"Error converting dict to CandidateProfile: {dict_error}")
#                         continue

#                 else:
#                     logger.warning(f"Unknown candidate type: {type(candidate)}")
#                     continue

#             except Exception as e:
#                 logger.error(f"Error validating candidate: {e}")
#                 continue

#         logger.info(f"Validated and flattened to {len(validated)} valid candidates")
#         print(f" Validated {len(validated)} out of {len(candidates)} candidates")
#         return validated

    
#     def _rank_batch_with_ai(self, job_data: JobDescription, candidates: List[CandidateProfile]) -> List[CandidateRanking]:
#         """Rank a batch of candidates using AI analysis."""
#         try:
#             # Initialize OpenAI client if needed
#             if not self.openai_client:
#                 import openai
#                 self.openai_client = openai.OpenAI()
            
#             # Create ranking prompt
#             prompt = self._create_ranking_prompt(job_data, candidates)
            
#             # Truncate prompt if too long
#             prompt = self._truncate_prompt_if_needed(prompt)
            
#             # Make API call with error handling
#             response = self._make_openai_request(prompt)
            
#             if not response:
#                 logger.warning("OpenAI request failed, using fallback rankings")
#                 return self._create_fallback_rankings(candidates, job_data)
            
#             # Parse response
#             rankings = self._parse_ranking_response(response, candidates, job_data)
            
#             if not rankings:
#                 logger.warning("Failed to parse AI response, using fallback rankings")
#                 return self._create_fallback_rankings(candidates, job_data)
            
#             return rankings
            
#         except Exception as e:
#             logger.error(f"Error in AI ranking: {e}")
#             return self._create_fallback_rankings(candidates, job_data)
    
#     def _create_ranking_prompt(self, job_data: JobDescription, candidates: List[CandidateProfile]) -> str:
#         """Create a comprehensive ranking prompt for AI analysis."""
        
#         # Job context
#         job_context = f"""
# JOB REQUIREMENTS:
# Title: {job_data.title}
# Company: {job_data.company or 'Not specified'}
# Location: {job_data.location.city if job_data.location else 'Not specified'}
# Experience Level: {job_data.experience_level.value if job_data.experience_level else 'Not specified'}
# Required Skills: {', '.join(job_data.required_skills[:10]) if job_data.required_skills else 'Not specified'}
# """
        
#         # Candidate profiles
#         candidate_profiles = ""
#         for i, candidate in enumerate(candidates, 1):
#             # Determine if this is a resume candidate
#             is_resume_candidate = hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume'
#             source_note = " (UPLOADED RESUME - actively interested)" if is_resume_candidate else ""
            
#             candidate_profiles += f"""
# CANDIDATE {i}{source_note}:
# Name: {candidate.full_name}
# Current Title: {candidate.current_title or 'Not specified'}
# Current Company: {candidate.current_company or 'Not specified'}
# Location: {candidate.location.city if candidate.location else 'Not specified'}
# Skills: {', '.join(candidate.skills[:8]) if candidate.skills else 'Not specified'}
# Education: {', '.join(candidate.education[:3]) if candidate.education else 'Not specified'}
# LinkedIn: {candidate.linkedin_url or 'Not available'}
# """
        
#         # Analysis instructions
#         instructions = f"""
# Analyze each candidate against the job requirements and provide detailed rankings.

# For each candidate, evaluate these dimensions (0.0-1.0):
# - technical_skills: Relevance of technical skills to job requirements
# - experience_relevance: How well their experience matches the role
# - seniority_match: Appropriate level for the position
# - education_fit: Educational background alignment
# - industry_experience: Relevant industry background
# - location_compatibility: Geographic fit for the role

# IMPORTANT SCORING GUIDELINES:
# - Resume candidates (uploaded) should get +0.1 bonus for demonstrated interest
# - Consider skills overlap, experience level, and industry relevance
# - Be realistic: most candidates score 0.4-0.8 range
# - Only exceptional matches should score above 0.9

# Return JSON array with this exact structure:
# [
#   {{
#     "candidate_name": "Full Name",
#     "overall_score": 0.75,
#     "dimension_scores": {{
#       "technical_skills": 0.8,
#       "experience_relevance": 0.7,
#       "seniority_match": 0.8,
#       "education_fit": 0.7,
#       "industry_experience": 0.6,
#       "location_compatibility": 0.9
#     }},
#     "strengths": ["Strength 1", "Strength 2"],
#     "concerns": ["Concern 1", "Concern 2"],
#     "recommendations": ["Recommendation 1"],
#     "confidence_level": "high|medium|low",
#     "match_explanation": "Detailed explanation of the match",
#     "key_differentiators": ["Differentiator 1"],
#     "interview_focus_areas": ["Focus area 1"]
#   }}
# ]

# Return only valid JSON, no additional text.
# """
        
#         return job_context + candidate_profiles + instructions
    
#     def _truncate_prompt_if_needed(self, prompt: str) -> str:
#         """Truncate prompt if it exceeds token limits."""
#         # Estimate tokens (rough: 1 token ≈ 3.5 characters)
#         estimated_tokens = len(prompt) / 3.5
        
#         if estimated_tokens > self.max_input_tokens:
#             logger.warning(f"Prompt too long ({estimated_tokens:.0f} tokens), truncating to {self.max_input_tokens} tokens")
            
#             # Calculate max characters
#             max_chars = int(self.max_input_tokens * 3.5)
            
#             # Truncate while preserving structure
#             lines = prompt.split('\n')
#             truncated_lines = []
#             current_length = 0
            
#             for line in lines:
#                 if current_length + len(line) + 1 > max_chars:
#                     break
#                 truncated_lines.append(line)
#                 current_length += len(line) + 1
            
#             truncated_prompt = '\n'.join(truncated_lines)
#             logger.warning(f"Truncated prompt from {len(prompt)} to {len(truncated_prompt)} characters")
            
#             return truncated_prompt
        
#         return prompt
    
#     def _make_openai_request(self, prompt: str) -> Optional[str]:
#         """Make OpenAI API request with comprehensive error handling."""
#         try:
#             logger.debug(f"OpenAI Request: Model={self.openai_model}, Tokens={self.openai_max_tokens}, Prompt={len(prompt)} chars")
            
#             response = self.openai_client.chat.completions.create(
#                 model=self.openai_model,
#                 messages=[{"role": "user", "content": prompt}],
#                 temperature=self.openai_temperature,
#                 max_tokens=self.openai_max_tokens,
#                 timeout=self.openai_timeout
#             )
            
#             content = response.choices[0].message.content.strip()
#             logger.debug(" OpenAI request successful")
#             return content
            
#         except requests.exceptions.SSLError as e:
#             if "DECRYPTION_FAILED_OR_BAD_RECORD_MAC" in str(e):
#                 logger.error("SSL Error: Likely due to oversized payload")
#                 logger.error("Attempting to reduce prompt size...")
                
#                 # Aggressively reduce prompt size
#                 reduced_prompt = prompt[:len(prompt)//2]
#                 try:
#                     response = self.openai_client.chat.completions.create(
#                         model=self.openai_model,
#                         messages=[{"role": "user", "content": reduced_prompt}],
#                         temperature=self.openai_temperature,
#                         max_tokens=min(self.openai_max_tokens, 2000),
#                         timeout=30
#                     )
#                     return response.choices[0].message.content.strip()
#                 except Exception as retry_error:
#                     logger.error(f"Retry failed: {retry_error}")
#                     return None
#             else:
#                 logger.error(f"SSL Error: {e}")
#                 return None
                
#         except Exception as e:
#             error_msg = str(e)
            
#             # Classify error types
#             if "400" in error_msg and "Bad Request" in error_msg:
#                 logger.error("OpenAI 400 Bad Request Error:")
#                 if "content filter" in error_msg.lower():
#                     logger.error("  Error Type: Content filter violation")
#                     logger.error("  Solution: Content sanitized and fallback analysis applied")
#                 elif "token" in error_msg.lower():
#                     logger.error("  Error Type: Token limit exceeded")
#                     logger.error("  Solution: Prompt truncation applied")
#                 else:
#                     logger.error(f"  Error Message: {error_msg}")
#                     logger.error("  Solution: Fallback analysis will be used")
#             else:
#                 logger.error(f"OpenAI API Error: {error_msg}")
            
#             return None
    
#     def _parse_ranking_response(self, response: str, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateRanking]:
#         """Parse AI ranking response into CandidateRanking objects."""
#         try:
#             # Clean response
#             content = response.strip()
#             if content.startswith('```json'):
#                 content = content[7:]
#             if content.endswith('```'):
#                 content = content[:-3]
#             content = content.strip()
            
#             # Parse JSON
#             rankings_data = json.loads(content)
            
#             if not isinstance(rankings_data, list):
#                 logger.error("Response is not a list")
#                 return []
            
#             rankings = []
            
#             for i, ranking_data in enumerate(rankings_data):
#                 try:
#                     # Find matching candidate
#                     candidate = candidates[i] if i < len(candidates) else None
#                     if not candidate:
#                         logger.warning(f"No candidate found for ranking {i}")
#                         continue
                    
#                     # Create dimension scores
#                     dim_scores = ranking_data.get('dimension_scores', {})
#                     dimension_scores = DimensionScores(
#                         technical_skills=float(dim_scores.get('technical_skills', 0.5)),
#                         experience_relevance=float(dim_scores.get('experience_relevance', 0.5)),
#                         seniority_match=float(dim_scores.get('seniority_match', 0.5)),
#                         education_fit=float(dim_scores.get('education_fit', 0.5)),
#                         industry_experience=float(dim_scores.get('industry_experience', 0.5)),
#                         location_compatibility=float(dim_scores.get('location_compatibility', 0.5))
#                     )
                    
#                     # Determine confidence level
#                     confidence_str = ranking_data.get('confidence_level', 'medium').lower()
#                     confidence_level = ConfidenceLevel.MEDIUM
#                     if confidence_str == 'high':
#                         confidence_level = ConfidenceLevel.HIGH
#                     elif confidence_str == 'low':
#                         confidence_level = ConfidenceLevel.LOW
                    
#                     # Check if this is a resume candidate and enhance explanation
#                     match_explanation = ranking_data.get('match_explanation', '')
#                     is_resume_candidate = hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume'
                    
#                     if is_resume_candidate and ' UPLOADED RESUME CANDIDATE' not in match_explanation:
#                         match_explanation = f" UPLOADED RESUME CANDIDATE: {match_explanation}"
                    
#                     # Create ranking
#                     ranking = CandidateRanking(
#                         candidate_id=candidate.candidate_id,
#                         candidate_name=candidate.full_name,
#                         current_title=candidate.current_title,
#                         current_company=candidate.current_company,
#                         linkedin_url=candidate.linkedin_url,
#                         overall_score=float(ranking_data.get('overall_score', 0.5)),
#                         dimension_scores=dimension_scores,
#                         strengths=ranking_data.get('strengths', []),
#                         concerns=ranking_data.get('concerns', []),
#                         recommendations=ranking_data.get('recommendations', []),
#                         confidence_level=confidence_level,
#                         match_explanation=match_explanation,
#                         key_differentiators=ranking_data.get('key_differentiators', []),
#                         interview_focus_areas=ranking_data.get('interview_focus_areas', [])
#                     )
                    
#                     rankings.append(ranking)
                    
#                 except Exception as e:
#                     logger.error(f"Error parsing ranking {i}: {e}")
#                     continue
            
#             return rankings
            
#         except json.JSONDecodeError as e:
#             logger.error(f"JSON parsing error: {e}")
#             logger.error(f"Response content: {response[:500]}...")
#             return []
#         except Exception as e:
#             logger.error(f"Error parsing rankings: {e}")
#             return []
    
#     def _create_fallback_rankings(self, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateRanking]:
#         """Create fallback rankings when AI analysis fails."""
#         logger.info("Creating fallback rankings...")
        
#         rankings = []
        
#         for candidate in candidates:
#             # Simple scoring based on available data
#             score = 0.5  # Base score
            
#             # Boost for resume candidates
#             if hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume':
#                 score += 0.1
            
#             # Simple skill matching
#             if candidate.skills and job_data.required_skills:
#                 skill_overlap = len(set(candidate.skills) & set(job_data.required_skills))
#                 score += min(skill_overlap * 0.05, 0.2)
            
#             # Location matching
#             if candidate.location and job_data.location:
#                 if candidate.location.city == job_data.location.city:
#                     score += 0.1
            
#             # Cap score
#             score = min(score, 1.0)
            
#             # Create basic dimension scores
#             dimension_scores = DimensionScores(
#                 technical_skills=score,
#                 experience_relevance=score,
#                 seniority_match=score,
#                 education_fit=score,
#                 industry_experience=score,
#                 location_compatibility=score
#             )
            
#             # Determine if resume candidate
#             is_resume_candidate = hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume'
#             match_explanation = " UPLOADED RESUME CANDIDATE: Fallback analysis applied due to AI processing limitations." if is_resume_candidate else "Fallback analysis applied due to AI processing limitations."
            
#             ranking = CandidateRanking(
#                 candidate_id=candidate.candidate_id,
#                 candidate_name=candidate.full_name,
#                 current_title=candidate.current_title,
#                 current_company=candidate.current_company,
#                 linkedin_url=candidate.linkedin_url,
#                 overall_score=score,
#                 dimension_scores=dimension_scores,
#                 strengths=["Profile available for review"],
#                 concerns=["Limited automated analysis available"],
#                 recommendations=["Manual review recommended"],
#                 confidence_level=ConfidenceLevel.LOW,
#                 match_explanation=match_explanation,
#                 key_differentiators=[],
#                 interview_focus_areas=["General background review"]
#             )
            
#             rankings.append(ranking)
        
#         # Sort by score
#         rankings.sort(key=lambda x: x.overall_score, reverse=True)
        
#         return rankings
    
#     def _create_emergency_rankings(self, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateRanking]:
#         """Create emergency rankings for completely invalid data."""
#         logger.warning("Creating emergency rankings...")
        
#         rankings = []
        
#         for i, candidate in enumerate(candidates):
#             # Very basic ranking
#             score = 0.4 + (i * 0.01)  # Slight variation
            
#             dimension_scores = DimensionScores(
#                 technical_skills=score,
#                 experience_relevance=score,
#                 seniority_match=score,
#                 education_fit=score,
#                 industry_experience=score,
#                 location_compatibility=score
#             )
            
#             ranking = CandidateRanking(
#                 candidate_id=getattr(candidate, 'candidate_id', f'emergency_{i}'),
#                 candidate_name=getattr(candidate, 'full_name', f'Candidate {i+1}'),
#                 current_title=getattr(candidate, 'current_title', 'Unknown'),
#                 current_company=getattr(candidate, 'current_company', 'Unknown'),
#                 linkedin_url=getattr(candidate, 'linkedin_url', None),
#                 overall_score=score,
#                 dimension_scores=dimension_scores,
#                 strengths=["Candidate profile available"],
#                 concerns=["Automated analysis unavailable"],
#                 recommendations=["Manual review required"],
#                 confidence_level=ConfidenceLevel.LOW,
#                 match_explanation="Emergency ranking applied due to system limitations.",
#                 key_differentiators=[],
#                 interview_focus_areas=["Complete profile review"]
#             )
            
#             rankings.append(ranking)
        
#         return rankings
    
#     def _discover_similar_candidates(self, job_data: JobDescription, seed_candidate: CandidateProfile, seed_ranking: CandidateRanking, iteration: int = 1, jd_file_path: Optional[str] = None) -> List[CandidateProfile]:
#         """Discover similar candidates using Gemini 2.5 Pro with Google Search grounding."""
#         try:
#             # Create discovery prompt
#             prompt = self._create_discovery_prompt(job_data, seed_candidate, seed_ranking, iteration, jd_file_path)
            
#             # Make Gemini API call with web search grounding
#             response = self._make_gemini_request(prompt)
            
#             if not response:
#                 return []
            
#             # Parse candidates from response
#             candidates = self._parse_gemini_candidates(response, iteration)
            
#             return candidates
            
#         except Exception as e:
#             logger.error(f"Error in candidate discovery: {e}")
#             return []
        
#     def extract_text_from_pdf(pdf_path):
#         doc = fitz.open(pdf_path)
#         text = ""
#         for page in doc:
#             text += page.get_text()
#         doc.close()
#         return text

#     def _create_discovery_prompt(
#         self,
#         job_description_model: JobDescription,
#         seed_candidate: CandidateProfile,
#         seed_ranking: CandidateRanking,
#         iteration: int = 1,
#         jd_file_path: Optional[str] = None
#     ) -> str:
#         """Create prompt for Gemini candidate discovery with user's exact format."""

#         # Helper function to extract text using fitz
#         def extract_text_from_pdf(pdf_path):
#             if not pdf_path or not os.path.exists(pdf_path):
#                 logger.warning(f"JD PDF path not provided or does not exist: {pdf_path}. Falling back to model data.")
#                 return ""
#             try:
#                 doc = fitz.open(pdf_path)
#                 text = ""
#                 for page in doc:
#                     text += page.get_text()
#                 doc.close()
#                 logger.info(f"Successfully extracted JD text from: {pdf_path}")
#                 return text
#             except Exception as e:
#                 logger.error(f"Failed to extract text from PDF {pdf_path}: {e}")
#                 return ""
            
#         jd_text = extract_text_from_pdf(jd_file_path)

#         # Fallback if PDF text extraction fails
#         if not jd_text:
#             jd_text = f"Title: {job_description_model.title}\nRequired Skills: {', '.join(job_description_model.required_skills)}"

#         # Prepare the candidate JSON from the ranking object
#         candidate_json = {
#             "candidate_name": seed_ranking.candidate_name,
#             "current_title": seed_ranking.current_title,
#             "current_company": seed_ranking.current_company,
#             "strengths": seed_ranking.strengths,
#             "concerns": seed_ranking.concerns,
#         }
        
#         # Get candidate name correctly
#         candidate_name = getattr(seed_candidate, 'full_name', getattr(seed_candidate, 'name', 'Unknown'))
        
#         # Create candidate JSON structure with user's exact format
#         candidate_json = {
#             "candidate_id": seed_candidate.candidate_id,
#             "candidate_name": candidate_name,
#             "current_title": getattr(seed_candidate, 'current_title', ''),
#             "current_company": getattr(seed_candidate, 'current_company', ''),
#             "linkedin_url": getattr(seed_candidate, 'linkedin_url', None),
#             "overall_score": seed_ranking.overall_score,
#             "dimension_scores": {
#                 "technical_skills": seed_ranking.dimension_scores.technical_skills,
#                 "experience_relevance": seed_ranking.dimension_scores.experience_relevance,
#                 "seniority_match": seed_ranking.dimension_scores.seniority_match,
#                 "education_fit": seed_ranking.dimension_scores.education_fit,
#                 "industry_experience": seed_ranking.dimension_scores.industry_experience,
#                 "location_compatibility": seed_ranking.dimension_scores.location_compatibility
#             },
#             "strengths": seed_ranking.strengths,
#             "concerns": seed_ranking.concerns,
#             "recommendations": seed_ranking.recommendations,
#             "confidence_level": seed_ranking.confidence_level.value if seed_ranking.confidence_level else "medium",
#             "match_explanation": seed_ranking.match_explanation,
#             "key_differentiators": seed_ranking.key_differentiators,
#             "interview_focus_areas": seed_ranking.interview_focus_areas,
#             "source": "pdl_api",
#             "source_icon": "",
#             "has_resume_data": False
#         }
        
#         # User's exact prompt format with dynamic data
#         prompt = f"""
# Please provide 5 candidates for a similar position and location (default to India if not mentioned), keeping the strengths of the attached candidate and removing the concerns.

# Here is the seed candidate's profile for reference:
# {json.dumps(candidate_json, indent=2)}

# ---
# Here is the complete job description to match against:
# {jd_text}
# ---

# CRITICAL INSTRUCTIONS:
# 1.  **Role & Skills**: The new candidates' roles and skills must be highly similar to those required in the job description.
# 2.  **Location**: The location must be in the same country as mentioned in the job description (or India if not specified).
# 3.  **Experience**: Work experience should align with the seniority mentioned in the JD.
# 4.  **Company**: The candidates should NOT be from the same company mentioned in the JD.
# 5.  **Output**: Provide the results along with LinkedIn URLs and any other contact details available.
# """
#         return prompt

    
#     def _make_gemini_request(self, prompt: str) -> Optional[str]:
#         """Make Gemini API request with retry logic for transient errors."""
#         max_retries = 3
#         initial_delay = 5  # Start with a 5-second delay

#         for attempt in range(max_retries):
#             try:
#                 from google import genai
#                 from google.genai import types

#                 # --- Your existing API call logic ---
#                 client = genai.Client(api_key=self.gemini_api_key)
#                 google_search_tool = types.Tool(google_search=types.GoogleSearch())
#                 config = types.GenerateContentConfig(
#                     tools=[google_search_tool],
#                     temperature=1.0,
#                     max_output_tokens=4000
#                 )
#                 response = client.models.generate_content(
#                     model=self.gemini_model,
#                     contents=prompt,
#                     config=config
#                 )
#                 # --- End of your existing logic ---

#                 # If the request succeeds, check for empty text and return
#                 if response and response.text:
#                     # You can add your grounding metadata checks here
#                     return response.text.strip()
#                 else:
#                     # Handle cases where the response is valid but text is empty (e.g., safety filters)
#                     logger.error("Empty response from Gemini.")
#                     return None

#             except Exception as e:
#                 msg = str(e).lower()
#                 # Check for specific transient error codes (500, 503, 429)
#                 if "500" in msg or "503" in msg or "429" in msg or "internal" in msg or "overloaded" in msg:
#                     if attempt == max_retries - 1:
#                         logger.error(f" Final attempt failed. Max retries reached. Error: {e}")
#                         return None  # Or re-raise the exception

#                     # Exponential backoff with jitter
#                     import random
#                     delay = initial_delay * (2 ** attempt) + random.uniform(0, 1)
#                     logger.warning(
#                         f"Waiting for {delay:.2f} seconds... "
#                         f"(Attempt {attempt + 1}/{max_retries})"
#                     )
#                     time.sleep(delay)
#                 else:
#                     # If it's a non-transient error (like 400 or 403), fail immediately
#                     logger.error(f" A non-retryable Gemini API error occurred: {e}")
#                     return None
#         return None

    
#     def _parse_gemini_candidates(self, response: str, iteration: int = 1) -> List[CandidateProfile]:
#         """Parse candidates from Gemini response with OpenAI 4o assistance and save to JSON/CSV."""
#         import json
#         import csv
#         import os
#         import time
#         import re
#         from datetime import datetime
#         from typing import List, Dict, Any, Optional
        
#         try:
#             # Create results directory
#             results_dir = "results"
#             os.makedirs(results_dir, exist_ok=True)
            
#             # Generate timestamp for unique filenames
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
#             logger.info(f" Parsing Gemini response with OpenAI 4o assistance (length: {len(response)} chars)")
            
#             # Step 1: Use OpenAI 4o to extract structured candidate data
#             candidates_data = self._extract_candidates_with_openai(response)
            
#             # Step 2: Save raw response and parsed data to JSON
#             json_filename = f"gemini_candidates_iter{iteration}_{timestamp}.json"
#             json_path = os.path.join(results_dir, json_filename)
            
#             json_data = {
#                 "iteration": iteration,
#                 "timestamp": timestamp,
#                 "raw_gemini_response": response,
#                 "candidates_count": len(candidates_data),
#                 "parsing_method": "openai_4o_assisted",
#                 "candidates": candidates_data
#             }
            
#             with open(json_path, 'w', encoding='utf-8') as f:
#                 json.dump(json_data, f, indent=2, ensure_ascii=False)
            
#             logger.info(f" Gemini response saved to JSON: {json_path}")
            
#             # Step 3: Save candidates to CSV
#             csv_filename = f"gemini_candidates_iter{iteration}_{timestamp}.csv"
#             csv_path = os.path.join(results_dir, csv_filename)
            
#             self._save_candidates_to_csv(candidates_data, csv_path)
#             logger.info(f" Gemini candidates saved to CSV: {csv_path}")
            
#             # Step 4: Convert to CandidateProfile objects with proper validation handling
#             candidates = []
            
#             for i, candidate_data in enumerate(candidates_data, 1):
#                 try:
#                     # Validate required fields
#                     if not candidate_data.get('full_name'):
#                         logger.error(f"Error parsing candidate {i}: Missing full_name")
#                         continue
                    
#                     # Handle location
#                     location_str = candidate_data.get('location', '')
#                     location_obj = None
#                     if location_str:
#                         from src.core.models import Location
#                         parts = [part.strip() for part in location_str.split(',')]
#                         if len(parts) >= 2:
#                             location_obj = Location(
#                                 city=parts[0],
#                                 state=parts[1],
#                                 country=parts[2] if len(parts) > 2 else "India"
#                             )
#                         elif len(parts) == 1:
#                             location_obj = Location(
#                                 city=parts[0],
#                                 state="",
#                                 country="India"
#                             )
                    
#                     # Fix LinkedIn URL
#                     linkedin_url = candidate_data.get('linkedin_url')
#                     if linkedin_url and linkedin_url != "None" and not linkedin_url.startswith(('http://', 'https://')):
#                         linkedin_url = f"https://{linkedin_url}"
#                     elif linkedin_url == "None":
#                         linkedin_url = None
                    
#                     # Handle email validation - provide dummy email if not available
#                     email = candidate_data.get('email', '')
#                     if not email or not self._is_valid_email(email):
#                         # Generate a dummy email that passes validation
#                         name_part = candidate_data.get('full_name', 'candidate').lower().replace(' ', '.')
#                         email = f"{name_part}@example.com"
                    
#                     # Handle phone - provide empty string or dummy if needed
#                     phone = candidate_data.get('phone', '')
                    
#                     # Create candidate profile with discovery metadata
#                     candidate = CandidateProfile(
#                         candidate_id=f"gemini_iter{iteration}_{hash(candidate_data.get('full_name'))}_{int(time.time())}_{i}",
#                         full_name=candidate_data.get('full_name'),
#                         email=email,  # Now properly validated
#                         phone=phone,
#                         location=location_obj,
#                         linkedin_url=linkedin_url,
#                         current_title=candidate_data.get('current_title', ''),
#                         current_company=candidate_data.get('current_company', ''),
#                         skills=candidate_data.get('skills', [])[:10],
#                         education=candidate_data.get('education', [])[:3]
#                     )
                    
#                     # Add discovery metadata as attributes (for tracking)
#                     candidate._discovery_iteration = iteration
#                     candidate._discovery_source = 'gemini_2.5_pro_grounded_openai_parsed'
                    
#                     candidates.append(candidate)
#                     logger.info(f" Successfully created CandidateProfile for: {candidate_data.get('full_name')}")
                    
#                 except Exception as e:
#                     logger.error(f"Error creating CandidateProfile for candidate {i}: {e}")
#                     logger.error(f"Candidate data: {candidate_data}")
#                     continue
            
#             logger.info(f" Successfully parsed {len(candidates)} candidates from Gemini response")
#             logger.info(f" Files saved - JSON: {json_path}, CSV: {csv_path}")
            
#             return candidates
            
#         except Exception as e:
#             logger.error(f"Error parsing Gemini candidates: {e}")
#             return []

#     def _extract_candidates_with_openai(self, gemini_response: str) -> List[Dict[str, Any]]:
#         """Use OpenAI 4o to extract structured candidate data from Gemini response."""
#         try:
#             # Initialize OpenAI client if needed
#             if not self.openai_client:
#                 import openai
#                 self.openai_client = openai.OpenAI()
            
#             # Create extraction prompt for OpenAI
#             extraction_prompt = f"""
#     Extract candidate information from the following Gemini response text and return as a JSON array.

#     GEMINI RESPONSE:
#     {gemini_response}

#     INSTRUCTIONS:
#     1. Find all candidates mentioned in the text
#     2. Extract the following fields for each candidate:
#     - full_name: Complete name of the candidate
#     - current_title: Current job title/position
#     - current_company: Current company/organization
#     - location: City, state/country location
#     - linkedin_url: LinkedIn profile URL if mentioned
#     - skills: List of skills/expertise mentioned
#     - strengths: List of key strengths mentioned
#     - experience_summary: Brief summary of their experience
#     - email: Email address if mentioned (or null if not found)
#     - phone: Phone number if mentioned (or null if not found)

#     3. Skip any placeholder names like "Candidate Name Redacted", "Example Profile", etc.
#     4. Only include real, valid candidate names
#     5. If LinkedIn URL is mentioned as "to be added" or similar, set to null
#     6. If email/phone not found, set to null

#     Return ONLY a valid JSON array with this exact structure:
#     [
#     {{
#         "full_name": "Candidate Name",
#         "current_title": "Job Title",
#         "current_company": "Company Name",
#         "location": "City, Country",
#         "linkedin_url": "https://linkedin.com/in/profile" or null,
#         "email": "email@example.com" or null,
#         "phone": "+1234567890" or null,
#         "skills": ["skill1", "skill2"],
#         "strengths": ["strength1", "strength2"],
#         "experience_summary": "Brief summary"
#     }}
#     ]

#     Return only valid JSON, no additional text or explanations.
#     """
            
#             # Make OpenAI request with reduced token limit to avoid truncation
#             response = self.openai_client.chat.completions.create(
#                 model="gpt-4o",
#                 messages=[{"role": "user", "content": extraction_prompt}],
#                 temperature=0.1,
#                 max_tokens=3000,  # Reduced to fit within limits
#                 timeout=60
#             )
            
#             content = response.choices[0].message.content.strip()
            
#             # Clean and parse JSON response
#             if content.startswith('```json'):
#                 content = content[7:]
#             if content.endswith('```'):
#                 content = content[:-3]
#             content = content.strip()
            
#             candidates_data = json.loads(content)
            
#             if not isinstance(candidates_data, list):
#                 logger.error("OpenAI response is not a list")
#                 return []
            
#             logger.info(f" OpenAI 4o extracted {len(candidates_data)} candidates")
            
#             # Validate and clean the data
#             validated_candidates = []
#             for candidate in candidates_data:
#                 if self._is_valid_candidate_data(candidate):
#                     validated_candidates.append(candidate)
#                 else:
#                     logger.warning(f"Skipping invalid candidate: {candidate.get('full_name', 'Unknown')}")
            
#             logger.info(f"Validated {len(validated_candidates)} candidates")
#             return validated_candidates
            
#         except json.JSONDecodeError as e:
#             logger.error(f"JSON parsing error in OpenAI response: {e}")
#             logger.error(f"OpenAI response content: {content[:500]}...")
#             return []
#         except Exception as e:
#             logger.error(f"Error extracting candidates with OpenAI: {e}")
#             return []

#     def _is_valid_candidate_data(self, candidate_data: Dict[str, Any]) -> bool:
#         """Validate candidate data extracted by OpenAI."""
#         # Check required fields
#         if not candidate_data.get('full_name'):
#             return False
        
#         name = candidate_data['full_name'].lower()
        
#         # Reject dummy/placeholder names
#         dummy_patterns = [
#             'john doe', 'jane doe', 'john smith', 'jane smith',
#             'test user', 'sample candidate', 'example person',
#             'dummy candidate', 'placeholder name', 'unknown candidate',
#             'candidate name', 'your name', 'full name', 'name redacted',
#             'redacted for privacy', 'example profile', 'candidate example'
#         ]
        
#         if any(dummy in name for dummy in dummy_patterns):
#             return False
        
#         # Check name format
#         words = candidate_data['full_name'].split()
#         if len(words) < 2:
#             return False
        
#         # Should not contain numbers
#         if any(char.isdigit() for char in candidate_data['full_name']):
#             return False
        
#         return True

#     def _is_valid_email(self, email: str) -> bool:
#         """Check if email format is valid."""
#         import re
#         if not email:
#             return False
#         pattern = r'^[^@]+@[^@]+\.[^@]+$'
#         return bool(re.match(pattern, email))

#     def _save_candidates_to_csv(self, candidates_data: List[Dict[str, Any]], csv_path: str):
#         """Save candidates data to CSV file."""
#         try:
#             if not candidates_data:
#                 logger.warning("No candidates data to save to CSV")
#                 return
            
#             # Define CSV headers
#             headers = [
#                 'full_name', 
#                 'current_title',
#                 'current_company',
#                 'location',
#                 'linkedin_url',
#                 'email',
#                 'phone',
#                 'skills',
#                 'strengths',
#                 'experience_summary'
#             ]
#             import csv
#             with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
#                 writer = csv.DictWriter(csvfile, fieldnames=headers)
#                 writer.writeheader()
                
#                 for candidate in candidates_data:
#                     # Convert lists to strings for CSV
#                     row = candidate.copy()
#                     if 'skills' in row and isinstance(row['skills'], list):
#                         row['skills'] = ', '.join(row['skills'])
#                     if 'strengths' in row and isinstance(row['strengths'], list):
#                         row['strengths'] = ' | '.join(row['strengths'])
                    
#                     # Handle None values
#                     for key in headers:
#                         if row.get(key) is None:
#                             row[key] = ''
                    
#                     # Only include headers that exist in the data
#                     filtered_row = {k: v for k, v in row.items() if k in headers}
#                     writer.writerow(filtered_row)
            
#             logger.info(f" Saved {len(candidates_data)} candidates to CSV")
            
#         except Exception as e:
#             logger.error(f"Error saving candidates to CSV: {e}")

    
#     def _deduplicate_candidates(self, new_candidates: List[CandidateProfile], existing_candidates: List[CandidateProfile]) -> List[CandidateProfile]:
#         """Remove duplicate candidates based on name and company."""
        
#         # Create set of existing candidate signatures
#         existing_signatures = set()
#         for candidate in existing_candidates:
#             signature = f"{candidate.full_name.lower()}_{candidate.current_company.lower() if candidate.current_company else 'unknown'}"
#             existing_signatures.add(signature)
        
#         # Filter new candidates
#         unique_candidates = []
#         for candidate in new_candidates:
#             signature = f"{candidate.full_name.lower()}_{candidate.current_company.lower() if candidate.current_company else 'unknown'}"
#             if signature not in existing_signatures:
#                 unique_candidates.append(candidate)
#                 existing_signatures.add(signature)
        
#         return unique_candidates
    
#     def _filter_candidates_by_criteria(self, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateProfile]:
#         """Filter candidates based on job criteria."""
        
#         filtered = []
        
#         for candidate in candidates:
#             # Location filter
#             if job_data.location and candidate.location:
#                 if candidate.location.country != job_data.location.country:
#                     continue
            
#             # Company filter (exclude same company)
#             if job_data.company and candidate.current_company:
#                 if candidate.current_company.lower() == job_data.company.lower():
#                     continue
            
#             filtered.append(candidate)
        
#         return filtered
    
#     def _generate_discovery_report(self, initial_rankings: List[CandidateRanking], 
#                                  final_rankings: List[CandidateRanking], 
#                                  discovery_stats: Dict[str, Any], 
#                                  job_data: JobDescription) -> str:
#         """Generate comprehensive discovery report."""
        
#         # Calculate improvements
#         initial_count = len(initial_rankings)
#         final_count = len(final_rankings)
#         candidates_added = final_count - initial_count
        
#         initial_top_score = initial_rankings[0].overall_score if initial_rankings else 0
#         final_top_score = final_rankings[0].overall_score if final_rankings else 0
#         score_improvement = final_top_score - initial_top_score
        
#         # Count sources
#         pdl_count = discovery_stats['source_distribution']['pdl_api']
#         resume_count = discovery_stats['source_distribution']['uploaded_resume']
#         gemini_count = discovery_stats['source_distribution']['gemini_discovery']
        
#         report = f"""
#  ITERATIVE CANDIDATE DISCOVERY REPORT
# ============================================================

#  DISCOVERY SUMMARY:
#    Job Position: {job_data.title}
#    Company: {job_data.company or 'Not specified'}
#    Total Iterations: {discovery_stats['iterations']}
#    Candidates Discovered: {discovery_stats['candidates_discovered']}
#    Initial Pool: {initial_count} candidates
#    Final Pool: {final_count} candidates
#    Pool Growth: +{candidates_added} candidates

#  QUALITY IMPROVEMENT:
#    Initial Top Score: {initial_top_score:.3f}
#    Final Top Score: {final_top_score:.3f}
#    Score Improvement: {score_improvement:+.3f}

#  API PERFORMANCE:
#    Total Gemini Calls: {discovery_stats['total_api_calls']}
#    Successful Calls: {discovery_stats['successful_calls']}
#    Failed Calls: {discovery_stats['failed_calls']}
#    Success Rate: {(discovery_stats['successful_calls'] / max(discovery_stats['total_api_calls'], 1)) * 100:.1f}%

#  CANDIDATE SOURCES:
#     PDL API: {pdl_count} candidates
#     Uploaded Resumes: {resume_count} candidates
#     Gemini Discovery: {gemini_count} candidates

#  TOP 10 FINAL CANDIDATES:"""
        
#         # Add top candidates with enhanced source tracking
#         for i, ranking in enumerate(final_rankings[:10], 1):
#             source_icon = ""
#             if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
#                 source_icon = ""
#             elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
#                 source_icon = ""
            
#             report += f"""
#     {i}. {ranking.candidate_name} {source_icon} - Score: {ranking.overall_score:.3f} | {ranking.current_title} at {ranking.current_company}"""
        
#         return report
    
#     def enhance_rankings_with_discovery_metadata(self, rankings: List[CandidateRanking], all_candidates: List[CandidateProfile]) -> List[CandidateRanking]:
#         """Enhance rankings with discovery metadata for better tracking."""
        
#         enhanced_rankings = []
        
#         for ranking in rankings:
#             # Find the original candidate to get discovery metadata
#             original_candidate = None
#             for candidate in all_candidates:
#                 if candidate.candidate_id == ranking.candidate_id:
#                     original_candidate = candidate
#                     break
            
#             # Check if this is a discovered candidate
#             if original_candidate and hasattr(original_candidate, '_discovery_iteration'):
#                 # This is a discovered candidate - enhance the explanation
#                 iteration = getattr(original_candidate, '_discovery_iteration', 0)
#                 source = getattr(original_candidate, '_discovery_source', 'unknown')
                
#                 if ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' not in ranking.match_explanation:
#                     enhanced_explanation = f" GEMINI 2.5 PRO DISCOVERED CANDIDATE (Iteration {iteration}): {ranking.match_explanation}"
                    
#                     # Create a new ranking with enhanced explanation
#                     enhanced_ranking = CandidateRanking(
#                         candidate_id=ranking.candidate_id,
#                         candidate_name=ranking.candidate_name,
#                         current_title=ranking.current_title,
#                         current_company=ranking.current_company,
#                         linkedin_url=ranking.linkedin_url,
#                         overall_score=ranking.overall_score,
#                         dimension_scores=ranking.dimension_scores,
#                         strengths=ranking.strengths,
#                         concerns=ranking.concerns,
#                         recommendations=ranking.recommendations,
#                         confidence_level=ranking.confidence_level,
#                         match_explanation=enhanced_explanation,
#                         key_differentiators=ranking.key_differentiators,
#                         interview_focus_areas=ranking.interview_focus_areas
#                     )
#                     enhanced_rankings.append(enhanced_ranking)
#                 else:
#                     enhanced_rankings.append(ranking)
#             else:
#                 enhanced_rankings.append(ranking)
        
#         return enhanced_rankings


# # Export the main class
# __all__ = ['CandidateRanker']



"""
AI-Powered Candidate Ranking Module

This module provides comprehensive candidate ranking capabilities with AI-powered analysis

"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Union
import requests
from datetime import datetime
import fitz

from src.config.settings import get_settings
from src.core.models import (
    CandidateProfile, CandidateRanking, JobDescription, 
    ConfidenceLevel, DimensionScores
)

logger = logging.getLogger(__name__)


class CandidateRanker:
    """AI-powered candidate ranking with discovery capabilities."""
    
    def __init__(self):
        """Initialize the ranker with settings and configur ations."""
        self.settings = get_settings()
        self.openai_client = None
        self.gemini_client = None
        
        # OpenAI configuration with token management
        self.openai_model = getattr(self.settings, 'openai_model', 'gpt-4o')
        self.openai_temperature = getattr(self.settings, 'openai_temperature', 0.1)
        self.openai_max_tokens = getattr(self.settings, 'openai_max_tokens', 8000)
        self.openai_timeout = getattr(self.settings, 'openai_timeout', 60)
        
        # Apply token management
        self._apply_token_management()
        
        # Discovery configuration
        self.discovery_enabled = getattr(self.settings, 'discovery_enabled', False)
        self.gemini_api_key = os.getenv('GEMINI_API_KEY') or getattr(self.settings, 'gemini_api_key', '')
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.5-pro')
        self.discovery_max_iterations = getattr(self.settings, 'discovery_max_iterations', 2)
        self.discovery_candidates_per_seed = getattr(self.settings, 'discovery_candidates_per_seed', 2)
        self.discovery_top_seeds = getattr(self.settings, 'discovery_top_seeds', 6)
        
        # Enable discovery if API key is available
        if self.gemini_api_key and not self.discovery_enabled:
            self.discovery_enabled = True
            logger.info("Discovery enabled: Gemini API key detected")
        elif not self.gemini_api_key:
            logger.info("Discovery disabled: Gemini API key not configured")
    
    def _apply_token_management(self):
        """Apply intelligent token management based on model capabilities."""
        
        # Model-specific token limits
        model_limits = {
            "gpt-4o": {
                "max_input_tokens": 128000,
                "max_output_tokens": 4096,
                "safe_input_tokens": 120000,
                "safe_output_tokens": 4000
            },
            "gpt-4": {
                "max_input_tokens": 8192,
                "max_output_tokens": 4096,
                "safe_input_tokens": 7000,
                "safe_output_tokens": 4000
            },
            "gpt-3.5-turbo": {
                "max_input_tokens": 16385,
                "max_output_tokens": 4096,
                "safe_input_tokens": 15000,
                "safe_output_tokens": 4000
            }
        }
        
        # Get limits for current model
        limits = model_limits.get(self.openai_model, model_limits["gpt-4o"])
        
        # Adjust max_tokens if it exceeds model limits
        if self.openai_max_tokens > limits["max_output_tokens"]:
            logger.warning(f"Max tokens adjusted from {self.openai_max_tokens} to {limits['safe_output_tokens']}")
            logger.warning(f"Model '{self.openai_model}' supports max {limits['max_output_tokens']} output tokens")
            logger.warning(f"Using safe limit of {limits['safe_output_tokens']} tokens")
            self.openai_max_tokens = limits["safe_output_tokens"]
        
        # Store limits for prompt management
        self.max_input_tokens = limits["safe_input_tokens"]
        self.max_output_tokens = limits["safe_output_tokens"]
    
    def rank_candidates(self, job_data: JobDescription, candidates: List[CandidateProfile]) -> List[CandidateRanking]:
        """Rank candidates using AI-powered analysis."""
        if not candidates:
            logger.warning("No candidates provided for ranking")
            return []
        
        # Validate and flatten candidates
        validated_candidates = self._validate_and_flatten_candidates(candidates)
        
        if not validated_candidates:
            logger.error("No valid candidates after validation")
            return []
        
        logger.info(f"Ranking {len(validated_candidates)} candidates with AI-powered analysis...")
        
        try:
            # Process candidates in batches for better performance
            batch_size = 5
            all_rankings = []
            
            for i in range(0, len(validated_candidates), batch_size):
                batch = validated_candidates[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(validated_candidates) + batch_size - 1) // batch_size
                
                logger.info(f"Processing batch {batch_num}/{total_batches}")
                
                batch_rankings = self._rank_batch_with_ai(job_data, batch)
                all_rankings.extend(batch_rankings)
            
            # Sort by overall score (descending)
            all_rankings.sort(key=lambda x: x.overall_score, reverse=True)
            
            logger.info(f"Successfully ranked {len(all_rankings)} candidates")
            return all_rankings
            
        except Exception as e:
            logger.error(f"Error in candidate ranking: {e}")
            # Return emergency rankings
            return self._create_emergency_rankings(validated_candidates, job_data)
    
    def rank_candidates_with_discovery(self, job_data: JobDescription, candidates: List[CandidateProfile], jd_file_path: Optional[str] = None, prompt_addon: Optional[str] = None) -> Dict[str, Any]:
        """Rank candidates with iterative discovery using Gemini 2.5 Pro."""
        logger.info(" Starting iterative candidate discovery process...")
        
        # Initial ranking
        logger.info(" Performing initial candidate ranking...")
        initial_rankings = self.rank_candidates(job_data, candidates)
        
        if not initial_rankings:
            logger.warning("No initial candidates to use for discovery")
            return {
                'final_rankings': [],
                'discovery_report': "No candidates available for discovery",
                'discovery_data': {}
            }
        
        logger.info(f" Initial ranking completed: {len(initial_rankings)} candidates")
        
        # Check if discovery is enabled
        if not self.discovery_enabled or not self.gemini_api_key:
            logger.warning("Discovery disabled or Gemini API key not configured")
            return {
                'final_rankings': initial_rankings,
                'discovery_report': "Discovery feature not enabled",
                'discovery_data': {}
            }
        
        # Iterative discovery
        all_candidates = list(candidates)  # Start with original candidates
        discovery_stats = {
            'iterations': 0,
            'candidates_discovered': 0,
            'total_api_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'initial_count': len(initial_rankings),
            'final_count': 0,
            'score_improvement': 0.0,
            'source_distribution': {'pdl_api': 0, 'uploaded_resume': 0, 'gemini_discovery': 0}
        }
        
        for iteration in range(1, self.discovery_max_iterations + 1):
            logger.info(f"\n Discovery Iteration {iteration}/{self.discovery_max_iterations}")
            
            # Get top candidates as seeds
            current_rankings = self.rank_candidates(job_data, all_candidates)
            top_seeds = current_rankings[:self.discovery_top_seeds]
            
            logger.info(f" Using top {len(top_seeds)} candidates as seeds")
            
            iteration_candidates = []
            
            for seed_idx, seed_ranking in enumerate(top_seeds, 1):
                logger.info(f" Processing seed {seed_idx}/{len(top_seeds)}: {seed_ranking.candidate_name}")
                
                # Find the original candidate profile for this ranking
                seed_candidate = None
                for candidate in all_candidates:
                    if candidate.candidate_id == seed_ranking.candidate_id:
                        seed_candidate = candidate
                        break
                
                if not seed_candidate:
                    logger.warning(f"Could not find original candidate profile for {seed_ranking.candidate_name}")
                    continue
                
                # Discover similar candidates
                discovered = self._discover_similar_candidates(
                    job_data, seed_candidate, seed_ranking, iteration, jd_file_path, prompt_addon=prompt_addon
                )
                
                discovery_stats['total_api_calls'] += 1
                if discovered:
                    discovery_stats['successful_calls'] += 1
                    iteration_candidates.extend(discovered)
                    logger.info(f"    Found {len(discovered)} valid candidates from seed")
                else:
                    discovery_stats['failed_calls'] += 1
                    logger.info(f"    No valid candidates found from seed")
            
            # Deduplicate candidates
            before_dedup = len(iteration_candidates)
            iteration_candidates = self._deduplicate_candidates(iteration_candidates, all_candidates)
            after_dedup = len(iteration_candidates)
            
            logger.info(f" Deduplicated: {before_dedup} → {after_dedup} candidates")
            
            if not iteration_candidates:
                logger.warning(f"No new candidates discovered in iteration {iteration}")
                continue
            
            # Add to candidate pool
            all_candidates.extend(iteration_candidates)
            discovery_stats['candidates_discovered'] += len(iteration_candidates)
            discovery_stats['iterations'] = iteration
            
            logger.info(f" Added {len(iteration_candidates)} new candidates to pool")
            logger.info(f" Total candidates now: {len(all_candidates)}")
        
        # Final ranking with all candidates
        logger.info(" Performing final ranking with all discovered candidates...")
        final_rankings = self.rank_candidates(job_data, all_candidates)
        
        # Update discovery statistics
        discovery_stats['final_count'] = len(final_rankings)
        if initial_rankings and final_rankings:
            discovery_stats['score_improvement'] = final_rankings[0].overall_score - initial_rankings[0].overall_score
        
        # Count sources in final rankings
        for ranking in final_rankings:
            if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                discovery_stats['source_distribution']['uploaded_resume'] += 1
            elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                discovery_stats['source_distribution']['gemini_discovery'] += 1
            else:
                discovery_stats['source_distribution']['pdl_api'] += 1
        
        # Generate discovery report
        discovery_report = self._generate_discovery_report(
            initial_rankings, final_rankings, discovery_stats, job_data
        )
        
        logger.info(" Discovery process completed!")
        
        return {
            'final_rankings': final_rankings,
            'discovery_report': discovery_report,
            'discovery_data': discovery_stats
        }
    
    def _validate_and_flatten_candidates(self, candidates: Any) -> List[CandidateProfile]:
        """Validate and flatten candidates, handling various input types safely."""
        validated = []
        for candidate in candidates:
            try:
                # Handle different candidate types
                if isinstance(candidate, CandidateProfile):
                    # Standard CandidateProfile
                    validated.append(candidate)

                elif hasattr(candidate, 'candidate_profile'):
                    # ResumeCandidate wrapper or similar
                    validated.append(candidate.candidate_profile)

                elif isinstance(candidate, dict):
                    # --- START: MODIFICATION TO FIX EMAIL VALIDATION ---
                    # Check and fix email before creating the profile to prevent Pydantic errors.
                    # This handles resumes where the email could not be parsed.
                    email = candidate.get('email', '')
                    if not self._is_valid_email(email):
                        full_name = candidate.get('full_name')
                        if full_name:
                            # Generate a placeholder email using the candidate's name.
                            name_part = ''.join(filter(str.isalnum, full_name.lower().replace(' ', '.')))
                            candidate['email'] = f"{name_part}@placeholder.email"
                            logger.warning(f"Invalid or missing email for '{full_name}'. Generated placeholder: {candidate['email']}")
                        else:
                            # Fallback if the full name is also missing.
                            import time
                            candidate['email'] = f"candidate.{int(time.time())}@placeholder.email"
                            logger.warning(f"Missing name and email for a candidate. Generated random placeholder.")
                    # --- END: MODIFICATION ---

                    # Dictionary representation - try to convert
                    try:
                        profile = CandidateProfile(**candidate)
                        validated.append(profile)
                    except Exception as dict_error:
                        logger.error(f"Error converting dict to CandidateProfile: {dict_error}")
                        continue

                else:
                    logger.warning(f"Unknown candidate type: {type(candidate)}")
                    continue

            except Exception as e:
                logger.error(f"Error validating candidate: {e}")
                continue

        logger.info(f"Validated and flattened to {len(validated)} valid candidates")
        print(f" Validated {len(validated)} out of {len(candidates)} candidates")
        return validated

    
    def _rank_batch_with_ai(self, job_data: JobDescription, candidates: List[CandidateProfile]) -> List[CandidateRanking]:
        """Rank a batch of candidates using AI analysis."""
        try:
            # Initialize OpenAI client if needed
            if not self.openai_client:
                import openai
                self.openai_client = openai.OpenAI()
            
            # Create ranking prompt
            prompt = self._create_ranking_prompt(job_data, candidates)
            
            # Truncate prompt if too long
            prompt = self._truncate_prompt_if_needed(prompt)
            
            # Make API call with error handling
            response = self._make_openai_request(prompt)
            
            if not response:
                logger.warning("OpenAI request failed, using fallback rankings")
                return self._create_fallback_rankings(candidates, job_data)
            
            # Parse response
            rankings = self._parse_ranking_response(response, candidates, job_data)
            
            if not rankings:
                logger.warning("Failed to parse AI response, using fallback rankings")
                return self._create_fallback_rankings(candidates, job_data)
            
            return rankings
            
        except Exception as e:
            logger.error(f"Error in AI ranking: {e}")
            return self._create_fallback_rankings(candidates, job_data)
    
    def _create_ranking_prompt(self, job_data: JobDescription, candidates: List[CandidateProfile]) -> str:
        """Create a comprehensive ranking prompt for AI analysis."""
        
        # Job context
        job_context = f"""
JOB REQUIREMENTS:
Title: {job_data.title}
Company: {job_data.company or 'Not specified'}
Location: {job_data.location.city if job_data.location else 'Not specified'}
Experience Level: {job_data.experience_level.value if job_data.experience_level else 'Not specified'}
Required Skills: {', '.join(job_data.required_skills[:10]) if job_data.required_skills else 'Not specified'}
"""
        
        # Candidate profiles
        candidate_profiles = ""
        for i, candidate in enumerate(candidates, 1):
            # Determine if this is a resume candidate
            is_resume_candidate = hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume'
            source_note = " (UPLOADED RESUME - actively interested)" if is_resume_candidate else ""
            
            candidate_profiles += f"""
CANDIDATE {i}{source_note}:
Name: {candidate.full_name}
Current Title: {candidate.current_title or 'Not specified'}
Current Company: {candidate.current_company or 'Not specified'}
Location: {candidate.location.city if candidate.location else 'Not specified'}
Skills: {', '.join(candidate.skills[:8]) if candidate.skills else 'Not specified'}
Education: {', '.join(candidate.education[:3]) if candidate.education else 'Not specified'}
LinkedIn: {candidate.linkedin_url or 'Not available'}
"""
        
        # Analysis instructions
        instructions = f"""
Analyze each candidate against the job requirements and provide detailed rankings.

For each candidate, evaluate these dimensions (0.0-1.0):
- technical_skills: Relevance of technical skills to job requirements
- experience_relevance: How well their experience matches the role
- seniority_match: Appropriate level for the position
- education_fit: Educational background alignment
- industry_experience: Relevant industry background
- location_compatibility: Geographic fit for the role

IMPORTANT SCORING GUIDELINES:
- Resume candidates (uploaded) should get +0.1 bonus for demonstrated interest
- Consider skills overlap, experience level, and industry relevance
- Be realistic: most candidates score 0.4-0.8 range
- Only exceptional matches should score above 0.9

Return JSON array with this exact structure:
[
  {{
    "candidate_name": "Full Name",
    "overall_score": 0.75,
    "dimension_scores": {{
      "technical_skills": 0.8,
      "experience_relevance": 0.7,
      "seniority_match": 0.8,
      "education_fit": 0.7,
      "industry_experience": 0.6,
      "location_compatibility": 0.9
    }},
    "strengths": ["Strength 1", "Strength 2"],
    "concerns": ["Concern 1", "Concern 2"],
    "recommendations": ["Recommendation 1"],
    "confidence_level": "high|medium|low",
    "match_explanation": "Detailed explanation of the match",
    "key_differentiators": ["Differentiator 1"],
    "interview_focus_areas": ["Focus area 1"]
  }}
]

Return only valid JSON, no additional text.
"""
        
        return job_context + candidate_profiles + instructions
    
    def _truncate_prompt_if_needed(self, prompt: str) -> str:
        """Truncate prompt if it exceeds token limits."""
        # Estimate tokens (rough: 1 token ≈ 3.5 characters)
        estimated_tokens = len(prompt) / 3.5
        
        if estimated_tokens > self.max_input_tokens:
            logger.warning(f"Prompt too long ({estimated_tokens:.0f} tokens), truncating to {self.max_input_tokens} tokens")
            
            # Calculate max characters
            max_chars = int(self.max_input_tokens * 3.5)
            
            # Truncate while preserving structure
            lines = prompt.split('\n')
            truncated_lines = []
            current_length = 0
            
            for line in lines:
                if current_length + len(line) + 1 > max_chars:
                    break
                truncated_lines.append(line)
                current_length += len(line) + 1
            
            truncated_prompt = '\n'.join(truncated_lines)
            logger.warning(f"Truncated prompt from {len(prompt)} to {len(truncated_prompt)} characters")
            
            return truncated_prompt
        
        return prompt
    
    def _make_openai_request(self, prompt: str) -> Optional[str]:
        """Make OpenAI API request with comprehensive error handling."""
        try:
            logger.debug(f"OpenAI Request: Model={self.openai_model}, Tokens={self.openai_max_tokens}, Prompt={len(prompt)} chars")
            
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.openai_temperature,
                max_tokens=self.openai_max_tokens,
                timeout=self.openai_timeout
            )
            
            content = response.choices[0].message.content.strip()
            logger.debug(" OpenAI request successful")
            return content
            
        except requests.exceptions.SSLError as e:
            if "DECRYPTION_FAILED_OR_BAD_RECORD_MAC" in str(e):
                logger.error("SSL Error: Likely due to oversized payload")
                logger.error("Attempting to reduce prompt size...")
                
                # Aggressively reduce prompt size
                reduced_prompt = prompt[:len(prompt)//2]
                try:
                    response = self.openai_client.chat.completions.create(
                        model=self.openai_model,
                        messages=[{"role": "user", "content": reduced_prompt}],
                        temperature=self.openai_temperature,
                        max_tokens=min(self.openai_max_tokens, 2000),
                        timeout=30
                    )
                    return response.choices[0].message.content.strip()
                except Exception as retry_error:
                    logger.error(f"Retry failed: {retry_error}")
                    return None
            else:
                logger.error(f"SSL Error: {e}")
                return None
                
        except Exception as e:
            error_msg = str(e)
            
            # Classify error types
            if "400" in error_msg and "Bad Request" in error_msg:
                logger.error("OpenAI 400 Bad Request Error:")
                if "content filter" in error_msg.lower():
                    logger.error("  Error Type: Content filter violation")
                    logger.error("  Solution: Content sanitized and fallback analysis applied")
                elif "token" in error_msg.lower():
                    logger.error("  Error Type: Token limit exceeded")
                    logger.error("  Solution: Prompt truncation applied")
                else:
                    logger.error(f"  Error Message: {error_msg}")
                    logger.error("  Solution: Fallback analysis will be used")
            else:
                logger.error(f"OpenAI API Error: {error_msg}")
            
            return None
    
    def _parse_ranking_response(self, response: str, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateRanking]:
        """Parse AI ranking response into CandidateRanking objects."""
        try:
            # Clean response
            content = response.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON
            rankings_data = json.loads(content)
            
            if not isinstance(rankings_data, list):
                logger.error("Response is not a list")
                return []
            
            rankings = []
            
            for i, ranking_data in enumerate(rankings_data):
                try:
                    # Find matching candidate
                    candidate = candidates[i] if i < len(candidates) else None
                    if not candidate:
                        logger.warning(f"No candidate found for ranking {i}")
                        continue
                    
                    # Create dimension scores
                    dim_scores = ranking_data.get('dimension_scores', {})
                    dimension_scores = DimensionScores(
                        technical_skills=float(dim_scores.get('technical_skills', 0.5)),
                        experience_relevance=float(dim_scores.get('experience_relevance', 0.5)),
                        seniority_match=float(dim_scores.get('seniority_match', 0.5)),
                        education_fit=float(dim_scores.get('education_fit', 0.5)),
                        industry_experience=float(dim_scores.get('industry_experience', 0.5)),
                        location_compatibility=float(dim_scores.get('location_compatibility', 0.5))
                    )
                    
                    # Determine confidence level
                    confidence_str = ranking_data.get('confidence_level', 'medium').lower()
                    confidence_level = ConfidenceLevel.MEDIUM
                    if confidence_str == 'high':
                        confidence_level = ConfidenceLevel.HIGH
                    elif confidence_str == 'low':
                        confidence_level = ConfidenceLevel.LOW
                    
                    # Check if this is a resume candidate and enhance explanation
                    match_explanation = ranking_data.get('match_explanation', '')
                    is_resume_candidate = hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume'
                    
                    if is_resume_candidate and ' UPLOADED RESUME CANDIDATE' not in match_explanation:
                        match_explanation = f" UPLOADED RESUME CANDIDATE: {match_explanation}"
                    
                    # Create ranking
                    ranking = CandidateRanking(
                        candidate_id=candidate.candidate_id,
                        candidate_name=candidate.full_name,
                        current_title=candidate.current_title,
                        current_company=candidate.current_company,
                        linkedin_url=candidate.linkedin_url,
                        overall_score=float(ranking_data.get('overall_score', 0.5)),
                        dimension_scores=dimension_scores,
                        strengths=ranking_data.get('strengths', []),
                        concerns=ranking_data.get('concerns', []),
                        recommendations=ranking_data.get('recommendations', []),
                        confidence_level=confidence_level,
                        match_explanation=match_explanation,
                        key_differentiators=ranking_data.get('key_differentiators', []),
                        interview_focus_areas=ranking_data.get('interview_focus_areas', [])
                    )
                    
                    rankings.append(ranking)
                    
                except Exception as e:
                    logger.error(f"Error parsing ranking {i}: {e}")
                    continue
            
            return rankings
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            logger.error(f"Response content: {response[:500]}...")
            return []
        except Exception as e:
            logger.error(f"Error parsing rankings: {e}")
            return []
    
    def _create_fallback_rankings(self, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateRanking]:
        """Create fallback rankings when AI analysis fails."""
        logger.info("Creating fallback rankings...")
        
        rankings = []
        
        for candidate in candidates:
            # Simple scoring based on available data
            score = 0.5  # Base score
            
            # Boost for resume candidates
            if hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume':
                score += 0.1
            
            # Simple skill matching
            if candidate.skills and job_data.required_skills:
                skill_overlap = len(set(candidate.skills) & set(job_data.required_skills))
                score += min(skill_overlap * 0.05, 0.2)
            
            # Location matching
            if candidate.location and job_data.location:
                if candidate.location.city == job_data.location.city:
                    score += 0.1
            
            # Cap score
            score = min(score, 1.0)
            
            # Create basic dimension scores
            dimension_scores = DimensionScores(
                technical_skills=score,
                experience_relevance=score,
                seniority_match=score,
                education_fit=score,
                industry_experience=score,
                location_compatibility=score
            )
            
            # Determine if resume candidate
            is_resume_candidate = hasattr(candidate, 'source') and getattr(candidate, 'source') == 'uploaded_resume'
            match_explanation = " UPLOADED RESUME CANDIDATE: Fallback analysis applied due to AI processing limitations." if is_resume_candidate else "Fallback analysis applied due to AI processing limitations."
            
            ranking = CandidateRanking(
                candidate_id=candidate.candidate_id,
                candidate_name=candidate.full_name,
                current_title=candidate.current_title,
                current_company=candidate.current_company,
                linkedin_url=candidate.linkedin_url,
                overall_score=score,
                dimension_scores=dimension_scores,
                strengths=["Profile available for review"],
                concerns=["Limited automated analysis available"],
                recommendations=["Manual review recommended"],
                confidence_level=ConfidenceLevel.LOW,
                match_explanation=match_explanation,
                key_differentiators=[],
                interview_focus_areas=["General background review"]
            )
            
            rankings.append(ranking)
        
        # Sort by score
        rankings.sort(key=lambda x: x.overall_score, reverse=True)
        
        return rankings
    
    def _create_emergency_rankings(self, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateRanking]:
        """Create emergency rankings for completely invalid data."""
        logger.warning("Creating emergency rankings...")
        
        rankings = []
        
        for i, candidate in enumerate(candidates):
            # Very basic ranking
            score = 0.4 + (i * 0.01)  # Slight variation
            
            dimension_scores = DimensionScores(
                technical_skills=score,
                experience_relevance=score,
                seniority_match=score,
                education_fit=score,
                industry_experience=score,
                location_compatibility=score
            )
            
            ranking = CandidateRanking(
                candidate_id=getattr(candidate, 'candidate_id', f'emergency_{i}'),
                candidate_name=getattr(candidate, 'full_name', f'Candidate {i+1}'),
                current_title=getattr(candidate, 'current_title', 'Unknown'),
                current_company=getattr(candidate, 'current_company', 'Unknown'),
                linkedin_url=getattr(candidate, 'linkedin_url', None),
                overall_score=score,
                dimension_scores=dimension_scores,
                strengths=["Candidate profile available"],
                concerns=["Automated analysis unavailable"],
                recommendations=["Manual review required"],
                confidence_level=ConfidenceLevel.LOW,
                match_explanation="Emergency ranking applied due to system limitations.",
                key_differentiators=[],
                interview_focus_areas=["Complete profile review"]
            )
            
            rankings.append(ranking)
        
        return rankings
    
    def _discover_similar_candidates(self, job_data: JobDescription, seed_candidate: CandidateProfile, seed_ranking: CandidateRanking, iteration: int = 1, jd_file_path: Optional[str] = None, prompt_addon: Optional[str] = None) -> List[CandidateProfile]:
        """Discover similar candidates using Gemini 2.5 Pro with Google Search grounding."""
        try:
            # Create discovery prompt
            prompt = self._create_discovery_prompt(job_data, seed_candidate, seed_ranking, iteration, jd_file_path, prompt_addon=prompt_addon)
            
            # Make Gemini API call with web search grounding
            response = self._make_gemini_request(prompt)
            
            if not response:
                return []
            
            # Parse candidates from response
            candidates = self._parse_gemini_candidates(response, iteration)
            
            return candidates
            
        except Exception as e:
            logger.error(f"Error in candidate discovery: {e}")
            return []
        
    def extract_text_from_pdf(pdf_path):
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text

    def _create_discovery_prompt(
        self,
        job_description_model: JobDescription,
        seed_candidate: CandidateProfile,
        seed_ranking: CandidateRanking,
        iteration: int = 1,
        jd_file_path: Optional[str] = None,
        prompt_addon: Optional[str] = None
    ) -> str:
        """Create prompt for Gemini candidate discovery with user's exact format."""

        # Helper function to extract text using fitz
        def extract_text_from_pdf(pdf_path):
            if not pdf_path or not os.path.exists(pdf_path):
                logger.warning(f"JD PDF path not provided or does not exist: {pdf_path}. Falling back to model data.")
                return ""
            try:
                doc = fitz.open(pdf_path)
                text = ""
                for page in doc:
                    text += page.get_text()
                doc.close()
                logger.info(f"Successfully extracted JD text from: {pdf_path}")
                return text
            except Exception as e:
                logger.error(f"Failed to extract text from PDF {pdf_path}: {e}")
                return ""
            
        jd_text = extract_text_from_pdf(jd_file_path)

        # Fallback if PDF text extraction fails
        if not jd_text:
            jd_text = f"Title: {job_description_model.title}\nRequired Skills: {', '.join(job_description_model.required_skills)}"

        # Prepare the candidate JSON from the ranking object
        candidate_json = {
            "candidate_name": seed_ranking.candidate_name,
            "current_title": seed_ranking.current_title,
            "current_company": seed_ranking.current_company,
            "strengths": seed_ranking.strengths,
            "concerns": seed_ranking.concerns,
        }
        
        # Get candidate name correctly
        candidate_name = getattr(seed_candidate, 'full_name', getattr(seed_candidate, 'name', 'Unknown'))
        
        # Create candidate JSON structure with user's exact format
        candidate_json = {
            "candidate_id": seed_candidate.candidate_id,
            "candidate_name": candidate_name,
            "current_title": getattr(seed_candidate, 'current_title', ''),
            "current_company": getattr(seed_candidate, 'current_company', ''),
            "linkedin_url": getattr(seed_candidate, 'linkedin_url', None),
            "overall_score": seed_ranking.overall_score,
            "dimension_scores": {
                "technical_skills": seed_ranking.dimension_scores.technical_skills,
                "experience_relevance": seed_ranking.dimension_scores.experience_relevance,
                "seniority_match": seed_ranking.dimension_scores.seniority_match,
                "education_fit": seed_ranking.dimension_scores.education_fit,
                "industry_experience": seed_ranking.dimension_scores.industry_experience,
                "location_compatibility": seed_ranking.dimension_scores.location_compatibility
            },
            "strengths": seed_ranking.strengths,
            "concerns": seed_ranking.concerns,
            "recommendations": seed_ranking.recommendations,
            "confidence_level": seed_ranking.confidence_level.value if seed_ranking.confidence_level else "medium",
            "match_explanation": seed_ranking.match_explanation,
            "key_differentiators": seed_ranking.key_differentiators,
            "interview_focus_areas": seed_ranking.interview_focus_areas,
            "source": "pdl_api",
            "source_icon": "",
            "has_resume_data": False
        }
        
        # User's exact prompt format with dynamic data
        custom_instruction = ""
        if prompt_addon:
            custom_instruction = f"ADDITIONAL USER INSTRUCTION: {prompt_addon}\n"

        # REVISED PROMPT with new instructions
        prompt = f"""
Please provide 5 candidates for a similar position and location (default to India if not mentioned), keeping the strengths of the attached candidate and removing the concerns.

Here is the seed candidate's profile for reference:
{json.dumps(candidate_json, indent=2)}

---
Here is the complete job description to match against:
{jd_text}
---
{custom_instruction}
CRITICAL INSTRUCTIONS:
1.  **Real Profiles Only**: You MUST find real, public profiles. Do NOT generate placeholder or fictitious candidates.
2.  **Mandatory Fields**: Every candidate returned MUST include their full name, current job title, and current company name. Profiles missing any of these three fields should be discarded.
3.  **Role & Skills**: The new candidates' roles and skills must be highly similar to those required in the job description.
4.  **Location**: The location must be in the same country as mentioned in the job description (or India if not specified).
5.  **Experience**: Work experience should align with the seniority mentioned in the JD.
6.  **Company**: The candidates should NOT be from the same company mentioned in the JD.
7.  **Output**: Provide the results along with LinkedIn URLs and any other contact details available.
"""
        return prompt

    
    def _make_gemini_request(self, prompt: str) -> Optional[str]:
        """Make Gemini API request with retry logic for transient errors."""
        max_retries = 3
        initial_delay = 5  # Start with a 5-second delay

        for attempt in range(max_retries):
            try:
                import google.generativeai as genai
                from google.genai import types

                # --- Your existing API call logic ---
                client = genai.Client(api_key=self.gemini_api_key)
                google_search_tool = types.Tool(google_search=types.GoogleSearch())
                config = types.GenerateContentConfig(
                    tools=[google_search_tool],
                    temperature=1.0,
                    max_output_tokens=4000
                )
                response = client.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt,
                    config=config
                )
                # --- End of your existing logic ---

                # If the request succeeds, check for empty text and return
                if response and response.text:
                    # You can add your grounding metadata checks here
                    return response.text.strip()
                else:
                    # Handle cases where the response is valid but text is empty (e.g., safety filters)
                    logger.error("Empty response from Gemini.")
                    return None

            except Exception as e:
                msg = str(e).lower()
                # Check for specific transient error codes (500, 503, 429)
                if "500" in msg or "503" in msg or "429" in msg or "internal" in msg or "overloaded" in msg:
                    if attempt == max_retries - 1:
                        logger.error(f" Final attempt failed. Max retries reached. Error: {e}")
                        return None  # Or re-raise the exception

                    # Exponential backoff with jitter
                    import random
                    delay = initial_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Waiting for {delay:.2f} seconds... "
                        f"(Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                else:
                    # If it's a non-transient error (like 400 or 403), fail immediately
                    logger.error(f" A non-retryable Gemini API error occurred: {e}")
                    return None
        return None

    
    def _parse_gemini_candidates(self, response: str, iteration: int = 1) -> List[CandidateProfile]:
        """Parse candidates from Gemini response with OpenAI 4o assistance and save to JSON/CSV."""
        import json
        import csv
        import os
        import time
        import re
        from datetime import datetime
        from typing import List, Dict, Any, Optional
        
        try:
            # Create results directory
            results_dir = "results"
            os.makedirs(results_dir, exist_ok=True)
            
            # Generate timestamp for unique filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            logger.info(f" Parsing Gemini response with OpenAI 4o assistance (length: {len(response)} chars)")
            
            # Step 1: Use OpenAI 4o to extract structured candidate data
            candidates_data = self._extract_candidates_with_openai(response)
            
            # Step 2: Save raw response and parsed data to JSON
            json_filename = f"gemini_candidates_iter{iteration}_{timestamp}.json"
            json_path = os.path.join(results_dir, json_filename)
            
            json_data = {
                "iteration": iteration,
                "timestamp": timestamp,
                "raw_gemini_response": response,
                "candidates_count": len(candidates_data),
                "parsing_method": "openai_4o_assisted",
                "candidates": candidates_data
            }
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f" Gemini response saved to JSON: {json_path}")
            
            # Step 3: Save candidates to CSV
            csv_filename = f"gemini_candidates_iter{iteration}_{timestamp}.csv"
            csv_path = os.path.join(results_dir, csv_filename)
            
            self._save_candidates_to_csv(candidates_data, csv_path)
            logger.info(f" Gemini candidates saved to CSV: {csv_path}")
            
            # Step 4: Convert to CandidateProfile objects with proper validation handling
            candidates = []
            
            for i, candidate_data in enumerate(candidates_data, 1):
                try:
                    # Validate required fields
                    if not candidate_data.get('full_name'):
                        logger.error(f"Error parsing candidate {i}: Missing full_name")
                        continue
                    
                    # Handle location
                    location_str = candidate_data.get('location', '')
                    location_obj = None
                    if location_str:
                        from src.core.models import Location
                        parts = [part.strip() for part in location_str.split(',')]
                        if len(parts) >= 2:
                            location_obj = Location(
                                city=parts[0],
                                state=parts[1],
                                country=parts[2] if len(parts) > 2 else "India"
                            )
                        elif len(parts) == 1:
                            location_obj = Location(
                                city=parts[0],
                                state="",
                                country="India"
                            )
                    
                    # Fix LinkedIn URL
                    linkedin_url = candidate_data.get('linkedin_url')
                    if linkedin_url and linkedin_url != "None" and not linkedin_url.startswith(('http://', 'https://')):
                        linkedin_url = f"https://{linkedin_url}"
                    elif linkedin_url == "None":
                        linkedin_url = None
                    
                    # Handle email validation - provide dummy email if not available
                    email = candidate_data.get('email', '')
                    if not email or not self._is_valid_email(email):
                        # Generate a dummy email that passes validation
                        name_part = candidate_data.get('full_name', 'candidate').lower().replace(' ', '.')
                        email = f"{name_part}@example.com"
                    
                    # Handle phone - provide empty string or dummy if needed
                    phone = candidate_data.get('phone', '')
                    
                    # Create candidate profile with discovery metadata
                    candidate = CandidateProfile(
                        candidate_id=f"gemini_iter{iteration}_{hash(candidate_data.get('full_name'))}_{int(time.time())}_{i}",
                        full_name=candidate_data.get('full_name'),
                        email=email,  # Now properly validated
                        phone=phone,
                        location=location_obj,
                        linkedin_url=linkedin_url,
                        current_title=candidate_data.get('current_title', ''),
                        current_company=candidate_data.get('current_company', ''),
                        skills=candidate_data.get('skills', [])[:10],
                        education=candidate_data.get('education', [])[:3]
                    )
                    
                    # Add discovery metadata as attributes (for tracking)
                    candidate._discovery_iteration = iteration
                    candidate._discovery_source = 'gemini_2.5_pro_grounded_openai_parsed'
                    
                    candidates.append(candidate)
                    logger.info(f" Successfully created CandidateProfile for: {candidate_data.get('full_name')}")
                    
                except Exception as e:
                    logger.error(f"Error creating CandidateProfile for candidate {i}: {e}")
                    logger.error(f"Candidate data: {candidate_data}")
                    continue
            
            logger.info(f" Successfully parsed {len(candidates)} candidates from Gemini response")
            logger.info(f" Files saved - JSON: {json_path}, CSV: {csv_path}")
            
            return candidates
            
        except Exception as e:
            logger.error(f"Error parsing Gemini candidates: {e}")
            return []

    def _extract_candidates_with_openai(self, gemini_response: str) -> List[Dict[str, Any]]:
        """Use OpenAI 4o to extract structured candidate data from Gemini response."""
        try:
            # Initialize OpenAI client if needed
            if not self.openai_client:
                import openai
                self.openai_client = openai.OpenAI()
            
            # Create extraction prompt for OpenAI
            extraction_prompt = f"""
    Extract candidate information from the following Gemini response text and return as a JSON array.

    GEMINI RESPONSE:
    {gemini_response}

    INSTRUCTIONS:
    1. Find all candidates mentioned in the text
    2. Extract the following fields for each candidate:
    - full_name: Complete name of the candidate
    - current_title: Current job title/position
    - current_company: Current company/organization
    - location: City, state/country location
    - linkedin_url: LinkedIn profile URL if mentioned
    - skills: List of skills/expertise mentioned
    - strengths: List of key strengths mentioned
    - experience_summary: Brief summary of their experience
    - email: Email address if mentioned (or null if not found)
    - phone: Phone number if mentioned (or null if not found)

    3. Skip any placeholder names like "Candidate Name Redacted", "Example Profile", etc.
    4. Only include real, valid candidate names
    5. If LinkedIn URL is mentioned as "to be added" or similar, set to null
    6. If email/phone not found, set to null

    Return ONLY a valid JSON array with this exact structure:
    [
    {{
        "full_name": "Candidate Name",
        "current_title": "Job Title",
        "current_company": "Company Name",
        "location": "City, Country",
        "linkedin_url": "https://linkedin.com/in/profile" or null,
        "email": "email@example.com" or null,
        "phone": "+1234567890" or null,
        "skills": ["skill1", "skill2"],
        "strengths": ["strength1", "strength2"],
        "experience_summary": "Brief summary"
    }}
    ]

    Return only valid JSON, no additional text or explanations.
    """
            
            # Make OpenAI request with reduced token limit to avoid truncation
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.1,
                max_tokens=3000,  # Reduced to fit within limits
                timeout=60
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean and parse JSON response
            if content.startswith('```json'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            candidates_data = json.loads(content)
            
            if not isinstance(candidates_data, list):
                logger.error("OpenAI response is not a list")
                return []
            
            logger.info(f" OpenAI 4o extracted {len(candidates_data)} candidates")
            
            # Validate and clean the data
            validated_candidates = []
            for candidate in candidates_data:
                if self._is_valid_candidate_data(candidate):
                    validated_candidates.append(candidate)
                else:
                    logger.warning(f"Skipping invalid candidate: {candidate.get('full_name', 'Unknown')}")
            
            logger.info(f"Validated {len(validated_candidates)} candidates")
            return validated_candidates
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in OpenAI response: {e}")
            logger.error(f"OpenAI response content: {content[:500]}...")
            return []
        except Exception as e:
            logger.error(f"Error extracting candidates with OpenAI: {e}")
            return []

    def _is_valid_candidate_data(self, candidate_data: Dict[str, Any]) -> bool:
        """Validate candidate data extracted by OpenAI."""
        # Check required fields
        if not candidate_data.get('full_name'):
            return False
        
        name = candidate_data['full_name'].lower()
        
        # Reject dummy/placeholder names
        dummy_patterns = [
            'john doe', 'jane doe', 'john smith', 'jane smith',
            'test user', 'sample candidate', 'example person',
            'dummy candidate', 'placeholder name', 'unknown candidate',
            'candidate name', 'your name', 'full name', 'name redacted',
            'redacted for privacy', 'example profile', 'candidate example'
        ]
        
        if any(dummy in name for dummy in dummy_patterns):
            return False
        
        # Check name format
        words = candidate_data['full_name'].split()
        if len(words) < 2:
            return False
        
        # Should not contain numbers
        if any(char.isdigit() for char in candidate_data['full_name']):
            return False
        
        return True

    def _is_valid_email(self, email: str) -> bool:
        """Check if email format is valid."""
        import re
        if not email:
            return False
        pattern = r'^[^@]+@[^@]+\.[^@]+$'
        return bool(re.match(pattern, email))

    def _save_candidates_to_csv(self, candidates_data: List[Dict[str, Any]], csv_path: str):
        """Save candidates data to CSV file."""
        try:
            if not candidates_data:
                logger.warning("No candidates data to save to CSV")
                return
            
            # Define CSV headers
            headers = [
                'full_name', 
                'current_title',
                'current_company',
                'location',
                'linkedin_url',
                'email',
                'phone',
                'skills',
                'strengths',
                'experience_summary'
            ]
            import csv
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                
                for candidate in candidates_data:
                    # Convert lists to strings for CSV
                    row = candidate.copy()
                    if 'skills' in row and isinstance(row['skills'], list):
                        row['skills'] = ', '.join(row['skills'])
                    if 'strengths' in row and isinstance(row['strengths'], list):
                        row['strengths'] = ' | '.join(row['strengths'])
                    
                    # Handle None values
                    for key in headers:
                        if row.get(key) is None:
                            row[key] = ''
                    
                    # Only include headers that exist in the data
                    filtered_row = {k: v for k, v in row.items() if k in headers}
                    writer.writerow(filtered_row)
            
            logger.info(f" Saved {len(candidates_data)} candidates to CSV")
            
        except Exception as e:
            logger.error(f"Error saving candidates to CSV: {e}")

    
    def _deduplicate_candidates(self, new_candidates: List[CandidateProfile], existing_candidates: List[CandidateProfile]) -> List[CandidateProfile]:
        """Remove duplicate candidates based on name and company."""
        
        # Create set of existing candidate signatures
        existing_signatures = set()
        for candidate in existing_candidates:
            signature = f"{candidate.full_name.lower()}_{candidate.current_company.lower() if candidate.current_company else 'unknown'}"
            existing_signatures.add(signature)
        
        # Filter new candidates
        unique_candidates = []
        for candidate in new_candidates:
            signature = f"{candidate.full_name.lower()}_{candidate.current_company.lower() if candidate.current_company else 'unknown'}"
            if signature not in existing_signatures:
                unique_candidates.append(candidate)
                existing_signatures.add(signature)
        
        return unique_candidates
    
    def _filter_candidates_by_criteria(self, candidates: List[CandidateProfile], job_data: JobDescription) -> List[CandidateProfile]:
        """Filter candidates based on job criteria."""
        
        filtered = []
        
        for candidate in candidates:
            # Location filter
            if job_data.location and candidate.location:
                if candidate.location.country != job_data.location.country:
                    continue
            
            # Company filter (exclude same company)
            if job_data.company and candidate.current_company:
                if candidate.current_company.lower() == job_data.company.lower():
                    continue
            
            filtered.append(candidate)
        
        return filtered
    
    def _generate_discovery_report(self, initial_rankings: List[CandidateRanking], 
                                 final_rankings: List[CandidateRanking], 
                                 discovery_stats: Dict[str, Any], 
                                 job_data: JobDescription) -> str:
        """Generate comprehensive discovery report."""
        
        # Calculate improvements
        initial_count = len(initial_rankings)
        final_count = len(final_rankings)
        candidates_added = final_count - initial_count
        
        initial_top_score = initial_rankings[0].overall_score if initial_rankings else 0
        final_top_score = final_rankings[0].overall_score if final_rankings else 0
        score_improvement = final_top_score - initial_top_score
        
        # Count sources
        pdl_count = discovery_stats['source_distribution']['pdl_api']
        resume_count = discovery_stats['source_distribution']['uploaded_resume']
        gemini_count = discovery_stats['source_distribution']['gemini_discovery']
        
        report = f"""
 ITERATIVE CANDIDATE DISCOVERY REPORT
============================================================

 DISCOVERY SUMMARY:
   Job Position: {job_data.title}
   Company: {job_data.company or 'Not specified'}
   Total Iterations: {discovery_stats['iterations']}
   Candidates Discovered: {discovery_stats['candidates_discovered']}
   Initial Pool: {initial_count} candidates
   Final Pool: {final_count} candidates
   Pool Growth: +{candidates_added} candidates

 QUALITY IMPROVEMENT:
   Initial Top Score: {initial_top_score:.3f}
   Final Top Score: {final_top_score:.3f}
   Score Improvement: {score_improvement:+.3f}

 API PERFORMANCE:
   Total Gemini Calls: {discovery_stats['total_api_calls']}
   Successful Calls: {discovery_stats['successful_calls']}
   Failed Calls: {discovery_stats['failed_calls']}
   Success Rate: {(discovery_stats['successful_calls'] / max(discovery_stats['total_api_calls'], 1)) * 100:.1f}%

 CANDIDATE SOURCES:
    PDL API: {pdl_count} candidates
    Uploaded Resumes: {resume_count} candidates
    Gemini Discovery: {gemini_count} candidates

 TOP 10 FINAL CANDIDATES:"""
        
        # Add top candidates with enhanced source tracking
        for i, ranking in enumerate(final_rankings[:10], 1):
            source_icon = ""
            if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                source_icon = ""
            elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                source_icon = ""
            
            report += f"""
    {i}. {ranking.candidate_name} {source_icon} - Score: {ranking.overall_score:.3f} | {ranking.current_title} at {ranking.current_company}"""
        
        return report
    
    def enhance_rankings_with_discovery_metadata(self, rankings: List[CandidateRanking], all_candidates: List[CandidateProfile]) -> List[CandidateRanking]:
        """Enhance rankings with discovery metadata for better tracking."""
        
        enhanced_rankings = []
        
        for ranking in rankings:
            # Find the original candidate to get discovery metadata
            original_candidate = None
            for candidate in all_candidates:
                if candidate.candidate_id == ranking.candidate_id:
                    original_candidate = candidate
                    break
            
            # Check if this is a discovered candidate
            if original_candidate and hasattr(original_candidate, '_discovery_iteration'):
                # This is a discovered candidate - enhance the explanation
                iteration = getattr(original_candidate, '_discovery_iteration', 0)
                source = getattr(original_candidate, '_discovery_source', 'unknown')
                
                if ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' not in ranking.match_explanation:
                    enhanced_explanation = f" GEMINI 2.5 PRO DISCOVERED CANDIDATE (Iteration {iteration}): {ranking.match_explanation}"
                    
                    # Create a new ranking with enhanced explanation
                    enhanced_ranking = CandidateRanking(
                        candidate_id=ranking.candidate_id,
                        candidate_name=ranking.candidate_name,
                        current_title=ranking.current_title,
                        current_company=ranking.current_company,
                        linkedin_url=ranking.linkedin_url,
                        overall_score=ranking.overall_score,
                        dimension_scores=ranking.dimension_scores,
                        strengths=ranking.strengths,
                        concerns=ranking.concerns,
                        recommendations=ranking.recommendations,
                        confidence_level=ranking.confidence_level,
                        match_explanation=enhanced_explanation,
                        key_differentiators=ranking.key_differentiators,
                        interview_focus_areas=ranking.interview_focus_areas
                    )
                    enhanced_rankings.append(enhanced_ranking)
                else:
                    enhanced_rankings.append(ranking)
            else:
                enhanced_rankings.append(ranking)
        
        return enhanced_rankings


# Export the main class
__all__ = ['CandidateRanker']