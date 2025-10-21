
import argparse
import csv
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import PyPDF2
import re
import logging
# Handle docx import with proper error handling
try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("  ")

from src.config.settings import get_settings, get_logger, validate_config
from src.workflows.recruitment_workflow import RecruitmentWorkflow, workflow_monitor
from src.modules.jd_parser.parser import PDFProcessor
from src.core.models import WorkflowResult, CandidateProfile

logger = get_logger()


class OutputFormatter:
    """Handles various output formats for recruitment results."""
    
    @staticmethod
    def print_executive_summary(result: WorkflowResult) -> None:
        """Print an executive summary of the recruitment results."""
        print("\n" + "="*100)
        print(" RECRUITMENT ANALYSIS - EXECUTIVE SUMMARY")
        print("="*100)
        
        # Job overview
        job_data = result.job_data
        print(f"\n POSITION ANALYSIS")
        print(f"   Job Title: {job_data.title}")
        if job_data.company:
            print(f"   Company: {job_data.company}")
        if job_data.experience_level:
            print(f"   Seniority Level: {job_data.experience_level.value.title()}")
        
        # Key requirements
        if job_data.required_skills:
            print(f"   Key Skills Required: {', '.join(job_data.required_skills[:5])}")
        
        # Search results
        metadata = result.metadata
        print(f"\n SEARCH RESULTS")
        print(f"   Total Candidates Found: {metadata.candidates_found}")
        print(f"   Candidates Analyzed: {metadata.candidates_ranked}")
        print(f"   Processing Time: {metadata.processing_time_seconds:.1f} seconds")
        
        if not result.rankings:
            print(f"\n NO QUALIFIED CANDIDATES FOUND")
            print(f"   Consider:")
            print(f"   • Broadening search criteria")
            print(f"   • Adjusting required skills")
            print(f"   • Expanding geographic scope")
            print(f"   • Reviewing experience level requirements")
            return
        
        # Top candidates analysis
        rankings = result.rankings
        print(f"\n TOP CANDIDATES ANALYSIS")
        
        # Score distribution
        scores = [r.overall_score for r in rankings]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        
        print(f"   Highest Score: {max_score:.3f}")
        print(f"   Average Score: {avg_score:.3f}")
        
        # Confidence levels
        confidence_counts = {}
        for ranking in rankings:
            conf = ranking.confidence_level.value
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
        
        print(f"   Confidence Distribution: {dict(confidence_counts)}")
        
        # Top 5 candidates detailed view
        print(f"\n TOP 5 CANDIDATES")
        for i, ranking in enumerate(rankings[:5], 1):
            # Determine source icon
            source_icon = ""  # Default PDL
            if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                source_icon = ""
            elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                source_icon = ""
            
            print(f"\n   {i}. {ranking.candidate_name} {source_icon}")
            print(f"       Overall Score: {ranking.overall_score:.3f}")
            print(f"       Current Role: {ranking.current_title or 'Not specified'}")
            print(f"       Company: {ranking.current_company or 'Not specified'}")
            print(f"       Confidence: {ranking.confidence_level.value.title()}")
            
            # Key strengths
            if ranking.strengths:
                print(f"       Key Strengths: {', '.join(ranking.strengths[:2])}")
            
            # Main concerns
            if ranking.concerns:
                print(f"       Main Concerns: {', '.join(ranking.concerns[:2])}")
            
            # Recommendations
            if ranking.recommendations:
                print(f"       Next Steps: {ranking.recommendations[0]}")
        
        # Hiring recommendations
        print(f"\n HIRING RECOMMENDATIONS")
        
        # Categorize candidates by score and confidence
        immediate_interviews = []
        secondary_review = []
        
        for ranking in rankings:
            if ranking.overall_score >= 0.7 and ranking.confidence_level.value in ['high', 'medium']:
                immediate_interviews.append(ranking)
            elif ranking.overall_score >= 0.5:
                secondary_review.append(ranking)
        
        if immediate_interviews:
            print(f"   🟢 IMMEDIATE INTERVIEWS ({len(immediate_interviews)} candidates)")
            for ranking in immediate_interviews[:5]:  # Top 5
                source_icon = ""
                if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                    source_icon = ""
                elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                    source_icon = ""
                print(f"      • {ranking.candidate_name} {source_icon}")
        
        if secondary_review:
            print(f"   🟡 SECONDARY REVIEW ({len(secondary_review)} candidates)")
            for ranking in secondary_review[:3]:  # Top 3
                source_icon = ""
                if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                    source_icon = ""
                elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                    source_icon = ""
                print(f"      • {ranking.candidate_name} {source_icon}")
    
    @staticmethod
    def print_discovery_report(discovery_report: str) -> None:
        """Print the iterative discovery report."""
        print("\n" + "="*100)
        print(discovery_report)
        print("="*100)
    
    @staticmethod
    def save_to_csv(result: WorkflowResult, filepath: Path) -> None:
        """Save results to CSV format."""
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'rank', 'candidate_name', 'current_title', 'current_company', 
                'linkedin_url', 'overall_score', 'technical_skills', 'experience_relevance',
                'seniority_match', 'education_fit', 'industry_experience', 'location_compatibility',
                'confidence_level', 'strengths', 'concerns', 'recommendations',
                'match_explanation', 'key_differentiators', 'interview_focus_areas', 'source'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for rank, ranking in enumerate(result.rankings, 1):
                # Determine source
                source = "PDL API"
                if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                    source = "Uploaded Resume"
                elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                    source = "Gemini 2.5 Pro Discovery"
                
                writer.writerow({
                    'rank': rank,
                    'candidate_name': ranking.candidate_name,
                    'current_title': ranking.current_title,
                    'current_company': ranking.current_company,
                    'linkedin_url': ranking.linkedin_url,
                    'overall_score': ranking.overall_score,
                    'technical_skills': ranking.dimension_scores.technical_skills,
                    'experience_relevance': ranking.dimension_scores.experience_relevance,
                    'seniority_match': ranking.dimension_scores.seniority_match,
                    'education_fit': ranking.dimension_scores.education_fit,
                    'industry_experience': ranking.dimension_scores.industry_experience,
                    'location_compatibility': ranking.dimension_scores.location_compatibility,
                    'confidence_level': ranking.confidence_level.value,
                    'strengths': '; '.join(ranking.strengths),
                    'concerns': '; '.join(ranking.concerns),
                    'recommendations': '; '.join(ranking.recommendations),
                    'match_explanation': ranking.match_explanation,
                    'key_differentiators': '; '.join(ranking.key_differentiators),
                    'interview_focus_areas': '; '.join(ranking.interview_focus_areas),
                    'source': source
                })
    
    @staticmethod
    def save_to_json(result: WorkflowResult, filepath: Path, discovery_data: Optional[Dict] = None) -> None:
        """Save results to JSON format with optional discovery data."""
        data = {
            'job_analysis': {
                'title': result.job_data.title,
                'company': result.job_data.company,
                'location': {
                    'city': result.job_data.location.city if result.job_data.location else None,
                    'state': result.job_data.location.state if result.job_data.location else None,
                    'country': result.job_data.location.country if result.job_data.location else None
                },
                'required_skills': result.job_data.required_skills,
                'experience_level': result.job_data.experience_level.value if result.job_data.experience_level else None
            },
            'search_metadata': {
                'candidates_found': result.metadata.candidates_found,
                'candidates_ranked': result.metadata.candidates_ranked,
                'processing_time_seconds': result.metadata.processing_time_seconds,
                'timestamp': result.metadata.timestamp.isoformat()
            },
            'candidates': []
        }
        
        # Add discovery data if available
        if discovery_data:
            data['discovery_analysis'] = discovery_data
        
        for rank, ranking in enumerate(result.rankings, 1):
            # Determine source
            source = "pdl_api"
            source_icon = ""
            has_resume_data = False
            
            if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                source = "uploaded_resume"
                source_icon = ""
                has_resume_data = True
            elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                source = "gemini_discovery"
                source_icon = ""
            
            candidate_data = {
                "rank": rank,
                "candidate_id": ranking.candidate_id,
                "candidate_name": ranking.candidate_name,
                "current_title": ranking.current_title,
                "current_company": ranking.current_company,
                "linkedin_url": ranking.linkedin_url,
                "overall_score": ranking.overall_score,
                "dimension_scores": {
                    "technical_skills": ranking.dimension_scores.technical_skills,
                    "experience_relevance": ranking.dimension_scores.experience_relevance,
                    "seniority_match": ranking.dimension_scores.seniority_match,
                    "education_fit": ranking.dimension_scores.education_fit,
                    "industry_experience": ranking.dimension_scores.industry_experience,
                    "location_compatibility": ranking.dimension_scores.location_compatibility
                },
                "strengths": ranking.strengths,
                "concerns": ranking.concerns,
                "recommendations": ranking.recommendations,
                "confidence_level": ranking.confidence_level.value,
                "match_explanation": ranking.match_explanation,
                "key_differentiators": ranking.key_differentiators,
                "interview_focus_areas": ranking.interview_focus_areas,
                "source": source,
                "source_icon": source_icon,
                "has_resume_data": has_resume_data
            }
            
            data['candidates'].append(candidate_data)
        
        with open(filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)

    @staticmethod
    def save_post_discovery_results(final_rankings, job_data, discovery_data: Optional[Dict] = None) -> None:
        """Save final results after discovery in both CSV and JSON formats."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create results directory if it doesn't exist
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        
        # Save CSV
        csv_path = results_dir / f"post_discovery_results_{timestamp}.csv"
        OutputFormatter._save_discovery_csv(final_rankings, job_data, csv_path, discovery_data)
        
        # Save JSON
        json_path = results_dir / f"post_discovery_results_{timestamp}.json"
        OutputFormatter._save_discovery_json(final_rankings, job_data, json_path, discovery_data)
        
        print(f"\n POST-DISCOVERY RESULTS SAVED:")
        print(f"    CSV: {csv_path}")
        print(f"    JSON: {json_path}")
        
        return str(csv_path), str(json_path)
    
    @staticmethod
    def _save_discovery_csv(final_rankings, job_data, filepath: Path, discovery_data: Optional[Dict] = None) -> None:
        """Save discovery results to CSV format."""
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'rank', 'candidate_name', 'current_title', 'current_company', 
                'linkedin_url', 'email', 'phone', 'location', 'overall_score', 
                'technical_skills', 'experience_relevance', 'seniority_match', 
                'education_fit', 'industry_experience', 'location_compatibility',
                'confidence_level', 'strengths', 'concerns', 'recommendations',
                'match_explanation', 'key_differentiators', 'interview_focus_areas', 
                'source', 'source_icon', 'discovery_iteration'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for rank, ranking in enumerate(final_rankings, 1):
                # Determine source and discovery iteration
                source = "PDL API"
                source_icon = ""
                discovery_iteration = 0
                
                if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                    source = "Uploaded Resume"
                    source_icon = ""
                elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                    source = "Gemini 2.5 Pro Discovery"
                    source_icon = ""
                    # Try to extract iteration number from explanation
                    if 'iteration' in ranking.match_explanation.lower():
                        import re
                        match = re.search(r'iteration (\d+)', ranking.match_explanation.lower())
                        if match:
                            discovery_iteration = int(match.group(1))
                
                # Get location string
                location_str = ""
                if hasattr(ranking, 'location') and ranking.location:
                    location_str = f"{ranking.location.city}, {ranking.location.state}, {ranking.location.country}"
                
                writer.writerow({
                    'rank': rank,
                    'candidate_name': ranking.candidate_name,
                    'current_title': ranking.current_title or '',
                    'current_company': ranking.current_company or '',
                    'linkedin_url': ranking.linkedin_url or '',
                    'email': getattr(ranking, 'email', '') or '',
                    'phone': getattr(ranking, 'phone', '') or '',
                    'location': location_str,
                    'overall_score': ranking.overall_score,
                    'technical_skills': ranking.dimension_scores.technical_skills,
                    'experience_relevance': ranking.dimension_scores.experience_relevance,
                    'seniority_match': ranking.dimension_scores.seniority_match,
                    'education_fit': ranking.dimension_scores.education_fit,
                    'industry_experience': ranking.dimension_scores.industry_experience,
                    'location_compatibility': ranking.dimension_scores.location_compatibility,
                    'confidence_level': ranking.confidence_level.value,
                    'strengths': '; '.join(ranking.strengths),
                    'concerns': '; '.join(ranking.concerns),
                    'recommendations': '; '.join(ranking.recommendations),
                    'match_explanation': ranking.match_explanation,
                    'key_differentiators': '; '.join(ranking.key_differentiators),
                    'interview_focus_areas': '; '.join(ranking.interview_focus_areas),
                    'source': source,
                    'source_icon': source_icon,
                    'discovery_iteration': discovery_iteration
                })
    
    @staticmethod
    def _save_discovery_json(final_rankings, job_data, filepath: Path, discovery_data: Optional[Dict] = None) -> None:
        """Save discovery results to JSON format."""
        data = {
            'job_analysis': {
                'title': job_data.title,
                'company': job_data.company,
                'location': {
                    'city': job_data.location.city if job_data.location else None,
                    'state': job_data.location.state if job_data.location else None,
                    'country': job_data.location.country if job_data.location else None
                },
                'required_skills': job_data.required_skills,
                'experience_level': job_data.experience_level.value if job_data.experience_level else None
            },
            'discovery_metadata': {
                'total_candidates': len(final_rankings),
                'timestamp': datetime.now().isoformat(),
                'discovery_enabled': discovery_data is not None
            },
            'discovery_statistics': discovery_data or {},
            'candidates': []
        }
        
        # Count sources
        source_counts = {'pdl_api': 0, 'uploaded_resume': 0, 'gemini_discovery': 0}
        
        for rank, ranking in enumerate(final_rankings, 1):
            # Determine source
            source = "pdl_api"
            source_icon = ""
            discovery_iteration = 0
            
            if ' UPLOADED RESUME CANDIDATE' in ranking.match_explanation:
                source = "uploaded_resume"
                source_icon = ""
            elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in ranking.match_explanation:
                source = "gemini_discovery"
                source_icon = ""
                # Try to extract iteration number
                import re
                match = re.search(r'iteration (\d+)', ranking.match_explanation.lower())
                if match:
                    discovery_iteration = int(match.group(1))
            
            source_counts[source] += 1
            
            candidate_data = {
                "rank": rank,
                "candidate_id": ranking.candidate_id,
                "candidate_name": ranking.candidate_name,
                "current_title": ranking.current_title,
                "current_company": ranking.current_company,
                "linkedin_url": ranking.linkedin_url,
                "email": getattr(ranking, 'email', None),
                "phone": getattr(ranking, 'phone', None),
                "location": {
                    "city": getattr(ranking, 'location', {}).get('city') if hasattr(ranking, 'location') else None,
                    "state": getattr(ranking, 'location', {}).get('state') if hasattr(ranking, 'location') else None,
                    "country": getattr(ranking, 'location', {}).get('country') if hasattr(ranking, 'location') else None
                },
                "overall_score": ranking.overall_score,
                "dimension_scores": {
                    "technical_skills": ranking.dimension_scores.technical_skills,
                    "experience_relevance": ranking.dimension_scores.experience_relevance,
                    "seniority_match": ranking.dimension_scores.seniority_match,
                    "education_fit": ranking.dimension_scores.education_fit,
                    "industry_experience": ranking.dimension_scores.industry_experience,
                    "location_compatibility": ranking.dimension_scores.location_compatibility
                },
                "strengths": ranking.strengths,
                "concerns": ranking.concerns,
                "recommendations": ranking.recommendations,
                "confidence_level": ranking.confidence_level.value,
                "match_explanation": ranking.match_explanation,
                "key_differentiators": ranking.key_differentiators,
                "interview_focus_areas": ranking.interview_focus_areas,
                "source": source,
                "source_icon": source_icon,
                "discovery_iteration": discovery_iteration
            }
            
            data['candidates'].append(candidate_data)
        
        # Add source distribution
        data['source_distribution'] = source_counts
        
        with open(filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)


class CLIApplication:
    """Main CLI application class."""
    
    def __init__(self):
        """Initialize the CLI application."""
        self.settings = get_settings()
        self.workflow = RecruitmentWorkflow()
        self.formatter = OutputFormatter()
    
    def run(self, args: argparse.Namespace) -> int:
        """Run the CLI application with parsed arguments."""
        try:
            # Handle special commands
            if args.config_check:
                return self._handle_config_check()
            
            if args.workflow_status:
                return self._handle_workflow_status()
            
            if args.performance_metrics:
                return self._handle_performance_metrics()
            
            # Validate configuration
            config_validation = validate_config()
            if not config_validation['valid']:
                print(" Configuration validation failed:")
                for error in config_validation['errors']:
                    print(f"   • {error}")
                return 1
            
            # Get job description
            job_description_text = self._get_job_description(args)
            if not job_description_text:
                print(" Error: No job description provided")
                return 1
            
            # Run workflow
            print(" Starting recruitment workflow...")
            start_time = datetime.now()
            
            result = self.workflow.run_workflow(job_description_text, args.max_candidates)
            
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            # Record execution for monitoring
            workflow_monitor.record_execution(result, execution_time)
            
            # Display initial results
            self.formatter.print_executive_summary(result)
            
            # RESUME UPLOAD FEATURE (restored from original working code)
            resume_candidates = []
            if not hasattr(args, 'non_interactive') or not args.non_interactive:
                resume_candidates = self._handle_resume_upload(result.job_data)
            
            # Re-rank with resume candidates if any were added
            if resume_candidates:
                print(f"\n Re-ranking all candidates including {len(resume_candidates)} uploaded resumes...")
                
                # Get all original candidates
                all_candidates = []
                if hasattr(result, 'candidates') and result.candidates:
                    all_candidates.extend(result.candidates)
                
                # Add resume candidates
                all_candidates.extend(resume_candidates)
                
                # Re-rank all candidates
                from src.modules.candidate_ranking.ranker import CandidateRanker
                ranker = CandidateRanker()
                
                new_rankings = ranker.rank_candidates(result.job_data, all_candidates)
                result.rankings = new_rankings
                
                print(f" Combined ranking completed: {len(result.rankings)} total candidates")
            
            # DISCOVERY FEATURE (if enabled)
            discovery_data = None
            final_rankings = result.rankings  # Default to current rankings
            
            if hasattr(args, 'with_discovery') and args.with_discovery:
                discovery_data = self._run_iterative_discovery(result, args)
                if discovery_data and 'final_rankings' in discovery_data:
                    final_rankings = discovery_data['final_rankings']
            elif not hasattr(args, 'non_interactive') or not args.non_interactive:
                # Ask user if they want discovery (unless in non-interactive mode)
                discovery_data = self._prompt_for_discovery(result, args)
                if discovery_data and 'final_rankings' in discovery_data:
                    final_rankings = discovery_data['final_rankings']
            
            # NEW FEATURE: Save post-discovery results automatically
            if discovery_data and final_rankings:
                print("\n UPDATED RESULTS AFTER DISCOVERY:")
                
                # Update result with final rankings for display
                result.rankings = final_rankings
                self.formatter.print_executive_summary(result)
                
                # Save post-discovery results in both formats
                csv_path, json_path = self.formatter.save_post_discovery_results(
                    final_rankings, 
                    result.job_data, 
                    discovery_data.get('discovery_data', {})
                )
                
                logger.info(f"Post-discovery results saved to CSV: {csv_path}")
                logger.info(f"Post-discovery results saved to JSON: {json_path}")
            
            # Save regular results if requested
            if args.csv or args.json:
                self._save_results(result, args, discovery_data)
            
            # Final summary
            if final_rankings:
                top_candidate = final_rankings[0]
                source_icon = ""
                if ' UPLOADED RESUME CANDIDATE' in top_candidate.match_explanation:
                    source_icon = ""
                elif ' GEMINI 2.5 PRO DISCOVERED CANDIDATE' in top_candidate.match_explanation:
                    source_icon = ""
                print(f"\n Top Recommendation: {top_candidate.candidate_name} {source_icon} (Score: {top_candidate.overall_score:.3f})")
            
            print(f"\n Recruitment workflow completed successfully in {execution_time:.1f} seconds!")
            return 0
            
        except KeyboardInterrupt:
            print("\n Workflow interrupted by user")
            return 1
        except Exception as e:
            print(f"\ Workflow failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return 1
    
    def _handle_resume_upload(self, job_data) -> List[CandidateProfile]:
        """Handle resume upload functionality (restored from working version)."""
        print("\n" + "="*100)
        print(" ADDITIONAL RESUME UPLOAD")
        print("="*100)
        print(f"Job Position: {job_data.title}")
        if job_data.company:
            print(f"Company: {job_data.company}")
        
        try:
            response = input("\nDo you want to add additional resumes for ranking? (y/n): ").strip().lower()
            
            if response not in ['y', 'yes']:
                return []
            
            print("\n Resume Upload Instructions:")
            print("- Supported formats: PDF, TXT" + (", DOCX" if DOCX_AVAILABLE else ""))
            print("- Enter file path or drag & drop file")
            print("- Type 'done' when finished")
            print("- Type 'skip' to skip a file")
            
            resume_candidates = []
            resume_count = 1
            
            while True:
                print(f"\n Resume #{resume_count}:")
                try:
                    file_path = input("Enter resume file path (or 'done' to finish): ").strip().strip('"')
                    
                    if file_path.lower() == 'done':
                        break
                    
                    if file_path.lower() == 'skip':
                        resume_count += 1
                        continue
                    
                    if not file_path or not os.path.exists(file_path):
                        print(f" File not found: {file_path}")
                        continue
                    
                    print(f" Processing resume #{resume_count}...")
                    
                    # Process the resume
                    candidate = self._process_resume_file(file_path, job_data)
                    
                    if candidate:
                        resume_candidates.append(candidate)
                        print(f" Successfully processed: {candidate.full_name}")
                        print(f"   Title: {candidate.current_title or 'Not specified'}")
                        print(f"   Company: {candidate.current_company or 'Not specified'}")
                    else:
                        print(f" Failed to process resume: {file_path}")
                    
                    resume_count += 1
                    
                except (EOFError, KeyboardInterrupt):
                    print("\n Resume upload interrupted")
                    break
                except Exception as e:
                    print(f" Error processing resume: {e}")
                    continue
            
            print(f"\n Successfully processed {len(resume_candidates)} additional resumes")
            return resume_candidates
            
        except (EOFError, KeyboardInterrupt):
            print("\n Skipping resume upload")
            return []
    
    def _process_resume_file(self, file_path: str, job_data) -> Optional[CandidateProfile]:
        """Process a resume file and create a candidate profile."""
        try:
            # Extract text from file
            text_content = self._extract_text_from_file(file_path)
            if not text_content:
                logger.error(f"Could not extract text from file: {file_path}")
                return None
            
            logger.info(f"Extracting text from PDF: {file_path}")
            logger.info(f"Successfully extracted {len(text_content)} characters using PyPDF2")
            
            # Parse with AI
            candidate_data = self._parse_resume_with_ai(text_content, job_data)
            if not candidate_data:
                # Fallback parsing
                candidate_data = self._parse_resume_fallback(text_content)
            
            # Create candidate profile
            candidate = self._create_candidate_from_resume_data(candidate_data, file_path)
            
            logger.info(f" AI parsed resume: {candidate.full_name}")
            return candidate
            
        except Exception as e:
            logger.error(f"Error processing resume file {file_path}: {e}")
            return None
    
    def _extract_text_from_file(self, file_path: str) -> Optional[str]:
        """Extract text from various file formats."""
        try:
            file_extension = Path(file_path).suffix.lower()
            
            if file_extension == '.pdf':
                return self._extract_text_from_pdf(file_path)
            elif file_extension == '.docx' and DOCX_AVAILABLE:
                return self._extract_text_from_docx(file_path)
            elif file_extension == '.txt':
                return self._extract_text_from_txt(file_path)
            else:
                if file_extension == '.docx' and not DOCX_AVAILABLE:
                    logger.error(f"DOCX support not available. Please install python-docx: pip install python-docx")
                else:
                    logger.error(f"Unsupported file format: {file_extension}")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return None
    
    def _extract_text_from_pdf(self, file_path: str) -> Optional[str]:
        """Extract text from PDF file."""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return None
    
    def _extract_text_from_docx(self, file_path: str) -> Optional[str]:
        """Extract text from DOCX file."""
        if not DOCX_AVAILABLE:
            logger.error("DOCX support not available")
            return None
            
        try:
            doc = Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting DOCX text: {e}")
            return None
    
    def _extract_text_from_txt(self, file_path: str) -> Optional[str]:
        """Extract text from TXT file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except Exception as e:
            logger.error(f"Error extracting TXT text: {e}")
            return None
    
    # In cli.py, REPLACE the existing function with this one:

    def _parse_resume_with_ai(self, text_content: str, job_data) -> Optional[Dict[str, Any]]:
        """Parse resume using OpenAI."""
        try:
            import openai
            
            client = openai.OpenAI()
            
            prompt = f"""
            Parse the following resume and extract structured information in JSON format.
            
            Job Context:
            - Position: {job_data.title}
            - Company: {job_data.company or 'Not specified'}
            - Required Skills: {', '.join(job_data.required_skills[:5]) if job_data.required_skills else 'Not specified'}
            
            Resume Text:
            {text_content[:8000]}  # Limit to prevent token overflow
            
            Extract the following information in JSON format:
            {{
                "full_name": "Full name",
                "email": "Email address",
                "phone": "Phone number",
                "location": "City, State/Country",
                "current_title": "Current job title",
                "current_company": "Current company",
                "linkedin_url": "LinkedIn profile URL with https:// prefix",
                "skills": ["skill1", "skill2", "skill3"],
                "education": ["degree1", "degree2"]
            }}
            
            Important:
            - Use "full_name" not "name"
            - LinkedIn URL must start with "https://" or "http://"
            - If LinkedIn URL is incomplete, add "https://" prefix
            - Only include the fields listed above
            
            Return only valid JSON, no additional text.
            """
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean up the response content
            if content.startswith('```json'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            # Additional cleaning for common issues
            if not content.startswith('{'):
                start_idx = content.find('{')
                end_idx = content.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    content = content[start_idx:end_idx+1]
            
            try:
                candidate_data = json.loads(content)
                
                # --- START: NEW FIX FOR LINKEDIN URL ---
                # Validate and fix the LinkedIn URL before returning the data.
                if candidate_data.get('linkedin_url'):
                    linkedin_url = candidate_data['linkedin_url']
                    # Check if it's a valid-looking URL. If not, set it to None.
                    if not isinstance(linkedin_url, str) or not '.com/in/' in linkedin_url.lower():
                        logger.warning(f"Invalid LinkedIn URL found for '{candidate_data.get('full_name')}': '{linkedin_url}'. Discarding it.")
                        candidate_data['linkedin_url'] = None
                    # Ensure it has a protocol and is lowercase
                    elif not linkedin_url.startswith(('http://', 'https://')):
                        candidate_data['linkedin_url'] = f"https://{linkedin_url.lower()}"
                    else:
                        candidate_data['linkedin_url'] = linkedin_url.lower()
                # --- END: NEW FIX FOR LINKEDIN URL ---

                return candidate_data
            except json.JSONDecodeError as json_error:
                logger.warning(f"JSON parsing failed: {json_error}")
                logger.warning(f"Raw content: {content[:200]}...")
                raise ValueError(f"Invalid JSON response from AI")
                
        except Exception as e:
            logger.warning(f"AI resume parsing failed: {e}, using fallback")
            return None
    
    def _parse_resume_fallback(self, text_content: str) -> Dict[str, Any]:
        """Fallback resume parsing using simple text extraction."""
        import re
        
        # Basic extraction patterns
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        phone_pattern = r'[\+]?[1-9]?[0-9]{7,15}'
        
        # Extract basic information
        candidate_data = {
            "full_name": "Unknown",
            "email": None,
            "phone": None,
            "location": "Not specified",
            "current_title": "Not specified",
            "current_company": "Not specified",
            "linkedin_url": None,
            "skills": [],
            "education": []
        }
        
        # Extract email
        email_matches = re.findall(email_pattern, text_content)
        if email_matches:
            candidate_data["email"] = email_matches[0]
        
        # Extract phone
        phone_matches = re.findall(phone_pattern, text_content)
        if phone_matches:
            candidate_data["phone"] = phone_matches[0]
        
        # Try to extract name from first few lines
        lines = text_content.split('\n')[:5]
        for line in lines:
            line = line.strip()
            if len(line) > 2 and len(line) < 50 and not '@' in line and not any(char.isdigit() for char in line):
                candidate_data["full_name"] = line
                break
        
        return candidate_data
    

    # You will need to import the 're' and 'logging' modules at the top of cli.py
    logger = get_logger()

    # Add this helper function inside the CLIApplication class or at the module level
    def _is_valid_email(self, email: str) -> bool:
        """Helper function to validate email format."""
        if not email:
            return False
        # Standard email validation pattern
        pattern = r'^[^@]+@[^@]+\.[^@]+$'
        return bool(re.match(pattern, email))

    # Then, REPLACE the existing _create_candidate_from_resume_data function with this one:
    def _create_candidate_from_resume_data(self, candidate_data: Dict[str, Any], file_path: str) -> CandidateProfile:
        """Create a CandidateProfile from parsed resume data with validation."""
        from src.core.models import Location

        # --- START: NEW VALIDATION LOGIC ---
        # Validate and fix the email before creating the profile.
        email = candidate_data.get('email', '')
        if not self._is_valid_email(email):
            full_name = candidate_data.get('full_name')
            if full_name and full_name != 'Unknown':
                # Generate a placeholder email from the candidate's name
                name_part = ''.join(filter(str.isalnum, full_name.lower().replace(' ', '.')))
                candidate_data['email'] = f"{name_part}@placeholder.email"
                logger.warning(f"Invalid or missing email for '{full_name}'. Generated placeholder: {candidate_data['email']}")
            else:
                # Fallback if the name is also missing
                import time
                candidate_data['email'] = f"candidate.{int(time.time())}@placeholder.email"
                logger.warning(f"Missing name and email for a candidate. Generated random placeholder.")
        # --- END: NEW VALIDATION LOGIC ---

        # Handle location
        location_data = candidate_data.get('location')
        location_obj = None
        if isinstance(location_data, str):
            parts = [part.strip() for part in location_data.split(',')]
            if len(parts) >= 2:
                location_obj = Location(city=parts[0], state=parts[1], country=parts[2] if len(parts) > 2 else "India")
            elif len(parts) == 1:
                location_obj = Location(city=parts[0], state="", country="India")
        elif isinstance(location_data, dict):
            location_obj = Location(**location_data)

        # Create candidate profile
        candidate = CandidateProfile(
            candidate_id=f"resume_{hash(file_path)}_{hash(candidate_data.get('full_name', 'unknown'))}",
            full_name=candidate_data.get('full_name', 'Unknown'),
            email=candidate_data.get('email'), # This is now a valid or placeholder email
            phone=candidate_data.get('phone'),
            location=location_obj,
            linkedin_url=candidate_data.get('linkedin_url'),
            current_title=candidate_data.get('current_title'),
            current_company=candidate_data.get('current_company'),
            skills=candidate_data.get('skills', [])[:10],
            education=candidate_data.get('education', [])[:3]
        )

        # Add a source attribute for better tracking
        # candidate.source = 'uploaded_resume'
        
        return candidate
    
    def _prompt_for_discovery(self, result: WorkflowResult, args: argparse.Namespace) -> Optional[Dict]:
        """Prompt user for iterative discovery."""
        if not result.rankings:
            return None
        
        print("\n" + "="*100)
        print(" ITERATIVE CANDIDATE DISCOVERY")
        print("="*100)
        print(f"Job Position: {result.job_data.title}")
        if result.job_data.company:
            print(f"Company: {result.job_data.company}")
        
        print(f"\nCurrent candidate pool: {len(result.rankings)} candidates")
        print(f"Top candidate score: {result.rankings[0].overall_score:.3f}")
        
        # Check if Gemini is configured
        gemini_api_key = os.getenv('GEMINI_API_KEY') or getattr(self.settings, 'gemini_api_key', '')
        
        if not gemini_api_key:
            print("\n Gemini 2.5 Pro API not configured. Discovery feature unavailable.")
            print("   To enable discovery, add GEMINI_API_KEY to your .env file")
            return None
        
        try:
            response = input("\nDo you want to discover more candidates using Gemini 2.5 Pro AI? (y/n): ").strip().lower()
            
            if response in ['y', 'yes']:
                custom_addon = input("Enter an optional sentence to guide the AI discovery (or press Enter to skip): ").strip()
                if custom_addon:
                    args.discovery_prompt_addon = custom_addon
                return self._run_iterative_discovery(result, args)
            else:
                print(" Skipping iterative discovery")
                return None
                
        except (EOFError, KeyboardInterrupt):
            print("\n Skipping iterative discovery")
            return None
    
    def _run_iterative_discovery(self, result: WorkflowResult, args: argparse.Namespace) -> Optional[Dict]:
        """Run the iterative candidate discovery process."""
        try:
            print("\n Starting iterative candidate discovery...")
            print("   This will use Gemini 2.5 Pro to find similar candidates")
            print("   Based on your top candidates as reference templates")
            
            # Check Gemini configuration
            gemini_api_key = os.getenv('GEMINI_API_KEY') or getattr(self.settings, 'gemini_api_key', '')
            
            if not gemini_api_key:
                print("    Gemini API key not configured")
                return None
            
            # Import the ranker with discovery capabilities
            from src.modules.candidate_ranking.ranker import CandidateRanker
            
            ranker = CandidateRanker()
            
            # Temporarily enable discovery and set Gemini API key
            ranker.discovery_enabled = True
            ranker.gemini_api_key = gemini_api_key
            ranker.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.5-pro')
            
            print("    Discovery enabled for this session")
            
            # Get all candidates from the result
            all_candidates = []
            
            # Add PDL candidates
            if hasattr(result, 'candidates') and result.candidates:
                all_candidates.extend(result.candidates)
            
            # Add resume candidates if available
            if hasattr(result, 'resume_candidates') and result.resume_candidates:
                all_candidates.extend(result.resume_candidates)
            
            # If no candidates available, extract from rankings
            if not all_candidates:
                print("    No candidate profiles available for discovery")
                print("   Discovery requires original candidate profiles")
                return None
            
            # Run discovery
            discovery_results = ranker.rank_candidates_with_discovery(
                result.job_data, 
                all_candidates,
                jd_file_path=args.jd_file,
                prompt_addon=args.discovery_prompt_addon
            )
            
            # Display discovery report
            if 'discovery_report' in discovery_results:
                self.formatter.print_discovery_report(discovery_results['discovery_report'])
            
            return discovery_results
            
        except ImportError as e:
            print(f"\ Discovery feature unavailable: {e}")
            print("   Please ensure the ranker module is properly configured")
            return None
        except Exception as e:
            print(f"\ Discovery failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return None
    
    def _handle_config_check(self) -> int:
        """Handle configuration check command."""
        print(" Configuration Check:")
        
        validation_result = validate_config()
        
        # API Keys
        api_keys = validation_result.get('api_keys', {})
        print(f"   OpenAI API Key: {' Set' if api_keys.get('openai') else ' Missing'}")
        print(f"   PDL API Key: {' Set' if api_keys.get('pdl') else ' Missing'}")
        
        # Check Gemini API key
        gemini_api_key = os.getenv('GEMINI_API_KEY') or getattr(self.settings, 'gemini_api_key', '')
        print(f"   Gemini API Key: {' Set' if gemini_api_key else ' Missing (Discovery disabled)'}")
        
        # Check DOCX support
        print(f"   DOCX Support: {' Available' if DOCX_AVAILABLE else ' Missing (pip install python-docx)'}")
        
        # Directories
        directories = validation_result.get('directories', {})
        print(f"   Output Directory: {' Available' if directories.get('output') else ' Error'}")
        
        # Optional features
        settings = validation_result.get('settings', {})
        print(f"   PDF Support: {' Available' if settings.get('pdf_support') else ' Limited'}")
        
        # Discovery feature
        discovery_enabled = getattr(self.settings, 'discovery_enabled', False)
        print(f"   Discovery Feature: {' Enabled' if discovery_enabled and gemini_api_key else ' Disabled'}")
        
        # Workflow validation
        workflow_validation = self.workflow.validate_workflow_configuration()
        print(f"   Workflow Components: {' Valid' if workflow_validation['valid'] else ' Issues'}")
        
        # Show errors and warnings
        if validation_result['errors']:
            print("\n Errors:")
            for error in validation_result['errors']:
                print(f"   • {error}")
        
        if validation_result['warnings']:
            print("\n Warnings:")
            for warning in validation_result['warnings']:
                print(f"   • {warning}")
        
        return 0 if validation_result['valid'] else 1
    
    def _handle_workflow_status(self) -> int:
        """Handle workflow status command."""
        print(" Workflow Status:")
        
        status = workflow_monitor.get_status()
        
        print(f"   Total Executions: {status['total_executions']}")
        print(f"   Success Rate: {status['success_rate']:.1%}")
        print(f"   Average Processing Time: {status['avg_processing_time']:.1f}s")
        
        if status['recent_executions']:
            print(f"\n Recent Performance:")
            for execution in status['recent_executions'][-5:]:
                timestamp = execution['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                print(f"   {timestamp}: {execution['candidates_found']} candidates, {execution['processing_time']:.1f}s")
        
        return 0
    
    def _handle_performance_metrics(self) -> int:
        """Handle performance metrics command."""
        print(" Performance Metrics:")
        
        metrics = workflow_monitor.get_performance_metrics()
        
        print(f"   Average Candidates Found: {metrics['avg_candidates_found']:.1f}")
        print(f"   Average Success Score: {metrics['avg_success_score']:.3f}")
        print(f"   Processing Time Trend: {metrics['processing_time_trend']}")
        
        return 0
    
    def _get_job_description(self, args: argparse.Namespace) -> Optional[str]:
        """Get job description from various sources."""
        if args.jd_file:
            try:
                processor = PDFProcessor()
                return processor.extract_text_from_pdf(args.jd_file)
            except Exception as e:
                print(f" Error reading job description file: {e}")
                return None
        elif args.jd:
            return args.jd
        else:
            return None
    
    def _save_results(self, result: WorkflowResult, args: argparse.Namespace, discovery_data: Optional[Dict] = None) -> None:
        """Save results to requested formats."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if args.csv:
            csv_path = Path(f"results/recruitment_analysis_{timestamp}.csv")
            csv_path.parent.mkdir(exist_ok=True)
            self.formatter.save_to_csv(result, csv_path)
            logger.info(f"Detailed results saved to CSV: {csv_path}")
            print(f"CSV results saved: {csv_path}")
        
        if args.json:
            json_path = Path(f"results/recruitment_analysis_{timestamp}.json")
            json_path.parent.mkdir(exist_ok=True)
            self.formatter.save_to_json(result, json_path, discovery_data)
            logger.info(f"Comprehensive results saved to JSON: {json_path}")
            print(f"JSON results saved: {json_path}")


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="AI-Powered Recruitment System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --jd "Software Engineer position..." --max-candidates 10
  %(prog)s --jd-file job_description.pdf --csv --json
  %(prog)s --jd-file job.pdf --with-discovery --max-candidates 5
  %(prog)s --config-check
  %(prog)s --workflow-status
        """
    )
    
    # Job description input
    jd_group = parser.add_mutually_exclusive_group(required=True)
    jd_group.add_argument("--jd", type=str, help="Job description text")
    jd_group.add_argument("--jd-file", type=str, help="Path to job description file (PDF)")
    
    # Search parameters
    parser.add_argument("--max-candidates", type=int, default=10, 
                       help="Maximum number of candidates to retrieve (default: 10)")
    
    # Discovery options
    parser.add_argument("--with-discovery", action="store_true", 
                       help="Enable iterative candidate discovery using Gemini 2.5 Pro")
    parser.add_argument("--discovery-prompt-addon", type=str,
                       help="A custom sentence to add to the Gemini discovery prompt for more specific instructions.")
    parser.add_argument("--non-interactive", action="store_true", 
                       help="Run in non-interactive mode (no prompts)")
    
    # Output options
    parser.add_argument("--csv", action="store_true", help="Save results to CSV file")
    parser.add_argument("--json", action="store_true", help="Save results to JSON file")
    
    # System commands
    system_group = parser.add_mutually_exclusive_group()
    system_group.add_argument("--config-check", action="store_true", 
                             help="Check system configuration")
    system_group.add_argument("--workflow-status", action="store_true", 
                             help="Show workflow execution status")
    system_group.add_argument("--performance-metrics", action="store_true", 
                             help="Show performance metrics")
    
    # Logging options
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-essential output")
    
    return parser


def main() -> int:
    """Main entry point for the CLI application."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Adjust logging level based on arguments
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        import logging
        logging.getLogger().setLevel(logging.WARNING)
    
    # Create and run CLI application
    app = CLIApplication()
    return app.run(args)


if __name__ == "__main__":
    sys.exit(main())