// src/components/ui/PipelineCandidateRow.tsx
import { Link, Star, Send, Phone, Trash2 } from 'lucide-react';
import React from 'react';
// MODIFIED: Imported new types
import type { PipelineCandidate, CandidateStage } from '../../types/candidate';
import { candidateStages } from '../../types/candidate';


interface PipelineCandidateRowProps {
  candidate: PipelineCandidate;
  // ADDED: Prop to handle stage changes
  onStageChange: (id: string, newStage: CandidateStage) => void;
}

// A helper to determine badge color based on status
const getStatusBadgeClass = (status: PipelineCandidate['status']) => {
  switch (status) {
    case 'Favourited':
      return 'bg-yellow-100 text-yellow-800';
    case 'Contacted':
      return 'bg-blue-100 text-blue-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
};

export function PipelineCandidateRow({ candidate, onStageChange }: PipelineCandidateRowProps) {
  const avatarInitial = candidate.name.split(' ').map(n => n[0]).join('');

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onStageChange(candidate.id, e.target.value as CandidateStage);
  };

  return (
    <div className="grid grid-cols-12 items-center py-3 border-b border-slate-100 text-sm">
      <div className="col-span-1 flex justify-center">
        <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
      </div>

      <div className="col-span-4 flex items-center gap-3">
        <div className="w-9 h-9 flex-shrink-0 flex items-center justify-center bg-slate-200 text-slate-600 rounded-full font-semibold text-xs">
          {avatarInitial}
        </div>
        <div>
          <p className="font-semibold text-slate-800">{candidate.name}</p>
          <p className="text-slate-500">{`${candidate.role} at ${candidate.company}`}</p>
        </div>
      </div>

      <div className="col-span-2">
        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusBadgeClass(candidate.status)}`}>
          {candidate.status}
        </span>
      </div>

      <div className="col-span-1">
        <a href="#" className="text-slate-500 hover:text-teal-600">
            <Link size={18} />
        </a>
      </div>

      {/* MODIFIED: This is now an interactive dropdown */}
      <div className="col-span-2">
        <select
          value={candidate.stage}
          onChange={handleSelectChange}
          className="w-full p-1 border-gray-300 rounded-md bg-slate-100 text-slate-700 text-sm focus:ring-2 focus:ring-teal-500 text-left"
        >
          {candidateStages.map(stage => (
            <option key={stage} value={stage}>{stage}</option>
          ))}
        </select>
      </div>

      <div className="col-span-2 flex items-center gap-4 text-slate-500">
        <button className="hover:text-yellow-500"><Star size={18} /></button>
        <button className="hover:text-blue-500"><Send size={18} /></button>
        <button className="hover:text-green-500"><Phone size={18} /></button>
        <button className="hover:text-red-500"><Trash2 size={18} /></button>
      </div>
    </div>
  );
}