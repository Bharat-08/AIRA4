import type { Candidate } from '../types/candidate';

// --- TYPES for the asynchronous API responses ---
interface TaskStartResponse {
  task_id: string;
  status: 'processing';
}

interface TaskStatusResponse {
  status: 'processing' | 'completed' | 'failed';
  data?: Candidate[];
  error?: string;
}

/** Result shape for the Google+LinkedIn sourcing task */
export interface GoogleLinkedinTaskResult {
  status: 'processing' | 'completed' | 'failed';
  attempted?: number;
  inserted_count?: number;
  queries?: string[];
  sample?: Array<{
    name?: string | null;
    profile_link?: string | null;
    position?: string | null;
    company?: string | null;
  }>;
  error?: string;
}

// --- MAIN SEARCH & RANK PIPELINE ---

/**
 * Starts the main search and rank pipeline on the backend.
 * @param jdId The ID of the job description.
 * @param prompt The user's search prompt.
 * @returns An object containing the task_id for the background job.
 */
export const startSearchAndRankTask = async (jdId: string, prompt: string): Promise<TaskStartResponse> => {
  const response = await fetch(`/api/search/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ jd_id: jdId, prompt: prompt }),
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to start search and rank task' }));
    throw new Error(errorData.detail || 'Failed to start search and rank task');
  }

  return response.json();
};

/**
 * Starts the Apollo-backed search (Fast or Web+Apollo) on the backend.
 * Calls the endpoint: POST /api/search/apollo-search/{jd_id}
 *
 * @param jdId The ID of the job description.
 * @param prompt Optional prompt string (may be empty).
 * @param searchOption Numeric option:
 * 1 -> Fast search (Apollo-only)
 * 2 -> Web search + Apollo
 *
 * @returns TaskStartResponse with task_id
 */
export const startApolloSearchTask = async (jdId: string, prompt: string, searchOption: number): Promise<TaskStartResponse> => {
  // Validate option early to provide a clear client-side error
  if (![1, 2].includes(searchOption)) {
    throw new Error('searchOption must be 1 (Fast) or 2 (Web + Apollo)');
  }

  const response = await fetch(`/api/search/apollo-search/${encodeURIComponent(jdId)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({
      search_option: searchOption,
      prompt: prompt || ''
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to start Apollo search task' }));
    throw new Error(errorData.detail || 'Failed to start Apollo search task');
  }

  return response.json();
};

/**
 * Polls the backend for the result of the search and rank task.
 * @param taskId The ID of the background task.
 * @returns The current status of the task and the final data if completed.
 */
export const getSearchResults = async (taskId: string): Promise<TaskStatusResponse> => {
  const response = await fetch(`/api/search/search/results/${taskId}`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to get task results' }));
    throw new Error(errorData.detail || 'Failed to get task results');
  }

  return response.json();
};


// --- RESUME RANKING PIPELINE ---

/**
 * Starts the resume ranking process on the backend.
 * @param jdId The ID of the job description.
 * @param prompt A prompt (can be empty if not needed by this endpoint).
 * @returns An object containing the task_id for the background job.
 */
export const startRankResumesTask = async (jdId: string, prompt: string): Promise<TaskStartResponse> => {
  const response = await fetch(`/api/search/rank-resumes`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ jd_id: jdId, prompt: prompt }),
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to start resume ranking task' }));
    throw new Error(errorData.detail || 'Failed to start resume ranking task');
  }

  return response.json();
};

/**
 * Polls the backend for the result of the resume ranking task.
 * @param taskId The ID of the background task.
 * @returns The current status of the task and the final data if completed.
 */
export const getRankResumesResults = async (taskId: string): Promise<TaskStatusResponse> => {
  const response = await fetch(`/api/search/rank-resumes/results/${taskId}`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to get resume ranking results' }));
    throw new Error(errorData.detail || 'Failed to get resume ranking results');
  }

  return response.json();
};


// --- NEW: Combined Search (web + optional single resume) ---

/**
 * Triggers the combined search endpoint which will:
 * - start the apollo/web search task
 * - optionally upload a single resume and start processing it
 * Returns the task ids (apollo_task_id, resume_task_id) for backend tasks.
 *
 * @param jdId string
 * @param prompt string | null
 * @param searchOption number (1 or 2)
 * @param file File | null  -> single resume file (if provided)
 */
export const triggerCombinedSearch = async (
  jdId: string,
  prompt: string | null,
  searchOption: number,
  file: File | null
): Promise<{ apollo_task_id: string; resume_task_id?: string | null } & { status: string }> => {
  // build multipart/form-data
  const form = new FormData();
  form.append('jd_id', jdId);
  form.append('search_option', String(searchOption || 2));
  if (prompt) form.append('prompt', prompt);
  if (file) {
    // backend expects 'file' as the field name
    form.append('file', file, file.name);
  }

  const response = await fetch(`/api/search/combined-search`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to trigger combined search' }));
    throw new Error(errorData.detail || 'Failed to trigger combined search');
  }

  return response.json();
};

/**
 * Poll the combined-results endpoint using a timestamp.
 * The 'since' param should be an ISO string (UTC) representing when the search started.
 *
 * @param jdId string
 * @param since ISO datetime string (e.g. new Date().toISOString())
 * @returns An array of Candidate objects (may be empty)
 */
export const getCombinedSearchResults = async (jdId: string, since: string): Promise<Candidate[]> => {
  // encode the timestamp safely
  const url = new URL(`/api/search/combined-results`, window.location.origin);
  url.searchParams.set('jd_id', jdId);
  url.searchParams.set('since', since);

  const response = await fetch(url.toString(), {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    // try to parse the response for better error messages
    const err = await response.json().catch(() => ({ detail: 'Failed to fetch combined results' }));
    throw new Error(err.detail || 'Failed to fetch combined results');
  }

  // The backend returns a JSON array (list) of candidate-like objects
  const data = await response.json();
  // Assume the array items already include 'favorite' (enrich_with_favorites done server-side)
  return data as Candidate[];
};


// --- NEW: Google + LinkedIn Sourcing ---

/**
 * Starts the Google+LinkedIn sourcing task on the backend.
 * Endpoint: POST /api/search/google-linkedin/{jd_id}
 * Body: form-data with "prompt" (optional)
 */
export const startGoogleLinkedinTask = async (jdId: string, prompt: string): Promise<TaskStartResponse> => {
  const form = new FormData();
  // backend endpoint defines `prompt` as a Form parameter (optional)
  form.append('prompt', prompt || '');

  const response = await fetch(`/api/search/google-linkedin/${encodeURIComponent(jdId)}`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to start Google+LinkedIn task' }));
    throw new Error(errorData.detail || 'Failed to start Google+LinkedIn task');
  }

  return response.json();
};

/**
 * Polls the backend for the result of the Google+LinkedIn sourcing task.
 * Endpoint: GET /api/search/google-linkedin/results/{task_id}
 */
export const getGoogleLinkedinResults = async (taskId: string): Promise<GoogleLinkedinTaskResult> => {
  const response = await fetch(`/api/search/google-linkedin/results/${encodeURIComponent(taskId)}`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to get Google+LinkedIn task result' }));
    throw new Error(errorData.detail || 'Failed to get Google+LinkedIn task result');
  }

  return response.json();
};


// --- UTILITY FUNCTIONS (Cancellation and LinkedIn URL) ---

/**
 * Sends a request to the backend to stop a running Celery task.
 * @param taskId The ID of the task to cancel.
 */
export const stopTask = async (taskId: string): Promise<{ message: string }> => {
  const response = await fetch(`/api/search/cancel/${taskId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to stop the task' }));
    throw new Error(errorData.detail || 'Failed to stop the task');
  }

  return response.json();
};

/**
 * Calls the backend to generate a LinkedIn URL for a given candidate.
 * (This function's logic remains unchanged).
 * @param profileId The ID of the candidate's profile.
 * @returns An object containing the newly generated profile_url.
 */
export const generateLinkedInUrl = async (profileId: string): Promise<{ linkedin_url: string }> => {
  const response = await fetch(`/api/search/generate-linkedin-url`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ profile_id: profileId }),
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to generate LinkedIn URL' }));
    throw new Error(errorData.detail || 'Failed to generate LinkedIn URL');
  }

  return response.json();
};

/**
 * Toggle favorite status for a candidate.
 * @param candidateId The profile_id or resume_id of the candidate.
 * @param source Either "ranked_candidates" or "ranked_candidates_from_resume".
 * @param favorite The desired boolean favorite value.
 */
export const toggleFavorite = async (
  candidateId: string,
  source: 'ranked_candidates' | 'ranked_candidates_from_resume',
  favorite: boolean
): Promise<{ candidate_id: string; favorite: boolean }> => {
  const response = await fetch(`/api/favorites/toggle`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({
      candidate_id: candidateId,
      source,
      favorite,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to toggle favorite' }));
    throw new Error(errorData.detail || 'Failed to toggle favorite');
  }

  return response.json();
};
