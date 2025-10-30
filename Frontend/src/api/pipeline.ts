// src/api/pipeline.ts
// We import the 'Candidate' type which should match the backend schema
import type { Candidate } from '../types/candidate';

/**
 * Fetches the ranked candidate pipeline for a specific JD.
 * This data is combined from SQL (ranks) and Supabase (profile info).
 */
export const getRankedCandidatesForJd = async (jd_id: string): Promise<Candidate[]> => {
  // Return empty array if no JD is selected
  if (!jd_id) {
    return [];
  }

  const res = await fetch(`/api/pipeline/${encodeURIComponent(jd_id)}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch pipeline candidates (${res.status})`);
  }

  const data = await res.json();
  // The response from the backend (PipelineCandidateResponse)
  // should match the frontend 'Candidate' type.
  return data as Candidate[];
};