// Frontend/src/pages/RolesPage.tsx
import React, { useState, useEffect, useCallback } from 'react';
import type { Role, RoleStatus } from '../types/role';
import { getRoles, createRole, updateRoleStatus, deleteRole } from '../api/roles';
import RoleList from '../components/roles/RoleList';
import RoleDetails from '../components/roles/RoleDetails';
import { Header } from '../components/layout/Header';
import { useAuth } from '../hooks/useAuth';
import { useLocation, useNavigate } from 'react-router-dom';

export default function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [statusUpdateError, setStatusUpdateError] = useState<string | null>(null);
  
  // --- MODIFIED: Sorting and Filtering State ---
  const [sort, setSort] = useState<string>('created_at');
  const [sortOrder, setSortOrder] = useState<string>('desc'); // New State for Order
  const [filter, setFilter] = useState<string>('all');
  // --------------------------------------------

  const [roleToDelete, setRoleToDelete] = useState<Role | null>(null);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState<boolean>(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  const { user, isLoading: isAuthLoading } = useAuth();

  const userName = user?.name || 'User';

  const location = useLocation();
  const navigate = useNavigate();

  const [openEditorForRoleId, setOpenEditorForRoleId] = useState<string | null>(null);

  const handleUpdateRoleContent = useCallback((updatedRole: Role) => {
    setRoles(prev => prev.map(r => (r.id === updatedRole.id ? updatedRole : r)));
    if (selectedRole?.id === updatedRole.id) {
      setSelectedRole(updatedRole);
    }
  }, [selectedRole?.id]);

  useEffect(() => {
    if (user) {
      const fetchUserRoles = async () => {
        setIsLoading(true);
        setError(null);
        try {
          // --- MODIFIED: Pass sortOrder to API ---
          const userRoles = await getRoles(sort, filter, sortOrder);
          setRoles(userRoles);

          const navSelectedId = (location?.state as any)?.selectedRoleId as string | undefined;
          const navOpenEditor = Boolean((location?.state as any)?.openEditor);

          if (navSelectedId) {
            const match = userRoles.find(r => r.id === navSelectedId || (r as any).jd_id === navSelectedId);
            if (match) {
              setSelectedRole(match);
              if (navOpenEditor) setOpenEditorForRoleId(match.id);
              setIsLoading(false);
              return;
            }
          }

          if (userRoles.length > 0) {
            const currentSelected = selectedRole ? userRoles.find(r => r.id === selectedRole.id) : null;
            setSelectedRole(currentSelected || userRoles[0]);
          } else {
            setSelectedRole(null);
          }
        } catch (err) {
          setError('Failed to fetch roles. Please try again.');
          console.error(err);
        } finally {
          setIsLoading(false);
        }
      };
      fetchUserRoles();
    } else if (!isAuthLoading) {
      setIsLoading(false);
    }
    // --- MODIFIED: Add sortOrder to dependency array ---
  }, [user, isAuthLoading, sort, filter, sortOrder, location, navigate]);

  useEffect(() => {
    if (openEditorForRoleId && selectedRole?.id === openEditorForRoleId) {
      setTimeout(() => setOpenEditorForRoleId(null), 50);
    }
  }, [openEditorForRoleId, selectedRole]);

  const handleSelectRole = (role: Role) => {
    setSelectedRole(role);
    setStatusUpdateError(null);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      setJdFile(event.target.files[0]);
    }
  };

  const handleUploadAndCreateRole = async () => {
    if (!jdFile) {
      setUploadError('Please select a file to upload.');
      return;
    }
    if (!user) {
      setUploadError("You must be logged in to create a role.");
      return;
    }

    setUploading(true);
    setUploadError(null);
    try {
      const newRole = await createRole(jdFile);
      setRoles(prev => [newRole, ...prev]);
      setSelectedRole(newRole);
      setIsModalOpen(false);
      setJdFile(null);
    } catch (err: any) {
      setUploadError(err.message || 'An unexpected error occurred.');
      console.error(err);
    } finally {
      setUploading(false);
    }
  };

  const handleUpdateStatus = async (roleId: string, newStatus: RoleStatus) => {
    setStatusUpdateError(null);
    const idx = roles.findIndex(r => r.id === roleId);
    if (idx === -1) {
      console.warn('Role not found for status update:', roleId);
      return;
    }

    const previousRole = roles[idx];
    const updatedRole: Role = { ...previousRole, status: newStatus };

    setRoles(prev => {
      const copy = [...prev];
      copy[idx] = updatedRole;
      return copy;
    });
    if (selectedRole?.id === roleId) {
      setSelectedRole(updatedRole);
    }

    try {
      const persisted = await updateRoleStatus(roleId, newStatus);
      setRoles(prev => prev.map(r => (r.id === roleId ? persisted : r)));
      if (selectedRole?.id === roleId) {
        setSelectedRole(persisted);
      }
    } catch (err: any) {
      console.error('Failed to update role status', err);
      setStatusUpdateError(err?.message || 'Failed to update role status. Please try again.');
      setRoles(prev => prev.map(r => (r.id === roleId ? previousRole : r)));
      if (selectedRole?.id === roleId) {
        setSelectedRole(previousRole);
      }
    }
  };

  const handleDeleteRequest = (roleId: string) => {
    const role = roles.find(r => r.id === roleId);
    if (role) {
      setRoleToDelete(role);
      setIsDeleteModalOpen(true);
      setDeleteError(null);
    }
  };

  const confirmDeleteRole = async () => {
    if (!roleToDelete) return;

    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteRole(roleToDelete.id);
      setRoles(prev => prev.filter(r => r.id !== roleToDelete.id));
      if (selectedRole?.id === roleToDelete.id) {
        const remainingRoles = roles.filter(r => r.id !== roleToDelete.id);
        setSelectedRole(remainingRoles.length > 0 ? remainingRoles[0] : null);
      }
      setIsDeleteModalOpen(false);
      setRoleToDelete(null);
    } catch (err: any) {
      setDeleteError(err.message || 'An unexpected error occurred while deleting the role.');
      console.error(err);
    } finally {
      setIsDeleting(false);
    }
  };


  return (
    <div className="flex flex-col h-screen bg-slate-50">
      <Header userName={userName} showBackButton={true} />

      <main className="flex-grow p-4 overflow-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 h-full gap-4">
          <div className="md:col-span-1 lg:col-span-1 h-full bg-white rounded-lg shadow-sm overflow-auto flex flex-col">
            <RoleList
              roles={roles}
              selectedRoleId={selectedRole?.id}
              onSelectRole={handleSelectRole}
              onNewRoleClick={() => setIsModalOpen(true)}
              sort={sort}
              filter={filter}
              // --- MODIFIED: Pass new props to RoleList ---
              sortOrder={sortOrder} 
              onSortOrderChange={setSortOrder}
              // ------------------------------------------
              onSortChange={setSort}
              onFilterChange={setFilter}
              onDeleteRole={handleDeleteRequest}
            />
          </div>

          <div className="md:col-span-2 lg:col-span-3 h-full bg-white p-6 rounded-lg shadow-sm overflow-auto">
            {isLoading ? (
              <div className="text-center text-slate-500">Loading roles...</div>
            ) : error ? (
              <div className="text-red-500 text-center">{error}</div>
            ) : selectedRole ? (
              <>
                {statusUpdateError && (
                  <div className="mb-3 text-sm text-red-600">
                    {statusUpdateError}
                  </div>
                )}
                <RoleDetails
                  role={selectedRole}
                  onUpdateStatus={(newStatus) => handleUpdateStatus(selectedRole.id, newStatus)}
                  onUpdateContent={handleUpdateRoleContent}
                  startEditing={Boolean(openEditorForRoleId && selectedRole?.id === openEditorForRoleId)}
                  onDelete={handleDeleteRequest}
                />
              </>
            ) : (
              <div className="text-center text-slate-500">{user ? 'No roles found. Select "New Role" to begin.' : 'Please log in to view roles.'}</div>
            )}
          </div>
        </div>
      </main>

      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg shadow-xl w-full max-w-md">
            <h2 className="text-2xl font-bold mb-4">Create New Role</h2>
            <p className="mb-4 text-gray-600">Upload a Job Description.</p>
            <input
              type="file"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:font-semibold file:bg-teal-600 file:text-white hover:file:bg-teal-500 mb-4"
              accept=".pdf,.doc,.docx,.txt"
            />
            {uploadError && <p className="text-red-500 text-sm mb-4">{uploadError}</p>}
            <div className="flex justify-end space-x-4">
              <button onClick={() => setIsModalOpen(false)} className="px-4 py-2 bg-gray-300 rounded-md" disabled={uploading}>Cancel</button>
              <button onClick={handleUploadAndCreateRole} className="px-4 py-2 bg-teal-600 text-white rounded-md disabled:bg-teal-600" disabled={uploading || !jdFile}>
                {uploading ? 'Uploading...' : 'Upload & Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isDeleteModalOpen && roleToDelete && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg shadow-xl w-full max-w-md">
            <h2 className="text-2xl font-bold mb-4">Confirm Deletion</h2>
            <p className="mb-4 text-gray-600">Are you sure you want to delete the role "{roleToDelete.title}"? This action cannot be undone.</p>
            {deleteError && <p className="text-red-500 text-sm mb-4">{deleteError}</p>}
            <div className="flex justify-end space-x-4">
              <button onClick={() => setIsDeleteModalOpen(false)} className="px-4 py-2 bg-gray-300 rounded-md" disabled={isDeleting}>Cancel</button>
              <button onClick={confirmDeleteRole} className="px-4 py-2 bg-red-600 text-white rounded-md" disabled={isDeleting}>
                {isDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}