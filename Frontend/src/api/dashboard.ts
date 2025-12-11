// Frontend/src/api/dashboard.ts

export interface DashboardStats {
  open_roles: number;
  contacted_candidates: number;
  favorited_candidates: number;
  recommendations_received: number; // ✅ Added this field
}

export const fetchDashboardStats = async (): Promise<DashboardStats> => {
  // We assume your backend routers are prefixed with /api like the roles router
  const res = await fetch('/api/dashboard/stats', {
    credentials: 'include',
  });

  if (!res.ok) {
    throw new Error('Failed to fetch dashboard stats');
  }

  return res.json();
};