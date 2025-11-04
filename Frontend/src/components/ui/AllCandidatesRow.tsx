// src/components/ui/AllCandidatesRow.tsx
import React, { useEffect, useState } from 'react';
import type { Candidate } from '../../types/candidate';
import { Link, Trash2, Send, CornerUpRight, Star, Bookmark } from 'lucide-react';

interface AllCandidatesRowProps {
  candidate: Candidate;
  onToggleFavorite?: (
    candidateId: string,
    source: 'ranked_candidates' | 'ranked_candidates_from_resume',
    favorite: boolean
  ) => void;
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
  // debug log to ensure file loaded
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.log('[AllCandidatesRow] mounted for candidate:', candidate?.profile_id || candidate?.profile_name);
  }, [candidate]);

  const [isFav, setIsFav] = useState<boolean>(!!(candidate as any).favorite);
  const [isSaved, setIsSaved] = useState<boolean>(!!(candidate as any).saved);

  const avatarInitial = (candidate.profile_name || (candidate as any).name || '')
    .split(' ')
    .map((n) => (n ? n[0] : ''))
    .join('')
    .toUpperCase();

  const handleFavoriteClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const newVal = !isFav;
    setIsFav(newVal);

    try {
      if (onToggleFavorite) {
        await onToggleFavorite(candidate.profile_id || (candidate as any).resume_id, source, newVal);
      }
    } catch (err) {
      setIsFav(!newVal);
      // eslint-disable-next-line no-console
      console.warn('Failed to toggle favorite', err);
    }
  };

  const handleSaveClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsSaved((prev) => !prev);
    // eslint-disable-next-line no-console
    console.log('[AllCandidatesRow] save toggled', candidate?.profile_id, !isSaved);
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
        <a
          href={candidate.profile_url || candidate.linkedin_url || '#'}
          className="text-slate-400 hover:text-teal-600"
          target="_blank"
          rel="noreferrer"
        >
          <Link size={18} />
        </a>
      </div>

      {/* ACTIONS COLUMN */}
      <div className="col-span-4 flex items-center gap-6 text-slate-400 justify-end pr-2 min-w-[200px]">
        {/* DEBUG visible Save pill — extremely visible, red background */}
        <button
          data-qa="action-save"
          onClick={handleSaveClick}
          title={isSaved ? 'Unsave Candidate' : 'Save Candidate'}
          className="px-3 py-1 rounded-md bg-red-500 text-white text-sm font-semibold hover:bg-red-600"
        >
          SAVE
        </button>

        {/* Bookmark icon (also present) */}
        <button
          data-qa="action-bookmark"
          onClick={handleSaveClick}
          title={isSaved ? 'Unsave Candidate' : 'Save Candidate'}
          className="p-2 rounded hover:bg-slate-100 transition-colors"
          aria-pressed={isSaved}
        >
          <Bookmark
            size={20}
            strokeWidth={1.6}
            className={isSaved ? 'text-blue-600' : 'text-slate-400'}
          />
        </button>

        {/* Favorite / Star */}
        <button
          data-qa="action-fav"
          onClick={handleFavoriteClick}
          aria-pressed={isFav}
          title={isFav ? 'Unfavorite' : 'Favorite'}
          className="p-2 rounded hover:bg-slate-100 transition-colors"
        >
          <Star
            size={20}
            strokeWidth={1.6}
            className={isFav ? 'text-yellow-400' : 'text-slate-400'}
          />
        </button>

        {/* Delete */}
        <button data-qa="action-delete" className="p-2 rounded hover:bg-slate-100 transition-colors" title="Delete">
          <Trash2 size={18} />
        </button>

        {/* Send */}
        <button data-qa="action-send" className="p-2 rounded hover:bg-slate-100 transition-colors" title="Send">
          <Send size={18} />
        </button>

        {/* Open / Call */}
        <button data-qa="action-open" className="p-2 rounded hover:bg-slate-100 transition-colors" title="Open">
          <CornerUpRight size={18} />
        </button>
      </div>
    </div>
  );
};
