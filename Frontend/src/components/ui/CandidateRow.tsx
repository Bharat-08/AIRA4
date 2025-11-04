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
import CallSchedulePopup from "./CallSchedulePopup"; // adjust path if needed
import RecommendPopup from "./RecommendPopup"; // adjust path if needed

interface CandidateRowProps {
  candidate: Candidate;
  onUpdateCandidate: (updatedCandidate: Candidate) => void;
  onNameClick: (candidate: Candidate) => void;
  /**
   * Optional toggle handler injected from SearchPage.
   * signature: (candidateId, source, newFavorite) => Promise<void> | void
   */
  onToggleFavorite?: (
    candidateId: string,
    source: "ranked_candidates" | "ranked_candidates_from_resume",
    favorite: boolean
  ) => Promise<void> | void;
  /**
   * Which backend table this row corresponds to. Default is ranked_candidates.
   */
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

  // favorited state (optimistic UI)
  const [isFav, setIsFav] = useState<boolean>(!!candidate.favorite);
  // saved/bookmark state (optimistic UI)
  const [isSaved, setIsSaved] = useState<boolean>(!!(candidate as any).saved);

  const avatarInitial = candidate.profile_name
    ? candidate.profile_name
        .split(" ")
        .map((n) => (n ? n[0] : ""))
        .join("")
        .toUpperCase()
    : "C";

  const handleLinkedInClick = async () => {
    if (generatedUrl) {
      window.open(generatedUrl, "_blank", "noopener,noreferrer");
      return;
    }

    if (isGeneratingUrl) return;

    setIsGeneratingUrl(true);
    setError(null);

    try {
      const result = await generateLinkedInUrl(candidate.profile_id);
      const newUrl = result.linkedin_url;

      if (newUrl) {
        window.open(newUrl, "_blank", "noopener,noreferrer");
        setGeneratedUrl(newUrl);
        const updatedCandidate = { ...candidate, linkedin_url: newUrl };
        onUpdateCandidate(updatedCandidate);
      } else {
        throw new Error("API did not return a valid URL.");
      }
    } catch (err) {
      console.error("Failed to generate LinkedIn URL:", err);
      setError("Failed to find URL.");
    } finally {
      setIsGeneratingUrl(false);
    }
  };

  const renderLinkedInButton = () => {
    const finalUrl = generatedUrl || candidate.linkedin_url;

    if (finalUrl) {
      return (
        <a
          href={finalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-teal-600 hover:text-teal-700 transition-colors"
          title="Open Generated LinkedIn Profile"
        >
          <Linkedin size={18} />
        </a>
      );
    }

    if (isGeneratingUrl) {
      return <Loader2 size={18} className="animate-spin text-gray-500" />;
    }

    if (error) {
      return (
        <button
          onClick={handleLinkedInClick}
          className="text-red-500 hover:text-red-700 transition-colors"
          title={`Error: ${error}. Click to try again.`}
        >
          <Linkedin size={18} />
        </button>
      );
    }

    return (
      <button
        onClick={handleLinkedInClick}
        className="text-gray-400 hover:text-teal-600 transition-colors"
        title="Find LinkedIn Profile (Costly)"
      >
        <Linkedin size={18} />
      </button>
    );
  };

  // Called when user sends message from CallSchedulePopup
  const handleSendFromCallPopup = (
    message: string,
    channel?: "whatsapp" | "email"
  ) => {
    console.info(
      `Sending message to ${candidate.profile_name} via ${channel}:`,
      message
    );

    // lightweight local update (modify to match your backend/data model)
    try {
      const updatedCandidate: Candidate = {
        ...candidate,
        // @ts-ignore - optional metadata field; replace with real field if required
        last_contacted_at: new Date().toISOString(),
      } as unknown as Candidate;
      onUpdateCandidate(updatedCandidate);
    } catch (err) {
      console.warn(
        "Could not apply last_contacted update to candidate (type mismatch?)",
        err
      );
    }

    setIsCallPopupOpen(false);
  };

  // Called when user sends recommendation from RecommendPopup
  const handleRecommendSend = (type: "role" | "team", selection: string) => {
    console.info(
      `Recommended ${candidate.profile_name} to ${type} with selection: ${selection}`
    );

    // Example local update (customize as needed)
    try {
      const updatedCandidate: Candidate = {
        ...candidate,
        // @ts-ignore allow flexible property - change to a valid field if desired
        last_recommended_at: new Date().toISOString(),
      } as unknown as Candidate;
      onUpdateCandidate(updatedCandidate);
    } catch (err) {
      console.warn(
        "Could not apply recommendation update to candidate (type mismatch?)",
        err
      );
    }

    setIsRecommendPopupOpen(false);
  };

  // Favorite toggle handler (optimistic)
  const handleFavoriteClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const newVal = !isFav;
    // optimistic UI update
    setIsFav(newVal);
    try {
      if (onToggleFavorite) {
        await onToggleFavorite(
          candidate.profile_id || (candidate as any).resume_id,
          source,
          newVal
        );
      }
      // notify parent to persist the change in its state
      onUpdateCandidate({ ...candidate, favorite: newVal });
    } catch (err) {
      // rollback on error
      setIsFav(!newVal);
      console.warn("Failed to toggle favorite", err);
    }
  };

  // Save / bookmark toggle handler (optimistic)
  const handleSaveClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const newSaved = !isSaved;
    setIsSaved(newSaved);

    try {
      // notify parent so it can persist saved state (if desired)
      onUpdateCandidate({ ...(candidate as any), saved: newSaved } as Candidate);
    } catch (err) {
      // no-op rollback would require parent confirmation; keep optimistic for now
      setIsSaved(!newSaved);
      console.warn("Failed to update saved state locally", err);
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
              {candidate.profile_name}
            </p>
            <p className="text-gray-500">{`${candidate.role || "—"} at ${
              candidate.company || "—"
            }`}</p>
          </div>
        </div>

        {/* Match score */}
        <div className="col-span-2">
          <div className="relative w-24 h-6 bg-green-100 rounded-full">
            <div
              className="absolute top-0 left-0 h-full bg-green-500 rounded-full"
              style={{ width: `${Math.round(candidate.match_score || 0)}%` }}
            />
            <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold text-green-800">
              {Math.round(candidate.match_score || 0)}%
            </span>
          </div>
        </div>

        {/* Links */}
        <div className="col-span-2 flex items-center gap-4">
          <a
            href={candidate.profile_url || "#"}
            target="_blank"
            rel="noopener noreferrer"
            className={
              candidate.profile_url
                ? "text-teal-600 hover:text-teal-700"
                : "text-gray-400 cursor-not-allowed"
            }
            title="Open Original Profile URL"
          >
            <LinkIcon size={18} />
          </a>

          {renderLinkedInButton()}
        </div>

        {/* Actions (bookmark/save, star, send/message arrow -> opens RecommendPopup, phone -> opens CallSchedulePopup) */}
        <div className="col-span-1 flex items-center gap-3 text-gray-500 justify-end">
          {/* SAVE / BOOKMARK */}
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

          {/* Send (paper-plane) icon — opens Recommend popup */}
          <button
            onClick={() => setIsRecommendPopupOpen(true)}
            className="hover:text-teal-500"
            title="Recommend Action"
            aria-haspopup="dialog"
            aria-expanded={isRecommendPopupOpen}
          >
            <Send size={18} />
          </button>

          {/* Phone button opens CallSchedulePopup */}
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
        candidateName={candidate.profile_name}
        initialMessage={`Hi ${candidate.profile_name},

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
