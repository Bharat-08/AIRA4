// Frontend/src/components/ui/PipelineCandidateRow.tsx
import React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Star, Linkedin } from 'lucide-react';
import type { Candidate, CandidateStage } from '../../types/candidate';
import { candidateStages } from '../../types/candidate';
import {
  updateCandidateStage,
  updateCandidateFavoriteStatus,
} from '../../api/pipeline';

interface PipelineCandidateRowProps {
  candidate: Candidate;
  jdId?: string; // optional: used to invalidate the pipeline query if present
}

export const PipelineCandidateRow: React.FC<PipelineCandidateRowProps> = ({
  candidate,
  jdId = '',
}) => {
  const queryClient = useQueryClient();

  const { mutate: mutateStage, isPending: isUpdatingStage } = useMutation({
    mutationFn: ({ rankId, stage }: { rankId: string; stage: string }) =>
      updateCandidateStage(rankId, stage),
    onSuccess: () => {
      if (jdId) {
        queryClient.invalidateQueries({ queryKey: ['pipelineForJD', jdId] });
      }
    },
    onError: (err: unknown) => {
      console.error('Failed to update candidate stage', err);
    },
  });

  const { mutate: mutateFavorite, isPending: isTogglingFavorite } = useMutation({
    mutationFn: ({ rankId, favorite }: { rankId: string; favorite: boolean }) =>
      updateCandidateFavoriteStatus(rankId, favorite),
    onSuccess: () => {
      if (jdId) {
        queryClient.invalidateQueries({ queryKey: ['pipelineForJD', jdId] });
      }
    },
    onError: (err: unknown) => {
      console.error('Failed to toggle favorite', err);
    },
  });

  const handleStageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newStage = e.target.value as CandidateStage;
    if (!candidate.rank_id) {
      console.error('Missing rank_id for candidate, cannot update stage');
      return;
    }
    mutateStage({ rankId: candidate.rank_id, stage: newStage });
  };

  const handleFavoriteToggle = () => {
    if (!candidate.rank_id) {
      console.error('Missing rank_id for candidate, cannot toggle favorite');
      return;
    }
    mutateFavorite({ rankId: candidate.rank_id, favorite: !candidate.favorite });
  };

  const avatarInitial =
    (candidate.profile_name || 'N/A')
      .split(' ')
      .map((n) => n[0])
      .join('')
      .slice(0, 2)
      .toUpperCase() || '??';

  return (
    <tr className="border-b border-gray-200 hover:bg-gray-50">
      {/* Name + Favorite */}
      <td className="p-4">
        <div className="flex items-center space-x-3">
          <button
            onClick={handleFavoriteToggle}
            aria-label={candidate.favorite ? 'Remove from favorites' : 'Add to favorites'}
            className="p-0"
            disabled={isTogglingFavorite}
            title={candidate.favorite ? 'Favorited' : 'Add to favorites'}
          >
            <Star
              size={18}
              className={`transition-colors ${candidate.favorite ? 'text-yellow-500 fill-yellow-500' : 'text-gray-400 hover:text-gray-600'}`}
            />
          </button>

          <div className="flex items-start gap-3">
            <div className="w-9 h-9 flex-shrink-0 flex items-center justify-center bg-slate-300 text-slate-700 rounded-full font-bold text-xs">
              {avatarInitial}
            </div>
            <div>
              <div className="font-medium text-sm text-slate-800">{candidate.profile_name || 'N/A'}</div>
              <div className="text-xs text-slate-500">{`${candidate.role || 'N/A'} at ${candidate.company || 'N/A'}`}</div>
            </div>
          </div>
        </div>
      </td>

      {/* Status */}
      <td className="p-4">
        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
          candidate.contacted ? 'bg-blue-100 text-blue-800' : candidate.favorite ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'
        }`}>
          {candidate.contacted ? 'Contacted' : candidate.favorite ? 'Favourited' : 'In Pipeline'}
        </span>
      </td>

      {/* Stage Dropdown */}
      <td className="p-4">
        <select
          value={candidate.stage || 'In Consideration'}
          onChange={handleStageChange}
          disabled={isUpdatingStage}
          aria-label={`Stage (current: ${candidate.stage || 'In Consideration'})`}
          className="border border-gray-300 rounded-md p-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-70 disabled:bg-gray-100"
        >
          {candidateStages.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </td>

      {/* Match Score */}
      <td className="p-4 text-sm text-gray-700">
        {typeof candidate.match_score === 'number' && !Number.isNaN(candidate.match_score)
          ? `${Number(candidate.match_score).toFixed(1)}%`
          : 'N/A'}
      </td>

      {/* Recommended / Placeholder */}
      <td className="p-4 text-sm text-gray-700">-</td>

      {/* LinkedIn */}
      <td className="p-4">
        {candidate.linkedin_url ? (
          <a
            href={candidate.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800"
            aria-label={`View ${candidate.profile_name || 'candidate'}'s LinkedIn`}
          >
            <Linkedin size={18} />
          </a>
        ) : (
          <span className="text-gray-400">
            <Linkedin size={18} />
          </span>
        )}
      </td>
    </tr>
  );
};

export default PipelineCandidateRow;
