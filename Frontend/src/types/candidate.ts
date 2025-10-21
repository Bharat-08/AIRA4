// frontend/src/types/candidate.ts

// Defines the possible states for a candidate in the pipeline, used on the Pipeline page.
export type CandidateStatus = 'Favourited' | 'Contacted';
export type CandidateStage = 'Rejected' | 'Offer Extended' | 'Interviewing' | 'In Consideration';

// An array of stages, used to populate dropdowns on the Pipeline page.
export const candidateStages: CandidateStage[] = ['In Consideration', 'Interviewing', 'Offer Extended', 'Rejected'];

/**
 * This interface is specifically for the Pipeline page, which has a different
 * data structure and UI requirements than the search results.
 */
export interface PipelineCandidate {
  id: string;
  name: string;
  role: string;
  company: string;
  status: CandidateStatus;
  stage: CandidateStage;
}

/**
 * --- FINAL VERSION ---
 * This is the primary interface for the Search page.
 * It is now aligned with the full data structure returned by the
 * `get_ranked_candidates_with_details` RPC function and the `search.py` API endpoint.
 */
export interface Candidate {
  // Unique identifier from the database, used for keys and future actions.
  profile_id: string;
  
  // The numerical score from the ranking agent, used for the progress pill.
  match_score: number;

  // The detailed text summary from the ranking agent (strengths, weaknesses).
  strengths: string;

  // The full name of the candidate.
  profile_name: string | null;

  // The candidate's job title.
  role: string | null;

  // The candidate's current company.
  company: string | null;

  // The URL to the candidate's profile (e.g., LinkedIn).
  profile_url: string | null;
  linkedin_url: string | null; 

  // NEW: whether the candidate is favorited (synchronized with backend)
  favorite: boolean;
}
