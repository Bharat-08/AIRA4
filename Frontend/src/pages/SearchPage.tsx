// Frontend/src/pages/SearchPage.tsx
import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Header } from '../components/layout/Header';
import { CandidateRow } from '../components/ui/CandidateRow';
import {
  Plus,
  UploadCloud,
  Search as SearchIcon,
  SendHorizonal,
  Eye,
  History,
  RefreshCw,
  XCircle,
  Download,
} from 'lucide-react';
// ✅ Updated: Import useLocation
import { useLocation } from 'react-router-dom';
import type { User } from '../types/user';
import { uploadJdFile, uploadResumeFiles, uploadBulkJds } from '../api/upload';
import { fetchJdsForUser, type JdSummary } from '../api/roles';
import CandidatePopupCard from '../components/ui/CandidatePopupCard';
import JdPopupCard from '../components/ui/JdPopupCard';

import {
  startSearchAndRankTask,
  startRankResumesTask,
  getSearchResults,
  getRankResumesResults,
  stopTask,
  toggleFavorite,
  toggleSave,
  startApolloSearchTask,
  triggerCombinedSearch,
  getCombinedSearchResults,
  startGoogleLinkedinTask,
  getGoogleLinkedinResults,
  fetchLinkedInCandidates,
  downloadSearchResults,
} from '../api/search';

import { getRankedCandidatesForJd } from '../api/pipeline';

import type { Candidate, LinkedInCandidate } from '../types/candidate';
import { LinkedInCandidateRow } from '../components/ui/LinkedInCandidateRow';

// stable key for react lists
const stableKey = (c: Candidate) => {
  if ((c as any).rank_id) return `rank-${(c as any).rank_id}`;
  if ((c as any).resume_id) return `resume-${(c as any).resume_id}-${(c as any).rank || Math.random()}`;
  if (c.profile_id) return `web-${c.profile_id}`;
  return `fallback-${Math.random().toString(36).substring(2, 9)}`;
};

const Loader = () => (
  <svg
    className="animate-spin h-5 w-5 text-teal-600"
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a 8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 0 1 4 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    ></path>
  </svg>
);

interface JobDescriptionDetails {
  jd_id: string;
  jd_parsed_summary: string;
  location: string;
  job_type: string;
  experience_required: string;
}

type PersistedCandidates = {
  jd_id: string | null;
  candidates: Candidate[];
};

