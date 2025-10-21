import logging
import json
import time
from typing import List, Dict, Any, Optional, Union
import requests

# Import models
from src.core.models import CandidateProfile

logger = logging.getLogger(__name__)

class PDLAPIClient:
    """People Data Labs API client with 100% AI-powered search term generation"""
    
    def __init__(self):
        from src.config.settings import get_settings
        self.settings = get_settings()
        self.api_key = self.settings.pdl_api_key
        self.base_url = "https://api.peopledatalabs.com/v5"
        
        # Initialize OpenAI if available
        try:
            if hasattr(self.settings, 'openai_api_key') and self.settings.openai_api_key and self.settings.openai_api_key != "your_openai_api_key_here":
                try:
                    from openai import OpenAI
                    self.openai_client = OpenAI(api_key=self.settings.openai_api_key)
                    logger.info(" OpenAI client initialized for 100% AI-powered query generation")
                except ImportError:
                    self.openai_client = None
                    logger.error(" OpenAI not installed - this client requires OpenAI for operation")
                    raise ImportError("OpenAI package is required for PureAIPDLClient")
            else:
                self.openai_client = None
                logger.error(" OpenAI API key not provided - this client requires OpenAI for operation")
                raise ValueError("OpenAI API key is required for PureAIPDLClient")
        except Exception as e:
            self.openai_client = None
            logger.error(f" OpenAI initialization failed: {e} - this client requires OpenAI for operation")
            raise
    
    def search_candidates(self, job_description: str, max_candidates: int = 10) -> List[Dict[str, Any]]:
        """Search for candidates using PDL API with 100% AI-generated terms."""
        logger.info(f" Starting AI-powered candidate search for: {job_description[:100]}...")
        logger.info(f" Target: {max_candidates} candidates")
        
        # Generate search terms using ONLY AI
        search_terms = self.generate_search_terms(job_description)
        
        all_candidates = []
        
        # Search strategies
        search_strategies = [
            ("job_and_skills", self._search_job_and_skills),
            ("job_titles_only", self._search_job_titles_only),
            ("basic_terms", self._search_basic_terms)
        ]
        
        for strategy_name, strategy_func in search_strategies:
            if len(all_candidates) >= max_candidates:
                break
                
            logger.info(f"🔍 Trying {strategy_name} search...")
            try:
                new_candidates = strategy_func(search_terms, max_candidates - len(all_candidates))
                
                # Deduplicate by LinkedIn URL
                existing_urls = {c.get('linkedin_url') for c in all_candidates if c.get('linkedin_url')}
                unique_new = [
                    c for c in new_candidates 
                    if c.get('linkedin_url') and c.get('linkedin_url') not in existing_urls
                ]
                
                all_candidates.extend(unique_new)
                logger.info(f" {strategy_name} added {len(unique_new)} new candidates")
                
                if len(all_candidates) >= max_candidates:
                    break
                    
            except Exception as e:
                logger.warning(f"⚠️ {strategy_name} search failed: {e}")
                continue
        
        logger.info(f"🎯 Total unique candidates found: {len(all_candidates)}")
        return all_candidates[:max_candidates]
    
    def generate_search_terms(self, job_description: str) -> Dict[str, Any]:
        """Generate search terms using ONLY AI - no fallback, no hardcoded elements."""
        
        if not self.openai_client:
            raise ValueError("OpenAI client is required for pure AI term generation")
        
        # Try AI generation with multiple attempts for reliability
        for attempt in range(3):  # Try up to 3 times
            try:
                ai_terms = self._generate_pure_ai_terms(job_description)
                if ai_terms:
                    return ai_terms
                logger.warning(f"AI attempt {attempt + 1} failed, retrying...")
            except Exception as e:
                logger.warning(f"AI attempt {attempt + 1} failed: {str(e)}")
                if attempt == 2:  # Last attempt
                    raise RuntimeError(f"All AI generation attempts failed. Last error: {str(e)}")
        
        raise RuntimeError("Failed to generate terms using AI after 3 attempts")
    
    def _generate_pure_ai_terms(self, job_description: str) -> Optional[Dict[str, Any]]:
        """Generate ALL search terms using OpenAI 4o - completely dynamic, zero hardcoded elements."""
        
        try:
            # Enhanced prompt that asks AI to generate EVERYTHING dynamically
            prompt = f"""
            You are an expert recruiter and talent acquisition specialist with deep knowledge of global job markets, industries, and professional terminology. Your task is to analyze the following job description and dynamically extract ALL relevant search terms that would help find qualified candidates in a professional database.

            Job Description:
            {job_description}

            IMPORTANT: Do NOT use any predefined lists or categories. Analyze the SPECIFIC job description provided and extract terms that are DIRECTLY relevant to THIS particular role.

            Extract the following information dynamically:

            1. **JOB TITLES** (3-6 titles):
               - Extract the exact job title mentioned in the description
               - Generate similar/equivalent titles used in the industry for this specific role
               - Consider different seniority levels (junior, mid, senior, lead, principal)
               - Include alternative titles that different companies might use for the same role
               - Consider both formal and informal variations

            2. **SKILLS** (6-10 skills):
               - Extract ALL technical skills explicitly mentioned
               - Identify tools, technologies, programming languages, frameworks mentioned
               - Extract soft skills that are crucial for this specific role
               - Include industry-standard skills that would be expected for this position
               - Consider certifications, methodologies, or qualifications mentioned
               - Include both primary skills and related/adjacent skills

            3. **LOCATION INFORMATION**:
               - Extract specific country if mentioned Else take India by default
               - Consider city/state information if provided
               - Identify if remote work is mentioned
               - Return null if no location information is found

            4. **EXPERIENCE LEVEL**:
               - Analyze years of experience mentioned
               - Look for seniority indicators (junior, senior, lead, etc.)
               - Consider education requirements (PhD, Masters, etc.)
               - Classify as: "entry" (0-2 years), "mid" (3-5 years), "senior" (5+ years), "executive" (director+ level)

            5. **INDUSTRY CLASSIFICATION**:
               - Identify the specific industry/sector from context
               - Consider company type, domain, or business model mentioned
               - Be specific (e.g., "fintech" instead of just "technology")

            6. **ADDITIONAL CONTEXT** (extract if relevant):
               - Company size indicators (startup, enterprise, etc.)
               - Work arrangement (remote, hybrid, on-site)
               - Team structure (individual contributor, manager, etc.)
               - Special requirements or preferences

            **CRITICAL INSTRUCTIONS:**
            - Analyze the ACTUAL content of this specific job description
            - Do NOT use generic or template-based responses
            - Be specific and contextual to the role described
            - Use lowercase for consistency
            - Focus on terms that would realistically appear in candidate profiles
            - Consider synonyms and industry variations
            - Prioritize relevance and specificity over generic terms
            location_country by India by default until some other not mentioned
            Return ONLY a valid JSON object in this exact format:
            {{
                "job_titles": ["specific_title_1", "specific_title_2", "specific_title_3"],
                "skills": ["skill_1", "skill_2", "skill_3", "skill_4", "skill_5", "skill_6"],
                "location_country": "specific_country_or_null",
                "experience_level": "entry_or_mid_or_senior_or_executive_or_null",
                "industry": "specific_industry_or_null",
                "work_arrangement": "remote_or_hybrid_or_onsite_or_null",
                "company_size": "startup_or_small_or_medium_or_large_or_enterprise_or_null",
                "team_role": "individual_contributor_or_team_lead_or_manager_or_director_or_null"
            }}
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Very low temperature for consistent, focused results
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content.strip()
            terms = json.loads(content)
            
            # Validate the AI response structure and content
            validated_terms = self._validate_pure_ai_terms(terms, job_description)
            
            if validated_terms:
                logger.info(f" Pure AI generated search terms: {json.dumps(validated_terms)}")
                return validated_terms
            else:
                logger.warning("AI generated terms failed validation")
                return None
            
        except json.JSONDecodeError as e:
            logger.warning(f"AI returned malformed JSON. Content: '{content[:500]}' Error: {str(e)}")
            return None
        except Exception as e:
            logger.warning(f"Pure AI term generation failed: {str(e)}")
            return None
    
    def _validate_pure_ai_terms(self, terms: Dict[str, Any], job_description: str) -> Optional[Dict[str, Any]]:
        """Validate AI-generated terms to ensure quality and relevance."""
        
        try:
            validated = {}
            
            # Validate job titles
            job_titles = terms.get('job_titles', [])
            if isinstance(job_titles, list) and len(job_titles) > 0:
                validated_titles = []
                for title in job_titles[:6]:  # Max 6 titles
                    if isinstance(title, str) and len(title.strip()) > 2:
                        clean_title = title.lower().strip()
                        if len(clean_title) <= 100:  # Reasonable length
                            validated_titles.append(clean_title)
                
                if len(validated_titles) > 0:
                    validated['job_titles'] = validated_titles
                else:
                    logger.warning("No valid job titles found in AI response")
                    return None
            else:
                logger.warning("AI did not provide valid job titles")
                return None
            
            # Validate skills
            skills = terms.get('skills', [])
            if isinstance(skills, list) and len(skills) > 0:
                validated_skills = []
                for skill in skills[:10]:  # Max 10 skills
                    if isinstance(skill, str) and len(skill.strip()) > 1:
                        clean_skill = skill.lower().strip()
                        if len(clean_skill) <= 50:  # Reasonable length
                            validated_skills.append(clean_skill)
                
                if len(validated_skills) > 0:
                    validated['skills'] = validated_skills
                else:
                    logger.warning("No valid skills found in AI response")
                    return None
            else:
                logger.warning("AI did not provide valid skills")
                return None
            
            # Validate optional fields
            optional_fields = [
                'location_country', 'experience_level', 'industry', 
                'work_arrangement', 'company_size', 'team_role'
            ]
            
            for field in optional_fields:
                value = terms.get(field)
                if value and isinstance(value, str) and value.lower() != 'null':
                    clean_value = value.lower().strip()
                    if len(clean_value) > 0 and len(clean_value) <= 50:
                        validated[field] = clean_value
                else:
                    validated[field] = None
            
            # Additional validation: ensure terms are relevant to job description
            jd_lower = job_description.lower()
            
            # Check if at least some job titles or skills appear in the job description
            relevance_score = 0
            total_terms = len(validated['job_titles']) + len(validated['skills'])
            
            for title in validated['job_titles']:
                # Check if parts of the title appear in the job description
                title_words = title.split()
                if any(word in jd_lower for word in title_words if len(word) > 2):
                    relevance_score += 1
            
            for skill in validated['skills']:
                if skill in jd_lower or any(word in jd_lower for word in skill.split() if len(word) > 2):
                    relevance_score += 1
            
            relevance_ratio = relevance_score / total_terms if total_terms > 0 else 0
            
            if relevance_ratio < 0.3:  # At least 30% of terms should be relevant
                logger.warning(f"AI terms have low relevance score: {relevance_ratio:.2f}")
                return None
            
            logger.info(f"AI terms validation passed with relevance score: {relevance_ratio:.2f}")
            return validated
            
        except Exception as e:
            logger.warning(f"Failed to validate AI terms: {str(e)}")
            return None
    
    def _search_job_and_skills(self, terms: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """Search by job titles and skills."""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"job_title": terms.get('job_titles', [])}},
                        {"terms": {"skills": terms.get('skills', [])}}
                    ],
                    "filter": [
                        {"exists": {"field": "linkedin_url"}},
                    ]
                }
            },
            "size": limit
        }
        
        if terms.get('location_country'):
            query["query"]["bool"]["filter"].append({
                "term": {"location_country": terms['location_country']}
            })
        
        return self._make_request(query)
    
    def _search_job_titles_only(self, terms: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """Search by job titles only."""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"job_title": terms.get('job_titles', [])}}
                    ],
                    "filter": [
                        {"exists": {"field": "linkedin_url"}},
                    ]
                }
            },
            "size": limit
        }
        
        return self._make_request(query)
    
    def _search_basic_terms(self, terms: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """Basic search with minimal requirements."""
        query = {
            "query": {
                "bool": {
                    "should": [
                        {"terms": {"job_title": terms.get('job_titles', [])}},
                        {"terms": {"skills": terms.get('skills', [])}}
                    ],
                    "filter": [
                        {"exists": {"field": "linkedin_url"}},
                    ]
                }
            },
            "size": limit
        }
        
        return self._make_request(query)
    
    def _make_request(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Make request to PDL API."""
        
        if not self.api_key or self.api_key == "your_pdl_api_key_here":
            logger.warning("⚠️ PDL API key not configured, returning mock data")
            return self._get_mock_candidates()
        
        headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/person/search",
                headers=headers,
                json=query,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            elif response.status_code == 401:
                logger.error(" PDL API authentication failed - check your API key")
                return []
            else:
                logger.error(f" PDL API error {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f" PDL API request failed: {e}")
            return []
    
    def _get_mock_candidates(self) -> List[Dict[str, Any]]:
        """Return mock candidates for testing."""
        return [
            {
                "id": "mock_candidate_1",
                "full_name": "John Smith",
                "job_title": "Software Engineer",
                "job_company_name": "Tech Corp",
                "linkedin_url": "linkedin.com/in/johnsmith",
                "skills": ["Python", "JavaScript", "React"]
            }
        ]


# Keep the converter classes unchanged as they don't contain hardcoded search logic
class ResearchBasedCandidateConverter:
    """Candidate converter with LinkedIn URL fix."""
    
    @staticmethod
    def convert_pdl_data(pdl_data: List[Any]) -> List[CandidateProfile]:
        """Convert PDL data to CandidateProfile objects."""
        if not pdl_data:
            logger.warning("No PDL data to convert")
            return []
        
        logger.info(f" Converting {len(pdl_data)} PDL candidates...")
        
        converted_candidates = []
        conversion_errors = 0
        
        for i, candidate_data in enumerate(pdl_data):
            try:
                # Handle different data formats
                if isinstance(candidate_data, str):
                    try:
                        candidate_data = json.loads(candidate_data)
                    except json.JSONDecodeError:
                        logger.warning(f"Candidate {i+1}: Invalid JSON string")
                        conversion_errors += 1
                        continue
                
                if not isinstance(candidate_data, dict):
                    logger.warning(f"Candidate {i+1}: Expected dict, got {type(candidate_data)}")
                    conversion_errors += 1
                    continue
                
                # Convert single candidate
                candidate = ResearchBasedCandidateConverter._convert_single_candidate(candidate_data)
                if candidate:
                    converted_candidates.append(candidate)
                else:
                    conversion_errors += 1
                    
            except Exception as e:
                logger.warning(f"Failed to convert candidate {i+1}: {e}")
                conversion_errors += 1
                continue
        
        success_rate = (len(converted_candidates) / len(pdl_data)) * 100 if pdl_data else 0
        logger.info(f" Successfully converted {len(converted_candidates)} out of {len(pdl_data)} candidates ({success_rate:.1f}%)")
        
        return converted_candidates
    
    @staticmethod
    def _convert_single_candidate(person_data: Dict[str, Any]) -> Optional[CandidateProfile]:
        """Convert single candidate with LinkedIn URL fix."""
        try:
            # Extract basic info
            candidate_id = (
                person_data.get('id') or 
                person_data.get('person_id') or 
                f"pdl_{hash(str(person_data))}"
            )
            
            full_name = (
                person_data.get('full_name') or
                person_data.get('name') or
                f"{person_data.get('first_name', '')} {person_data.get('last_name', '')}".strip()
            )
            
            if not full_name or len(full_name.strip()) < 2:
                return None
            
            # Extract job info
            current_title = (
                person_data.get('job_title') or
                person_data.get('title') or
                person_data.get('current_title')
            )
            
            current_company = (
                person_data.get('job_company_name') or
                person_data.get('company') or
                person_data.get('current_company')
            )
            
            # Extract LinkedIn URL
            linkedin_url = (
                person_data.get('linkedin_url') or
                person_data.get('linkedin') or
                person_data.get('profile_url')
            )
            
            # 🔗 CRITICAL FIX: Add protocol to LinkedIn URL if missing
            if linkedin_url and isinstance(linkedin_url, str):
                if not linkedin_url.startswith(('http://', 'https://')):
                    if 'linkedin.com' in linkedin_url:
                        linkedin_url = f"https://{linkedin_url}"
                    else:
                        linkedin_url = None  # Not a valid LinkedIn URL
            
            # Extract skills
            skills = person_data.get('skills', [])
            if not isinstance(skills, list):
                skills = []
            
            # Create candidate profile
            candidate = CandidateProfile(
                candidate_id=candidate_id,
                full_name=full_name,
                current_title=current_title,
                current_company=current_company,
                location=None,
                linkedin_url=linkedin_url,  # Now properly formatted!
                email=None,
                phone=None,
                skills=skills[:10],
                experience_years=None,
                education=[]
            )
            
            return candidate
            
        except Exception as e:
            logger.error(f"Failed to convert single candidate: {e}")
            return None
    
    @staticmethod
    def convert_to_candidate_profile(pdl_data: Any) -> Optional[CandidateProfile]:
        """Convert single candidate or list to CandidateProfile."""
        if isinstance(pdl_data, dict):
            # Single candidate
            return ResearchBasedCandidateConverter._convert_single_candidate(pdl_data)
        elif isinstance(pdl_data, list):
            # List of candidates - return first one
            if pdl_data:
                return ResearchBasedCandidateConverter._convert_single_candidate(pdl_data[0])
            return None
        else:
            logger.warning(f"convert_to_candidate_profile received invalid data: {type(pdl_data)}")
            return None


# Alias for backward compatibility
CandidateConverter = ResearchBasedCandidateConverter

# Export the main classes
__all__ = ['PureAIPDLClient', 'CandidateConverter', 'ResearchBasedCandidateConverter']

