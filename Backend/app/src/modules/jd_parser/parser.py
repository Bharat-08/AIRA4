"""
Job Description Parser Module

This module handles the parsing and extraction of structured information
from job descriptions
.
"""

import json
import re
import requests
from typing import Dict, Any, Optional, List
from pathlib import Path

from src.core.models import JobDescription, Location, ExperienceYears, ExperienceLevel, EmploymentType, CompanySize
from src.config.settings import get_settings, get_logger

logger = get_logger()


class PDFProcessor:
    """PDF processing utility for extracting text from PDF files."""
    
    @staticmethod
    def extract_text_from_pdf(file_path: str) -> str:
        """Extract text from PDF using multiple methods."""
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("PyPDF2 is required for PDF processing. Install with: pip install PyPDF2")
        
        logger.info(f"Extracting text from PDF: {file_path}")
        
        # Method 1: PyPDF2
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text.strip():
                            text += page_text + "\n"
                    except Exception as e:
                        logger.warning(f"Error extracting page {page_num}: {e}")
                        continue
                
                if text.strip():
                    logger.info(f"Successfully extracted {len(text)} characters using PyPDF2")
                    return text.strip()
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {e}")
        
        # Method 2: Try reading as text file (fallback)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                text = file.read()
                if text.strip():
                    logger.info(f"Successfully read as text file: {len(text)} characters")
                    return text.strip()
        except Exception as e:
            logger.warning(f"Text file reading failed: {e}")
        
        # Method 3: Try different encodings
        encodings = ['latin-1', 'cp1252', 'iso-8859-1']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='ignore') as file:
                    text = file.read()
                    if text.strip():
                        logger.info(f"Successfully read with {encoding} encoding: {len(text)} characters")
                        return text.strip()
            except Exception as e:
                logger.warning(f"Reading with {encoding} encoding failed: {e}")
                continue
        
        raise ValueError(f"Could not extract text from PDF: {file_path}")


