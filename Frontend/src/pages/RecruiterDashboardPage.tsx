// src/pages/RecruiterDashboardPage.tsx
import { ArrowRight } from 'lucide-react';
import { Header } from '../components/layout/Header';
import { KpiCard } from '../components/ui/KpiCard';
import type { User } from '../types/user';
import { Link, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { fetchDashboardStats } from '../api/dashboard';

// Utility to format time (or install 'date-fns')
const formatTimeAgo = (timestamp: number) => {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

export function RecruiterDashboardPage({ user }: { user: User }) {
  const userName = user.name || 'User';
  const navigate = useNavigate();

  const [stats, setStats] = useState({
    openRoles: 0,
    contactedCandidates: 0,
    favoritedCandidates: 0,
    recommendationsReceived: 0 // ✅ New State
  });

  // --- State for Last Activity ---
  const [lastActivity, setLastActivity] = useState<{ 
    roleName: string; 
    lastUpdated: string;
    jd_id?: string 
  } | null>(null);

  useEffect(() => {
    // 1. Fetch Stats
    fetchDashboardStats()
      .then((data) => {
        setStats({
          openRoles: data.open_roles,
          contactedCandidates: data.contacted_candidates,
          favoritedCandidates: data.favorited_candidates,
          recommendationsReceived: data.recommendations_received // ✅ Map response
        });
      })
      .catch((err) => console.error("Failed to load dashboard stats:", err));

    // 2. Load Last Activity from Local Storage
    try {
      const savedActivity = localStorage.getItem('last_search_activity');
      if (savedActivity) {
        const parsed = JSON.parse(savedActivity);
        setLastActivity({
          roleName: parsed.roleName,
          lastUpdated: formatTimeAgo(parsed.lastUpdated),
          jd_id: parsed.jd_id
        });
      }
    } catch (e) {
      console.error("Error parsing last activity", e);
    }
  }, []);

  const kpis = [
    { id: 1, icon: 'folder-open', value: stats.openRoles, label: "Open Roles" },
    { id: 2, icon: 'users', value: stats.contactedCandidates, label: "Candidates Contacted" },
    { id: 3, icon: 'star', value: stats.favoritedCandidates, label: "Profiles Favourited" },
  ];

  // --- Handle Continue Navigation ---
  const handleContinueClick = () => {
    if (lastActivity?.jd_id) {
      // Navigate to search page. 
      navigate('/search');
    } else {
      navigate('/search'); // Fallback
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-800">
      <Header userName={userName} />

      <main className="p-4 sm:p-6 md:p-8 max-w-7xl mx-auto">
        {/* Section 1: Welcome */}
        <section className="mb-10">
          <h2 className="text-3xl font-bold text-gray-900">Welcome back, {userName}!</h2>
          <p className="text-gray-500 mt-1">From JD to first outreach in under an hour</p>
          <div className="mt-6 flex flex-col sm:flex-row gap-4">
            <button
              onClick={() => navigate('/roles')}
              className="px-6 py-3 bg-white border border-gray-300 rounded-lg font-semibold text-gray-700 hover:bg-gray-100 transition-colors text-left"
            >
              MANAGE ROLES
              <span className="block text-xs font-normal text-gray-500">upload JD, edit requirements</span>
            </button>
            <Link to="/search" className="px-6 py-3 bg-teal-500 text-white rounded-lg font-semibold hover:bg-teal-600 transition-colors text-left">
              START SEARCH
              <span className="block text-xs font-normal text-teal-100">find your perfect candidate</span>
            </Link>
          </div>
        </section>

        {/* Section 2: Activity and Recommendations */}
        <section className="grid md:grid-cols-2 gap-6 mb-10">
          {/* Continue Card */}
          <div className="p-6 bg-white rounded-lg shadow-sm border border-gray-200">
            <h3 className="font-semibold text-gray-500 mb-4">Continue where you left off</h3>
            <div className="flex justify-between items-center">
              <div>
                {lastActivity ? (
                  <>
                    <p className="font-semibold text-gray-900">{lastActivity.roleName}</p>
                    <p className="text-sm text-gray-400">Last updated: {lastActivity.lastUpdated}</p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-gray-900">No recent searches</p>
                    <p className="text-sm text-gray-400">Start a new search to see activity here</p>
                  </>
                )}
              </div>
              <button 
                onClick={handleContinueClick} 
                className="p-2 rounded-full hover:bg-gray-100 transition-colors"
                disabled={!lastActivity}
              >
                <ArrowRight className={`text-gray-600 ${!lastActivity ? 'opacity-50' : ''}`} />
              </button>
            </div>
          </div>

          {/* Recommended Profiles Card (Dynamic) */}
          <div className="p-6 bg-white rounded-lg shadow-sm border border-gray-200">
            <h3 className="font-semibold text-gray-500 mb-4">Recommended Profiles</h3>
            <div>
              <p className="font-semibold text-gray-900">
                {stats.recommendationsReceived > 0 
                  ? `${stats.recommendationsReceived} profiles recommended to you`
                  : "No new recommendations"}
              </p>
              <button
                // Assuming 'defaultTab' helps navigate to the right list. 
                // You can expand this to pass a 'filter' state if your pipeline supports it.
                onClick={() => navigate('/pipeline', { state: { defaultTab: 'allCandidates', filter: 'recommended_to_me' } })}
                className="flex items-center gap-2 mt-2 text-sm font-semibold text-teal-600 hover:underline"
              >
                View Pipeline <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </section>

        {/* Section 3: KPIs */}
        <section className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {kpis.map(kpi => (
            <KpiCard key={kpi.id} icon={kpi.icon} value={kpi.value} label={kpi.label} />
          ))}
        </section>
      </main>
    </div>
  );
}