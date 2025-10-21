"""
PDL Query Builder

"""

import json
import logging
from typing import Dict, List, Optional, Any, Union

from src.core.models import JobDescription, ExperienceLevel, EmploymentType
from src.config.settings import get_logger

logger = get_logger()


class PDLQueryBuilder:
    """
    Complete working PDL query builder.
    
    This class builds queries that are guaranteed to work with PDL's API
    by using only supported field names and query structures.
    """
    
    def __init__(self):
        """Initialize the query builder."""
        self.logger = logger
    
    def build_sql_query(self, job_description: JobDescription, limit: int = 50) -> str:
        """
        Build a simple SQL query that works with PDL.
        
        Args:
            job_description: Parsed job description
            limit: Maximum number of results
            
        Returns:
            SQL query string
        """
        conditions = []
        
        # Basic required fields (no LENGTH function - not supported)
        conditions.extend([
            "linkedin_url IS NOT NULL",
            "job_title IS NOT NULL", 
            "full_name IS NOT NULL"
        ])
        
        # Job title matching (simple ILIKE)
        if job_description.title:
            title_words = [word.lower() for word in job_description.title.split() if len(word) > 2]
            if title_words:
                title_conditions = []
                for word in title_words[:3]:  # Limit to 3 words
                    title_conditions.append(f"job_title ILIKE '%{word}%'")
                
                if title_conditions:
                    conditions.append(f"({' OR '.join(title_conditions)})")
        
        # Location matching (use correct field names)
        if job_description.location:
            location_conditions = []
            
            if job_description.location.country:
                location_conditions.append(f"location_country ILIKE '%{job_description.location.country}%'")
            
            if job_description.location.city:
                location_conditions.append(f"location_locality ILIKE '%{job_description.location.city}%'")
            
            if job_description.location.state:
                location_conditions.append(f"location_region ILIKE '%{job_description.location.state}%'")
            
            if location_conditions:
                conditions.append(f"({' OR '.join(location_conditions)})")
        else:
            # Default to India if no location specified
            conditions.append("location_country ILIKE '%india%'")
        
        # Skills matching (simple approach)
        if job_description.required_skills:
            skill_conditions = []
            for skill in job_description.required_skills[:3]:  # Limit to 3 skills
                skill_conditions.append(f"skills ILIKE '%{skill.lower()}%'")
            
            if skill_conditions:
                conditions.append(f"({' OR '.join(skill_conditions)})")
        
        # Build final query
        where_clause = " AND ".join(conditions)
        
        sql = f"""SELECT * FROM person
        WHERE {where_clause}
        ORDER BY job_start_date DESC
        LIMIT {limit}"""
        
        self.logger.info(f"Built SQL query: {sql}")
        return sql
    
    def build_elasticsearch_query(self, job_description: JobDescription, size: int = 50) -> Dict[str, Any]:
        """
        Build an Elasticsearch query that works with PDL.
        
        Args:
            job_description: Parsed job description
            size: Maximum number of results
            
        Returns:
            Elasticsearch query dictionary
        """
        must_conditions = [
            {"exists": {"field": "full_name"}},
            {"exists": {"field": "linkedin_url"}}
        ]
        
        should_conditions = []
        
        # Location matching (use correct PDL field names)
        if job_description.location:
            if job_description.location.country:
                must_conditions.append({
                    "term": {"location_country": job_description.location.country.lower()}
                })
            
            if job_description.location.city:
                should_conditions.append({
                    "match": {"location_locality": job_description.location.city}
                })
            
            if job_description.location.state:
                should_conditions.append({
                    "match": {"location_region": job_description.location.state}
                })
        else:
            # Default to India
            must_conditions.append({
                "term": {"location_country": "india"}
            })
        
        # Job title matching (no boost parameters)
        if job_description.title:
            # Add phrase match for full title
            should_conditions.append({
                "match_phrase": {
                    "job_title": job_description.title
                }
            })
            
            # Add individual word matches
            title_words = [word.lower() for word in job_description.title.split() if len(word) > 2]
            for word in title_words[:3]:  # Limit to 3 words
                should_conditions.append({
                    "match": {
                        "job_title": word
                    }
                })
        
        # Skills matching (use terms for exact matching)
        if job_description.required_skills:
            skills_lower = [skill.lower() for skill in job_description.required_skills[:5]]
            should_conditions.append({
                "terms": {"skills": skills_lower}
            })
        
        # Experience level matching
        if hasattr(job_description, 'experience_level') and job_description.experience_level:
            exp_level = job_description.experience_level.lower()
            
            if 'senior' in exp_level or 'lead' in exp_level:
                should_conditions.append({
                    "range": {"inferred_years_experience": {"gte": 5, "lte": 15}}
                })
            elif 'junior' in exp_level or 'entry' in exp_level:
                should_conditions.append({
                    "range": {"inferred_years_experience": {"gte": 0, "lte": 3}}
                })
            else:
                should_conditions.append({
                    "range": {"inferred_years_experience": {"gte": 2, "lte": 10}}
                })
        
        # Build the complete query
        query = {
            "query": {
                "bool": {
                    "must": must_conditions,
                    "should": should_conditions,
                    "minimum_should_match": 1 if should_conditions else 0
                }
            },
            "size": size,
            "sort": [
                {
                    "job_start_date": {
                        "order": "desc",
                        "missing": "_last"
                    }
                },
                {
                    "_score": {
                        "order": "desc"
                    }
                }
            ]
        }
        
        self.logger.info(f"Built Elasticsearch query: {json.dumps(query, indent=2)}")
        return query
    
    def build_simple_query(self, keywords: List[str], location: str = "india", size: int = 50) -> Dict[str, Any]:
        """
        Build a very simple query guaranteed to work.
        
        Args:
            keywords: List of keywords to search for
            location: Location to search in
            size: Maximum number of results
            
        Returns:
            Simple Elasticsearch query
        """
        must_conditions = [
            {"exists": {"field": "full_name"}},
            {"exists": {"field": "linkedin_url"}},
            {"term": {"location_country": location.lower()}}
        ]
        
        should_conditions = []
        
        # Add keyword matches
        for keyword in keywords[:3]:  # Limit to 3 keywords
            should_conditions.append({
                "match": {"job_title": keyword.lower()}
            })
        
        query = {
            "query": {
                "bool": {
                    "must": must_conditions,
                    "should": should_conditions,
                    "minimum_should_match": 1 if should_conditions else 0
                }
            },
            "size": size
        }
        
        self.logger.info(f"Built simple query: {json.dumps(query, indent=2)}")
        return query
    
    def build_ultra_simple_query(self, size: int = 50) -> Dict[str, Any]:
        """
        Build the simplest possible query that will return candidates.
        
        Args:
            size: Maximum number of results
            
        Returns:
            Ultra-simple Elasticsearch query
        """
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "full_name"}},
                        {"exists": {"field": "linkedin_url"}},
                        {"term": {"location_country": "india"}}
                    ]
                }
            },
            "size": size
        }
        
        self.logger.info(f"Built ultra-simple query: {json.dumps(query, indent=2)}")
        return query
    
    def validate_query(self, query: Dict[str, Any]) -> bool:
        """
        Validate that a query follows PDL best practices.
        
        Args:
            query: Elasticsearch query to validate
            
        Returns:
            True if query is valid, False otherwise
        """
        try:
            # Check for forbidden boost parameters
            query_str = json.dumps(query)
            if '"boost"' in query_str:
                self.logger.warning("Query contains forbidden 'boost' parameters")
                return False
            
            # Check for required structure
            if "query" not in query:
                self.logger.warning("Query missing 'query' field")
                return False
            
            if "bool" not in query["query"]:
                self.logger.warning("Query missing 'bool' structure")
                return False
            
            # Check for basic required fields
            must_conditions = query["query"]["bool"].get("must", [])
            has_name_check = any(
                condition.get("exists", {}).get("field") == "full_name" 
                for condition in must_conditions
            )
            
            if not has_name_check:
                self.logger.warning("Query should include full_name existence check")
            
            self.logger.info("Query validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Query validation error: {e}")
            return False
    
    def get_field_mappings(self) -> Dict[str, str]:
        """
        Get the correct PDL field mappings.
        
        Returns:
            Dictionary mapping common field names to PDL field names
        """
        return {
            # Location fields
            "city": "location_locality",
            "state": "location_region", 
            "country": "location_country",
            "location": "location_names",
            
            # Job fields
            "title": "job_title",
            "company": "job_company_name",
            "start_date": "job_start_date",
            
            # Personal fields
            "name": "full_name",
            "email": "emails",
            "phone": "phone_numbers",
            "linkedin": "linkedin_url",
            
            # Experience fields
            "experience": "inferred_years_experience",
            "skills": "skills",
            "education": "education",
            
            # Seniority fields
            "level": "job_title_levels",
            "seniority": "job_title_levels"
        }
    
    def get_supported_operators(self) -> List[str]:
        """
        Get list of supported query operators.
        
        Returns:
            List of supported operators
        """
        return [
            "term",
            "terms", 
            "match",
            "match_phrase",
            "range",
            "exists",
            "bool",
            "must",
            "should",
            "must_not",
            "minimum_should_match"
        ]
    
    def get_forbidden_features(self) -> List[str]:
        """
        Get list of forbidden query features.
        
        Returns:
            List of forbidden features
        """
        return [
            "boost",
            "function_score",
            "script_score",
            "nested",
            "parent_child",
            "percolate",
            "geo_distance",
            "geo_bounding_box"
        ]