class JobDescriptionParser:
    """Advanced job description parser with AI integration."""
    
    def __init__(self):
        """Initialize the parser with configuration."""
        self.settings = get_settings()
        self.openai_config = {
            'model': self.settings.openai_model,
            'temperature': self.settings.openai_temperature,
            'max_tokens': self.settings.openai_max_tokens,
            'timeout': self.settings.openai_timeout
        }
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    def parse_job_description(self, text: str) -> JobDescription:
        """Parse job description text into structured format."""
        logger.info("Parsing job description with AI-powered analysis...")
        
        try:
            # Use OpenAI for advanced parsing
            parsed_data = self._parse_with_openai(text)
            logger.info(f"Successfully parsed job description: {parsed_data.get('title', 'Unknown')}")
            
            # Convert to Pydantic model
            return self._convert_to_job_description(parsed_data)
            
        except Exception as e:
            logger.warning(f"OpenAI parsing failed: {e}. Using fallback parser.")
            return self._fallback_parse(text)
    
    def parse_from_file(self, file_path: str) -> JobDescription:
        """Parse job description from file (PDF or text)."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix.lower() == '.pdf':
            text = PDFProcessor.extract_text_from_pdf(str(file_path))
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        
        return self.parse_job_description(text)
    
    def _parse_with_openai(self, text: str) -> Dict[str, Any]:
        """Parse using OpenAI API with enhanced prompting."""
        
        prompt = f"""
        You are an expert HR assistant. Parse this job description and extract structured information.
        
        Return a JSON object with these exact fields:
        {{
            "title": "exact job title",
            "company": "company name or null",
            "location": {{
                "city": "city name or null",
                "state": "state/province or null", 
                "country": "country or null",
                "remote_allowed": true/false
            }},
            "experience_level": "entry/junior/mid/senior/lead/principal/executive or null",
            "experience_years": {{
                "minimum": number or null,
                "maximum": number or null
            }},
            "required_skills": ["skill1", "skill2", ...],
            "preferred_skills": ["skill1", "skill2", ...],
            "responsibilities": ["responsibility1", "responsibility2", ...],
            "requirements": ["requirement1", "requirement2", ...],
            "benefits": ["benefit1", "benefit2", ...],
            "salary_range": "salary range text or null",
            "employment_type": "full_time/part_time/contract/freelance/internship or null",
            "industry": "industry name or null",
            "company_size": "startup/small/medium/large/enterprise or null",
            "education_requirements": ["degree1", "degree2", ...],
            "certifications": ["cert1", "cert2", ...]
        }}
        
        Guidelines:
        - Extract exact information from the text
        - Use null for missing information
        - Keep skills concise and relevant
        - Limit arrays to most important items
        - Ensure experience_level matches the enum values
        - Ensure employment_type matches the enum values
        
        Job Description:
        {text}
        
        Return only valid JSON:
        """
        
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.openai_config['model'],
            "messages": [
                {
                    "role": "system", 
                    "content": "You are an expert HR assistant that parses job descriptions into structured data. Always return valid JSON with accurate information extraction."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": self.openai_config['temperature'],
            "max_tokens": self.openai_config['max_tokens']
        }
        
        response = requests.post(
            self.base_url, 
            headers=headers, 
            json=data, 
            timeout=self.openai_config['timeout']
        )
        response.raise_for_status()
        
        result = response.json()
        content = result['choices'][0]['message']['content'].strip()
        
        # Clean up JSON response
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        
        return json.loads(content)
    
    def _fallback_parse(self, text: str) -> JobDescription:
        """Fallback parser using basic text analysis."""
        logger.info("Using fallback job description parser...")
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Extract title (usually first meaningful line)
        title = "Unknown Position"
        for line in lines[:10]:
            if line and len(line) > 5 and not line.lower().startswith(('job', 'position', 'role', 'we are', 'about')):
                title = line
                break
        
        # Extract company name
        company = None
        company_indicators = ['company:', 'organization:', 'employer:', 'at ']
        for line in lines[:15]:
            line_lower = line.lower()
            for indicator in company_indicators:
                if indicator in line_lower:
                    company = line.split(':', 1)[-1].strip() if ':' in line else line.strip()
                    break
            if company:
                break
        
        # Extract location
        location_data = self._extract_location(text)
        
        # Extract skills using keyword matching
        skills = self._extract_skills(text)
        
        # Extract experience requirements
        experience_years = self._extract_experience_years(text)
        experience_level = self._extract_experience_level(text)
        
        # Extract employment type
        employment_type = self._extract_employment_type(text)
        
        # Extract other information
        responsibilities = self._extract_list_items(text, ['responsibilities', 'duties', 'role'])
        requirements = self._extract_list_items(text, ['requirements', 'qualifications', 'must have'])
        benefits = self._extract_list_items(text, ['benefits', 'perks', 'we offer'])
        
        return JobDescription(
            title=title,
            company=company,
            location=location_data,
            experience_level=experience_level,
            experience_years=experience_years,
            required_skills=skills[:15],  # Limit to top 15
            preferred_skills=[],
            responsibilities=responsibilities[:10],
            requirements=requirements[:10],
            benefits=benefits[:10],
            salary_range=self._extract_salary_range(text),
            employment_type=employment_type,
            industry=None,
            company_size=None,
            education_requirements=self._extract_education_requirements(text),
            certifications=[]
        )
    
    def _extract_location(self, text: str) -> Optional[Location]:
        """Extract location information from text."""
        text_lower = text.lower()
        
        # Look for location patterns
        location_patterns = [
            r'location[:\s]+([^\\n]+)',
            r'based in[:\s]+([^\\n]+)',
            r'office[:\s]+([^\\n]+)',
            r'([a-zA-Z\s]+,\s*[a-zA-Z]{2,})',  # City, State pattern
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                location_str = matches[0].strip()
                parts = [part.strip() for part in location_str.split(',')]
                
                return Location(
                    city=parts[0] if len(parts) > 0 else None,
                    state=parts[1] if len(parts) > 1 else None,
                    country=parts[-1] if len(parts) > 2 else None,
                    remote_allowed='remote' in text_lower or 'work from home' in text_lower
                )
        
        return Location(remote_allowed='remote' in text_lower or 'work from home' in text_lower)
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills from text using keyword matching."""
        skill_keywords = [
            # Programming languages
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 'php', 'ruby',
            'swift', 'kotlin', 'scala', 'r', 'matlab', 'sql',
            
            # Frameworks and libraries
            'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask', 'spring', 'laravel',
            'rails', 'asp.net', 'jquery', 'bootstrap', 'tensorflow', 'pytorch', 'pandas', 'numpy',
            
            # Databases
            'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'cassandra', 'oracle',
            'sqlite', 'dynamodb',
            
            # Cloud and DevOps
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'ci/cd', 'terraform',
            'ansible', 'chef', 'puppet', 'git', 'github', 'gitlab', 'bitbucket',
            
            # Other technologies
            'machine learning', 'ai', 'data science', 'analytics', 'tableau', 'power bi',
            'project management', 'agile', 'scrum', 'leadership', 'communication', 'api',
            'rest', 'graphql', 'microservices', 'linux', 'unix', 'windows'
        ]
        
        text_lower = text.lower()
        found_skills = []
        
        for keyword in skill_keywords:
            if keyword in text_lower:
                # Capitalize properly
                if keyword in ['ai', 'api', 'sql', 'ci/cd']:
                    found_skills.append(keyword.upper())
                elif keyword == 'node.js':
                    found_skills.append('Node.js')
                elif keyword == 'asp.net':
                    found_skills.append('ASP.NET')
                else:
                    found_skills.append(keyword.title())
        
        return list(set(found_skills))  # Remove duplicates
    
    def _extract_experience_years(self, text: str) -> Optional[ExperienceYears]:
        """Extract experience years from text."""
        text_lower = text.lower()
        
        # Look for patterns like "5+ years", "3-5 years", "minimum 2 years"
        exp_patterns = [
            r'(\d+)\+?\s*years?',
            r'(\d+)-(\d+)\s*years?',
            r'minimum\s+(\d+)\s*years?',
            r'at least\s+(\d+)\s*years?',
            r'(\d+)\s*to\s*(\d+)\s*years?'
        ]
        
        for pattern in exp_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                match = matches[0]
                if isinstance(match, tuple) and len(match) == 2:
                    # Range pattern
                    return ExperienceYears(minimum=int(match[0]), maximum=int(match[1]))
                else:
                    # Single number
                    return ExperienceYears(minimum=int(match))
        
        return None
    
    def _extract_experience_level(self, text: str) -> Optional[ExperienceLevel]:
        """Extract experience level from text."""
        text_lower = text.lower()
        
        level_mapping = {
            'entry': ExperienceLevel.ENTRY,
            'junior': ExperienceLevel.JUNIOR,
            'mid': ExperienceLevel.MID,
            'senior': ExperienceLevel.SENIOR,
            'lead': ExperienceLevel.LEAD,
            'principal': ExperienceLevel.PRINCIPAL,
            'executive': ExperienceLevel.EXECUTIVE
        }
        
        for keyword, level in level_mapping.items():
            if keyword in text_lower:
                return level
        
        return None
    
    def _extract_employment_type(self, text: str) -> Optional[EmploymentType]:
        """Extract employment type from text."""
        text_lower = text.lower()
        
        type_mapping = {
            'full time': EmploymentType.FULL_TIME,
            'full-time': EmploymentType.FULL_TIME,
            'part time': EmploymentType.PART_TIME,
            'part-time': EmploymentType.PART_TIME,
            'contract': EmploymentType.CONTRACT,
            'freelance': EmploymentType.FREELANCE,
            'internship': EmploymentType.INTERNSHIP
        }
        
        for keyword, emp_type in type_mapping.items():
            if keyword in text_lower:
                return emp_type
        
        return None
    
    def _extract_list_items(self, text: str, section_keywords: List[str]) -> List[str]:
        """Extract list items from specific sections."""
        text_lower = text.lower()
        items = []
        
        for keyword in section_keywords:
            # Find section starting with keyword
            pattern = rf'{keyword}[:\s]*([^\\n]*(?:\\n[^\\n]*)*?)(?=\\n\\n|\\n[A-Z]|$)'
            matches = re.findall(pattern, text_lower, re.MULTILINE | re.DOTALL)
            
            for match in matches:
                # Split by bullet points or line breaks
                lines = re.split(r'[•\-\*]|\n', match)
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 10:  # Filter out short lines
                        items.append(line[:200])  # Limit length
        
        return list(set(items))[:10]  # Remove duplicates and limit
    
    def _extract_salary_range(self, text: str) -> Optional[str]:
        """Extract salary range from text."""
        # Look for salary patterns
        salary_patterns = [
            r'\$[\d,]+\s*-\s*\$[\d,]+',
            r'\$[\d,]+k?\s*-\s*\$[\d,]+k?',
            r'salary[:\s]*\$[\d,]+',
            r'compensation[:\s]*\$[\d,]+'
        ]
        
        for pattern in salary_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return None
    
    def _extract_education_requirements(self, text: str) -> List[str]:
        """Extract education requirements from text."""
        text_lower = text.lower()
        education_keywords = [
            "bachelor's degree", "master's degree", "phd", "doctorate",
            "computer science", "engineering", "mathematics", "mba"
        ]
        
        found_education = []
        for keyword in education_keywords:
            if keyword in text_lower:
                found_education.append(keyword.title())
        
        return list(set(found_education))
    
    def _convert_to_job_description(self, data: Dict[str, Any]) -> JobDescription:
        """Convert parsed data dictionary to JobDescription model."""
        
        # Convert location
        location_data = data.get('location')
        location = None
        if location_data:
            location = Location(**location_data)
        
        # Convert experience years
        exp_years_data = data.get('experience_years')
        experience_years = None
        if exp_years_data:
            experience_years = ExperienceYears(**exp_years_data)
        
        # Convert enums
        experience_level = None
        if data.get('experience_level'):
            try:
                experience_level = ExperienceLevel(data['experience_level'])
            except ValueError:
                pass
        
        employment_type = None
        if data.get('employment_type'):
            try:
                employment_type = EmploymentType(data['employment_type'])
            except ValueError:
                pass
        
        company_size = None
        if data.get('company_size'):
            try:
                company_size = CompanySize(data['company_size'])
            except ValueError:
                pass
        
        return JobDescription(
            title=data.get('title', 'Unknown Position'),
            company=data.get('company'),
            location=location,
            experience_level=experience_level,
            experience_years=experience_years,
            required_skills=data.get('required_skills', []),
            preferred_skills=data.get('preferred_skills', []),
            responsibilities=data.get('responsibilities', []),
            requirements=data.get('requirements', []),
            benefits=data.get('benefits', []),
            salary_range=data.get('salary_range'),
            employment_type=employment_type,
            industry=data.get('industry'),
            company_size=company_size,
            education_requirements=data.get('education_requirements', []),
            certifications=data.get('certifications', [])
        )


# Export main classes
__all__ = ['JobDescriptionParser', 'PDFProcessor']