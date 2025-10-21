"""
This module orchestrates the complete recruitment workflow
for state management and workflow coordination.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Any, TypedDict
from dataclasses import dataclass

from src.core.models import (
    JobDescription, CandidateProfile, CandidateRanking, 
    SearchMetadata, WorkflowResult
)
from src.modules.jd_parser.parser import JobDescriptionParser
from src.modules.candidate_retrieval.client import PDLAPIClient, CandidateConverter
from src.modules.candidate_ranking.ranker import CandidateRanker
from src.config.settings import get_settings, get_logger

logger = get_logger()


class WorkflowState(TypedDict):
    """State management for the recruitment workflow."""
    # Input
    job_description_text: str
    max_candidates: int
    
    # Intermediate states
    parsed_job: Optional[JobDescription]
    raw_candidates: List[Dict[str, Any]]
    candidate_profiles: List[CandidateProfile]
    candidate_rankings: List[CandidateRanking]
    
    # Metadata
    start_time: float
    current_step: str
    errors: List[str]
    warnings: List[str]
    
    # Final result
    workflow_result: Optional[WorkflowResult]


@dataclass
class WorkflowStep:
    """Represents a single step in the workflow."""
    name: str
    description: str
    required_inputs: List[str]
    outputs: List[str]
    
    def __post_init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.success: bool = False
        self.error_message: Optional[str] = None


class RecruitmentWorkflow:
    """LangGraph-inspired recruitment workflow orchestrator."""
    
    def __init__(self):
        """Initialize the workflow orchestrator."""
        self.settings = get_settings()
        
        # Initialize components
        self.job_parser = JobDescriptionParser()
        self.pdl_client = PDLAPIClient()
        self.candidate_converter = CandidateConverter()
        self.candidate_ranker = CandidateRanker()
        
        # Define workflow steps
        self.workflow_steps = [
            WorkflowStep(
                name="parse_job_description",
                description="Parse and structure job description",
                required_inputs=["job_description_text"],
                outputs=["parsed_job"]
            ),
            WorkflowStep(
                name="search_candidates",
                description="Search for candidates using PDL API",
                required_inputs=["parsed_job", "max_candidates"],
                outputs=["raw_candidates"]
            ),
            WorkflowStep(
                name="convert_candidates",
                description="Convert raw candidate data to profiles",
                required_inputs=["raw_candidates"],
                outputs=["candidate_profiles"]
            ),
            WorkflowStep(
                name="rank_candidates",
                description="Rank candidates using AI analysis",
                required_inputs=["parsed_job", "candidate_profiles"],
                outputs=["candidate_rankings"]
            ),
            WorkflowStep(
                name="finalize_results",
                description="Create final workflow result",
                required_inputs=["parsed_job", "candidate_profiles", "candidate_rankings"],
                outputs=["workflow_result"]
            )
        ]
    
    def run_workflow(self, job_description_text: str, max_candidates: int, with_discovery: bool = False) -> WorkflowResult:
        """Run the complete recruitment workflow."""
        logger.info("Starting LangGraph-orchestrated recruitment workflow...")
        
        # Initialize state
        state = WorkflowState(
            job_description_text=job_description_text,
            max_candidates=max_candidates,
            parsed_job=None,
            raw_candidates=[],
            candidate_profiles=[],
            candidate_rankings=[],
            start_time=time.time(),
            current_step="initialization",
            errors=[],
            warnings=[],
            workflow_result=None
        )
        
        try:
            # Execute workflow steps
            for step in self.workflow_steps:
                state = self._execute_step(step, state)
                
                # Check for critical errors
                if step.name in ["parse_job_description", "search_candidates"] and not step.success:
                    raise Exception(f"Critical step failed: {step.name} - {step.error_message}")
            
            # Return final result
            if state["workflow_result"]:
                logger.info("Workflow completed successfully")
                return state["workflow_result"]
            else:
                raise Exception("Workflow completed but no result generated")
                
        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            # Create error result
            return self._create_error_result(state, str(e))
    
    def _execute_step(self, step: WorkflowStep, state: WorkflowState) -> WorkflowState:
        """Execute a single workflow step."""
        logger.info(f"Executing step: {step.name}")
        
        step.start_time = time.time()
        state["current_step"] = step.name
        
        try:
            # Validate required inputs
            self._validate_step_inputs(step, state)
            
            # Execute step based on name
            if step.name == "parse_job_description":
                state = self._parse_job_description(state)
            elif step.name == "search_candidates":
                state = self._search_candidates(state)
            elif step.name == "convert_candidates":
                state = self._convert_candidates(state)
            elif step.name == "rank_candidates":
                state = self._rank_candidates(state)
            elif step.name == "finalize_results":
                state = self._finalize_results(state)
            else:
                raise ValueError(f"Unknown step: {step.name}")
            
            step.success = True
            logger.info(f"Step {step.name} completed successfully")
            
        except Exception as e:
            step.success = False
            step.error_message = str(e)
            state["errors"].append(f"{step.name}: {str(e)}")
            logger.error(f"Step {step.name} failed: {e}")
        
        finally:
            step.end_time = time.time()
            step_duration = step.end_time - step.start_time
            logger.debug(f"Step {step.name} took {step_duration:.2f} seconds")
        
        return state
    
    def _validate_step_inputs(self, step: WorkflowStep, state: WorkflowState) -> None:
        """Validate that required inputs are available for a step."""
        for required_input in step.required_inputs:
            if required_input not in state or state[required_input] is None:
                raise ValueError(f"Required input '{required_input}' not available for step '{step.name}'")
    
    def _parse_job_description(self, state: WorkflowState) -> WorkflowState:
        """Parse job description step."""
        try:
            parsed_job = self.job_parser.parse_job_description(state["job_description_text"])
            state["parsed_job"] = parsed_job
            logger.info(f"Successfully parsed job: {parsed_job.title}")
        except Exception as e:
            logger.error(f"Job description parsing failed: {e}")
            raise
        
        return state
    
   

    def _search_candidates(self, state: WorkflowState) -> WorkflowState:
        """
        Search candidates step with an intelligent and strict safety net.
        This function will only call the PDL API if the 'with_discovery' flag
        in the state is False, AND the max_candidates is exactly 1.
        """
        try:
            # Determine the current mode of operation
            is_discovery_mode = state.get("with_discovery", False)

            # --- THIS IS THE CRUCIAL SAFETY NET YOU REQUESTED ---
            # It checks two conditions before allowing a PDL search:
            # 1. We must NOT be in discovery mode.
            # 2. The number of requested candidates must be exactly 1.
            if not is_discovery_mode:
                if state["max_candidates"] > 1:
                    # If we are in the initial search stage but somehow more than 1 candidate is requested,
                    # we abort immediately to prevent costs.
                    error_message = f"SAFETY_NET: Aborted PDL search. A request was made for {state['max_candidates']} candidates, but the strict limit is 1."
                    logger.error(error_message)
                    state["raw_candidates"] = []
                    if "warnings" not in state:
                        state["warnings"] = []
                    state["warnings"].append(error_message)
                    return state
                
                # If the conditions are met, proceed with the safe PDL call.
                job_description_text = state["job_description_text"]
                
                if hasattr(job_description_text, 'strip'):
                    search_text = job_description_text
                else:
                    search_text = str(job_description_text)
                
                logger.info(f"🔍 Calling PDL API for 1 candidate with job description: {search_text[:100]}...")
                
                raw_candidates = self.pdl_client.search_candidates(
                    search_text, 
                    state["max_candidates"] # This will always be 1 at this point
                )
                state["raw_candidates"] = raw_candidates
                logger.info(f"Found {len(raw_candidates)} raw candidates from PDL.")
            
            else:
                # If we ARE in discovery mode, we do not call PDL at all.
                logger.info("Discovery mode is active. Skipping new PDL search.")
                state["raw_candidates"] = []

        except Exception as e:
            logger.error(f"Candidate search failed: {e}")
            state["raw_candidates"] = []
            if "warnings" not in state:
                state["warnings"] = []
            state["warnings"].append(f"Candidate search failed: {str(e)}")
        
        return state
    
    def _convert_candidates(self, state: WorkflowState) -> WorkflowState:
        """Convert candidates step."""
        try:
            candidate_profiles = []
            conversion_errors = 0
            
            for raw_candidate in state["raw_candidates"]:
                try:
                    profile = self.candidate_converter.convert_to_candidate_profile(raw_candidate)
                    if profile:
                        candidate_profiles.append(profile)
                    else:
                        conversion_errors += 1
                except Exception as e:
                    conversion_errors += 1
                    logger.warning(f"Failed to convert candidate: {e}")
            
            state["candidate_profiles"] = candidate_profiles
            
            if conversion_errors > 0:
                warning_msg = f"Failed to convert {conversion_errors} candidates"
                if "warnings" not in state:
                    state["warnings"] = []
                state["warnings"].append(warning_msg)
                logger.warning(warning_msg)
            
            logger.info(f"Successfully converted {len(candidate_profiles)} candidates")
            
        except Exception as e:
            logger.error(f"Candidate conversion failed: {e}")
            raise
        
        return state
    
    def _rank_candidates(self, state: WorkflowState) -> WorkflowState:
        """Rank candidates step."""
        try:
            if not state["candidate_profiles"]:
                logger.warning("No candidates to rank")
                state["candidate_rankings"] = []
                return state
            
            candidate_rankings = self.candidate_ranker.rank_candidates(
                state["parsed_job"],
                state["candidate_profiles"]
            )
            state["candidate_rankings"] = candidate_rankings
            logger.info(f"Successfully ranked {len(candidate_rankings)} candidates")
            
        except Exception as e:
            logger.error(f"Candidate ranking failed: {e}")
            # Don't raise - we can continue with unranked candidates
            if "warnings" not in state:
                state["warnings"] = []
            state["warnings"].append(f"Ranking failed: {str(e)}")
            state["candidate_rankings"] = []
        
        return state
    
    def _finalize_results(self, state: WorkflowState) -> WorkflowState:
        """Finalize results step."""
        try:
            total_time = time.time() - state["start_time"]
            
            # Create metadata
            metadata = SearchMetadata(
                processing_time_seconds=round(total_time, 2),
                candidates_found=len(state["candidate_profiles"]),
                candidates_ranked=len(state["candidate_rankings"]),
                timestamp=datetime.now(),
                workflow_version=self.settings.workflow_version,
                search_queries_used=[],  # Could be populated from PDL client
                api_calls_made=0  # Could be tracked
            )
            
            # Create final result
            workflow_result = WorkflowResult(
                job_data=state["parsed_job"],
                candidates=state["candidate_profiles"],
                rankings=state["candidate_rankings"],
                metadata=metadata
            )
            
            state["workflow_result"] = workflow_result
            logger.info(f"Workflow finalized in {total_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Result finalization failed: {e}")
            raise
        
        return state
    
    def _create_error_result(self, state: WorkflowState, error_message: str) -> WorkflowResult:
        """Create an error result when workflow fails."""
        total_time = time.time() - state["start_time"]
        
        # Create minimal metadata
        metadata = SearchMetadata(
            processing_time_seconds=round(total_time, 2),
            candidates_found=0,
            candidates_ranked=0,
            timestamp=datetime.now(),
            workflow_version=self.settings.workflow_version
        )
        
        # Create minimal job data if parsing failed
        if not state["parsed_job"]:
            from src.core.models import JobDescription
            job_data = JobDescription(title="Failed to parse job description")
        else:
            job_data = state["parsed_job"]
        
        return WorkflowResult(
            job_data=job_data,
            candidates=[],
            rankings=[],
            metadata=metadata
        )
    
    def get_workflow_status(self) -> Dict[str, Any]:
        """Get current workflow status and step information."""
        status = {
            'total_steps': len(self.workflow_steps),
            'steps': []
        }
        
        for step in self.workflow_steps:
            step_info = {
                'name': step.name,
                'description': step.description,
                'required_inputs': step.required_inputs,
                'outputs': step.outputs,
                'executed': step.start_time is not None,
                'success': step.success,
                'duration': None,
                'error_message': step.error_message
            }
            
            if step.start_time and step.end_time:
                step_info['duration'] = round(step.end_time - step.start_time, 2)
            
            status['steps'].append(step_info)
        
        return status
    
    def validate_workflow_configuration(self) -> Dict[str, Any]:
        """Validate that all workflow components are properly configured."""
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'components': {}
        }
        
        # Test job parser
        try:
            test_jd = "Test Software Engineer position"
            self.job_parser.parse_job_description(test_jd)
            validation_result['components']['job_parser'] = True
        except Exception as e:
            validation_result['components']['job_parser'] = False
            validation_result['errors'].append(f"Job parser error: {e}")
        
        # Test PDL client
        try:
            connection_test = self.pdl_client.test_connection()
            validation_result['components']['pdl_client'] = connection_test.success
            if not connection_test.success:
                validation_result['errors'].append(f"PDL client error: {connection_test.error_message}")
        except Exception as e:
            validation_result['components']['pdl_client'] = False
            validation_result['errors'].append(f"PDL client error: {e}")
        
        # Test candidate ranker (basic validation)
        try:
            # This is a basic check - we can't easily test without actual data
            validation_result['components']['candidate_ranker'] = True
        except Exception as e:
            validation_result['components']['candidate_ranker'] = False
            validation_result['errors'].append(f"Candidate ranker error: {e}")
        
        validation_result['valid'] = len(validation_result['errors']) == 0
        
        return validation_result
    
    def run_workflow_async(self, job_description_text: str, max_candidates: int = 10):
        """Placeholder for async workflow execution (would require asyncio implementation)."""
        # This would be implemented with proper async/await patterns
        # For now, we'll just call the sync version
        logger.info("Async workflow not implemented, falling back to sync execution")
        return self.run_workflow(job_description_text, max_candidates)


class WorkflowMonitor:
    """Monitor and track workflow execution metrics."""
    
    def __init__(self):
        self.execution_history: List[Dict[str, Any]] = []
    
    def record_execution(self, workflow_result: WorkflowResult, execution_time: float):
        """Record a workflow execution for monitoring."""
        execution_record = {
            'timestamp': datetime.now().isoformat(),
            'job_title': workflow_result.job_data.title,
            'candidates_found': workflow_result.metadata.candidates_found,
            'candidates_ranked': workflow_result.metadata.candidates_ranked,
            'execution_time': execution_time,
            'success': len(workflow_result.candidates) > 0
        }
        
        self.execution_history.append(execution_record)
        
        # Keep only last 100 executions
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics from execution history."""
        if not self.execution_history:
            return {'message': 'No execution history available'}
        
        successful_executions = [e for e in self.execution_history if e['success']]
        
        metrics = {
            'total_executions': len(self.execution_history),
            'successful_executions': len(successful_executions),
            'success_rate': len(successful_executions) / len(self.execution_history),
            'average_execution_time': sum(e['execution_time'] for e in self.execution_history) / len(self.execution_history),
            'average_candidates_found': sum(e['candidates_found'] for e in self.execution_history) / len(self.execution_history),
            'recent_performance': self.execution_history[-10:] if len(self.execution_history) >= 10 else self.execution_history
        }
        
        return metrics


# Global workflow monitor instance
workflow_monitor = WorkflowMonitor()

# Export main classes
__all__ = ['RecruitmentWorkflow', 'WorkflowState', 'WorkflowStep', 'WorkflowMonitor', 'workflow_monitor']