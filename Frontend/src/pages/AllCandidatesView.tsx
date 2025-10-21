// src/pages/AllCandidatesView.tsx
import React from 'react';
import type { Candidate } from '../types/candidate';
import { AllCandidatesRow } from '../components/ui/AllCandidatesRow';

interface AllCandidatesViewProps {
  candidates: Candidate[];
  isLoading: boolean;
}

export const AllCandidatesView: React.FC<AllCandidatesViewProps> = ({ candidates, isLoading }) => {
  return (
    <div className="candidates-table mt-4">
      {/* Table Header */}
      <div className="grid grid-cols-12 text-xs font-semibold text-slate-500 uppercase py-3 px-2 border-b-2 border-slate-200">
        <div className="col-span-1"></div>
        <div className="col-span-3">Name</div>
        <div className="col-span-2">Status</div>
        <div className="col-span-2">Tagged Role</div>
        <div className="col-span-1">Profile Link</div>
        <div className="col-span-3">Actions</div>
      </div>
      
      {/* Scrollable Table Body */}
      <div className="max-h-[60vh] overflow-y-auto">
        {isLoading ? (
          <p className="text-center py-8 text-slate-500">Loading candidates...</p>
        ) : (
          candidates.map(candidate => (
            <AllCandidatesRow key={candidate.id} candidate={candidate} />
          ))
        )}
      </div>
    </div>
  );
};