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
  useEffect(() => {
    console.log('[AllCandidatesRow] mounted:', (candidate as any).profile_id || (candidate as any).profile_name);
  }, [candidate]);

  const [isFav, setIsFav] = useState<boolean>(!!(candidate as any).favorite);
  const [isSaved, setIsSaved] = useState<boolean>(!!(candidate as any).saved);

  const displayName =
    (candidate as any).profile_name ||
    (candidate as any).person_name ||
    (candidate as any).name ||
    (candidate as any).full_name ||
    'Unknown';

  const displayCompany =
    (candidate as any).company ||
    (candidate as any).current_company ||
    (candidate as any).organization_name ||
    (candidate as any).organization ||
    '';

  const displayRole =
    (candidate as any).role ||
    (candidate as any).current_title ||
    (candidate as any).title ||
    '';

  const profileId =
    (candidate as any).profile_id ||
    (candidate as any).resume_id ||
    (candidate as any).id ||
    '';

  const avatarInitial =
    displayName
      .split(' ')
      .map((n) => (n ? n[0] : ''))
      .join('')
      .toUpperCase() || 'NA';

  const handleFavoriteClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!profileId) return;

    const newVal = !isFav;
    setIsFav(newVal);
    try {
      if (onToggleFavorite) {
        await onToggleFavorite(String(profileId), source, newVal);
      }
    } catch (err) {
      setIsFav(!newVal);
      console.warn('Failed to toggle favorite', err);
    }
  };

  const handleSaveClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsSaved((prev) => !prev);
  };

  return (
    <div className="grid grid-cols-12 items-center py-3 px-2 border-b border-slate-100 text-sm hover:bg-slate-50 transition-colors">
      <div className="col-span-1 flex justify-center">
        <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
      </div>

      <div className="col-span-3 flex items-center gap-3">
        <div className="w-9 h-9 flex-shrink-0 flex items-center justify-center bg-slate-200 text-slate-600 rounded-full font-bold text-xs">
          {avatarInitial}
        </div>
        <div>
          <p className="font-bold text-slate-800">{displayName}</p>
          <p className="text-slate-500 text-xs">{displayCompany}</p>
        </div>
      </div>

      <div className="col-span-2">
        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusPillClass((candidate as any).status || '')}`}>
          {(candidate as any).status || ''}
        </span>
      </div>

      <div className="col-span-2">
        <span className="px-2 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-700">
          {displayRole}
        </span>
      </div>

      <div className="col-span-1">
        <a
          href={(candidate as any).profile_url || (candidate as any).validated_url || (candidate as any).linkedin_url || '#'}
          className="text-slate-400 hover:text-teal-600"
          target="_blank"
          rel="noreferrer"
        >
          <Link size={18} />
        </a>
      </div>

      <div className="col-span-4 flex items-center gap-6 text-slate-400 justify-end pr-2 min-w-[200px]">
        <button
          data-qa="action-save"
          onClick={handleSaveClick}
          title={isSaved ? 'Unsave Candidate' : 'Save Candidate'}
          className="px-3 py-1 rounded-md bg-red-500 text-white text-sm font-semibold hover:bg-red-600"
        >
          SAVE
        </button>

        <button
          data-qa="action-bookmark"
          onClick={handleSaveClick}
          title={isSaved ? 'Unsave Candidate' : 'Save Candidate'}
          className="p-2 rounded hover:bg-slate-100 transition-colors"
          aria-pressed={isSaved}
        >
          <Bookmark size={20} strokeWidth={1.6} className={isSaved ? 'text-blue-600' : 'text-slate-400'} />
        </button>

        <button
          data-qa="action-fav"
          onClick={handleFavoriteClick}
          aria-pressed={isFav}
          title={isFav ? 'Unfavorite' : 'Favorite'}
          className="p-2 rounded hover:bg-slate-100 transition-colors"
        >
          <Star size={20} strokeWidth={1.6} className={isFav ? 'text-yellow-400' : 'text-slate-400'} />
        </button>

        <button data-qa="action-delete" className="p-2 rounded hover:bg-slate-100 transition-colors" title="Delete">
          <Trash2 size={18} />
        </button>

        <button data-qa="action-send" className="p-2 rounded hover:bg-slate-100 transition-colors" title="Send">
          <Send size={18} />
        </button>

        <button data-qa="action-open" className="p-2 rounded hover:bg-slate-100 transition-colors" title="Open">
          <CornerUpRight size={18} />
        </button>
      </div>
    </div>
  );
};
