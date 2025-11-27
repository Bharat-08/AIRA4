import React, { useEffect, useRef, useState } from 'react';
import type { Candidate } from '../../types/candidate';
import { generateLinkedInUrl } from '../../api/search';
import { Bookmark, Star, Send, Phone, Loader2 } from 'lucide-react';
import CallSchedulePopup from './CallSchedulePopup';
import RecommendPopup from './RecommendPopup';

interface CandidatePopupCardProps {
  candidate: Candidate | null;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  // ✅ Added these to support actions inside the popup
  onUpdateCandidate?: (updated: Candidate) => void;
  onToggleFavorite?: (candidateId: string, source: any, favorite: boolean) => void;
  onToggleSave?: (candidateId: string, source: any, save: boolean) => void;
}

const parseSections = (text: string) => {
  const res: Record<string, string> = {};
  if (!text) return res;
  const headingRegex = /\*{0,2}\s*(Verdict|Strengths|Strength|Weaknesses\/Gaps|Weaknesses|Weakness|Gaps|Reasoning|Reasonings)\s*\*{0,2}\s*:\s*/ig;
  const matches: { name: string; index: number; length: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = headingRegex.exec(text)) !== null) {
    matches.push({ name: m[1].toLowerCase(), index: m.index, length: m[0].length });
  }
  if (matches.length === 0) {
    res['strengths'] = text.trim();
    return res;
  }
  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].index + matches[i].length;
    const end = i + 1 < matches.length ? matches[i + 1].index : text.length;
    const sectionText = text.slice(start, end).trim();
    let key = matches[i].name;
    if (key === 'strength') key = 'strengths';
    if (key === 'weakness' || key === 'gaps') key = 'weaknesses';
    res[key] = sectionText;
  }
  return res;
};


const stripStars = (s: string) => s.replace(/\*+/g, '').trim();

const splitIntoLines = (s: string) => s.split(/\r?\n/).map(l => l.trim()).filter(Boolean);

const looksLikeList = (lines: string[]) => {
  if (lines.length === 0) return false;
  // If at least half lines start with -, •, — or a digit + dot -> treat as list
  const listLike = lines.filter(l => /^[-–—•]\s+/.test(l) || /^\d+\.\s+/.test(l));
  return listLike.length >= Math.max(1, Math.floor(lines.length / 2));
};

const normalizeListItem = (line: string) => {
  // Remove leading bullet tokens or numeric prefixes
  return line.replace(/^[-–—•]\s+/, '').replace(/^\d+\.\s+/, '').trim();
};

