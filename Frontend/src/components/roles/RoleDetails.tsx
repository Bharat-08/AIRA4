// Frontend/src/components/roles/RoleDetails.tsx
import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Role, RoleStatus } from '../../types/role';
import { ChevronDown, Edit3, Save, X } from 'lucide-react';
import { editRoleContent } from '../../api/roles';

interface RoleDetailsProps {
  role: Role;
  onUpdateStatus: (status: RoleStatus) => void;
  onUpdateContent: (updatedRole: Role) => void; 
  startEditing?: boolean;
}

const RoleDetails: React.FC<RoleDetailsProps> = ({ role, onUpdateStatus, onUpdateContent, startEditing }) => {
  const navigate = useNavigate();

  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState(role.full_content || '');
  const [isSaving, setIsSaving] = useState(false);
  const [isStatusDropdownOpen, setIsStatusDropdownOpen] = useState(false);

  // Sync editedContent when role.full_content changes
  useEffect(() => {
    setEditedContent(role.full_content || '');
    setIsEditing(false);
  }, [role.full_content]);

  useEffect(() => {
    if (startEditing) {
      setIsEditing(true);
    }
  }, [startEditing]);

  const formatDate = (dateString: string) => {
      if (!dateString) return 'N/A';
      return new Date(dateString).toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
      });
  };

  const handleSave = useCallback(async () => {
    if (editedContent === role.full_content || !editedContent.trim()) {
      setIsEditing(false);
      return;
    }
    
    setIsSaving(true);
    try {
      const updatedRole = await editRoleContent(role.id, editedContent);
      // updatedRole is the mapped Role object from api/roles.ts
      onUpdateContent(updatedRole); 
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save JD content:', error);
      alert('Failed to save changes. Please try again.');
    } finally {
      setIsSaving(false);
    }
  }, [role.id, editedContent, role.full_content, onUpdateContent]);
  
  const handleCancel = () => {
    setEditedContent(role.full_content || '');
    setIsEditing(false);
  };
  
  const handleGoToPipeline = () => {
    navigate(`/pipeline/${role.id}`);
  };

  const getStatusStyles = (status: RoleStatus) => {
    switch (status) {
      case 'open':
        return 'bg-teal-100 text-teal-800';
      case 'close':
        return 'bg-red-100 text-red-800';
      case 'deprioritized':
        return 'bg-amber-100 text-amber-800';
      default:
        return 'bg-slate-100 text-slate-800';
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="pb-5 border-b border-slate-100 mb-6">
        <div className="flex justify-between items-start gap-x-4">
            <div>
                <h2 className="text-2xl font-bold text-slate-900">{role.title}</h2>
                <p className="mt-1.5 text-sm text-slate-500">
                    Last updated on {formatDate(role.updated_at)}
                </p>
                <p className="mt-1 text-xs text-slate-400 italic">
                    Created on {formatDate(role.created_at)}
                </p>
            </div>
            <div className="relative inline-block text-left">
                <button 
                    type="button" 
                    onClick={() => setIsStatusDropdownOpen(prev => !prev)}
                    className={`inline-flex w-full justify-center items-center gap-x-1.5 rounded-md px-3 py-2 text-sm font-semibold shadow-sm ring-1 ring-inset ring-slate-300 ${getStatusStyles(role.status)}`}
                >
                    {role.status.charAt(0).toUpperCase() + role.status.slice(1)}
                    <ChevronDown className="-mr-1 h-5 w-5 text-slate-400" />
                </button>

                <div className={`absolute right-0 z-10 mt-2 w-40 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none transition-all duration-200 ${isStatusDropdownOpen ? 'opacity-100 scale-100' : 'opacity-0 scale-95 pointer-events-none'}`}>
                    <div className="py-1">
                        {(['open', 'close', 'deprioritized'] as RoleStatus[]).map((status) => (
                            <button
                                key={status}
                                onClick={() => {
                                    onUpdateStatus(status);
                                    setIsStatusDropdownOpen(false); // Close after selection
                                }}
                                className="block w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-100"
                            >
                                {status.charAt(0).toUpperCase() + status.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </div>
      </div>
      
      <div className="flex-grow overflow-auto">
          <div className="space-y-6">
              <div className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
                  <div className="flex justify-between items-center mb-2">
                      <h3 className="text-sm font-medium text-slate-500">
                          {isEditing ? 'EDITING: Full Job Description' : 'Full Job Description Content'}
                      </h3>
                      {isEditing ? (
                          <div className='flex gap-2'>
                              <button 
                                onClick={handleSave} 
                                disabled={isSaving}
                                className="inline-flex items-center rounded-md bg-teal-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-teal-500 disabled:opacity-50"
                              >
                                  {isSaving ? 'Saving...' : <><Save className="h-4 w-4 mr-1" /> Save</>}
                              </button>
                              <button 
                                onClick={handleCancel} 
                                disabled={isSaving}
                                className="inline-flex items-center rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-50"
                              >
                                  <X className="h-4 w-4 mr-1" /> Cancel
                              </button>
                          </div>
                      ) : (
                          <button 
                            onClick={() => setIsEditing(true)} 
                            className="inline-flex items-center text-sm font-medium text-slate-600 hover:text-slate-900"
                          >
                              <Edit3 className="h-4 w-4 mr-1" /> Edit Content
                          </button>
                      )}
                  </div>

                  {isEditing ? (
                      <textarea
                          value={editedContent}
                          onChange={(e) => setEditedContent(e.target.value)}
                          className="w-full min-h-[400px] p-2 border border-slate-300 rounded-md focus:ring-teal-500 focus:border-teal-500 text-sm text-slate-800"
                          disabled={isSaving}
                      />
                  ) : (
                      <div className="max-h-[400px] overflow-y-auto mt-2 p-2 bg-white rounded-md border border-slate-200">
                          <p className="text-sm text-slate-700 whitespace-pre-wrap">
                              {role.full_content || 'No detailed JD content uploaded.'}
                          </p>
                      </div>
                  )}
              </div>
              
              <div>
                  <h3 className="text-sm font-medium text-slate-500">AI-Parsed Summary</h3>
                  <p className="mt-1 text-sm text-slate-600 italic">{role.summary}</p>
              </div>

              <div className="grid grid-cols-2 gap-x-8 gap-y-4">
                  <div>
                      <h3 className="text-sm font-medium text-slate-500">Location</h3>
                      <p className="mt-1 text-base text-slate-900">{role.location}</p>

                  </div>
                  <div>
                      <h3 className="text-sm font-medium text-slate-500">Experience Required</h3>
                      <p className="mt-1 text-base text-slate-900">{role.experience}</p>
                  </div>
              </div>
              
              <div>
                  <h3 className="text-sm font-medium text-slate-500">Key Requirements</h3>
                  <div className="mt-1 flex flex-wrap gap-2 max-w-full">
                      {role.key_requirements.map((req, index) => (
                          <span
                            key={index}
                            className="bg-teal-50 text-teal-800 text-xs font-semibold px-2.5 py-0.5 rounded-full max-w-full whitespace-normal break-words"
                          >
                              {req}
                          </span>
                      ))}
                  </div>
              </div>
          </div>
      </div>
      <div className="flex justify-between items-center pt-5 border-t border-slate-100">
        <p className="text-sm text-slate-600">
          Candidates Liked: <span className="font-semibold text-slate-900">{role.candidateStats.liked}</span> | Candidates Contacted: <span className="font-semibold text-slate-900">{role.candidateStats.contacted}</span>
        </p>

        <button
          onClick={handleGoToPipeline}
          className="px-4 py-2 border border-slate-300 text-sm font-medium rounded-md shadow-sm text-slate-700 bg-white hover:bg-slate-50"
        >
          Go to Pipeline
        </button>
      </div>
    </div>
  );
};

export default RoleDetails;
