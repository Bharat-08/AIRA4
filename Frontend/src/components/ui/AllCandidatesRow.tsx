// src/components/ui/AllCandidatesRow.tsx
import React, { useState } from 'react';
import type { Candidate } from '../../types/candidate';
import { Link, Trash2, Send, CornerUpRight, Star } from 'lucide-react';

interface AllCandidatesRowProps {
  candidate: Candidate;
  /**
   * Called when user toggles favorite.
   * signature: (candidateId, source, newFavorite) => Promise<void> | void
   */
  onToggleFavorite?: (
    candidateId: string,
    source: 'ranked_candidates' | 'ranked_candidates_from_resume',
    favorite: boolean
  ) => void;
  /**
   * Which backend table this row corresponds to. Default is ranked_candidates.
   * If your list comes from resume uploads use 'ranked_candidates_from_resume'.
   */
  source?: 'ranked_candidates' | 'ranked_candidates_from_resume';
}

const getStatusPillClass = (status: string) => {
  switch (status?.toLowerCase?.()) {
    case 'saved for future':
      return 'bg-blue-100 text-blue-800';
    case 'recommended':
      return 'bg-green-100 text-green-800';
    case 'contacted for ux designer':
      return 'bg-purple-100 text-purple-800';
    default:
      return 'bg-slate-100 text-slate-700';
  }
};

export const AllCandidatesRow: React.FC<AllCandidatesRowProps> = ({
  candidate,
  onToggleFavorite,
  source = 'ranked_candidates',
}) => {
  // Use local state for immediate UI responsiveness (optimistic)
  const [isFav, setIsFav] = useState<boolean>(!!(candidate as any).favorite);

  const avatarInitial = (candidate.profile_name || (candidate as any).name || '')
    .split(' ')
    .map((n) => (n ? n[0] : ''))
    .join('')
    .toUpperCase();

  const handleFavoriteClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const newVal = !isFav;
    // optimistic update
    setIsFav(newVal);

    try {
      if (onToggleFavorite) {
        await onToggleFavorite(candidate.profile_id || (candidate as any).resume_id, source, newVal);
      }
    } catch (err) {
      // rollback on error
      setIsFav(!newVal);
      console.warn('Failed to toggle favorite', err);
    }
  };

  return (
    <div className="grid grid-cols-12 items-center py-3 px-2 border-b border-slate-100 text-sm hover:bg-slate-50 transition-colors">
      <div className="col-span-1 flex justify-center">
        <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
      </div>

      <div className="col-span-3 flex items-center gap-3">
        <div className="w-9 h-9 flex-shrink-0 flex items-center justify-center bg-slate-200 text-slate-600 rounded-full font-bold text-xs">
          {avatarInitial || 'NA'}
        </div>
        <div>
          <p className="font-bold text-slate-800">{candidate.profile_name || (candidate as any).name || 'Unknown'}</p>
          <p className="text-slate-500 text-xs">{candidate.company || (candidate as any).company || ''}</p>
        </div>
      </div>

      <div className="col-span-2">
        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusPillClass((candidate as any).status || '')}`}>
          {(candidate as any).status || ''}
        </span>
      </div>

      <div className="col-span-2">
        <span className="px-2 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-700">
          {candidate.role || (candidate as any).role || ''}
        </span>
      </div>

      <div className="col-span-1">
        <a href={candidate.profile_url || candidate.linkedin_url || '#'} className="text-slate-400 hover:text-teal-600" target="_blank" rel="noreferrer">
          <Link size={18} />
        </a>
      </div>

      <div className="col-span-3 flex items-center gap-4 text-slate-400 justify-end">
        {/* Favorite / Star */}
        <button
          onClick={handleFavoriteClick}
          aria-pressed={isFav}
          title={isFav ? 'Unfavorite' : 'Favorite'}
          className="p-1 rounded hover:bg-slate-100 transition-colors"
        >
          {/* Use stroke color change to indicate state; lucide star is outline but will look good */}
          <Star size={18} className={isFav ? 'text-yellow-400' : 'text-slate-400'} />
        </button>

        <button className="hover:text-red-500" title="Delete"><Trash2 size={18} /></button>
        <button className="hover:text-blue-500" title="Send"><Send size={18} /></button>
        <button className="hover:text-green-500" title="Open"><CornerUpRight size={18} /></button>
      </div>
    </div>
  );
};
