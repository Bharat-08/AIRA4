// Frontend/src/components/ui/JdPopupCard.tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { X, Edit3 } from 'lucide-react';
import type { JdSummary } from '../../api/roles';

interface Props {
  jd: JdSummary;
  onClose: () => void;
}

const JdPopupCard: React.FC<Props> = ({ jd, onClose }) => {
  const navigate = useNavigate();

  const handleGoToRole = () => {
    // Navigate to Roles page and request that it select the role
    navigate('/roles', { state: { selectedRoleId: jd.jd_id } });
    onClose();
  };

  const handleEditRole = () => {
    // Navigate to Roles page and request it select the role and open editor
    navigate('/roles', { state: { selectedRoleId: jd.jd_id, openEditor: true } });
    onClose();
  };

  const fullText = jd.jd_text ?? jd.jd_parsed_summary ?? '';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />

      <div className="relative z-10 max-w-3xl w-full mx-4 bg-white rounded-2xl shadow-xl ring-1 ring-black/5 overflow-hidden">
        <div className="flex items-start justify-between p-6 border-b">
          <div>
            <h3 className="text-xl font-semibold text-gray-900">{jd.role || jd.title || 'Untitled Role'}</h3>
          </div>
          <button onClick={onClose} className="p-2 rounded-md hover:bg-gray-100">
            <X size={18} />
          </button>
        </div>

        <div className="p-6">
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Full Description</h4>
            <div className="text-sm text-gray-700 max-h-[60vh] overflow-y-auto whitespace-pre-wrap">{fullText || 'No description available.'}</div>
          </div>
        </div>

        <div className="p-4 border-t flex items-center justify-end gap-3">
          <button
            onClick={handleEditRole}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white font-medium hover:bg-teal-700"
          >
            <Edit3 size={16} /> Edit
          </button>

          <button
            onClick={handleGoToRole}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
          >
            Go to Role
          </button>
        </div>
      </div>
    </div>
  );
};

export default JdPopupCard;
