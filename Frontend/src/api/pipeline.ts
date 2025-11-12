// Frontend/src/api/pipeline.ts
import type { Candidate } from '../types/candidate';
import { toggleFavorite } from './search'; // reuse the existing favorite-toggle logic

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
 * Supports pagination and filters for favorite, contacted, and save_for_future.
 *
 * @param page - Page number (1-indexed)
 * @param limit - Number of candidates per page
 * @param filters - Optional filters: { favorite?: boolean, contacted?: boolean, save_for_future?: boolean }
 * @returns { items, page, limit, total, has_more }
 */
export const getAllRankedCandidates = async (
  page: number = 1,
  limit: number = 20,
  filters: { favorite?: boolean; contacted?: boolean; save_for_future?: boolean } = {}
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
