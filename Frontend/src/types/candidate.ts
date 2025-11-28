// Frontend/src/types/candidate.ts

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
 *
 * Note:
 * - Many fields are optional because candidates can originate from different
 * sources (web 'search' table vs resume table).
 * - `source` indicates which ranked table the row came from.
 */
export interface Candidate {
  // Unique identifier for the ranked row (ranked_candidates.rank_id or ranked_candidates_from_resume.rank_id)
  rank_id: string;

  // If web/profile sourced, profile_id will be present (maps to `search.profile_id`)
  profile_id?: string;

  // If resume-sourced, resume_id will be present
  resume_id?: string;

  // Which source table this row came from
  source?: 'ranked_candidates' | 'ranked_candidates_from_resume';

  // Matching / ranking metadata
  match_score: number | null;
  strengths: string | null;

  // Flags
  favorite: boolean;
  save_for_future: boolean;
  contacted: boolean;

  // Pipeline stage (server defaults to "In Consideration")
  stage: CandidateStage;

  // Optional LinkedIn URL (may be stored on ranked row)
  linkedin_url?: string | null;

  // Candidate display fields (prefer these for UI)
  profile_name?: string | null; // from 'search' table or resume person_name
  role?: string | null;
  company?: string | null;

  // --- ADD THIS FIELD ---
  jd_name?: string | null;

  // New field to check if candidate is recommended by current user
  is_recommended?: boolean;

  // Legacy / fallback fields (kept for compatibility across app)
  name?: string | null;
  full_name?: string | null;
  person_name?: string | null;

  // Additional optional fields used elsewhere in the app
  profile_url?: string | null;

  title?: string | null;
  current_title?: string | null;
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
  save_for_future?: boolean;
  is_recommended?: boolean;
}