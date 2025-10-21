import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Header } from '../components/layout/Header';
import { CandidateRow } from '../components/ui/CandidateRow';
import { Plus, UploadCloud, Search as SearchIcon, SendHorizonal, Bot, Eye, History, RefreshCw, XCircle } from 'lucide-react';
import type { User } from '../types/user';
import { uploadJdFile, uploadResumeFiles } from '../api/upload';
import { fetchJdsForUser, type JdSummary } from '../api/roles';
import CandidatePopupCard from '../components/ui/CandidatePopupCard';
import JdPopupCard from '../components/ui/JdPopupCard'; // <-- NEW IMPORT

import {
  startSearchAndRankTask,
  startRankResumesTask,
  getSearchResults,
  getRankResumesResults,
  stopTask,
  toggleFavorite,
  // NEW: helper to call the new apollo-search endpoint (will be added to frontend/src/api/search.ts next)
  startApolloSearchTask,
} from '../api/search';

import type { Candidate } from '../types/candidate';

// Loader component (Unchanged)
const Loader = () => (
  <svg className="animate-spin h-5 w-5 text-teal-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
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

  const [userJds, setUserJds] = useState<JdSummary[]>([]);
  const [currentJd, setCurrentJd] = useState<JobDescriptionDetails | null>(null);
  const [selectedJd, setSelectedJd] = useState<JdSummary | null>(null); // <-- NEW: holds full JD to show in popup
  const [resumeFiles, setResumeFiles] = useState<FileList | null>(null);
  const [isJdLoading, setIsJdLoading] = useState(false);
  const [isRankingLoading, setIsRankingLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [chatMessage, setChatMessage] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);

  // Sourcing option can be 'db' or 'web' (unchanged)
  const [sourcingOption, setSourcingOption] = useState<'web' | 'db'>('web');

  // NEW: which web search mode (1 = Fast Apollo-only, 2 = Web + Apollo)
  const [webSearchOption, setWebSearchOption] = useState<number>(2);

  const [taskId, setTaskId] = useState<string | null>(null);
  const pollingIntervalRef = useRef<number | null>(null);

  const jdInputRef = useRef<HTMLInputElement>(null);
  const resumeInputRef = useRef<HTMLInputElement>(null);

  // Track whether we are hydrating from sessionStorage to avoid overwriting it
  const isRestoringRef = useRef<boolean>(true);

  // stable, type-safe storage key helper — memoized so it won't change across renders
  const STORAGE_KEY = useMemo(() => {
    const maybeId = (user as unknown as { id?: string })?.id;
    return `search_candidates_v1::${maybeId ?? user.name ?? 'anon'}`;
  }, [user]);

  // Persist candidates + jd_id into sessionStorage whenever they change
  useEffect(() => {
    if (isRestoringRef.current) {
      return;
    }
    try {
      const payload: PersistedCandidates = {
        jd_id: currentJd?.jd_id ?? null,
        candidates,
      };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {
      // ignore storage failures
      console.warn('Failed to persist candidates to sessionStorage', e);
    }
  }, [candidates, currentJd, STORAGE_KEY]);

  // Combined restore + loadUserJds effect:
  useEffect(() => {
    let parsedStorage: PersistedCandidates | null = null;

    // mark start of restore
    isRestoringRef.current = true;

    // 1) Try restore sessionStorage (candidates + jd_id)
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        parsedStorage = JSON.parse(raw) as PersistedCandidates | null;
        if (parsedStorage?.candidates && Array.isArray(parsedStorage.candidates) && parsedStorage.candidates.length > 0) {
          setCandidates(parsedStorage.candidates);
          console.debug && console.debug('[SearchPage] Restored candidates from sessionStorage', parsedStorage);
        }
      }
    } catch (err) {
      console.warn('Failed to parse persisted storage', err);
    }

    (async () => {
      try {
        const jds = await fetchJdsForUser();
        setUserJds(jds);

        if (parsedStorage?.jd_id) {
          const match = jds.find(j => j.jd_id === parsedStorage!.jd_id);
          if (match) {
            setCurrentJd({
              jd_id: match.jd_id,
              jd_parsed_summary: match.jd_parsed_summary || '',
              location: match.location || 'N/A',
              job_type: match.job_type || 'N/A',
              experience_required: match.experience_required || 'N/A',
            });
            isRestoringRef.current = false;
            console.debug && console.debug('[SearchPage] Restored currentJd from sessionStorage:', match.jd_id);
            return;
          }
        }

        if (jds.length > 0 && !currentJd) {
          handleJdSelection(jds[0].jd_id, jds);
        }
      } catch (error) {
        setUploadStatus({ message: 'Could not load your saved roles.', type: 'error' });
      } finally {
        isRestoringRef.current = false;
      }
    })();

  }, [STORAGE_KEY]);

  const handleJdFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      const file = event.target.files[0];
      setIsJdLoading(true);
      setUploadStatus(null);
      try {
        const newJd = await uploadJdFile(file);
        const updatedJds = await fetchJdsForUser();
        setUserJds(updatedJds);
        handleJdSelection(newJd.jd_id, updatedJds);
        setUploadStatus({ message: 'JD uploaded and selected!', type: 'success' });
      } catch (error) {
        setUploadStatus({ message: (error as Error).message, type: 'error' });
      } finally {
        setIsJdLoading(false);
      }
    }
  };

  // selecting a JD from the dropdown (user action)
  const handleJdSelection = (selectedJdId: string, jds: JdSummary[]) => {
    const selectedJd = jds.find(jd => jd.jd_id === selectedJdId);
    if (selectedJd) {
      setCurrentJd({
        jd_id: selectedJd.jd_id,
        jd_parsed_summary: selectedJd.jd_parsed_summary || '',
        location: selectedJd.location || 'N/A',
        job_type: selectedJd.job_type || 'N/A',
        experience_required: selectedJd.experience_required || 'N/A',
      });

      if (isRestoringRef.current) {
        // we've either restored candidates already or will rely on persisted payload;
        console.debug && console.debug('[SearchPage] Skipping candidate clear during restore for JD', selectedJdId);
        setUploadStatus(null);
        setHasSearched(false);
        return;
      }

      // When the user manually selects a JD, restore persisted candidates for this JD if present,
      // otherwise clear previous results (user intent).
      let restoredForThisJd = false;
      try {
        const raw = sessionStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as PersistedCandidates | null;
          if (parsed && parsed.jd_id === selectedJdId && Array.isArray(parsed.candidates)) {
            setCandidates(parsed.candidates);
            restoredForThisJd = true;
          }
        }
      } catch {
        // ignore parse errors
      }
      if (!restoredForThisJd) {
        setCandidates([]);
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

  // NEW: When user clicks "View JD", open the JD popup for the selected JD
  const handleViewJd = (jdId?: string) => {
    const id = jdId ?? currentJd?.jd_id;
    if (!id) return;
    const jd = userJds.find(j => j.jd_id === id);
    if (jd) {
      setSelectedJd(jd);
    }
  };

  const handleCloseJdPopup = () => setSelectedJd(null);

  const handleSearchAndRank = async () => {
    if (!currentJd) {
      setUploadStatus({ message: 'Please upload a Job Description first.', type: 'error' });
      return;
    }

    // Clear old persisted results BEFORE starting a new search
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }

    // The chat input is disabled in UI for db
    setIsRankingLoading(true);
    setUploadStatus(null);
    setHasSearched(true);

    try {
      if (resumeFiles && resumeFiles.length > 0) {
        await uploadResumeFiles(resumeFiles, currentJd.jd_id);
        setResumeFiles(null);
        if (resumeInputRef.current) resumeInputRef.current.value = "";
        setUploadStatus({ message: 'Resumes uploaded. Starting ranking...', type: 'success' });
      }

      if (sourcingOption === 'db') {
        // chatMessage may be empty — that's OK for DB ranking
        const res = await startRankResumesTask(currentJd.jd_id, chatMessage || '');
        const newTaskId =
          (res as any)?.task_id ??
          (res as any)?.taskId ??
          (res as any)?.id ??
          null;
        if (!newTaskId) throw new Error('Failed to start ranking task.');
        setTaskId(newTaskId);
        setUploadStatus({ message: 'Ranking task started. Checking for results...', type: 'success' });
      } else {
        // WEB search path: call the new apollo-search API so we can pass search_option
        // 1 -> Fast (apollo_only), 2 -> Web + Apollo (apollo_and_web)
        const res = await startApolloSearchTask(currentJd.jd_id, chatMessage || '', webSearchOption);
        const newTaskId =
          (res as any)?.task_id ??
          (res as any)?.taskId ??
          (res as any)?.id ??
          null;
        if (!newTaskId) throw new Error('Failed to start search task.');
        setTaskId(newTaskId);
        setUploadStatus({ message: 'Search task started. Checking for results...', type: 'success' });
      }
    } catch (error) {
      if ((error as Error).message !== 'Search cancelled by user.') {
        setUploadStatus({ message: (error as Error).message, type: 'error' });
        setIsRankingLoading(false);
      }
    }
  };

  // --- useEffect for polling ---
  useEffect(() => {
    const clearPolling = () => {
      if (pollingIntervalRef.current !== null) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };

    if (!taskId) return;

    const pollOnce = async () => {
      try {
        let resp: any = null;
        if (sourcingOption === 'db') {
          resp = await getRankResumesResults(taskId);
        } else {
          resp = await getSearchResults(taskId);
        }

        const status = resp?.status?.toLowerCase?.() || resp?.state?.toLowerCase?.() || '';
        if (status === 'completed' || status === 'done' || status === 'success') {
          const results: Candidate[] = resp.results || resp.data || [];
          setCandidates(results);
          setUploadStatus({ message: `Found and ranked ${results.length} total candidates!`, type: 'success' });
          setIsRankingLoading(false);
          setTaskId(null);
          clearPolling();
        } else if (status === 'failed' || status === 'error') {
          const message = resp?.error || resp?.message || 'Task failed.';
          setUploadStatus({ message, type: 'error' });
          setIsRankingLoading(false);
          setTaskId(null);
          clearPolling();
        }
      } catch (error) {
        setUploadStatus({ message: (error as Error).message || 'Error while fetching task status.', type: 'error' });
        setIsRankingLoading(false);
        setTaskId(null);
        clearPolling();
      }
    };

    pollOnce();
    pollingIntervalRef.current = window.setInterval(pollOnce, 5000);

    return () => clearPolling();
  }, [taskId, sourcingOption]);

  // --- handleStopSearch ---
  const handleStopSearch = async () => {
    try {
      if (taskId) {
        try {
          await stopTask(taskId);
        } catch (err) {
          console.warn('stopTask error', err);
        }
      }
      if (pollingIntervalRef.current !== null) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      setTaskId(null);
      setUploadStatus({ message: 'Search has been stopped.', type: 'success' });
    } catch (error) {
      setUploadStatus({ message: (error as Error).message, type: 'error' });
    } finally {
      setIsRankingLoading(false);
    }
  };

  const handleUpdateCandidate = (updatedCandidate: Candidate) => {
    setCandidates(prev =>
      prev.map(c => c.profile_id === updatedCandidate.profile_id ? updatedCandidate : c)
    );
  };

  const handleCandidateNameClick = (candidate: Candidate) => {
    // open popup for candidate
    setSelectedCandidate(candidate);
  };
  
  const handleCloseCandidatePopup = () => {
    setSelectedCandidate(null);
  };
  

  const getMainActionButton = () => {
    if (isRankingLoading) {
      return (
        <button 
          onClick={handleStopSearch} 
          className="w-full bg-red-600 text-white font-semibold py-3 rounded-lg hover:bg-red-700 flex items-center justify-center gap-2 transition-colors"
        >
          <XCircle size={18}/> Stop Search
        </button>
      );
    }
    const buttonText = sourcingOption === 'db' ? 'Rank' : 'Search and Rank';
    return (
      <button 
        onClick={handleSearchAndRank} 
        disabled={isJdLoading} 
        className="w-full bg-teal-600 text-white font-semibold py-3 rounded-lg hover:bg-teal-700 flex items-center justify-center gap-2 disabled:bg-gray-400 transition-colors"
      >
        <SearchIcon size={18}/> {buttonText}
      </button>
    );
  };


  // dynamic helper text shown above candidate list
  const helperText = (() => {
    if (isRankingLoading) return '';
    if (sourcingOption === 'db') {
      return candidates.length > 0 ? `Found and ranked ${candidates.length} candidates.` : "Select 'My Database' and click 'Rank' to rank candidates from your database.";
    } else {
      return candidates.length > 0 ? `Found and ranked ${candidates.length} candidates.` : "Enter a prompt and click 'Search and Rank' to find candidates. Choose Fast or Web+Apollo.";
    }
  })();

  // ---------------------------
  // Favorite toggle handler
  // ---------------------------
  const handleToggleFavorite = async (
    candidateId: string,
    source: 'ranked_candidates' | 'ranked_candidates_from_resume' = 'ranked_candidates',
    newFavorite: boolean
  ) => {
    // optimistic update
    setCandidates(prev =>
      prev.map(c => {
        if (c.profile_id === candidateId || (c as any).resume_id === candidateId) {
          return { ...c, favorite: newFavorite };
        }
        return c;
      })
    );

    try {
      await toggleFavorite(candidateId, source, newFavorite);
      // backend returned ok; state already reflects it
    } catch (err) {
      // rollback on error
      console.warn('toggleFavorite failed', err);
      setCandidates(prev =>
        prev.map(c => {
          if (c.profile_id === candidateId || (c as any).resume_id === candidateId) {
            return { ...c, favorite: !newFavorite };
          }
          return c;
        })
      );
      setUploadStatus({ message: 'Failed to update favorite. Try again.', type: 'error' });
    }
  };

  return (
    <div className="h-screen bg-gray-50 text-gray-800 flex flex-col">
      <Header userName={userName} showBackButton={true} />
      <main className="flex-grow p-4 sm:p-6 md:p-8 max-w-screen-2xl mx-auto w-full overflow-y-hidden min-h-0">
        <div className="grid grid-cols-12 gap-8 h-full">
          <aside className="col-span-3 flex flex-col gap-6 overflow-y-auto pb-4">
            {/* JD Selection Box  */}
             <div className="p-4 bg-white rounded-lg border border-gray-200 flex-shrink-0">
              <div className="flex justify-between items-center mb-2">
                <label className="font-semibold text-gray-700">Select Role</label>
                <button onClick={() => jdInputRef.current?.click()} className="text-sm text-teal-600 hover:underline flex items-center gap-1">
                  <Plus size={14}/> Add New Role
                </button>
                <input type="file" ref={jdInputRef} onChange={handleJdFileChange} className="hidden" accept=".pdf,.docx,.txt"/>
              </div>
              
              <select
                value={currentJd?.jd_id || ''}
                onChange={(e) => handleJdSelection(e.target.value, userJds)}
                className="w-full p-2 border border-gray-300 rounded-md bg-gray-50 text-sm"
                disabled={userJds.length === 0}
              >
                {userJds.length > 0 ? (
                  userJds.map(jd => (
                    <option key={jd.jd_id} value={jd.jd_id}>
                      {jd.role}
                    </option>
                  ))
                ) : (
                  <option disabled value="">Upload a JD to begin</option>
                )}
              </select>

              {currentJd && (
                <div className="mt-4 text-sm text-gray-600 space-y-2">
                  <p><span className="font-medium">Location:</span> {currentJd.location}</p>
                  {/* <p><span className="font-medium">Type:</span> {currentJd.job_type}</p> */}
                  <p><span className="font-medium">Experience:</span> {currentJd.experience_required}</p>
                </div>
              )}
              <div className="mt-4 flex flex-col items-stretch gap-2 text-sm">
                <button onClick={() => handleViewJd()} className="flex items-center justify-center gap-2 p-2 rounded-md bg-gray-100 hover:bg-gray-200 border border-gray-200 text-gray-700 font-medium">
                  <Eye size={16} /> View JD
                </button>
                <button className="flex items-center justify-center gap-2 p-2 rounded-md bg-gray-100 hover:bg-gray-200 border border-gray-200 text-gray-700 font-medium">
                  <History size={16} /> Edit History
                </button>
              </div>
            </div>
            {/* --- START: SOURCING OPTIONS --- */}
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
                  /> My Database
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sourcing"
                    value="web"
                    checked={sourcingOption === 'web'}
                    onChange={() => setSourcingOption('web')}
                  /> Web Search
                </label>
                <label className="flex items-center gap-2 text-gray-400">
                  <input type="radio" name="sourcing" value="both" disabled /> Both (Coming Soon)
                </label>
              </div>

              {/* NEW: When 'Web Search' is selected, offer two modes */}
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
                    Fast search (Apollo-only)
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="webMode"
                      value="2"
                      checked={webSearchOption === 2}
                      onChange={() => setWebSearchOption(2)}
                    />
                    Web search + Apollo (comprehensive)
                  </label>
                  <p className="mt-2 text-xs text-gray-500">
                    Fast = structured Apollo API searches (fewer sources, quicker). Web+Apollo = broader web discovery plus Apollo.
                  </p>
                </div>
              )}

              <button onClick={() => resumeInputRef.current?.click()} className="mt-4 w-full border-dashed border-2 border-gray-300 rounded-lg p-6 text-center hover:border-teal-500 hover:text-teal-500 transition-colors">
                <UploadCloud size={24} className="mx-auto text-gray-400"/>
                <p className="text-sm text-gray-500 mt-2">
                  {resumeFiles ? `${resumeFiles.length} resumes selected` : 'Upload Resumes'}
                </p>
              </button>
              <input type="file" ref={resumeInputRef} onChange={handleResumeFilesChange} className="hidden" accept=".pdf,.docx,.txt" multiple/>
            </div>
            {getMainActionButton()}
            {uploadStatus && (
              <div className={`mt-4 p-3 rounded-md text-sm text-center flex-shrink-0 ${uploadStatus.type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                {uploadStatus.message}
              </div>
            )}
          </aside>
          
          {/* Main Content Area */}
          <div className="col-span-9 flex flex-col gap-8 h-full min-h-0">
            <div className="p-6 bg-white rounded-lg border border-gray-200 flex flex-col flex-grow min-h-0">
              <div className="flex-shrink-0">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-semibold">Top Matching Candidates</h2>
                  {isRankingLoading && (
                    <div className="flex items-center gap-2 text-sm text-teal-600">
                      <Loader />
                      <span>Searching & Ranking...</span>
                    </div>
                  )}
                </div>
                <p className="text-sm text-gray-500 mb-4 h-5">
                  {!isRankingLoading && helperText}
                </p>
                <div className="grid grid-cols-12 text-xs font-semibold text-gray-500 uppercase py-2 border-b-2">
                  <div className="col-span-6">Candidate</div>
                  <div className="col-span-2">Match Score</div>
                  <div className="col-span-2">Profile Link</div>
                  <div className="col-span-2">Actions</div>
                </div>
              </div>
              
              <div className="flex-grow overflow-y-auto max-h-[30vh]">
              {candidates.map((candidate) => (
                <CandidateRow 
                  key={candidate.profile_id} 
                  candidate={candidate} 
                  onUpdateCandidate={handleUpdateCandidate}
                  onNameClick={handleCandidateNameClick}
                  // NEW: favorite toggle prop
                  onToggleFavorite={(candidateId: string, source?: any, fav?: boolean) =>
                    handleToggleFavorite(candidateId, (source as any) ?? 'ranked_candidates', fav ?? !candidate.favorite)
                  }
                />
              ))}
              </div>
            </div>

            <div className="p-6 bg-white rounded-lg border border-gray-200 flex-shrink-0">
                <div className="flex flex-col gap-4 mb-4">
                    {hasSearched && (
                      <div className="self-end">
                          <div className="p-3 text-sm rounded-lg bg-green-100 text-green-800">
                             Okay, filtering for candidates... Here are the top results.
                          </div>
                      </div>
                    )}
                </div>

                <div className="relative">
                <input
  type="text"
  value={chatMessage}
  onChange={(e) => setChatMessage(e.target.value)}
  placeholder={sourcingOption === 'db' ? 'Disabled for My Database' : 'Chat with AIRA... (optional)'}
  className="w-full pl-4 pr-10 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
  onKeyDown={(e) => e.key === 'Enter' && !isRankingLoading && sourcingOption !== 'db' && handleSearchAndRank()}
  disabled={isRankingLoading || sourcingOption === 'db'}
/>
<button 
  onClick={isRankingLoading ? handleStopSearch : handleSearchAndRank} 
  className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-500 hover:text-teal-600"
  disabled={isRankingLoading || sourcingOption === 'db'}
  aria-disabled={isRankingLoading || sourcingOption === 'db'}
>
  {isRankingLoading ? <XCircle size={20} className="text-red-500"/> : <SendHorizonal size={20} />}
</button>

                </div>

                {hasSearched && !isRankingLoading && (
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
        />
      )}

      {/* JD Popup — shown when a JD is selected for viewing */}
      {selectedJd && (
        <JdPopupCard
          jd={selectedJd}
          onClose={handleCloseJdPopup}
        />
      )}
    </div>
  );
}
