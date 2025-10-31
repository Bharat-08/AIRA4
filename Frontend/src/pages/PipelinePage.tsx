import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Header } from '../components/layout/Header';
import { Search, ChevronDown, Link, Star, Send, Phone, Trash2, ArrowRight } from 'lucide-react';
import type { User } from '../types/user';

// --- NEW IMPORTS ---
import { getRankedCandidatesForJd, updateCandidateStage, updateCandidateFavoriteStatus } from '../api/pipeline';
import { fetchJdsForUser, type JdSummary } from '../api/roles';
import { candidateStages, type Candidate, type CandidateStage } from '../types/candidate';

// A type for our local state, combining backend data + local UI stage
type PipelineDisplayCandidate = Candidate & { stage: CandidateStage };

// --- "All Candidates" Row ---
const AllCandidatesRow: React.FC<{ candidate: Candidate }> = ({ candidate }) => {
  const avatarInitial = candidate.profile_name?.split(' ').map(n => n[0]).join('').toUpperCase() || '??';

  const getStatusDisplay = (candidate: Candidate) => {
    if (candidate.favorite) return 'Favourited';
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
          <p className="font-bold text-slate-800">{candidate.profile_name || 'N/A'}</p>
          <p className="text-slate-500">{`${candidate.role || 'N/A'} at ${candidate.company || 'N/A'}`}</p>
        </div>
      </div>
      <div className="col-span-2 text-slate-600">{getStatusDisplay(candidate)}</div>
      <div className="col-span-2 text-slate-600">{candidate.role || 'N/A'}</div>
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

// --- "Role Pipeline" Row (now accepts favorite handler) ---
const PipelineCandidateRow: React.FC<{
  candidate: PipelineDisplayCandidate;
  onStageChange: (id: string, newStage: CandidateStage) => void;
  onFavoriteToggle: (profileId: string) => void;
}> = ({ candidate, onStageChange, onFavoriteToggle }) => {
  const avatarInitial = candidate.profile_name?.split(' ').map(n => n[0]).join('').toUpperCase() || '??';

  const getStatusText = (candidate: Candidate) => {
    return candidate.favorite ? 'Favourited' : 'In Pipeline';
  };

  const getStatusTextClass = (candidate: Candidate) => {
    return candidate.favorite ? 'text-yellow-600 font-semibold' : 'text-gray-600';
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
          <p className="font-bold text-slate-800">{candidate.profile_name || 'N/A'}</p>
          <p className="text-slate-500">{`${candidate.role || 'N/A'} at ${candidate.company || 'N/A'}`}</p>
        </div>
      </div>

      <div className="col-span-2">
        <span className={`text-xs ${getStatusTextClass(candidate)}`}>{getStatusText(candidate)}</span>
      </div>

      <div className="col-span-1">
        <a href={candidate.linkedin_url || '#'} target="_blank" rel="noopener noreferrer" className="text-slate-400 hover:text-teal-600">
          <Link size={18} />
        </a>
      </div>

      <div className="col-span-2">
        <select
          value={candidate.stage}
          onChange={(e) => onStageChange(candidate.profile_id, e.target.value as CandidateStage)}
          className="w-full p-1.5 border-none rounded-md bg-slate-100 text-slate-700 text-xs focus:ring-2 focus:ring-teal-500 appearance-none text-left"
        >
          {candidateStages.map(stage => (<option key={stage} value={stage}>{stage}</option>))}
        </select>
      </div>

      <div className="col-span-2 flex items-center gap-4 text-slate-400">
        {/* Favorite star */}
        <button
          onClick={() => onFavoriteToggle(candidate.profile_id)}
          aria-label={candidate.favorite ? 'Unfavorite candidate' : 'Favorite candidate'}
          className="p-1"
          title={candidate.favorite ? 'Unfavorite' : 'Favorite'}
        >
          <Star
            size={18}
            className={`transition-colors ${candidate.favorite ? 'text-yellow-500 fill-yellow-500' : 'text-gray-400 hover:text-gray-600'}`}
          />
        </button>

        <button className="hover:text-blue-500"><Send size={18} /></button>
        <button className="hover:text-green-500"><Phone size={18} /></button>
        <button className="hover:text-red-500"><Trash2 size={18} /></button>
      </div>
    </div>
  );
};

export const PipelinePage = ({ user }: { user: User }) => {
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<'rolePipeline' | 'allCandidates'>(location.state?.defaultTab || 'rolePipeline');
  const [candidates, setCandidates] = useState<PipelineDisplayCandidate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [userJds, setUserJds] = useState<JdSummary[]>([]);
  const [selectedJdId, setSelectedJdId] = useState<string>('');

  // Load JDs and candidates
  useEffect(() => {
    const loadJdsAndCandidates = async () => {
      setIsLoading(true);
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
        }
      } catch (error) {
        console.error("Failed to load pipeline data", error);
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

  // Stage change (calls backend)
  const handleStageChange = async (id: string, newStage: CandidateStage) => {
    // optimistic UI update
    setCandidates(prev =>
      prev.map(c => c.profile_id === id ? { ...c, stage: newStage } : c)
    );

    try {
      const candidate = candidates.find(c => c.profile_id === id);
      if (!candidate?.rank_id) return;
      await updateCandidateStage(candidate.rank_id, newStage);
      console.log(`Stage updated successfully for ${id}`);
    } catch (error) {
      console.error('Failed to update stage:', error);
      // optionally revert: refetch or restore previous state
    }
  };

  // Favorite toggle (uses existing backend API)
  // Favorite toggle (uses existing backend API)
const handleFavoriteToggle = async (profileId: string) => {
  // find candidate by profile_id
  const candidate = candidates.find(c => c.profile_id === profileId);
  if (!candidate) return;

  const oldFavorite = candidate.favorite;
  const newFavorite = !oldFavorite;

  // Optimistic UI update
  setCandidates(prev => prev.map(c => c.profile_id === profileId ? { ...c, favorite: newFavorite } : c));

  try {
    // IMPORTANT: the favorites endpoint expects the candidate_id to be the profile_id
    // (not the ranked_candidates.rank_id). So pass profile_id and source 'ranked_candidates'.
    await updateCandidateFavoriteStatus(profileId, newFavorite);
    console.log(`Favorite toggled for ${profileId}: ${newFavorite}`);
  } catch (err) {
    console.error('Failed to toggle favorite:', err);
    // Roll back optimistic change on failure
    setCandidates(prev => prev.map(c => c.profile_id === profileId ? { ...c, favorite: oldFavorite } : c));
  }
};


  return (
    <div className="flex flex-col min-h-screen bg-slate-50 font-sans">
      <Header userName={user.name || "User"} showBackButton={true}/>
      <main className="flex-grow p-8">
        <h1 className="text-3xl font-bold text-slate-800 mb-6">Candidate Pipeline</h1>
        <div className="bg-white p-6 border border-slate-200 rounded-lg shadow-sm">
          <div className="flex border-b border-slate-200 mb-6">
            <button onClick={() => setActiveTab('rolePipeline')} className={`px-1 pb-3 text-sm font-semibold ${activeTab === 'rolePipeline' ? 'text-teal-600 border-b-2 border-teal-600' : 'text-slate-500 hover:text-slate-800'}`}>Role Pipeline</button>
            <button onClick={() => setActiveTab('allCandidates')} className={`ml-6 px-1 pb-3 text-sm font-semibold ${activeTab === 'allCandidates' ? 'text-teal-600 border-b-2 border-teal-600' : 'text-slate-500 hover:text-slate-800'}`}>All Candidates</button>
          </div>
          
          {activeTab === 'rolePipeline' ? (
             <>
               <div className="mb-6">
                 <select 
                   value={selectedJdId}
                   onChange={handleJdSelectionChange}
                   disabled={isLoading || userJds.length === 0}
                   className="w-full p-2.5 border border-slate-200 rounded-md text-sm text-slate-600 focus:ring-teal-500 focus:border-teal-500 appearance-none bg-white"
                 >
                   <option value="">{userJds.length > 0 ? 'Select role to view pipeline' : 'No roles found'}</option>
                   {userJds.map(jd => (
                     <option key={jd.jd_id} value={jd.jd_id}>
                       {jd.role || jd.title}
                     </option>
                   ))}
                 </select>
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
                 <button className="px-3 py-1.5 rounded-md bg-slate-100 font-semibold text-slate-800">All</button>
                 <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100">Favourited (5)</button>
                 <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100">Contacted (5)</button>
                 <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100 flex items-center gap-1">Stage <ChevronDown size={16}/></button>
               </div>
               <div className="candidates-table">
                 <div className="grid grid-cols-12 text-xs font-semibold text-slate-600 uppercase py-3 px-2 bg-slate-50 border-b border-slate-200">
                   <div className="col-span-1"></div><div className="col-span-4">Name</div><div className="col-span-2">Status</div><div className="col-span-1">Profile Link</div><div className="col-span-2">Stage</div><div className="col-span-2">Actions</div>
                 </div>
                 <div className="max-h-[60vh] overflow-y-auto">
                   {isLoading ? (<p className="text-center py-8 text-slate-500">Loading candidates...</p>) : (
                     candidates.length === 0 ? (
                       <p className="text-center py-8 text-slate-500">No candidates found for this role.</p>
                     ) : (
                       candidates.map(candidate => (
                         <PipelineCandidateRow 
                           key={candidate.profile_id} 
                           candidate={candidate} 
                           onStageChange={handleStageChange}
                           onFavoriteToggle={handleFavoriteToggle}
                         />
                       ))
                     )
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
              <div className="relative mb-4">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input 
                  type="text" 
                  placeholder="Search candidates" 
                  className="w-full pl-10 pr-4 py-2.5 bg-slate-100 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 text-slate-900 placeholder:text-slate-500" 
                />
              </div>
              <div className="flex items-center gap-2 border-b border-slate-200 pb-3 mb-3 text-sm">
                <button className="px-3 py-1.5 rounded-md bg-slate-100 font-semibold text-slate-800">All</button>
                <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100">Favourited</button>
                <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100">Contacted</button>
                <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100">Saved for future</button>
                <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100">Recommended to you</button>
                <button className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100 border border-blue-200 text-blue-600 bg-blue-50">You recommended</button>
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
                  {isLoading ? (<p className="text-center py-8 text-slate-500">Loading candidates...</p>) : (
                    candidates.length === 0 ? (
                      <p className="text-center py-8 text-slate-500">No candidates found for this role.</p>
                    ) : (
                      candidates.map(candidate => (
                        <AllCandidatesRow key={candidate.profile_id} candidate={candidate}/>
                      ))
                    )
                  )}
                </div>
              </div>
              <div className="mt-6 flex items-center justify-between">
                  <div className="flex gap-2">
                    <button className="px-4 py-2 bg-white border border-slate-300 font-semibold rounded-md text-sm text-slate-700 hover:bg-slate-50">Remove Selected</button>
                  </div>
                  <button className="px-4 py-2 bg-teal-600 text-white font-semibold rounded-md text-sm hover:bg-teal-700">Search More Candidates</button>
               </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
};
