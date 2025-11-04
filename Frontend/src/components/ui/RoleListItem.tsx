import React from 'react';
import type { Role } from '../../types/role';
import { Trash2 } from 'lucide-react';

interface RoleListItemProps {
  role: Role;
  isSelected: boolean;
  onClick: () => void;
  onDelete: (roleId: string) => void;
}

const getTimeAgo = (dateString: string): string => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diffTime = Math.abs(now.getTime() - date.getTime());
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  if (diffDays <= 1) return 'Today';
  if (diffDays < 7) return `${diffDays}d`;
  if (diffWeeks < 5) return `${diffWeeks}w`;
  if (diffMonths < 12) return `${diffMonths}m`;
  return `${diffYears}y`;
};

const RoleListItem: React.FC<RoleListItemProps> = ({ role, isSelected, onClick, onDelete }) => {
  // delete handler kept for API; UI deletion now triggered from details area.
  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete(role.id);
  };

  return (
    <div
      onClick={onClick}
      className={`flex justify-between items-start px-4 py-3.5 cursor-pointer transition-colors
        ${isSelected ? 'bg-teal-50' : 'hover:bg-slate-50'}
      `}
    >
      <div className="flex-1">
        <h3 className={`text-sm font-medium ${isSelected ? 'text-teal-900' : 'text-slate-800'}`}>
          {role.title}
        </h3>
        <p className={`text-sm ${isSelected ? 'text-teal-700' : 'text-slate-500'}`}>
          {role.location}
        </p>
      </div>

      {/* Right side shows time only. Delete moved to RoleDetails area as requested. */}
      <div className="flex items-center">
        <span className={`text-xs pt-0.5 whitespace-nowrap pl-3 ${isSelected ? 'text-teal-600 font-medium' : 'text-slate-400'}`}>
          {getTimeAgo(role.created_at)}
        </span>
        {/* NOTE: delete UI removed from list item. Keep handler available if needed. */}
      </div>
    </div>
  );
};

export default RoleListItem;
