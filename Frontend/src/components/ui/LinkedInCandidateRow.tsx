import React from "react";
import {
  Link as LinkIcon,
  Linkedin,
  Bookmark,
  Star,
  Send,
  Phone,
} from "lucide-react";
import type { LinkedInCandidate } from "../../types/candidate";

interface Props {
  candidate: LinkedInCandidate;
}

export function LinkedInCandidateRow({ candidate }: Props) {
    const displayName =
      candidate.name?.trim() ||
      candidate.summary?.split("\n")[0]?.trim() ||
      "—";
  
    const displayRole = candidate.position?.trim() || "—";
    const displayCompany = candidate.company?.trim() || "—";
    const profileUrl = candidate.profile_link || "";
  
    const avatarInitial =
      displayName
        .split(" ")
        .map((n) => (n ? n[0] : ""))
        .join("")
        .toUpperCase() || "C";
  
    const noop = (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };
  
    return (
      // EXACT 3 equal columns; align to header (left/center/right)
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
  <button onClick={noop} title="Save (coming soon)" className="p-1 rounded hover:bg-slate-100 transition-colors">
    <Bookmark size={18} />
  </button>
  <button onClick={noop} title="Favorite (coming soon)" className="p-1 rounded hover:bg-slate-100 transition-colors">
    <Star size={18} />
  </button>
  <button onClick={noop} title="Recommend (coming soon)" className="p-1 rounded hover:bg-slate-100 transition-colors">
    <Send size={18} />
  </button>
  <button onClick={noop} title="Schedule Call (coming soon)" className="p-1 rounded hover:bg-slate-100 transition-colors">
    <Phone size={18} />
  </button>
</div>
      </div>
    );
  }