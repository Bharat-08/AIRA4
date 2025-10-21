import React, { useEffect, useRef } from 'react';
import type { Candidate } from '../../types/candidate';
import { generateLinkedInUrl } from '../../api/search';
import { Bookmark, Star, Send, Phone } from 'lucide-react';

interface CandidatePopupCardProps {
  candidate: Candidate | null;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
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

const CandidatePopupCard: React.FC<CandidatePopupCardProps> = ({ candidate, onClose, onPrev, onNext }) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    setTimeout(() => dialogRef.current?.focus(), 0);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!candidate) return null;

  const avatarInitial = candidate.profile_name
    ? candidate.profile_name.split(' ').map(n => n[0]).slice(0, 2).join('')
    : 'C';

  // SOURCE: use candidate.strengths (DB field 'strength' per your instruction)
  const sourceText = String((candidate as any).strengths ?? '');

  const sections = parseSections(sourceText);
  const rawStrength = (sections['strengths'] && sections['strengths'].trim()) || sourceText.trim();
  const rawReasoning = (sections['reasoning'] && sections['reasoning'].trim()) || '';

  // Clean summary/reasoning: remove ** markers
  const reasoningText = stripStars(rawReasoning);
  const summaryFallback = stripStars((candidate as any).summary || '');

  // Strength: strip stars, then decide if it's a list
  const cleanedStrength = stripStars(rawStrength);
  const strengthLines = splitIntoLines(cleanedStrength);
  const isList = looksLikeList(strengthLines);

  const handleViewLinkedIn = async () => {
    try {
      let url = candidate.linkedin_url;
      if (!url || !url.startsWith('http')) {
        const data = token ? await generateLinkedInUrl(candidate.profile_id, token) : await generateLinkedInUrl(candidate.profile_id);
        url = data?.linkedin_url || url;
      }
      if (url) window.open(url, '_blank', 'noopener,noreferrer');
      else alert('A LinkedIn profile could not be found for this candidate.');
    } catch (error) {
      console.error('Error fetching LinkedIn URL:', error);
      alert('An error occurred while trying to fetch the LinkedIn profile.');
    }
  };

  const handleViewProfile = () => {
    const url = candidate.profile_url;
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
    else alert('Original profile URL not available.');
  };

  return (
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
                <img src={candidate.profile_image_url} alt={candidate.profile_name || 'Candidate'} className="w-24 h-24 rounded-full object-cover border-4 border-white shadow-sm" />
              ) : (
                <div className="w-24 h-24 rounded-full bg-rose-100 flex items-center justify-center text-xl font-semibold text-gray-700 border-4 border-white shadow-sm">
                  {avatarInitial}
                </div>
              )}
            </div>

            <div className="flex-1">
              <h2 className="text-2xl font-bold text-gray-900">{candidate.profile_name || 'Unnamed Candidate'}</h2>
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
                <button onClick={handleViewLinkedIn} className="text-sm font-medium text-teal-700 hover:underline">
                  View
                </button>
              </div>
            </div>

            {/* Actions + Prev/Next */}
            <div className="mt-4 flex items-center justify-between">
              <div className="flex items-center gap-4 text-gray-400">
                <Bookmark size={18} />
                <Star size={18} />
                <Send size={18} />
                <Phone size={18} />
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
  );
};

export default CandidatePopupCard;
