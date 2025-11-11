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
  // --- Common Ranked Fields ---
  rank_id: string;
  match_score: number | null;
  strengths: string | null;
  favorite: boolean;
  contacted: boolean;
  stage: CandidateStage;
  linkedin_url?: string | null;

  // --- Common Info Fields (in both 'search' and 'resume') ---
  role: string | null;
  company: string | null;
  profile_url?: string | null;

  // --- Web Search Fields (from 'search' table) ---
  profile_id?: string; // <-- Must be optional
  profile_name?: string | null; // <-- For web candidates

  // --- Resume Fields (from 'resume' table) ---
  resume_id?: string; // <-- Must be optional
  person_name?: string | null; // <-- For resume candidates

  // --- Fallback fields (if needed, good for safety) ---
  name?: string | null;
  full_name?: string | null;
  current_title?: string | null;
  title?: string | null;
  current_company?: string | null;
  organization_name?: string | null;
  organization?: string | null;
}

/**
 * ✅ New interface for LinkedIn-sourced candidates (no match_score)
 * Matches the `public.linkedin` table exactly.
 */
export interface LinkedInCandidate {
  linkedin_profile_id: string;
  jd_id: string;
  user_id: string;
  name?: string | null;
  profile_link?: string | null;
  position?: string | null;
  company?: string | null;
  summary?: string | null;
  created_at: string;
}
