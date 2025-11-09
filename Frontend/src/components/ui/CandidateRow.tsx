// frontend/src/components/ui/CandidateRow.tsx
import React, { useState } from "react";
import {
  Link as LinkIcon,
  Star,
  Send,
  Phone,
  Loader2,
  Linkedin,
  Bookmark,
} from "lucide-react";
import type { Candidate } from "../../types/candidate";
import { generateLinkedInUrl } from "../../api/search";
import CallSchedulePopup from "./CallSchedulePopup";
import RecommendPopup from "./RecommendPopup";

interface CandidateRowProps {
  candidate: Candidate;
  onUpdateCandidate: (updatedCandidate: Candidate) => void;
  onNameClick: (candidate: Candidate) => void;
  onToggleFavorite?: (
    candidateId: string,
    source: "ranked_candidates" | "ranked_candidates_from_resume",
    favorite: boolean
  ) => Promise<void> | void;
  source?: "ranked_candidates" | "ranked_candidates_from_resume";
}

export function CandidateRow({
  candidate,
  onUpdateCandidate,
  onNameClick,
  onToggleFavorite,
  source = "ranked_candidates",
}: CandidateRowProps) {
  const [isGeneratingUrl, setIsGeneratingUrl] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generatedUrl, setGeneratedUrl] = useState<string | null>(null);

  // popups
  const [isCallPopupOpen, setIsCallPopupOpen] = useState(false);
  const [isRecommendPopupOpen, setIsRecommendPopupOpen] = useState(false);

  // optimistic UI states
  const [isFav, setIsFav] = useState<boolean>(!!(candidate as any).favorite);
  const [isSaved, setIsSaved] = useState<boolean>(!!(candidate as any).saved);

  // ---- Robust display fields (covers all shapes coming from web + resume pipelines) ----
  const displayName =
  candidate.profile_name || // from 'search' table
  candidate.person_name || // from 'resume' table
  candidate.name ||
  candidate.full_name ||
  "—";

const displayRole =
  candidate.role || // from 'search' OR 'resume'
  candidate.current_title ||
  candidate.title ||
  "—";

const displayCompany =
  candidate.company || // from 'search' OR 'resume'
  candidate.current_company ||
  candidate.organization_name ||
  candidate.organization ||
  "—";

const profileId =
  candidate.profile_id || // from 'search' table
  candidate.resume_id || // from 'resume' table
  (candidate as any).id || // Keep this as a final fallback
  "";

// --- FIX IS HERE ---
// profileUrl should NOT fall back to linkedin_url
const profileUrl =
  candidate.profile_url || // from 'search' OR 'resume'
  (candidate as any).validated_url || // This isn't in the schema, so leave as 'any'
  "";

// --- FIX IS HERE ---
// linkedinUrl should NOT fall back to profile_url
// It should only be a *real* linkedin_url or the newly generated one.
const linkedinUrl =
  generatedUrl ||
  candidate.linkedin_url ||
  "";

