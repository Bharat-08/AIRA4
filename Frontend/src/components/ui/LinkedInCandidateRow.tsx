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
// ✅ Updated Import to include TeammateOption
import RecommendPopup, { type TeammateOption } from "./RecommendPopup";
import CallSchedulePopup from "./CallSchedulePopup";
import { recommendCandidate } from "../../api/pipeline";
import type { JdSummary } from "../../api/roles";

type CandidateSource = 'ranked_candidates' | 'ranked_candidates_from_resume' | 'linkedin';

interface Props {
  candidate: LinkedInCandidate;
  onToggleFavorite?: (
    candidateId: string,
    source: CandidateSource,
    favorite: boolean
  ) => void;
  onToggleSave?: (
    candidateId: string,
    source: CandidateSource,
    save_for_future: boolean
  ) => Promise<void> | void;
  userJds?: JdSummary[];
  // ✅ NEW: Added teammates prop
  teammates?: TeammateOption[];
}

export function LinkedInCandidateRow({
  candidate,
  onToggleFavorite,
  onToggleSave,
  userJds = [], 
  teammates = [], // ✅ Default to empty array
}: Props) {
  const [isFav, setIsFav] = useState<boolean>(!!(candidate as any).favorite);
  const [isSaved, setIsSaved] = useState<boolean>(!!(candidate as any).save_for_future);

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

  // Use the correct ID for LinkedIn candidates
  const profileId = candidate.linkedin_profile_id;

  const avatarInitial =
    displayName
      .split(" ")
      .map((n) => (n ? n[0] : ""))
      .join("")
      .toUpperCase() || "C";

  // Updated: async save handler that calls parent prop and reverts on failure
  const handleSaveClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!profileId || !onToggleSave) {
      setIsSaved((prev) => !prev);
      return;
    }

    const newVal = !isSaved;
    setIsSaved(newVal); // optimistic

    try {
      await onToggleSave(String(profileId), "linkedin", newVal);
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
    
    if (!profileId || !onToggleFavorite) {
      setIsFav((prev) => !prev);
      return;
    }

    const newVal = !isFav;
    setIsFav(newVal); // Optimistic UI update
    try {
      await onToggleFavorite(String(profileId), "linkedin", newVal);
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

  // ✅ UPDATED: Handle recommendation
  const handleRecommendSend = async (type: "role" | "team", selection: string) => {
    if (type === "role" && profileId) {
      try {
        await recommendCandidate(String(profileId), "linkedin", selection);
        console.info(`Successfully recommended ${displayName} to role ${selection}`);
        alert('Candidate recommended successfully!');
      } catch (err) {
        console.error("Failed to recommend to role", err);
        alert('Failed to recommend candidate.');
      }
    } else {
      // Handle team recommendation logic here
      console.info(`Recommended to team: ${selection}`);
      alert(`Recommend request sent to teammate!`);
    }
    // No local state update for timestamps needed for LinkedIn candidates yet based on schema
    setIsRecommendOpen(false);
  };

  return (
    <>
      {/* EXACT 3 equal columns; align to header (left/center/right) */}
      <div className="grid grid-cols-3 items-center py-3 border-b border-gray-200 text-sm hover:bg-gray-50 transition-colors">
        {/* Candidate (left) */}
        <div className="flex items-center gap-3 min-w-0 px-4">
          <div className="w-8 h-8 flex-shrink-0 flex items-center justify-center bg-blue-100 text-blue-700 rounded-full font-semibold">
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
            onClick={handleFavoriteClick}
            title={isFav ? 'Unfavorite' : 'Favorite'}
            className="p-1 rounded hover:bg-slate-100 transition-colors"
            aria-pressed={isFav}
          >
            <Star size={18} className={isFav ? 'text-yellow-400' : 'text-gray-500'} />
          </button>
          
          <button
            onClick={handleCallClick} 
            title="Schedule Call"
            className="p-1 rounded hover:bg-slate-100 transition-colors"
          >
            <Phone size={18} />
          </button>

          <button
            onClick={handleRecommendClick} 
            title="Recommend"
            className="p-1 rounded hover:bg-slate-100 transition-colors"
          >
            <Send size={18} />
          </button>

          <button
            onClick={handleSaveClick} 
            title={isSaved ? 'Unsave Candidate' : 'Save Candidate'} 
            className="p-1 rounded hover:bg-slate-100 transition-colors"
            aria-pressed={isSaved} 
          >
            <Bookmark size={18} className={isSaved ? 'text-blue-600' : 'text-gray-500'} /> 
          </button>
        </div>
      </div>

      {/* Popups (rendered outside the grid) */}
      <RecommendPopup
        isOpen={isRecommendOpen}
        onClose={() => setIsRecommendOpen(false)}
        onSend={handleRecommendSend}
        jds={userJds}
        // ✅ NEW: Passing teammates prop
        teammates={teammates} 
      />
      <CallSchedulePopup
        isOpen={isCallOpen}
        onClose={() => setIsCallOpen(false)}
        candidateName={displayName}
        onSend={(message, channel) => {
          console.log('Send message:', channel, message);
          setIsCallOpen(false);
        }}
      />
    </>
  );
}