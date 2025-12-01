import React from 'react';
import { Trash2, Search } from 'lucide-react';
import type { Candidate } from '../types/candidate';
import { AllCandidatesRow } from '../components/ui/AllCandidatesRow';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';

interface AllCandidatesViewProps {
  candidates: Candidate[];
  isLoading: boolean;
  hasMore: boolean;
  loadMore: () => void;
  onSearchMore?: () => void;
  onRemoveSelected?: () => void; // Placeholder for future implementation
}

export const AllCandidatesView: React.FC<AllCandidatesViewProps> = ({ 
  candidates, 
  isLoading, 
  hasMore,
  loadMore,
  onSearchMore,
  onRemoveSelected
}) => {
  // Setup the infinite scroll trigger
  const triggerRef = useInfiniteScroll(loadMore, isLoading, hasMore);

  const handleSearchClick = () => {
    if (onSearchMore) {
      onSearchMore();
    } else {
      window.open('/search', '_blank');
    }
  };

  return (
    <div className="flex flex-col h-full mt-4">
      {/* Header Actions */}
      <div className="flex justify-between items-center mb-4 px-1">
        <button 
          onClick={onRemoveSelected}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-red-200 text-red-600 hover:bg-red-50 rounded-md text-sm font-medium transition-colors shadow-sm"
          title="Remove Selected Candidates"
        >
          <Trash2 size={16} />
          Remove Selected
        </button>

        <button 
          onClick={handleSearchClick}
          className="flex items-center gap-2 px-4 py-2 bg-teal-600 text-white hover:bg-teal-700 rounded-md text-sm font-medium transition-colors shadow-sm"
        >
          <Search size={16} />
          Search for More Candidates
        </button>
      </div>

      {/* Candidates Table Container */}
      <div className="candidates-table bg-white rounded-lg border border-slate-200 flex-1 flex flex-col min-h-0 shadow-sm">
        {/* Table Header */}
        <div className="grid grid-cols-12 text-xs font-semibold text-slate-500 uppercase py-3 px-2 border-b border-slate-200 bg-slate-50 rounded-t-lg">
          <div className="col-span-1 text-center">
            {/* Future: Global Select Checkbox */}
          </div>
          <div className="col-span-3">Name</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-2">Tagged Role</div>
          <div className="col-span-1">Profile Link</div>
          <div className="col-span-3 text-right pr-4">Actions</div>
        </div>
        
        {/* Scrollable List Body */}
        <div className="overflow-y-auto flex-1">
          {candidates.length === 0 && !isLoading ? (
            <div className="text-center py-12 text-slate-400">
              No candidates found.
            </div>
          ) : (
            candidates.map((candidate) => (
              <AllCandidatesRow 
                key={candidate.rank_id || candidate.id || Math.random().toString()} 
                candidate={candidate} 
              />
            ))
          )}

          {/* Infinite Scroll Sentinel / Loader */}
          {hasMore && (
            <div ref={triggerRef} className="py-6 flex justify-center items-center w-full">
              {isLoading ? (
                <div className="flex flex-col items-center gap-2">
                  <div className="w-5 h-5 border-2 border-teal-600 border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-xs text-slate-500 font-medium">Loading more candidates...</span>
                </div>
              ) : (
                <div className="h-1 w-full" /> /* Invisible trigger target */
              )}
            </div>
          )}
          
          {!hasMore && candidates.length > 0 && (
            <div className="py-6 text-center text-slate-400 text-xs uppercase tracking-wider border-t border-slate-50">
              End of list
            </div>
          )}
        </div>
      </div>
    </div>
  );
};