const matchScorePct = Math.round(Number(candidate.match_score || 0));

  const avatarInitial =
    displayName
      .split(" ")
      .map((n) => (n ? n[0] : ""))
      .join("")
      .toUpperCase() || "C";

  const handleLinkedInClick = async () => {
    // This logic is now correct.
    // The `renderLinkedInButton` function will only call this
    // if `linkedinUrl` is empty (meaning no generatedUrl or candidate.linkedin_url).

    // If a URL *does* exist, the `renderLinkedInButton` will render an <a> tag instead,
    // so this onClick handler won't even be attached.

    if (!profileId || isGeneratingUrl) return;

    setIsGeneratingUrl(true);
    setError(null);

    try {
      const result = await generateLinkedInUrl(String(profileId));
      const newUrl = result.linkedin_url;
      if (!newUrl) throw new Error("API did not return a valid URL.");
      
      // Open the new URL
      window.open(newUrl, "_blank", "noopener,noreferrer");
      
      // Save to local state so the UI updates
      setGeneratedUrl(newUrl);
      
      // Update the parent component's state
      onUpdateCandidate({ ...(candidate as any), linkedin_url: newUrl } as Candidate);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Failed to generate LinkedIn URL:", err);
      setError("Failed to find URL.");
    } finally {
      setIsGeneratingUrl(false);
    }
  };

  const renderLinkedInButton = () => {
    // This logic is now correct because `linkedinUrl` is fixed.
    // if we already have a URL, render as link
    if (linkedinUrl) {
      return (
        <a
          href={linkedinUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-teal-600 hover:text-teal-700 transition-colors"
          title="Open LinkedIn/Profile"
        >
          <Linkedin size={18} />
        </a>
      );
    }

    // if `linkedinUrl` is empty, show the loading spinner or button
    if (isGeneratingUrl) {
      return <Loader2 size={18} className="animate-spin text-gray-500" />;
    }

    // if `linkedinUrl` is empty and not loading, show the button
    // that triggers the API call
    return (
      <button
        onClick={handleLinkedInClick}
        className={error ? "text-red-500 hover:text-red-700" : "text-gray-400 hover:text-teal-600"}
        title={error ? `Error: ${error}. Click to try again.` : "Find LinkedIn Profile (Costly)"}
      >
        <Linkedin size={18} />
      </button>
    );
  };

  const handleSendFromCallPopup = (message: string, channel?: "whatsapp" | "email") => {
    // eslint-disable-next-line no-console
    console.info(`Sending message to ${displayName} via ${channel}:`, message);
    try {
      onUpdateCandidate({
        ...(candidate as any),
        last_contacted_at: new Date().toISOString(),
      } as Candidate);
    } catch {}
    setIsCallPopupOpen(false);
  };

  const handleRecommendSend = (type: "role" | "team", selection: string) => {
    // eslint-disable-next-line no-console
    console.info(`Recommended ${displayName} to ${type}: ${selection}`);
    try {
      onUpdateCandidate({
        ...(candidate as any),
        last_recommended_at: new Date().toISOString(),
      } as Candidate);
    } catch {}
    setIsRecommendPopupOpen(false);
  };

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
      onUpdateCandidate({ ...(candidate as any), favorite: newVal } as Candidate);
    } catch (err) {
      setIsFav(!newVal);
      // eslint-disable-next-line no-console
      console.warn("Failed to toggle favorite", err);
    }
  };

  const handleSaveClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const newSaved = !isSaved;
    setIsSaved(newSaved);
    try {
      onUpdateCandidate({ ...(candidate as any), saved: newSaved } as Candidate);
    } catch {
      setIsSaved(!newSaved);
    }
  };

  return (
    <>
      <div className="grid grid-cols-12 items-center py-3 border-b border-gray-200 text-sm">
        {/* Left: avatar + name */}
        <div className="col-span-6 flex items-center gap-3">
          <div className="w-8 h-8 flex-shrink-0 flex items-center justify-center bg-gray-200 text-gray-600 rounded-full font-semibold">
            {avatarInitial}
          </div>
          <div onClick={() => onNameClick(candidate)} className="cursor-pointer">
            <p className="font-semibold text-gray-800 hover:text-teal-600">
              {displayName}
            </p>
            <p className="text-gray-500">
              {`${displayRole || "—"} at ${displayCompany || "—"}`}
            </p>
          </div>
        </div>

        {/* Match score */}
        <div className="col-span-2">
          <div className="relative w-24 h-6 bg-green-100 rounded-full">
            <div
              className="absolute top-0 left-0 h-full bg-green-500 rounded-full"
              style={{ width: `${Math.max(0, Math.min(100, matchScorePct))}%` }}
            />
            <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold text-green-800">
              {Math.max(0, Math.min(100, matchScorePct))}%
            </span>
          </div>
        </div>

        {/* Links */}
        <div className="col-span-2 flex items-center gap-4">
          <a
            href={profileUrl || "#"}
            target="_blank"
            rel="noopener noreferrer"
            className={profileUrl ? "text-teal-600 hover:text-teal-700" : "text-gray-400 cursor-not-allowed"}
            title={profileUrl ? "Open Original Profile URL" : "No profile URL"}
          >
            <LinkIcon size={18} />
          </a>

          {/* This function now renders the correct element */}
          {renderLinkedInButton()}
        </div>

        {/* Actions */}
        <div className="col-span-1 flex items-center gap-3 text-gray-500 justify-end">
          <button
            onClick={handleSaveClick}
            title={isSaved ? "Unsave" : "Save"}
            aria-pressed={isSaved}
            className="p-1 rounded hover:bg-slate-100 transition-colors"
          >
            <Bookmark size={18} className={isSaved ? "text-blue-600" : "text-gray-400"} />
          </button>

          <button
            onClick={handleFavoriteClick}
            title={isFav ? "Unfavorite" : "Favorite"}
            aria-pressed={isFav}
            className="p-1 rounded hover:bg-slate-100 transition-colors"
          >
            <Star size={18} className={isFav ? "text-yellow-400" : "text-gray-400"} />
          </button>

          <button
            onClick={() => setIsRecommendPopupOpen(true)}
            className="hover:text-teal-500"
            title="Recommend"
            aria-haspopup="dialog"
            aria-expanded={isRecommendPopupOpen}
          >
            <Send size={18} />
          </button>

          <button
            onClick={() => setIsCallPopupOpen(true)}
            className="hover:text-teal-500"
            title="Schedule Call"
            aria-haspopup="dialog"
            aria-expanded={isCallPopupOpen}
          >
            <Phone size={18} />
          </button>
        </div>
      </div>

      {/* Call schedule popup */}
      <CallSchedulePopup
        isOpen={isCallPopupOpen}
        onClose={() => setIsCallPopupOpen(false)}
        candidateName={displayName}
        initialMessage={`Hi ${displayName},

Hope you're doing well. I'd like to schedule a short call to discuss an opportunity. Are you available this week? Please share a few time slots that work for you.`}
        onSend={(message, channel) => handleSendFromCallPopup(message, channel)}
      />

      {/* Recommend popup */}
      <RecommendPopup
        isOpen={isRecommendPopupOpen}
        onClose={() => setIsRecommendPopupOpen(false)}
        onSend={(type, selection) => handleRecommendSend(type, selection)}
      />
    </>
  );
}