// frontend/src/types/candidate.ts

// Defines the possible statuses used in some UI bits.
export type CandidateStatus = 'Favourited' | 'Contacted';

// Define the canonical stages used in the Pipeline UI.
// Make sure these strings match what's used on the backend (server_default = "In Consideration").
export type CandidateStage = 'In Consideration' | 'Interviewing' | 'Offer Extended' | 'Rejected';

// An array of stages, used to populate dropdowns on the Pipeline page.
export const candidateStages: CandidateStage[] = [
  'In Consideration',
  'Interviewing',
  'Offer Extended',
  'Rejected',
];

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
 * Primary Candidate interface used across Search and Pipeline pages.
 * Fields returned from the backend API should map to this shape.
 */
export interface Candidate {
  // Unique identifier for the profile (from Supabase "search" table)
  profile_id: string;

  // The unique ID of the ranking entry in the ranked_candidates table.
  rank_id: string;

  // The numerical match score (may be null/undefined if not available)
  match_score: number | null;

  // The detailed text summary from the ranking agent (strengths, weaknesses).
  strengths: string | null;

  // The full name of the candidate (from Supabase search table).
  profile_name: string | null;

  // The candidate's job title.
  role: string | null;

  // The candidate's current company.
  company: string | null;

  // The URL to the candidate's profile (e.g., generated LinkedIn URL).
  profile_url?: string | null;
  linkedin_url?: string | null;

  // Whether the candidate has been favorited (synchronized with backend).
  favorite: boolean;

  // Whether the candidate has been contacted.
  contacted: boolean;

  // The candidate's current stage in the pipeline (synchronized with backend).
  stage: CandidateStage;
}
