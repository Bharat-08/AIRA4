import React, { useState } from "react";
import {
  Link as LinkIcon,
  Linkedin,
  Bookmark,
  Star,
  Send,
  Phone,
} from "lucide-react";
import type { LinkedInCandidate } from "../../types/candidate";
import RecommendPopup from "./RecommendPopup"; // Import RecommendPopup
import CallSchedulePopup from "./CallSchedulePopup"; // Import CallSchedulePopup

interface Props {
  candidate: LinkedInCandidate;
  onToggleFavorite?: (
    candidateId: string,
    source: 'ranked_candidates' | 'ranked_candidates_from_resume',
    favorite: boolean
  ) => void;
  onToggleSave?: (
    candidateId: string,
    source: 'ranked_candidates' | 'ranked_candidates_from_resume',
    save_for_future: boolean
  ) => Promise<void> | void;
  source?: 'ranked_candidates' | 'ranked_candidates_from_resume';
}

export function LinkedInCandidateRow({
  candidate,
  onToggleFavorite,
  onToggleSave,
  source = 'ranked_candidates',
}: Props) {
  const [isFav, setIsFav] = useState<boolean>(!!(candidate as any).favorite);
  const [isSaved, setIsSaved] = useState<boolean>(!!(candidate as any).save_for_future); // initialize from save_for_future

  // State for popups
  const [isRecommendOpen, setIsRecommendOpen] = useState(false);
  const [isCallOpen, setIsCallOpen] = useState(false);

  const displayName =
    candidate.name?.trim() ||
    candidate.summary?.split("\n")[0]?.trim() ||
    "—";

  const displayRole = candidate.position?.trim() || "—";
  const displayCompany = candidate.company?.trim() || "—";
  const profileUrl = candidate.profile_link || "";

  // Prefer linkedin_profile_id, then other fallbacks
  const profileId =
    (candidate as any).linkedin_profile_id ||
    (candidate as any).profile_id ||
    (candidate as any).id ||
    candidate.profile_link || // Fallback to profile_link if no other ID
    '';

  const avatarInitial =
    displayName
      .split(" ")
      .map((n) => (n ? n[0] : ""))
      .join("")
      .toUpperCase() || "C";

  // noop helper
  const noop = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Updated: async save handler that calls parent prop and reverts on failure
  const handleSaveClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    // If the parent didn't pass a handler or we don't have an id, do nothing (but toggle UI locally)
    if (!profileId) {
      // toggle locally so user gets instant feedback even if no ID
      setIsSaved((prev) => !prev);
      return;
    }
    if (!onToggleSave) {
      // still toggle locally
      setIsSaved((prev) => !prev);
      return;
    }

    const newVal = !isSaved;
    setIsSaved(newVal); // optimistic

    try {
      await onToggleSave(String(profileId), source, newVal);
      // success -> nothing else to do, parent is expected to update remote state
    } catch (err) {
      // revert on failure
      setIsSaved(!newVal);
      // eslint-disable-next-line no-console
      console.warn("Failed to toggle save_for_future for LinkedIn candidate", err);
    }
  };

  const handleFavoriteClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Do not proceed if onToggleFavorite prop is not provided or if there's no ID
    if (!profileId || !onToggleFavorite) return;

    const newVal = !isFav;
    setIsFav(newVal); // Optimistic UI update
    try {
      // Call the prop function passed from the parent
      await onToggleFavorite(String(profileId), source, newVal);
    } catch (err) {
      setIsFav(!newVal); // Revert on failure
      // eslint-disable-next-line no-console
      console.warn('Failed to toggle favorite', err);
    }
  };
  
  // Handlers for opening popups
  const handleRecommendClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsRecommendOpen(true);
  };

  const handleCallClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsCallOpen(true);
  };

  return (
    // We use a React.Fragment to return the row AND the popups
    <>
      {/* EXACT 3 equal columns; align to header (left/center/right) */}
      <div className="grid grid-cols-3 items-center py-3 border-b border-gray-200 text-sm">
        {/* Candidate (left) */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 flex-shrink-0 flex items-center justify-center bg-gray-200 text-gray-600 rounded-full font-semibold">
            {avatarInitial}
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-gray-800 truncate">{displayName}</p>
            <p className="text-gray-500 truncate">
              {`${displayRole} at ${displayCompany}`}
            </p>
          </div>
        </div>

        {/* Profile Link (center) */}
        <div className="flex items-center justify-center gap-4">
          <a
            href={profileUrl || "#"}
            target="_blank"
            rel="noopener noreferrer"
            className={profileUrl ? "text-teal-600 hover:text-teal-700" : "text-gray-400 cursor-not-allowed"}
            title={profileUrl ? "Open LinkedIn Profile" : "No profile URL"}
          >
            <LinkIcon size={18} />
          </a>
          <a
            href={profileUrl || "#"}
            target="_blank"
            rel="noopener noreferrer"
            className={profileUrl ? "text-teal-600 hover:text-teal-700" : "text-gray-400 cursor-not-allowed"}
            aria-label="Open on LinkedIn"
            title={profileUrl ? "Open on LinkedIn" : "No profile URL"}
          >
            <Linkedin size={18} />
          </a>
        </div>

        {/* Actions (left-aligned inside the third column) */}
        <div className="flex items-center justify-start gap-3 text-gray-500 pl-1">
          <button
            onClick={handleSaveClick} // Use save handler (now async & optimistic)
            title={isSaved ? 'Unsave Candidate' : 'Save Candidate'} // Dynamic title
            className="p-1 rounded hover:bg-slate-100 transition-colors"
            aria-pressed={isSaved} // Accessibility
          >
            <Bookmark size={18} className={isSaved ? 'text-blue-600' : 'text-gray-500'} /> 
          </button>
          <button
            onClick={handleFavoriteClick}
            title={isFav ? 'Unfavorite' : 'Favorite'}
            className="p-1 rounded hover:bg-slate-100 transition-colors"
            aria-pressed={isFav}
          >
            <Star size={18} className={isFav ? 'text-yellow-400' : 'text-gray-500'} />
          </button>
          <button
            onClick={handleRecommendClick} // Use recommend handler
            title="Recommend"
            className="p-1 rounded hover:bg-slate-100 transition-colors"
          >
            <Send size={18} />
          </button>
          <button
            onClick={handleCallClick} // Use call handler
            title="Schedule Call"
            className="p-1 rounded hover:bg-slate-100 transition-colors"
          >
            <Phone size={18} />
          </button>
        </div>
      </div>

      {/* Popups (rendered outside the grid) */}
      <RecommendPopup
        isOpen={isRecommendOpen}
        onClose={() => setIsRecommendOpen(false)}
        onSend={(type, selection) => {
          console.log('Recommend:', type, selection);
          // Add logic to handle the recommendation
        }}
      />
      <CallSchedulePopup
        isOpen={isCallOpen}
        onClose={() => setIsCallOpen(false)}
        candidateName={displayName}
        onSend={(message, channel) => {
          console.log('Send message:', channel, message);
          // Add logic to send the message
        }}
      />
    </>
  );
}
