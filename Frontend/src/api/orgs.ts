// Frontend/src/api/orgs.ts

export interface OrgUser {
  id: string;
  email: string;
  name: string | null;
  role: string;
}

// ✅ NEW: Interface for Teammates (used in Recommendation)
export interface Teammate {
  id: string;
  name: string | null;
  email: string;
  avatar_url?: string | null;
}

/**
 * Fetches all users who are members of the current user's organization.
 * Endpoint: GET /api/orgs/users
 * Note: This usually requires Admin privileges.
 */
export const fetchOrgUsers = async (): Promise<OrgUser[]> => {
  // Retrieve token if your app uses localStorage for auth, 
  // otherwise 'credentials: include' handles cookies.
  const token = localStorage.getItem("access_token");
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch('/api/orgs/users', {
    method: 'GET',
    headers: headers,
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch organization users' }));
    throw new Error(errorData.detail || 'Failed to fetch organization users');
  }

  return response.json();
};

/**
 * Fetches teammates for the recommendation feature.
 * Endpoint: GET /api/orgs/teammates
 * Accessible by regular users.
 */
export const getTeammates = async (): Promise<Teammate[]> => {
  const token = localStorage.getItem("access_token");
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch('/api/orgs/teammates', {
    method: 'GET',
    headers: headers,
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch teammates' }));
    throw new Error(errorData.detail || 'Failed to fetch teammates');
  }

  return response.json();
};