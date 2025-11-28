import React, { useState, useEffect, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { Header } from '../components/layout/Header';
import { Search, ChevronDown, Link, Star, Send, Phone, Trash2, ArrowRight, Download } from 'lucide-react'; // Added Download
import type { User } from '../types/user';

// --- API & TYPE IMPORTS ---
import {
  getRankedCandidatesForJd,
  getAllRankedCandidates,
  updateCandidateStage,
  updateCandidateFavoriteStatus,
  downloadJdPipeline,     // Added
  downloadAllCandidates,  // Added
} from '../api/pipeline';
import { fetchJdsForUser, type JdSummary } from '../api/roles';
import {
  candidateStages,
  type Candidate,
  type CandidateStage,
} from '../types/candidate';

// --- POPUP IMPORTS ---
import RecommendPopup from '../components/ui/RecommendPopup';
import CallSchedulePopup from '../components/ui/CallSchedulePopup';

// --- Local Display Type ---
type PipelineDisplayCandidate = Candidate & { stage: CandidateStage };

// --- Filter Types ---
type StatusFilter = 'all' | 'favorite' | 'contacted';
type StageFilter = 'all' | CandidateStage;

// --- Row components ---
const AllCandidatesRow: React.FC<{ candidate: Candidate }> = ({ candidate }) => {
  const avatarInitial =
    (candidate.profile_name || candidate.person_name || '')
      .split(' ')
      .map(n => n[0])
      .join('')
      .toUpperCase() || '??';

  const getStatusDisplay = (candidate: Candidate) => {
    if (candidate.favorite) return 'Favourited';
    if (candidate.contacted) return 'Contacted';
    if (candidate.save_for_future) return 'Saved for Future';
    return 'In Pipeline';
  };

  return (
    <div className="grid grid-cols-12 items-center py-3 px-2 border-b border-slate-100 text-sm hover:bg-slate-50">
      <div className="col-span-1 flex justify-center">
        <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
      </div>
      <div className="col-span-4 flex items-center gap-3">
        <div className="w-9 h-9 flex-shrink-0 flex items-center justify-center bg-slate-300 text-slate-700 rounded-full font-bold text-xs">
          {avatarInitial}
        </div>
        <div>
          <p className="font-bold text-slate-800">{candidate.profile_name || candidate.person_name || 'N/A'}</p>
          <p className="text-slate-500">{`${candidate.role || 'N/A'} at ${candidate.company || 'N/A'}`}</p>
        </div>
      </div>
      <div className="col-span-2 text-slate-600">{getStatusDisplay(candidate)}</div>
      <div className="col-span-2 text-slate-600">{candidate.jd_name || 'N/A'}</div>
      <div className="col-span-1">
        <a href={candidate.linkedin_url || '#'} target="_blank" rel="noopener noreferrer" className="text-slate-400 hover:text-teal-600">
          <Link size={18} />
        </a>
      </div>
      <div className="col-span-2 flex items-center gap-4 text-slate-400">
        <button className="hover:text-red-500"><Trash2 size={18} /></button>
        <button className="hover:text-blue-500"><Send size={18} /></button>
        <button className="hover:text-green-500"><ArrowRight size={18} /></button>
      </div>
    </div>
  );
};

const PipelineCandidateRow: React.FC<{
  candidate: PipelineDisplayCandidate;
  onStageChange: (id: string, newStage: CandidateStage) => void;
  onFavoriteToggle: (profileIdOrRankId: string) => void;
}> = ({ candidate, onStageChange, onFavoriteToggle }) => {
  const avatarInitial = candidate.profile_name?.split(' ').map(n => n[0]).join('').toUpperCase() || '??';
  const [isRecommendOpen, setIsRecommendOpen] = useState(false);
  const [isCallOpen, setIsCallOpen] = useState(false);

  const getStatusText = (candidate: Candidate) => {
    return candidate.favorite ? 'Favourited' : 'In Pipeline';
  };

  const getStatusTextClass = (candidate: Candidate) => {
    return candidate.favorite ? 'text-yellow-600 font-semibold' : 'text-gray-600';
  };

  const displayName = candidate.profile_name || candidate.person_name || 'Candidate';

  return (
    <>
      <div className="grid grid-cols-12 items-center py-3 px-2 border-b border-slate-100 text-sm hover:bg-slate-50">
        <div className="col-span-1 flex justify-center">
          <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
        </div>

        <div className="col-span-4 flex items-center gap-3">
          <div className="w-9 h-9 flex-shrink-0 flex items-center justify-center bg-slate-300 text-slate-700 rounded-full font-bold text-xs">
            {avatarInitial}
          </div>
          <div>
            <p className="font-bold text-slate-800">{candidate.profile_name || candidate.person_name || 'N/A'}</p>
            <p className="text-slate-500">{`${candidate.role || 'N/A'} at ${candidate.company || 'N/A'}`}</p>
          </div>
        </div>

        <div className="col-span-2">
          <span className={`text-xs ${getStatusTextClass(candidate)}`}>{getStatusText(candidate)}</span>
        </div>

        <div className="col-span-2">
          <select
            value={candidate.stage}
            onChange={(e) => {
              if (candidate.rank_id) {
                onStageChange(candidate.rank_id, e.target.value as CandidateStage);
              }
            }}
            className="w-full p-1.5 border-none rounded-md bg-slate-100 text-slate-700 text-xs focus:ring-2 focus:ring-teal-500 appearance-none text-left"
          >
            {candidateStages.map(stage => (<option key={stage} value={stage}>{stage}</option>))}
          </select>
        </div>

        <div className="col-span-3 flex items-center gap-4 text-slate-400">
          <button
            onClick={() => {
              if (candidate.rank_id) onFavoriteToggle(candidate.rank_id);
            }}
            aria-label={candidate.favorite ? 'Unfavorite candidate' : 'Favorite candidate'}
            className="p-1"
            title={candidate.favorite ? 'Unfavorite' : 'Favorite'}
          >
            <Star
              size={18}
              className={`transition-colors ${candidate.favorite ? 'text-yellow-500 fill-yellow-500' : 'text-gray-400 hover:text-gray-600'}`}
            />
          </button>

          <button onClick={(e) => { e.preventDefault(); e.stopPropagation(); setIsRecommendOpen(true); }} title="Recommend / Send Message" className="hover:text-blue-500">
            <Send size={18} />
          </button>

          <button onClick={(e) => { e.preventDefault(); e.stopPropagation(); setIsCallOpen(true); }} title="Schedule Call" className="hover:text-green-500">
            <Phone size={18} />
          </button>

          <button className="hover:text-red-500"><Trash2 size={18} /></button>
        </div>
      </div>

      <RecommendPopup
        isOpen={isRecommendOpen}
        onClose={() => setIsRecommendOpen(false)}
        onSend={(type, selection) => {
          console.log('Recommend:', type, selection);
        }}
      />
      <CallSchedulePopup
        isOpen={isCallOpen}
        onClose={() => setIsCallOpen(false)}
        candidateName={displayName}
        onSend={(message, channel) => {
          console.log('Send message:', channel, message);
        }}
      />
    </>
  );
};

// --- Page component ---
export const PipelinePage = ({ user }: { user: User }) => {
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<'rolePipeline' | 'allCandidates'>(location.state?.defaultTab || 'rolePipeline');

  // Role Pipeline states
  const [candidates, setCandidates] = useState<PipelineDisplayCandidate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [userJds, setUserJds] = useState<JdSummary[]>([]);
  const [selectedJdId, setSelectedJdId] = useState<string>('');

  // Filters for role pipeline
  const [activeStatusFilter, setActiveStatusFilter] = useState<StatusFilter>('all');
  const [activeStageFilter, setActiveStageFilter] = useState<StageFilter>('all');
  const [showStageDropdown, setShowStageDropdown] = useState(false);

  // All Candidates states (independent)
  const [allCandidatesList, setAllCandidatesList] = useState<Candidate[]>([]);
  const [isAllCandidatesLoading, setIsAllCandidatesLoading] = useState(false);
  const [hasMoreAllCandidates, setHasMoreAllCandidates] = useState(false);
  const [allCandidatesPage, setAllCandidatesPage] = useState(1);
  const [allCandidatesFilters, setAllCandidatesFilters] = useState<{
    favorite?: boolean;
    contacted?: boolean;
    save_for_future?: boolean;
    recommended?: boolean; // ✅ Added recommended filter
  }>({});

  // Load JDs and default JD pipeline candidates (Role Pipeline)
  useEffect(() => {
    const loadJdsAndCandidates = async () => {
      setIsLoading(true);
      setActiveStatusFilter('all');
      setActiveStageFilter('all');
      setShowStageDropdown(false);
      try {
        const jds = await fetchJdsForUser();
        setUserJds(jds);

        if (jds.length > 0) {
          const defaultJdId = jds[0].jd_id;
          setSelectedJdId(defaultJdId);

          const fetchedCandidates = await getRankedCandidatesForJd(defaultJdId);
          setCandidates(fetchedCandidates.map(c => ({
            ...c,
            stage: (c.stage as CandidateStage) || 'In Consideration',
          })));
        } else {
          setCandidates([]);
        }
      } catch (error) {
        console.error("Failed to load pipeline data", error);
        setCandidates([]);
      } finally {
        setIsLoading(false);
      }
    };
    loadJdsAndCandidates();
  }, []);

  // JD selection change
  const handleJdSelectionChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newJdId = e.target.value;
    setSelectedJdId(newJdId);
    setActiveStatusFilter('all');
    setActiveStageFilter('all');
    setShowStageDropdown(false);

    if (!newJdId) {
      setCandidates([]);
      return;
    }

    setIsLoading(true);
    try {
      const fetchedCandidates = await getRankedCandidatesForJd(newJdId);
      setCandidates(fetchedCandidates.map(c => ({
        ...c,
        stage: (c.stage as CandidateStage) || 'In Consideration',
      })));
    } catch (error) {
      console.error("Failed to fetch candidates for JD", newJdId, error);
      setCandidates([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStageChange = async (id: string, newStage: CandidateStage) => {
    setCandidates(prev =>
      prev.map(c => c.rank_id === id ? { ...c, stage: newStage } : c)
    );
    try {
      await updateCandidateStage(id, newStage);
    } catch (error) {
      console.error('Failed to update stage:', error);
    }
  };

  const handleFavoriteToggle = async (rankId: string) => {
    const candidate = candidates.find(c => c.rank_id === rankId);
    if (!candidate) return;
    const oldFavorite = candidate.favorite;
    const newFavorite = !oldFavorite;
    setCandidates(prev => prev.map(c => c.rank_id === rankId ? { ...c, favorite: newFavorite } : c));

    try {
      await updateCandidateFavoriteStatus(rankId, newFavorite);
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
      setCandidates(prev => prev.map(c => c.rank_id === rankId ? { ...c, favorite: oldFavorite } : c));
    }
  };

  const favoritedCount = useMemo(() => candidates.filter(c => c.favorite).length, [candidates]);
  const contactedCount = useMemo(() => candidates.filter(c => c.contacted).length, [candidates]);

  const filteredCandidates = useMemo(() => {
    let tempCandidates = [...candidates];
    if (activeStatusFilter === 'favorite') {
      tempCandidates = tempCandidates.filter(c => c.favorite);
    } else if (activeStatusFilter === 'contacted') {
      tempCandidates = tempCandidates.filter(c => c.contacted);
    }
    if (activeStageFilter !== 'all') {
      tempCandidates = tempCandidates.filter(c => c.stage === activeStageFilter);
    }
    return tempCandidates;
  }, [candidates, activeStatusFilter, activeStageFilter]);

  const getFilterButtonClass = (isActive: boolean) => {
    return `px-3 py-1.5 rounded-md text-sm ${
      isActive ? 'bg-slate-100 font-semibold text-slate-800' : 'text-slate-600 hover:bg-slate-100'
    }`;
  };

  // --- DOWNLOAD HANDLERS ---
  const handleDownloadJdPipeline = async () => {
    if (!selectedJdId) return;
    try {
      await downloadJdPipeline(selectedJdId, {
        stage: activeStageFilter,
        favorite: activeStatusFilter === 'favorite',
        contacted: activeStatusFilter === 'contacted'
      });
    } catch (err) {
      console.error("Download failed", err);
      alert("Failed to download pipeline");
    }
  };

  const handleDownloadAllCandidates = async () => {
    try {
      await downloadAllCandidates({
        favorite: allCandidatesFilters.favorite,
        contacted: allCandidatesFilters.contacted,
        save_for_future: allCandidatesFilters.save_for_future,
        recommended: allCandidatesFilters.recommended // ✅ Include recommended filter
      });
    } catch (err) {
      console.error("Download failed", err);
      alert("Failed to download candidates");
    }
  };
  // -------------------------

  useEffect(() => {
    if (activeTab !== 'allCandidates') return;
    const loadAllCandidates = async () => {
      setIsAllCandidatesLoading(true);
      try {
        const data = await getAllRankedCandidates(allCandidatesPage, 20, {
          favorite: allCandidatesFilters.favorite,
          contacted: allCandidatesFilters.contacted,
          save_for_future: allCandidatesFilters.save_for_future,
          recommended: allCandidatesFilters.recommended, // ✅ Include recommended filter
        });

        if (allCandidatesPage === 1) {
          setAllCandidatesList(data.items);
        } else {
          setAllCandidatesList(prev => [...prev, ...data.items]);
        }
        setHasMoreAllCandidates(data.has_more);
      } catch (err) {
        console.error('Failed to load all candidates:', err);
      } finally {
        setIsAllCandidatesLoading(false);
      }
    };
    loadAllCandidates();
  }, [activeTab, allCandidatesPage, allCandidatesFilters]);

  const handleAllFilterChange = (filterKey: keyof typeof allCandidatesFilters, value: boolean | undefined) => {
    setAllCandidatesFilters(prev => {
      const newFilters = { ...prev };
      if (value === undefined) delete newFilters[filterKey];
      else newFilters[filterKey] = value;
      return newFilters;
    });
    setAllCandidatesPage(1);
  };

  const loadMoreAllCandidates = () => {
    if (!hasMoreAllCandidates || isAllCandidatesLoading) return;
    setAllCandidatesPage(prev => prev + 1);
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 font-sans">
      <Header userName={user.name || "User"} showBackButton={true}/>
      <main className="flex-grow p-8">
        <h1 className="text-3xl font-bold text-slate-800 mb-6">Candidate Pipeline</h1>
        <div className="bg-white p-6 border border-slate-200 rounded-lg shadow-sm">
          <div className="flex border-b border-slate-200 mb-6">
            <button onClick={() => setActiveTab('rolePipeline')} className={`px-1 pb-3 text-sm font-semibold ${activeTab === 'rolePipeline' ? 'text-teal-600 border-b-2 border-teal-600' : 'text-slate-500 hover:text-slate-800'}`}>Role Pipeline</button>
            <button onClick={() => { setActiveTab('allCandidates'); setAllCandidatesPage(1); }} className={`ml-6 px-1 pb-3 text-sm font-semibold ${activeTab === 'allCandidates' ? 'text-teal-600 border-b-2 border-teal-600' : 'text-slate-500 hover:text-slate-800'}`}>All Candidates</button>
          </div>

          {activeTab === 'rolePipeline' ? (
            <>
              <div className="mb-6 flex justify-between items-center gap-4">
                <select
                  value={selectedJdId}
                  onChange={handleJdSelectionChange}
                  disabled={isLoading || userJds.length === 0}
                  className="w-full max-w-xl p-2.5 border border-slate-200 rounded-md text-sm text-slate-600 focus:ring-teal-500 focus:border-teal-500 appearance-none bg-white"
                >
                  <option value="">{userJds.length > 0 ? 'Select role to view pipeline' : 'No roles found'}</option>
                  {userJds.map(jd => (
                    <option key={jd.jd_id} value={jd.jd_id}>
                      {jd.role || jd.title}
                    </option>
                  ))}
                </select>
                
                {/* --- Role Pipeline Download Button --- */}
                <button 
                  onClick={handleDownloadJdPipeline}
                  disabled={!selectedJdId}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-sm font-medium transition-colors disabled:opacity-50"
                  title="Download current filtered list as CSV"
                >
                  <Download size={16} />
                  <span>Download CSV</span>
                </button>
              </div>

              <div className="relative mb-4">
                <div className="p-1 bg-cyan-50/60 rounded-lg">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-cyan-800/50" size={18} />
                    <input type="text" placeholder="Search candidates" className="w-full pl-10 pr-4 py-2 border-none rounded-md text-sm bg-transparent focus:ring-2 focus:ring-teal-500 text-cyan-900 placeholder:text-cyan-800/50" />
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 border-b border-slate-200 pb-3 mb-3 text-sm">
                <button
                  className={getFilterButtonClass(activeStatusFilter === 'all')}
                  onClick={() => { setActiveStatusFilter('all'); }}
                >
                  All
                </button>
                <button
                  className={getFilterButtonClass(activeStatusFilter === 'favorite')}
                  onClick={() => { setActiveStatusFilter('favorite'); }}
                >
                  Favourited ({favoritedCount})
                </button>
                <button
                  className={getFilterButtonClass(activeStatusFilter === 'contacted')}
                  onClick={() => { setActiveStatusFilter('contacted'); }}
                >
                  Contacted ({contactedCount})
                </button>

                <div className="relative">
                  <button
                    className={getFilterButtonClass(activeStageFilter !== 'all') + ' flex items-center gap-1'}
                    onClick={() => setShowStageDropdown(prev => !prev)}
                  >
                    {activeStageFilter !== 'all' ? activeStageFilter : 'Stage'}
                    <ChevronDown size={16}/>
                  </button>

                  {showStageDropdown && (
                    <div className="absolute top-full left-0 mt-1.5 w-48 bg-white border border-slate-200 rounded-md shadow-lg z-10 py-1">
                      <button
                        className={`w-full text-left px-3 py-1.5 text-sm ${activeStageFilter === 'all' ? 'bg-teal-50 text-teal-700 font-semibold' : 'text-slate-700 hover:bg-slate-50'}`}
                        onClick={() => { setActiveStageFilter('all'); setShowStageDropdown(false); }}
                      >
                        All Stages
                      </button>
                      {candidateStages.map(stage => (
                        <button
                          key={stage}
                          className={`w-full text-left px-3 py-1.5 text-sm ${activeStageFilter === stage ? 'bg-teal-50 text-teal-700 font-semibold' : 'text-slate-700 hover:bg-slate-50'}`}
                          onClick={() => { setActiveStageFilter(stage); setShowStageDropdown(false); }}
                        >
                          {stage}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="candidates-table">
                <div className="grid grid-cols-12 text-xs font-semibold text-slate-600 uppercase py-3 px-2 bg-slate-50 border-b border-slate-200">
                  <div className="col-span-1"></div>
                  <div className="col-span-4">Name</div>
                  <div className="col-span-2">Status</div>
                  <div className="col-span-2">Stage</div>
                  <div className="col-span-3">Actions</div>
                </div>
                <div className="max-h-[60vh] overflow-y-auto">
                  {isLoading ? (
                    <p className="text-center py-8 text-slate-500">Loading candidates...</p>
                  ) : candidates.length === 0 ? (
                    <p className="text-center py-8 text-slate-500">No candidates found for this role.</p>
                  ) : filteredCandidates.length === 0 ? (
                    <p className="text-center py-8 text-slate-500">No candidates match the current filters.</p>
                  ) : (
                    filteredCandidates.map(candidate => (
                      <PipelineCandidateRow
                        key={candidate.rank_id}
                        candidate={candidate}
                        onStageChange={handleStageChange}
                        onFavoriteToggle={handleFavoriteToggle}
                      />
                    ))
                  )}
                </div>
              </div>

              <div className="mt-6 flex items-center justify-between">
                <div className="flex gap-2">
                  <button className="px-4 py-2 bg-teal-600 text-white font-semibold rounded-md text-sm hover:bg-teal-700">Contact Selected</button>
                  <button className="px-4 py-2 bg-white border border-slate-300 font-semibold rounded-md text-sm text-slate-700 hover:bg-slate-50">Save Selected for Future</button>
                  <button className="px-4 py-2 bg-white border border-slate-300 font-semibold rounded-md text-sm text-slate-700 hover:bg-slate-50">Remove Selected</button>
                </div>
                <button className="px-4 py-2 bg-teal-600 text-white font-semibold rounded-md text-sm hover:bg-teal-700">Search More Candidates</button>
              </div>
            </>
          ) : (
            <>
              <div className="mb-4 flex justify-between items-center gap-4">
                 <div className="relative flex-grow">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    type="text"
                    placeholder="Search candidates"
                    className="w-full pl-10 pr-4 py-2.5 bg-slate-100 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 text-slate-900 placeholder:text-slate-500"
                  />
                </div>
                {/* --- All Candidates Download Button --- */}
                <button 
                  onClick={handleDownloadAllCandidates}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-sm font-medium transition-colors"
                  title="Download all candidates matching filters as CSV"
                >
                  <Download size={16} />
                  <span>Download CSV</span>
                </button>
              </div>

              <div className="flex items-center gap-2 border-b border-slate-200 pb-3 mb-3 text-sm">
                <button
                  className="px-3 py-1.5 rounded-md bg-slate-100 font-semibold text-slate-800"
                  onClick={() => { setAllCandidatesFilters({}); setAllCandidatesPage(1); }}
                >
                  All
                </button>
                <button
                  className={getFilterButtonClass(!!allCandidatesFilters.favorite)}
                  onClick={() => handleAllFilterChange('favorite', allCandidatesFilters.favorite ? undefined : true)}
                >
                  Favourited
                </button>
                <button
                  className={getFilterButtonClass(!!allCandidatesFilters.contacted)}
                  onClick={() => handleAllFilterChange('contacted', allCandidatesFilters.contacted ? undefined : true)}
                >
                  Contacted
                </button>
                <button
                  className={getFilterButtonClass(!!allCandidatesFilters.save_for_future)}
                  onClick={() => handleAllFilterChange('save_for_future', allCandidatesFilters.save_for_future ? undefined : true)}
                >
                  Saved for future
                </button>
                <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100">Recommended to you</button>
                
                {/* ✅ Updated: Wired up 'You recommended' button */}
                <button 
                  className={getFilterButtonClass(!!allCandidatesFilters.recommended)}
                  onClick={() => handleAllFilterChange('recommended', allCandidatesFilters.recommended ? undefined : true)}
                >
                  You recommended
                </button>
              </div>
              <div className="candidates-table">
                <div className="grid grid-cols-12 text-xs font-semibold text-slate-600 uppercase py-3 px-2 bg-slate-50 border-b border-slate-200">
                  <div className="col-span-1"></div>
                  <div className="col-span-4">Name</div>
                  <div className="col-span-2">Status</div>
                  <div className="col-span-2">Tagged Role</div>
                  <div className="col-span-1">Profile Link</div>
                  <div className="col-span-2">Actions</div>
                </div>
                <div className="max-h-[60vh] overflow-y-auto">
                  {isAllCandidatesLoading && allCandidatesPage === 1 ? (
                    <p className="text-center py-8 text-slate-500">Loading candidates...</p>
                  ) : allCandidatesList.length === 0 ? (
                    <p className="text-center py-8 text-slate-500">No candidates found.</p>
                  ) : (
                    allCandidatesList.map(candidate => (
                      <AllCandidatesRow key={candidate.rank_id} candidate={candidate} />
                    ))
                  )}
                </div>
              </div>

              {hasMoreAllCandidates && (
                <div className="flex justify-center mt-4">
                  <button
                    onClick={loadMoreAllCandidates}
                    disabled={isAllCandidatesLoading}
                    className="px-4 py-2 bg-teal-600 text-white font-semibold rounded-md text-sm hover:bg-teal-700 disabled:opacity-50"
                  >
                    {isAllCandidatesLoading ? 'Loading...' : 'Load More'}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
};