const CandidatePopupCard: React.FC<CandidatePopupCardProps> = ({ 
  candidate, 
  onClose, 
  onPrev, 
  onNext,
  onUpdateCandidate,
  onToggleFavorite,
  onToggleSave
}) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Local UI states for actions
  const [isFav, setIsFav] = useState<boolean>(!!candidate?.favorite);
  const [isSaved, setIsSaved] = useState<boolean>(!!candidate?.save_for_future);
  const [isGeneratingUrl, setIsGeneratingUrl] = useState(false);

  // Popups
  const [isCallPopupOpen, setIsCallPopupOpen] = useState(false);
  const [isRecommendPopupOpen, setIsRecommendPopupOpen] = useState(false);

  useEffect(() => {
    if (candidate) {
      setIsFav(!!candidate.favorite);
      setIsSaved(!!candidate.save_for_future);
    }
  }, [candidate]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    setTimeout(() => dialogRef.current?.focus(), 0);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!candidate) return null;

  const displayName = candidate.profile_name || candidate.person_name || candidate.name || 'Candidate';
  
  const avatarInitial = displayName
    ? displayName.split(' ').map(n => n[0]).slice(0, 2).join('')
    : 'C';

  // ID resolution for actions
  const profileId = candidate.rank_id || candidate.profile_id || candidate.resume_id || '';
  const source = (candidate as any).resume_id ? 'ranked_candidates_from_resume' : 'ranked_candidates';

  // SOURCE: use candidate.strengths
  const sourceText = String((candidate as any).strengths ?? '');

  const sections = parseSections(sourceText);
  const rawStrength = (sections['strengths'] && sections['strengths'].trim()) || sourceText.trim();
  const rawReasoning = (sections['reasoning'] && sections['reasoning'].trim()) || '';

  // Clean summary/reasoning
  const reasoningText = stripStars(rawReasoning);
  const summaryFallback = stripStars((candidate as any).summary || '');

  // Strength
  const cleanedStrength = stripStars(rawStrength);
  const strengthLines = splitIntoLines(cleanedStrength);
  const isList = looksLikeList(strengthLines);

  const handleViewLinkedIn = async () => {
    // If we already have a URL, just open it
    let url = candidate.linkedin_url;
    if (url && url.startsWith('http')) {
      window.open(url, '_blank', 'noopener,noreferrer');
      return;
    }

    setIsGeneratingUrl(true);
    try {
      const targetId = candidate.profile_id || candidate.rank_id; // Prefer profile_id for URL generation logic if available
      const data = token ? await generateLinkedInUrl(targetId!, token) : await generateLinkedInUrl(targetId!);
      
      url = data?.linkedin_url || url;
      
      if (url) {
        window.open(url, '_blank', 'noopener,noreferrer');
        
        // ✅ KEY FIX: Update parent state immediately so the main list (CandidateRow)
        // sees the new URL and switches the icon from Grey (Fetch) to Blue (Link).
        if (onUpdateCandidate) {
            onUpdateCandidate({ ...candidate, linkedin_url: url });
        }
      }
      else {
        alert('A LinkedIn profile could not be found for this candidate.');
      }
    } catch (error) {
      console.error('Error fetching LinkedIn URL:', error);
      alert('An error occurred while trying to fetch the LinkedIn profile.');
    } finally {
      setIsGeneratingUrl(false);
    }
  };

  const handleViewProfile = () => {
    const url = candidate.profile_url;
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
    else alert('Original profile URL not available.');
  };

  // --- Action Handlers ---

  const handleFavoriteClick = () => {
    const newVal = !isFav;
    setIsFav(newVal); // Optimistic
    if (onToggleFavorite && profileId) {
      onToggleFavorite(profileId, source, newVal);
    }
  };

  const handleSaveClick = () => {
    const newVal = !isSaved;
    setIsSaved(newVal); // Optimistic
    if (onToggleSave && profileId) {
      onToggleSave(profileId, source, newVal);
    }
  };

  const handleSendFromCallPopup = (message: string, channel?: "whatsapp" | "email") => {
    console.info(`Sending message to ${displayName} via ${channel}:`, message);
    if (onUpdateCandidate) {
      onUpdateCandidate({
        ...candidate,
        last_contacted_at: new Date().toISOString(),
      } as Candidate);
    }
    setIsCallPopupOpen(false);
  };

  const handleRecommendSend = (type: "role" | "team", selection: string) => {
    console.info(`Recommended ${displayName} to ${type}: ${selection}`);
    if (onUpdateCandidate) {
      onUpdateCandidate({
        ...candidate,
        last_recommended_at: new Date().toISOString(),
      } as Candidate);
    }
    setIsRecommendPopupOpen(false);
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-6"
        aria-modal="true"
        role="dialog"
        onClick={onClose}
      >
        <div
          className="absolute inset-0 bg-black bg-opacity-50 backdrop-blur-sm transition-opacity"
          style={{ backdropFilter: 'blur(4px)' }}
        />

        <div
          ref={dialogRef}
          tabIndex={-1}
          className="relative bg-white max-w-4xl w-full rounded-lg shadow-2xl transform transition-all duration-200 ease-out max-h-[90vh] overflow-hidden"
          onClick={(e) => e.stopPropagation()}
          role="document"
        >
          <button
            onClick={onClose}
            aria-label="Close"
            className="absolute top-4 right-4 text-gray-500 hover:text-gray-700 z-10"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          <div className="px-10 py-8 overflow-y-auto" style={{ maxHeight: 'calc(90vh - 48px)' }}>
            {/* Header */}
            <div className="flex items-center gap-6">
              <div className="flex-shrink-0">
                {candidate.profile_image_url ? (
                  <img src={candidate.profile_image_url} alt={displayName} className="w-24 h-24 rounded-full object-cover border-4 border-white shadow-sm" />
                ) : (
                  <div className="w-24 h-24 rounded-full bg-rose-100 flex items-center justify-center text-xl font-semibold text-gray-700 border-4 border-white shadow-sm">
                    {avatarInitial}
                  </div>
                )}
              </div>

              <div className="flex-1">
                <h2 className="text-2xl font-bold text-gray-900">{displayName}</h2>
                <div className="text-sm text-teal-600 mt-1">
                  {candidate.role ? `${candidate.role}` : ''}
                  {candidate.company ? ` at ${candidate.company}` : ''}
                  {typeof candidate.match_score === 'number' ? ` | ${Math.round(candidate.match_score)}% Match` : ''}
                </div>
              </div>
            </div>

            {/* Summary (Reasoning) */}
            <div className="mt-8">
              <h3 className="text-lg font-semibold text-gray-800 mb-3">Summary</h3>
              <div className="text-sm text-gray-700 leading-relaxed px-1 py-2">
                <p className="whitespace-pre-wrap">
                  {reasoningText || summaryFallback || 'No detailed summary available.'}
                </p>
              </div>
            </div>

            {/* Strength */}
            <div className="mt-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-3">Strength</h3>
              <div className="text-sm text-gray-700 leading-relaxed px-1 py-2">
                {isList ? (
                  <ol className="list-decimal ml-6 space-y-2">
                    {strengthLines.map((ln, idx) => (
                      <li key={idx} className="whitespace-pre-wrap">
                        {normalizeListItem(ln)}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="whitespace-pre-wrap">{cleanedStrength || 'No strength details available.'}</p>
                )}
              </div>
            </div>

            {/* Links + actions */}
            <div className="mt-8">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">Links</h3>

              <div className="flex items-center justify-between py-3 border-b border-transparent">
                <div className="text-sm text-gray-700">Profile Link</div>
                <div>
                  <button onClick={handleViewProfile} className="text-sm font-medium text-teal-700 hover:underline">
                    View
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between py-3 border-b border-transparent">
                <div className="text-sm text-gray-700">LinkedIn Link</div>
                <div>
                  <button 
                    onClick={handleViewLinkedIn} 
                    disabled={isGeneratingUrl}
                    className="text-sm font-medium text-teal-700 hover:underline flex items-center gap-2"
                  >
                    {isGeneratingUrl ? <Loader2 size={14} className="animate-spin" /> : 'View'}
                  </button>
                </div>
              </div>

              {/* Actions + Prev/Next */}
              <div className="mt-4 flex items-center justify-between">
                {/* Functional Action Buttons */}
                <div className="flex items-center gap-4 text-gray-400">
                  <button 
                    onClick={handleSaveClick} 
                    title={isSaved ? "Unsave" : "Save"}
                    className="hover:bg-gray-100 p-2 rounded-full transition-colors"
                  >
                    <Bookmark size={20} className={isSaved ? "text-blue-600 fill-current" : ""} />
                  </button>
                  
                  <button 
                    onClick={handleFavoriteClick}
                    title={isFav ? "Unfavorite" : "Favorite"}
                    className="hover:bg-gray-100 p-2 rounded-full transition-colors"
                  >
                    <Star size={20} className={isFav ? "text-yellow-400 fill-current" : ""} />
                  </button>
                  
                  <button 
                    onClick={() => setIsRecommendPopupOpen(true)}
                    title="Recommend"
                    className="hover:bg-gray-100 p-2 rounded-full transition-colors hover:text-teal-600"
                  >
                    <Send size={20} />
                  </button>
                  
                  <button 
                    onClick={() => setIsCallPopupOpen(true)}
                    title="Schedule Call"
                    className="hover:bg-gray-100 p-2 rounded-full transition-colors hover:text-teal-600"
                  >
                    <Phone size={20} />
                  </button>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() => { if (onPrev) onPrev(); else onClose(); }}
                    className="px-4 py-2 rounded-md bg-teal-50 text-teal-800 font-medium hover:bg-teal-100"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => { if (onNext) onNext(); else onClose(); }}
                    className="px-4 py-2 rounded-md bg-teal-50 text-teal-800 font-medium hover:bg-teal-100"
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>

            <div style={{ height: 8 }} />
          </div>
        </div>
      </div>

      {/* Nested Popups (Rendered outside the main card via React logic, z-index handles stacking) */}
      {isCallPopupOpen && (
        <CallSchedulePopup
          isOpen={isCallPopupOpen}
          onClose={() => setIsCallPopupOpen(false)}
          candidateName={displayName}
          initialMessage={`Hi ${displayName},\n\nHope you're doing well. I'd like to schedule a short call to discuss an opportunity. Are you available this week? Please share a few time slots that work for you.`}
          onSend={(message, channel) => handleSendFromCallPopup(message, channel)}
        />
      )}

      {isRecommendPopupOpen && (
        <RecommendPopup
          isOpen={isRecommendPopupOpen}
          onClose={() => setIsRecommendPopupOpen(false)}
          onSend={(type, selection) => handleRecommendSend(type, selection)}
        />
      )}
    </>
  );
};

export default CandidatePopupCard;