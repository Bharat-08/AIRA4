// Frontend/src/api/pipeline.ts
import type { Candidate } from '../types/candidate';
import { toggleFavorite, toggleSave } from './search'; // ✅ Updated import to include toggleSave

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
  return data as Candidate[];
};

/**
 * Fetches ALL ranked candidates (both JD and resume-sourced) for the current user.
 * Supports pagination and filters for favorite, contacted, save_for_future, recommended, AND search.
 *
 * @param page - Page number (1-indexed)
 * @param limit - Number of candidates per page
 * @param filters - Optional filters: { favorite, contacted, save_for_future, recommended, search }
 * @returns { items, page, limit, total, has_more }
 */
export const getAllRankedCandidates = async (
  page: number = 1,
  limit: number = 20,
  filters: { 
    favorite?: boolean; 
    contacted?: boolean; 
    save_for_future?: boolean; 
    recommended?: boolean;
    search?: string; // ✅ Added search parameter
  } = {}
): Promise<{
  items: Candidate[];
  page: number;
  limit: number;
  total: number;
  has_more: boolean;
}> => {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  });

  if (filters.favorite !== undefined) {
    params.append('favorite', String(filters.favorite));
  }
  if (filters.contacted !== undefined) {
    params.append('contacted', String(filters.contacted));
  }
  if (filters.save_for_future !== undefined) {
    params.append('save_for_future', String(filters.save_for_future));
  }
  if (filters.recommended !== undefined) {
    params.append('recommended', String(filters.recommended));
  }
  
  // ✅ NEW: Handle search query
  if (filters.search) {
    params.append('search', filters.search);
  }

  const res = await fetch(`/api/pipeline/all/?${params.toString()}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch all candidates (${res.status})`);
  }

  const data = await res.json();
  // Expect { items, page, limit, total, has_more }
  return {
    items: data.items as Candidate[],
    page: data.page,
    limit: data.limit,
    total: data.total,
    has_more: data.has_more,
  };
};

/**
 * Updates the stage of a candidate in the ranked_candidates table.
 * @param rankId The unique rank_id of the candidate entry
 * @param stage The new stage value (string)
 */
export const updateCandidateStage = async (rankId: string, stage: string): Promise<void> => {
  const res = await fetch(`/api/pipeline/stage/${encodeURIComponent(rankId)}`, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ stage }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update stage (${res.status})`);
  }

  return;
};

/**
 * Toggles the "favorite" status of a candidate.
 * Reuses the existing frontend `toggleFavorite` function which calls
 * the backend `/api/favorites/toggle` endpoint.
 *
 * @param candidateId The candidate identifier (for ranked candidates this should be the rank_id)
 * @param favorite The desired boolean favorite value
 */
export const updateCandidateFavoriteStatus = async (candidateId: string, favorite: boolean): Promise<void> => {
  try {
    // The toggleFavorite function accepts (candidateId, source, favorite)
    // For pipeline entries we use source 'ranked_candidates'.
    await toggleFavorite(candidateId, 'ranked_candidates', favorite);
    return;
  } catch (err: unknown) {
    // Normalize error shape similar to other functions
    if (err instanceof Error) throw err;
    throw new Error('Failed to toggle favorite');
  }
};

/**
 * ✅ NEW: Updates the "save_for_future" status of a candidate.
 * Reuses the existing frontend `toggleSave` function which calls
 * the backend `/api/saved_candidates/toggle` endpoint.
 *
 * @param candidateId The candidate identifier (rank_id)
 * @param save The desired boolean save value
 */
export const updateCandidateSaveStatus = async (candidateId: string, save: boolean): Promise<void> => {
  try {
    // For pipeline entries we use source 'ranked_candidates'.
    await toggleSave(candidateId, 'ranked_candidates', save);
    return;
  } catch (err: unknown) {
    // Normalize error shape similar to other functions
    if (err instanceof Error) throw err;
    throw new Error('Failed to update save status');
  }
};

/**
 * Recommends a candidate to a specific Job Description (Role).
 * This creates a new entry in the backend for the target JD.
 *
 * @param candidateId - The ID of the candidate to recommend
 * @param source - The source of the candidate ('ranked_candidates', etc.)
 * @param targetJdId - The ID of the JD to recommend them to
 */
export const recommendCandidate = async (
  candidateId: string,
  source: string,
  targetJdId: string
): Promise<void> => {
  const res = await fetch(`/api/pipeline/recommend`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      candidate_id: candidateId,
      source: source,
      target_jd_id: targetJdId,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to recommend candidate (${res.status})`);
  }
};

/**
 * Triggers a CSV download for the specific JD pipeline, respecting filters.
 */
export const downloadJdPipeline = async (
  jd_id: string,
  filters: { stage?: string; favorite?: boolean; contacted?: boolean } = {}
): Promise<void> => {
  if (!jd_id) return;

  const params = new URLSearchParams();
  if (filters.stage && filters.stage !== 'all') params.append('stage', filters.stage);
  if (filters.favorite) params.append('favorite', 'true');
  if (filters.contacted) params.append('contacted', 'true');

  const res = await fetch(`/api/pipeline/${encodeURIComponent(jd_id)}/download?${params.toString()}`, {
    credentials: 'include',
  });

  if (!res.ok) throw new Error('Failed to download pipeline');

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `pipeline_jd_${jd_id}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

/**
 * Triggers a CSV download for ALL candidates, respecting filters.
 */
export const downloadAllCandidates = async (
  filters: { favorite?: boolean; contacted?: boolean; save_for_future?: boolean; recommended?: boolean } = {}
): Promise<void> => {
  const params = new URLSearchParams();
  if (filters.favorite) params.append('favorite', 'true');
  if (filters.contacted) params.append('contacted', 'true');
  if (filters.save_for_future) params.append('save_for_future', 'true');
  // ✅ NEW: Handle recommended filter
  if (filters.recommended) params.append('recommended', 'true');

  const res = await fetch(`/api/pipeline/all/download?${params.toString()}`, {
    credentials: 'include',
  });

  if (!res.ok) throw new Error('Failed to download candidates');

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `all_candidates.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};