export function SearchPage({ user }: { user: User }) {
  const userName = user.name || 'User';
  // ✅ NEW: Use Location
  const location = useLocation();

  const [userJds, setUserJds] = useState<JdSummary[]>([]);
  const [currentJd, setCurrentJd] = useState<JobDescriptionDetails | null>(null);
  const [selectedJd, setSelectedJd] = useState<JdSummary | null>(null);
  const [resumeFiles, setResumeFiles] = useState<FileList | null>(null);
  const [isJdLoading, setIsJdLoading] = useState(false);
  const [isRankingLoading, setIsRankingLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [chatMessage, setChatMessage] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);

  // LinkedIn candidates state
  const [linkedInCandidates, setLinkedInCandidates] = useState<LinkedInCandidate[]>([]);

  // 'db' | 'web' | 'gl' (LinkedIn)
  const [sourcingOption, setSourcingOption] = useState<'web' | 'db' | 'gl'>('web');

  // web sub-option
  const [webSearchOption, setWebSearchOption] = useState<number>(2);

  const [taskId, setTaskId] = useState<string | null>(null);
  const pollingIntervalRef = useRef<number | null>(null);

  // Combined polling
  const [isCombinedSearch, setIsCombinedSearch] = useState(false);
  const combinedApolloTaskIdRef = useRef<string | null>(null);
  const combinedSinceRef = useRef<string | null>(null);
  const combinedPollingIntervalRef = useRef<number | null>(null);

  // LinkedIn since timestamp
  const linkedInSinceRef = useRef<string | null>(null);

  const jdInputRef = useRef<HTMLInputElement>(null);
  const resumeInputRef = useRef<HTMLInputElement>(null);

  const isRestoringRef = useRef<boolean>(true);

  // Limit for uploads
  const MAX_FILES_LIMIT = 3;
  
  // NEW: Download loading state
  const [isDownloading, setIsDownloading] = useState(false);

  const STORAGE_KEY = useMemo(() => {
    const maybeId = (user as unknown as { id?: string })?.id;
    return `search_candidates_v1::${maybeId ?? user.name ?? 'anon'}`;
  }, [user]);

  const TASK_POLLING_TIMEOUT_MS = 15 * 60 * 1000;
  const TASK_POLL_INTERVAL_MS = 5000;
  const COMBINED_OVERALL_TIMEOUT_MS = 15 * 60 * 1000;
  const taskStartedAtRef = useRef<number | null>(null);

  // Warning on Refresh (Page Unload)
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isRankingLoading || (candidates.length > 0 && !isRestoringRef.current)) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isRankingLoading, candidates.length]);

  // Persist candidates to session
  useEffect(() => {
    if (isRestoringRef.current) return;
    try {
      const payload: PersistedCandidates = {
        jd_id: currentJd?.jd_id ?? null,
        candidates,
      };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      /* ignore */
    }
  }, [candidates, currentJd, STORAGE_KEY]);

  // Load JDs and restore persistence (Updated for query param support)
  useEffect(() => {
    let parsedStorage: PersistedCandidates | null = null;
    isRestoringRef.current = true;

    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        parsedStorage = JSON.parse(raw) as PersistedCandidates | null;
        if (parsedStorage?.candidates?.length) {
          setCandidates(parsedStorage.candidates);
        }
      }
    } catch {
      /* ignore */
    }

    (async () => {
      try {
        const jds = await fetchJdsForUser();
        setUserJds(jds);

        // ✅ 1. Check Query Param First (from Pipeline Page)
        const params = new URLSearchParams(location.search);
        const queryJdId = params.get('jd_id');
        
        if (queryJdId) {
            const match = jds.find(j => j.jd_id === queryJdId);
            if (match) {
                // If query param exists, use it and clear potential storage mismatch
                setCurrentJd({
                  jd_id: match.jd_id,
                  jd_parsed_summary: match.jd_parsed_summary || '',
                  location: match.location || 'N/A',
                  job_type: match.job_type || 'N/A',
                  experience_required: match.experience_required || 'N/A',
                });
                
                // Clear candidates to reset for new search unless specific logic is added
                setCandidates([]);
                setLinkedInCandidates([]);
                isRestoringRef.current = false;
                return;
            }
        }

        // 2. Then check storage
        if (parsedStorage?.jd_id) {
          const match = jds.find((j) => j.jd_id === parsedStorage!.jd_id);
          if (match) {
            setCurrentJd({
              jd_id: match.jd_id,
              jd_parsed_summary: match.jd_parsed_summary || '',
              location: match.location || 'N/A',
              job_type: match.job_type || 'N/A',
              experience_required: match.experience_required || 'N/A',
            });
            isRestoringRef.current = false;
            return;
          }
        }

        // 3. Fallback to first JD
        if (jds.length > 0 && !currentJd) {
          const first = jds[0];
          setCurrentJd({
              jd_id: first.jd_id,
              jd_parsed_summary: first.jd_parsed_summary || '',
              location: first.location || 'N/A',
              job_type: first.job_type || 'N/A',
              experience_required: first.experience_required || 'N/A',
          });
          setCandidates([]);
        }
      } catch {
        setUploadStatus({ message: 'Could not load your saved roles.', type: 'error' });
      } finally {
        isRestoringRef.current = false;
      }
    })();
  }, [STORAGE_KEY, location.search]); // ✅ Added location.search dependency

  // Sync Hook - Refetch candidate status when window focuses or JD changes
  useEffect(() => {
    const syncCandidates = async () => {
      if (!currentJd?.jd_id) return;
      
      try {
        const freshData = await getRankedCandidatesForJd(currentJd.jd_id);
        
        if (!freshData || freshData.length === 0) return;

        setCandidates(prev => {
          let hasChanges = false;
          const next = prev.map(c => {
            const fresh = freshData.find(f => 
              (c.rank_id && f.rank_id === c.rank_id) || 
              (c.profile_id && f.profile_id === c.profile_id)
            );

            if (fresh) {
              if (fresh.favorite !== c.favorite || fresh.save_for_future !== c.save_for_future) {
                hasChanges = true;
                return { 
                  ...c, 
                  favorite: fresh.favorite, 
                  save_for_future: fresh.save_for_future 
                };
              }
            }
            return c;
          });
          return hasChanges ? next : prev;
        });
      } catch (err) {
        console.warn("Background sync failed", err);
      }
    };

    syncCandidates();

    const onFocus = () => syncCandidates();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [currentJd?.jd_id]);


  // Auto-select uploaded JD (Single & Bulk)
  const handleJdFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      
      if (files.length > MAX_FILES_LIMIT) {
        setUploadStatus({ message: `To ensure fast processing, please upload a maximum of ${MAX_FILES_LIMIT} files at a time.`, type: 'error' });
        if (jdInputRef.current) jdInputRef.current.value = ''; // reset input
        return;
      }

      setIsJdLoading(true);
      setUploadStatus(null);

      try {
        if (files.length === 1) {
            const file = files[0];
            const newJd = await uploadJdFile(file);
            const updatedJds = await fetchJdsForUser();
            setUserJds(updatedJds);
            handleJdSelection(newJd.jd_id, updatedJds);
            setUploadStatus({ message: 'JD uploaded and selected!', type: 'success' });
            setIsJdLoading(false);
        } 
        else {
            const existingIds = new Set(userJds.map(j => j.jd_id));
            
            await uploadBulkJds(files);
            setUploadStatus({ message: 'JDs queued. Processing in background...', type: 'success' });
            
            const startCount = userJds.length;
            const expectedCount = startCount + files.length;
            
            let attempts = 0;
            const intervalId = setInterval(async () => {
                attempts++;
                try {
                    const updatedJds = await fetchJdsForUser();
                    
                    if (updatedJds.length > userJds.length) {
                         setUserJds(updatedJds);
                    }

                    const newJds = updatedJds.filter(j => !existingIds.has(j.jd_id));

                    const isDone = updatedJds.length >= expectedCount;
                    const isTimeout = attempts > 24; // ~2 minutes

                    if (isDone || (isTimeout && newJds.length > 0)) {
                        setUploadStatus({ 
                          message: isDone ? 'All JDs parsed successfully!' : 'Bulk processing finished (check dropdown).', 
                          type: 'success' 
                        });
                        setIsJdLoading(false);
                        clearInterval(intervalId);
                        
                        if (newJds.length > 0) {
                            handleJdSelection(newJds[0].jd_id, updatedJds);
                        } else if (updatedJds.length > 0) {
                            handleJdSelection(updatedJds[0].jd_id, updatedJds);
                        }

                    } else if (isTimeout) {
                         setUploadStatus({ message: 'Processing timed out. Please check the dropdown manually.', type: 'error' });
                         setIsJdLoading(false);
                         clearInterval(intervalId);
                    }
                } catch (e) { 
                    console.error("Polling error", e);
                }
            }, 5000);
        }

      } catch (error) {
        setUploadStatus({ message: (error as Error).message, type: 'error' });
        setIsJdLoading(false);
      } finally {
        if (jdInputRef.current) jdInputRef.current.value = '';
      }
    }
  };

  const handleJdSelection = (selectedJdId: string, jds: JdSummary[]) => {
    const selectedJd = jds.find((jd) => jd.jd_id === selectedJdId);
    if (selectedJd) {
      setCurrentJd({
        jd_id: selectedJd.jd_id,
        jd_parsed_summary: selectedJd.jd_parsed_summary || '',
        location: selectedJd.location || 'N/A',
        job_type: selectedJd.job_type || 'N/A',
        experience_required: selectedJd.experience_required || 'N/A',
      });

      if (isRestoringRef.current) {
        setUploadStatus(null);
        setHasSearched(false);
        return;
      }

      let restored = false;
      try {
        const raw = sessionStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as PersistedCandidates | null;
          if (parsed && parsed.jd_id === selectedJdId && Array.isArray(parsed.candidates)) {
            setCandidates(parsed.candidates);
            restored = true;
          }
        }
      } catch {
        /* ignore */
      }
      if (!restored) {
        setCandidates([]);
        setLinkedInCandidates([]);
      }

      setUploadStatus(null);
      setHasSearched(false);
    }
  };

  const handleResumeFilesChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setResumeFiles(event.target.files);
    }
  };

  const handleViewJd = (jdId?: string) => {
    const id = jdId ?? currentJd?.jd_id;
    if (!id) return;
    const jd = userJds.find((j) => j.jd_id === id);
    if (jd) setSelectedJd(jd);
  };
  const handleCloseJdPopup = () => setSelectedJd(null);

  const handleSearchAndRank = async () => {
    if (!currentJd) {
      setUploadStatus({ message: 'Please upload a Job Description first.', type: 'error' });
      return;
    }

    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }

    setIsRankingLoading(true);
    setUploadStatus(null);
    setHasSearched(true);
    setLinkedInCandidates([]);

    const search_start_time = new Date().toISOString();

    try {
      if (sourcingOption === 'gl') {
        linkedInSinceRef.current = search_start_time;
        const res = await startGoogleLinkedinTask(currentJd.jd_id, chatMessage || '');
        const newTaskId = (res as any)?.task_id ?? (res as any)?.taskId ?? (res as any)?.id ?? null;
        if (!newTaskId) throw new Error('Failed to start Google+LinkedIn sourcing task.');
        setTaskId(newTaskId);
        taskStartedAtRef.current = Date.now();
        setUploadStatus({ message: 'Google+LinkedIn sourcing started. We’ll fetch new profiles when ready.', type: 'success' });
        return;
      }

      if (sourcingOption === 'web') {
        const res = await triggerCombinedSearch(
          currentJd.jd_id, 
          chatMessage || '', 
          webSearchOption, 
          resumeFiles
        );
        
        const apolloTaskId = (res as any)?.apollo_task_id ?? (res as any)?.apolloTaskId ?? (res as any)?.task_id ?? null;

        if (!apolloTaskId) {
           const fallback = await startApolloSearchTask(currentJd.jd_id, chatMessage || '', webSearchOption);
           combinedApolloTaskIdRef.current = fallback.task_id;
        } else {
           combinedApolloTaskIdRef.current = apolloTaskId;
        }

        combinedSinceRef.current = search_start_time;
        taskStartedAtRef.current = Date.now();
        setIsCombinedSearch(true);
        
        setResumeFiles(null);
        if (resumeInputRef.current) resumeInputRef.current.value = '';
        
        setUploadStatus({
          message: 'Combined search started. Polling for incremental & final results...',
          type: 'success',
        });
        return;
      }

      if (resumeFiles && resumeFiles.length > 0) {
        await uploadResumeFiles(resumeFiles, currentJd.jd_id);
        setResumeFiles(null);
        if (resumeInputRef.current) resumeInputRef.current.value = '';
        setUploadStatus({ message: 'Resumes uploaded. Starting ranking...', type: 'success' });
      }

      const res = await startRankResumesTask(currentJd.jd_id, chatMessage || '');
      const newTaskId = (res as any)?.task_id ?? (res as any)?.taskId ?? (res as any)?.id ?? null;
      if (!newTaskId) throw new Error('Failed to start ranking task.');
      setTaskId(newTaskId);
      taskStartedAtRef.current = Date.now();
      setUploadStatus({ message: 'Ranking task started. Checking for results...', type: 'success' });

    } catch (error) {
      if ((error as Error).message !== 'Search cancelled by user.') {
        setUploadStatus({ message: (error as Error).message, type: 'error' });
        setIsRankingLoading(false);
      }
    }
  };

  // NEW: Handle Download
  const handleDownload = async (format: 'csv' | 'xlsx') => {
    if (!currentJd) {
        setUploadStatus({ message: 'Please select a Job Description first.', type: 'error' });
        return;
    }
    
    // Only allow download if we have results (either regular candidates or linkedin candidates)
    if (!candidates.length && !linkedInCandidates.length) {
        setUploadStatus({ message: 'No candidates to download.', type: 'error' });
        return;
    }

    try {
      setIsDownloading(true);
      await downloadSearchResults(currentJd.jd_id, format);
      setUploadStatus({ message: 'Download started!', type: 'success' });
    } catch (error) {
      setUploadStatus({ message: (error as Error).message || 'Download failed', type: 'error' });
    } finally {
      setIsDownloading(false);
    }
  };

  useEffect(() => {
    if (isCombinedSearch) {
      const apolloTaskId = combinedApolloTaskIdRef.current;
      const since = combinedSinceRef.current;
      if (!since) {
        setIsCombinedSearch(false);
        setIsRankingLoading(false);
        return;
      }

      const overallTimeoutMs = COMBINED_OVERALL_TIMEOUT_MS;
      const pollIntervalMs = TASK_POLL_INTERVAL_MS;
      const startedAt = Date.now();

      const poller = async () => {
        try {
          const combined = await getCombinedSearchResults(currentJd!.jd_id, since);
          if (Array.isArray(combined)) {
            setCandidates(combined);
            setUploadStatus({ message: `Found and ranked ${combined.length} candidates (partial).`, type: 'success' });
          }

          let apolloDone = false;
          if (apolloTaskId) {
            try {
              const statusResp: any = await getSearchResults(apolloTaskId);
              const statusLower = (statusResp?.status || '').toString().toLowerCase();
              if (statusLower === 'completed' || statusLower === 'done' || statusLower === 'success') {
                apolloDone = true;
              } else if (statusLower === 'failed' || statusLower === 'error') {
                apolloDone = true;
                setUploadStatus({ message: statusResp?.error || 'Search task failed.', type: 'error' });
              }
            } catch {
              /* ignore */
            }
          }

          if (apolloDone || Date.now() - startedAt > overallTimeoutMs) {
            const final = await getCombinedSearchResults(currentJd!.jd_id, since);
            if (Array.isArray(final)) {
              setCandidates(final);
              setUploadStatus({ message: `Found and ranked ${final.length} total candidates!`, type: 'success' });
            } else {
              setUploadStatus({ message: 'No final candidates found.', type: 'error' });
            }

            setIsCombinedSearch(false);
            setIsRankingLoading(false);
            combinedApolloTaskIdRef.current = null;
            combinedSinceRef.current = null;
            if (combinedPollingIntervalRef.current !== null) {
              clearInterval(combinedPollingIntervalRef.current);
              combinedPollingIntervalRef.current = null;
            }
            taskStartedAtRef.current = null;
          }
        } catch {
          if (Date.now() - startedAt > overallTimeoutMs) {
            setIsCombinedSearch(false);
            setIsRankingLoading(false);
            setUploadStatus({ message: 'Polling timed out.', type: 'error' });
            if (combinedPollingIntervalRef.current !== null) {
              clearInterval(combinedPollingIntervalRef.current);
              combinedPollingIntervalRef.current = null;
            }
            taskStartedAtRef.current = null;
          }
        }
      };

      poller();
      combinedPollingIntervalRef.current = window.setInterval(poller, pollIntervalMs);
      return () => {
        if (combinedPollingIntervalRef.current !== null) {
          clearInterval(combinedPollingIntervalRef.current);
          combinedPollingIntervalRef.current = null;
        }
      };
    }

    if (!taskId) return;

    if (!taskStartedAtRef.current) {
      taskStartedAtRef.current = Date.now();
    }

    const pollOnce = async () => {
      try {
        const started = taskStartedAtRef.current ?? Date.now();
        if (Date.now() - started > TASK_POLLING_TIMEOUT_MS) {
          if (pollingIntervalRef.current !== null) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setIsRankingLoading(false);
          setTaskId(null);
          taskStartedAtRef.current = null;
          setUploadStatus({ message: 'Polling timed out after 15 minutes.', type: 'error' });
          try {
            await stopTask(taskId);
          } catch {
            /* ignore */
          }
          return;
        }

        let resp: any = null;

        if (sourcingOption === 'db') {
          resp = await getRankResumesResults(taskId);
        } else if (sourcingOption === 'web') {
          resp = await getSearchResults(taskId);
        } else if (sourcingOption === 'gl') {
          resp = await getGoogleLinkedinResults(taskId);
          const statusLower = (resp?.status || '').toString().toLowerCase();
          if (statusLower === 'completed') {
            const inserted = resp?.inserted_count ?? 0;
            try {
              const since = linkedInSinceRef.current || new Date(0).toISOString();
              const rows = await fetchLinkedInCandidates(currentJd!.jd_id, since);
              setLinkedInCandidates(rows);
              setUploadStatus({
                message: `Sourcing completed. Added ${inserted} profile(s). Showing ${rows.length} new result(s).`,
                type: 'success',
              });
            } catch {
              setUploadStatus({ message: 'Sourcing completed, but failed to fetch new rows.', type: 'error' });
            }

            setIsRankingLoading(false);
            setTaskId(null);
            taskStartedAtRef.current = null;
            if (pollingIntervalRef.current !== null) {
              clearInterval(pollingIntervalRef.current);
              pollingIntervalRef.current = null;
            }
            return;
          }
          if (statusLower === 'failed') {
            setUploadStatus({ message: resp?.error || 'Google+LinkedIn sourcing failed.', type: 'error' });
            setIsRankingLoading(false);
            setTaskId(null);
            taskStartedAtRef.current = null;
            if (pollingIntervalRef.current !== null) {
              clearInterval(pollingIntervalRef.current);
              pollingIntervalRef.current = null;
            }
            return;
          }
          return;
        }

        const status = resp?.status?.toLowerCase?.() || resp?.state?.toLowerCase?.() || '';
        if (status === 'completed' || status === 'done' || status === 'success') {
          const results: Candidate[] = resp.results || resp.data || [];
          setCandidates(results);
          setUploadStatus({ message: `Found and ranked ${results.length} total candidates!`, type: 'success' });
          setIsRankingLoading(false);
          setTaskId(null);
          taskStartedAtRef.current = null;
          if (pollingIntervalRef.current !== null) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
        } else if (status === 'failed' || status === 'error') {
          const message = resp?.error || resp?.message || 'Task failed.';
          setUploadStatus({ message, type: 'error' });
          setIsRankingLoading(false);
          setTaskId(null);
          taskStartedAtRef.current = null;
          if (pollingIntervalRef.current !== null) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
        }
      } catch (error) {
        setUploadStatus({ message: (error as Error).message || 'Error while fetching task status.', type: 'error' });
        setIsRankingLoading(false);
        setTaskId(null);
        taskStartedAtRef.current = null;
        if (pollingIntervalRef.current !== null) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      }
    };

    pollOnce();
    pollingIntervalRef.current = window.setInterval(pollOnce, TASK_POLL_INTERVAL_MS);
    return () => {
      if (pollingIntervalRef.current !== null) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [taskId, sourcingOption, isCombinedSearch, currentJd]);

  const handleStopSearch = async () => {
    try {
      if (taskId) {
        try {
          await stopTask(taskId);
        } catch { }
      }

      if (isCombinedSearch) {
        const apolloTaskId = combinedApolloTaskIdRef.current;
        if (apolloTaskId) {
          try {
            await stopTask(apolloTaskId);
          } catch { }
        }
        if (combinedPollingIntervalRef.current !== null) {
          clearInterval(combinedPollingIntervalRef.current);
          combinedPollingIntervalRef.current = null;
        }
        combinedApolloTaskIdRef.current = null;
        combinedSinceRef.current = null;
        setIsCombinedSearch(false);
      }

      if (pollingIntervalRef.current !== null) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      setTaskId(null);
      taskStartedAtRef.current = null;
      setUploadStatus({ message: 'Search has been stopped.', type: 'success' });
    } catch (error) {
      setUploadStatus({ message: (error as Error).message, type: 'error' });
    } finally {
      setIsRankingLoading(false);
    }
  };

  const handleUpdateCandidate = (updated: Candidate) => {
    setCandidates((prev) => prev.map((c) => {
        const idMatch = c.profile_id === updated.profile_id || 
                        (c.rank_id && c.rank_id === updated.rank_id) || 
                        (c.resume_id && c.resume_id === updated.resume_id);
        return idMatch ? updated : c;
    }));
    
    if (selectedCandidate) {
        const isSelected = selectedCandidate.profile_id === updated.profile_id || 
                           (selectedCandidate.rank_id && selectedCandidate.rank_id === updated.rank_id) ||
                           (selectedCandidate.resume_id && selectedCandidate.resume_id === updated.resume_id);
        if (isSelected) {
             setSelectedCandidate(updated);
        }
    }
  };

  const handleCandidateNameClick = (candidate: Candidate) => setSelectedCandidate(candidate);
  const handleCloseCandidatePopup = () => setSelectedCandidate(null);

  const handlePrevCandidate = () => {
    if (!selectedCandidate || candidates.length === 0) return;
    const currentIndex = candidates.findIndex(c => stableKey(c) === stableKey(selectedCandidate));
    if (currentIndex > 0) {
      setSelectedCandidate(candidates[currentIndex - 1]);
    }
  };

  const handleNextCandidate = () => {
    if (!selectedCandidate || candidates.length === 0) return;
    const currentIndex = candidates.findIndex(c => stableKey(c) === stableKey(selectedCandidate));
    if (currentIndex !== -1 && currentIndex < candidates.length - 1) {
      setSelectedCandidate(candidates[currentIndex + 1]);
    }
  };

  const getMainActionButton = () => {
    if (isRankingLoading) {
      return (
        <button
          onClick={handleStopSearch}
          className="w-full bg-red-600 text-white font-semibold py-3 rounded-lg hover:bg-red-700 flex items-center justify-center gap-2 transition-colors"
        >
          <XCircle size={18} /> Stop Search
        </button>
      );
    }
    let buttonText = 'Search and Rank';
    if (sourcingOption === 'db') buttonText = 'Rank';
    if (sourcingOption === 'gl') buttonText = 'Start Sourcing';
    
    return (
      <button
        onClick={handleSearchAndRank}
        disabled={isJdLoading}
        className="w-full bg-teal-600 text-white font-semibold py-3 rounded-lg hover:bg-teal-700 flex items-center justify-center gap-2 disabled:bg-gray-400 transition-colors"
      >
        <SearchIcon size={18} /> {buttonText}
      </button>
    );
  };

  const helperText = (() => {
    if (isRankingLoading) return '';
    if (sourcingOption === 'db') {
      return candidates.length > 0
        ? `Found and ranked ${candidates.length} candidates.`
        : "Select 'My Database' and click 'Rank' to rank candidates from your database.";
    } else if (sourcingOption === 'gl') {
      return linkedInCandidates.length > 0
        ? `Found ${linkedInCandidates.length} LinkedIn profile(s) added just now.`
        : 'This will source LinkedIn profiles with AI and add them to the LinkedIn table for this JD. You can process or use them later.';
    } else {
      return candidates.length > 0
        ? `Found and ranked ${candidates.length} candidates.`
        : "Enter a prompt and click 'Search and Rank' to find candidates. Choose Fast or Web+Apollo.";
    }
  })();

  const handleToggleFavorite = async (
    candidateId: string,
    source: 'ranked_candidates' | 'ranked_candidates_from_resume' = 'ranked_candidates',
    newFavorite: boolean
  ) => {
    const updateList = (list: Candidate[]) => list.map((c) => {
        const isMatch = c.profile_id === candidateId || (c as any).resume_id === candidateId || c.rank_id === candidateId;
        if (isMatch) {
          return { ...c, favorite: newFavorite };
        }
        return c;
    });

    setCandidates(prev => updateList(prev));

    if (selectedCandidate) {
      const isMatch = selectedCandidate.profile_id === candidateId || (selectedCandidate as any).resume_id === candidateId || selectedCandidate.rank_id === candidateId;
      if (isMatch) {
          setSelectedCandidate(prev => prev ? ({ ...prev, favorite: newFavorite }) : null);
      }
    }

    try {
      await toggleFavorite(candidateId, source, newFavorite);
    } catch {
      setCandidates((prev) => prev.map((c) => {
          const isMatch = c.profile_id === candidateId || (c as any).resume_id === candidateId || c.rank_id === candidateId;
          if (isMatch) return { ...c, favorite: !newFavorite };
          return c;
      }));
       if (selectedCandidate) {
           const isMatch = selectedCandidate.profile_id === candidateId || (selectedCandidate as any).resume_id === candidateId || selectedCandidate.rank_id === candidateId;
           if (isMatch) setSelectedCandidate(prev => prev ? ({ ...prev, favorite: !newFavorite }) : null);
       }
      setUploadStatus({ message: 'Failed to update favorite. Try again.', type: 'error' });
    }
  };

  const handleToggleSave = async (
    candidateId: string,
    source: 'ranked_candidates' | 'ranked_candidates_from_resume' = 'ranked_candidates',
    newSave: boolean
  ) => {
    const prevCandidates = candidates;
    const prevLinked = linkedInCandidates;

    setCandidates((prev) =>
      prev.map((c) => {
        const isMatch = c.profile_id === candidateId || (c as any).resume_id === candidateId || c.rank_id === candidateId;
        if (isMatch) {
          return { ...c, save_for_future: newSave };
        }
        return c;
      })
    );

    if (selectedCandidate) {
        const isMatch = selectedCandidate.profile_id === candidateId || (selectedCandidate as any).resume_id === candidateId || selectedCandidate.rank_id === candidateId;
        if (isMatch) {
            setSelectedCandidate(prev => prev ? ({ ...prev, save_for_future: newSave }) : null);
        }
    }

    setLinkedInCandidates((prev) =>
      prev.map((li) => {
        if ((li as any).linkedin_profile_id === candidateId || (li as any).profile_link === candidateId) {
          return { ...li, save_for_future: newSave };
        }
        return li;
      })
    );

    try {
      await toggleSave(candidateId, source, newSave);
    } catch {
      setCandidates(prevCandidates);
      setLinkedInCandidates(prevLinked);
      if (selectedCandidate) {
         const isMatch = selectedCandidate.profile_id === candidateId || (selectedCandidate as any).resume_id === candidateId || selectedCandidate.rank_id === candidateId;
         if (isMatch) setSelectedCandidate(prev => prev ? ({ ...prev, save_for_future: !newSave }) : null);
      }
      setUploadStatus({ message: 'Failed to update Save-for-Future. Try again.', type: 'error' });
    }
  };

  return (
    <div className="h-screen bg-gray-50 text-gray-800 flex flex-col">
      <Header userName={userName} showBackButton={true} />
      <main className="flex-grow p-4 sm:p-6 md:p-8 max-w-screen-2xl mx-auto w-full overflow-y-hidden min-h-0">
        <div className="grid grid-cols-12 gap-8 h-full">
          <aside className="col-span-3 flex flex-col gap-6 overflow-y-auto pb-4">
            {/* JD Selection */}
            <div className="p-4 bg-white rounded-lg border border-gray-200 flex-shrink-0">
              <div className="flex justify-between items-center mb-2">
                <label className="font-semibold text-gray-700">Select Role</label>
                <button
                  onClick={() => jdInputRef.current?.click()}
                  className="text-sm text-teal-600 hover:underline flex items-center gap-1"
                >
                  <Plus size={14} /> Add New Role
                </button>
                <input 
                  type="file" 
                  ref={jdInputRef} 
                  onChange={handleJdFileChange} 
                  className="hidden" 
                  accept=".pdf,.docx,.txt" 
                  multiple 
                />
              </div>

              <select
                value={currentJd?.jd_id || ''}
                onChange={(e) => handleJdSelection(e.target.value, userJds)}
                className="w-full p-2 border border-gray-300 rounded-md bg-gray-50 text-sm"
                disabled={userJds.length === 0}
              >
                {userJds.length > 0 ? (
                  userJds.map((jd) => (
                    <option key={jd.jd_id} value={jd.jd_id}>
                      {jd.role}
                    </option>
                  ))
                ) : (
                  <option disabled value="">
                    Upload a JD to begin
                  </option>
                )}
              </select>

              {currentJd && (
                <div className="mt-4 text-sm text-gray-600 space-y-2">
                  <p>
                    <span className="font-medium">Location:</span> {currentJd.location}
                  </p>
                  <p>
                    <span className="font-medium">Experience:</span> {currentJd.experience_required}
                  </p>
                </div>
              )}
              <div className="mt-4 flex flex-col items-stretch gap-2 text-sm">
                <button
                  onClick={() => handleViewJd()}
                  className="flex items-center justify-center gap-2 p-2 rounded-md bg-gray-100 hover:bg-gray-200 border border-gray-200 text-gray-700 font-medium"
                >
                  <Eye size={16} /> View JD
                </button>
                <button className="flex items-center justify-center gap-2 p-2 rounded-md bg-gray-100 hover:bg-gray-200 border border-gray-200 text-gray-700 font-medium">
                  <History size={16} /> Edit History
                </button>
              </div>
            </div>

            {/* Sourcing Options */}
            <div className="p-4 bg-white rounded-lg border border-gray-200 flex-shrink-0">
              <h3 className="font-semibold text-gray-700 mb-3">Sourcing Options</h3>
              <div className="space-y-2 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sourcing"
                    value="db"
                    checked={sourcingOption === 'db'}
                    onChange={() => setSourcingOption('db')}
                  />{' '}
                  My Database
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sourcing"
                    value="web"
                    checked={sourcingOption === 'web'}
                    onChange={() => setSourcingOption('web')}
                  />{' '}
                  Web Search
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sourcing"
                    value="gl"
                    checked={sourcingOption === 'gl'}
                    onChange={() => setSourcingOption('gl')}
                  />{' '}
                  LinkedIn
                </label>
              </div>

              {sourcingOption !== 'gl' && (
                <>
                  <button
                    onClick={() => resumeInputRef.current?.click()}
                    className="mt-4 w-full border-dashed border-2 border-gray-300 rounded-lg p-6 text-center hover:border-teal-500 hover:text-teal-500 transition-colors"
                  >
                    <UploadCloud size={24} className="mx-auto text-gray-400" />
                    <p className="text-sm text-gray-500 mt-2">
                      {resumeFiles ? `${resumeFiles.length} resumes selected` : 'Upload Resumes'}
                    </p>
                  </button>
                  <input
                    type="file"
                    ref={resumeInputRef}
                    onChange={handleResumeFilesChange}
                    className="hidden"
                    accept=".pdf,.docx,.txt"
                    multiple
                  />
                </>
              )}

              {/* Web Search modes */}
              {sourcingOption === 'web' && (
                <div className="mt-4 p-3 bg-gray-50 rounded-md border border-gray-100 text-sm">
                  <div className="font-medium mb-2">Web Sourcing Mode</div>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="webMode"
                      value="1"
                      checked={webSearchOption === 1}
                      onChange={() => setWebSearchOption(1)}
                    />
                    Fast search
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="webMode"
                      value="2"
                      checked={webSearchOption === 2}
                      onChange={() => setWebSearchOption(2)}
                    />
                    Web search
                  </label>
                  <p className="mt-2 text-xs text-gray-500">
                    Fast = structured Apollo API searches (quicker). Web+Apollo = broader web discovery plus Apollo.
                  </p>
                </div>
              )}

            </div>

            {getMainActionButton()}

            {uploadStatus && (
              <div
                className={`mt-4 p-3 rounded-md text-sm text-center flex-shrink-0 ${uploadStatus.type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}
              >
                {uploadStatus.message}
              </div>
            )}
          </aside>

          {/* Main Content */}
          <div className="col-span-9 flex flex-col gap-8 h-full min-h-0">
            <div className="p-6 bg-white rounded-lg border border-gray-200 flex flex-col flex-grow min-h-0">
              <div className="flex-shrink-0">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-semibold">Top Matching Candidates</h2>
                  <div className="flex gap-2">
                     {/* Download Buttons */}
                     <button
                       onClick={() => handleDownload('csv')}
                       disabled={isDownloading || (!candidates.length && !linkedInCandidates.length)}
                       className="flex items-center gap-1 text-sm px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md disabled:opacity-50"
                       title="Download CSV"
                     >
                       <Download size={14} /> CSV
                     </button>
                     <button
                       onClick={() => handleDownload('xlsx')}
                       disabled={isDownloading || (!candidates.length && !linkedInCandidates.length)}
                       className="flex items-center gap-1 text-sm px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md disabled:opacity-50"
                       title="Download Excel"
                     >
                       <Download size={14} /> Excel
                     </button>
                     {isRankingLoading && (
                        <div className="flex items-center gap-2 text-sm text-teal-600 ml-2">
                          <Loader />
                          <span>Processing...</span>
                        </div>
                     )}
                  </div>
                </div>
                <p className="text-sm text-gray-500 mb-4 h-5">{!isRankingLoading && helperText}</p>

                {/* Header row */}
                {sourcingOption === 'gl' ? (
                  <div className="grid grid-cols-3 text-xs font-semibold text-gray-500 uppercase py-2 border-b-2">
                    <div className="flex items-center justify-start">Candidate</div>
                    <div className="flex items-center justify-center">Profile Link</div>
                    <div className="flex items-center justify-start">Actions</div>
                  </div>
                ) : (
                  <div className="grid grid-cols-12 text-xs font-semibold text-gray-500 uppercase py-2 border-b-2">
                    <div className="col-span-6">Candidate</div>
                    <div className="col-span-2">Match Score</div>
                    <div className="col-span-2">Profile Link</div>
                    <div className="col-span-2">Actions</div>
                  </div>
                )}
              </div>

              <div className="flex-grow overflow-y-auto max-h-[30vh]">
                {sourcingOption === 'gl'
                  ? linkedInCandidates.map((li) => (
                      <LinkedInCandidateRow
                        key={li.linkedin_profile_id}
                        candidate={li}
                        onToggleFavorite={(candidateId: string, source?: any, fav?: boolean) =>
                          handleToggleFavorite(candidateId, (source as any) ?? 'ranked_candidates', fav ?? false)
                        }
                        onToggleSave={(candidateId: string, source?: any, save?: boolean) =>
                          handleToggleSave(candidateId, (source as any) ?? 'ranked_candidates', save ?? !li.save_for_future)
                        }
                        // ✅ NEW: Pass user JDs
                        userJds={userJds}
                      />
                    ))
                  : candidates.map((candidate) => (
                      <CandidateRow
                        key={stableKey(candidate)}
                        candidate={candidate}
                        onUpdateCandidate={handleUpdateCandidate}
                        onNameClick={handleCandidateNameClick}
                        onToggleFavorite={(candidateId: string, source?: any, fav?: boolean) =>
                          handleToggleFavorite(
                            candidateId,
                            (source as any) ?? 'ranked_candidates',
                            fav ?? !candidate.favorite
                          )
                        }
                        onToggleSave={(candidateId: string, source?: any, save?: boolean) =>
                          handleToggleSave(
                            candidateId,
                            (source as any) ?? ((candidate as any).resume_id ? 'ranked_candidates_from_resume' : 'ranked_candidates'),
                            save ?? !((candidate as any).save_for_future)
                          )
                        }
                        source={(candidate as any).resume_id ? 'ranked_candidates_from_resume' : 'ranked_candidates'}
                        // ✅ NEW: Pass user JDs
                        userJds={userJds}
                      />
                    ))}
              </div>
            </div>

            <div className="p-6 bg-white rounded-lg border border-gray-200 flex-shrink-0">
              <div className="flex flex-col gap-4 mb-4">
                {hasSearched && (
                  <div className="self-end">
                    <div className="p-3 text-sm rounded-lg bg-green-100 text-green-800">
                      {sourcingOption === 'gl'
                        ? linkedInCandidates.length > 0
                          ? `Okay — fetched ${linkedInCandidates.length} new LinkedIn profile(s).`
                          : 'Okay, sourcing LinkedIn profiles for this JD...'
                        : 'Okay, filtering for candidates... Here are the top results.'}
                    </div>
                  </div>
                )}
              </div>

              <div className="relative">
                <input
                  type="text"
                  value={chatMessage}
                  onChange={(e) => setChatMessage(e.target.value)}
                  placeholder={
                    sourcingOption === 'db'
                      ? 'Disabled for My Database'
                      : sourcingOption === 'gl'
                        ? 'Chat disabled for LinkedIn sourcing'
                        : 'Chat with AIRA... (optional)'
                  }
                  className={`w-full pl-4 pr-10 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-teal-500 ${sourcingOption === 'gl' ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : ''
                    }`}
                  onKeyDown={(e) =>
                    e.key === 'Enter' && !isRankingLoading && sourcingOption !== 'db' && sourcingOption !== 'gl' && handleSearchAndRank()
                  }
                  disabled={isRankingLoading || sourcingOption === 'db' || sourcingOption === 'gl'}
                />
                <button
                  onClick={isRankingLoading ? handleStopSearch : handleSearchAndRank}
                  className={`absolute inset-y-0 right-0 flex items-center pr-3 ${sourcingOption === 'gl' ? 'text-gray-300 cursor-not-allowed' : 'text-gray-500 hover:text-teal-600'
                    }`}
                  disabled={isRankingLoading || sourcingOption === 'db' || sourcingOption === 'gl'}
                  aria-disabled={isRankingLoading || sourcingOption === 'db' || sourcingOption === 'gl'}
                >
                  {isRankingLoading ? <XCircle size={20} className="text-red-500" /> : <SendHorizonal size={20} />}
                </button>
              </div>

              {hasSearched && !isRankingLoading && sourcingOption !== 'gl' && (
                <div className="flex justify-end pt-4">
                  <button
                    onClick={handleSearchAndRank}
                    className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900"
                  >
                    <RefreshCw size={14} /> Rerun Search
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {selectedCandidate && (
        <CandidatePopupCard 
          candidate={selectedCandidate} 
          onClose={handleCloseCandidatePopup}
          onUpdateCandidate={handleUpdateCandidate}
          onPrev={handlePrevCandidate}
          onNext={handleNextCandidate}
          onToggleFavorite={(candidateId: string, source?: any, fav?: boolean) =>
            handleToggleFavorite(
              candidateId,
              (source as any) ?? 'ranked_candidates',
              fav ?? !selectedCandidate.favorite
            )
          }
          onToggleSave={(candidateId: string, source?: any, save?: boolean) =>
            handleToggleSave(
              candidateId,
              (source as any) ?? ((selectedCandidate as any).resume_id ? 'ranked_candidates_from_resume' : 'ranked_candidates'),
              save ?? !((selectedCandidate as any).save_for_future)
            )
          }
        />
      )}

      {selectedJd && <JdPopupCard jd={selectedJd} onClose={handleCloseJdPopup} />}
    </div>
  );
}