import React, { useState } from 'react';
import type { Role } from '../../types/role';
import { Search, ChevronDown } from 'lucide-react';
import RoleListItem from '../ui/RoleListItem';

interface RoleListProps {
  roles: Role[];
  selectedRoleId: string | null | undefined;
  onSelectRole: (role: Role) => void;
  onNewRoleClick: () => void;
  onDeleteRole: (roleId: string) => void;
  
  sort: string;
  filter: string;
  sortOrder: string; // --- NEW PROP ---
  
  onSortChange: (value: string) => void;
  onFilterChange: (value: string) => void;
  onSortOrderChange: (value: string) => void; // --- NEW PROP ---
}

const RoleList: React.FC<RoleListProps> = ({
  roles,
  selectedRoleId,
  onSelectRole,
  onNewRoleClick,
  onDeleteRole,
  sort,
  filter,
  sortOrder,
  onSortChange,
  onFilterChange,
  onSortOrderChange,
}) => {
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [isSortOpen, setIsSortOpen] = useState(false);
  const [isOrderOpen, setIsOrderOpen] = useState(false); // --- NEW STATE ---

  const filterOptions = ['all', 'open', 'close', 'deprioritized'];
  
  // Sort Field Options
  const sortOptions = {
    'created_at': 'Created Date',
    'updated_at': 'Updated Date',
  };
  
  // --- NEW: Sort Order Options ---
  const orderOptions = {
    'asc': 'Ascending',
    'desc': 'Descending',
  };

  return (
    <div className="flex flex-col h-full">
      {/* Controls Section */}
      <div className="p-4 space-y-4 border-b border-slate-100">
        <button
          onClick={onNewRoleClick}
          className="w-full bg-teal-600 text-white font-semibold py-2 rounded-md hover:bg-teal-700 transition-colors flex items-center justify-center"
        >
          + New Role
        </button>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search roles"
            className="w-full bg-slate-100 text-slate-800 font-semibold py-2 pl-10 pr-4 border border-slate-200 rounded-md text-sm focus:ring-teal-600 focus:border-teal-500"
          />
        </div>
        <div className="flex items-center gap-2">
          {/* Filter Dropdown */}
          <div className="relative w-full">
            <button
              onClick={() => setIsFilterOpen(!isFilterOpen)}
              onBlur={() => setTimeout(() => setIsFilterOpen(false), 150)}
              className="flex items-center justify-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50 w-full"
            >
              Filter <ChevronDown size={16} />
            </button>
            {isFilterOpen && (
              <div className="absolute z-10 mt-1 w-full bg-white shadow-lg border rounded-md">
                {filterOptions.map((option) => (
                  <button
                    key={option}
                    onClick={() => {
                      onFilterChange(option);
                      setIsFilterOpen(false);
                    }}
                    className={`block w-full text-left px-4 py-2 text-sm ${
                      filter === option ? 'bg-teal-50 text-teal-700' : 'text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    {option.charAt(0).toUpperCase() + option.slice(1)}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* --- NEW: Sort Order Dropdown (Ascending/Descending) --- */}
          <div className="relative w-full">
            <button
              onClick={() => setIsOrderOpen(!isOrderOpen)}
              onBlur={() => setTimeout(() => setIsOrderOpen(false), 150)}
              className="flex items-center justify-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50 w-full"
            >
              Order <ChevronDown size={16} />
            </button>
            {isOrderOpen && (
              <div className="absolute z-10 mt-1 w-full bg-white shadow-lg border rounded-md">
                {Object.entries(orderOptions).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => {
                      onSortOrderChange(value);
                      setIsOrderOpen(false);
                    }}
                    className={`block w-full text-left px-4 py-2 text-sm ${
                      sortOrder === value ? 'bg-teal-50 text-teal-700' : 'text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Sort By Dropdown (Created/Updated) */}
          <div className="relative w-full">
            <button
              onClick={() => setIsSortOpen(!isSortOpen)}
              onBlur={() => setTimeout(() => setIsSortOpen(false), 150)}
              className="flex items-center justify-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-md text-sm font-medium text-slate-700 hover:bg-slate-50 w-full"
            >
              Sort By <ChevronDown size={16} />
            </button>
            {isSortOpen && (
              <div className="absolute z-10 mt-1 w-full bg-white shadow-lg border rounded-md">
                {Object.entries(sortOptions).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => {
                      onSortChange(value);
                      setIsSortOpen(false);
                    }}
                    className={`block w-full text-left px-4 py-2 text-sm ${
                      sort === value ? 'bg-teal-50 text-teal-700' : 'text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Role List Items */}
      <div className="flex-grow overflow-y-auto divide-y divide-slate-100">
        {roles.map((role) => (
          <RoleListItem
            key={role.id}
            role={role}
            isSelected={role.id === selectedRoleId}
            onClick={() => onSelectRole(role)}
            onDelete={onDeleteRole}
          />
        ))}
      </div>
    </div>
  );
};

export default RoleList;