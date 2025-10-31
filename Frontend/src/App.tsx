// src/App.tsx
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { LoginPage } from './pages/LoginPage';
import { RecruiterDashboardPage } from './pages/RecruiterDashboardPage';
import { AdminDashboardPage } from './pages/AdminDashboardPage';
import { SuperAdminDashboardPage } from './pages/SuperAdminDashboardPage';
import { SearchPage } from './pages/SearchPage';
import RolesPage from './pages/RolesPage';
import { PipelinePage } from './pages/PipelinePage';
import type { User as AppUser } from './types/user'; // helpful for explicit typing

// A small typed wrapper component for protected routes.
// Keeps the route elements concise and avoids recreating the function on every render.
const ProtectedRoute: React.FC<{ children: React.ReactNode; user?: AppUser | null }> = ({ children, user }) => {
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

function App() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="bg-gray-900 text-white flex items-center justify-center min-h-screen">
        <h1 className="text-3xl font-bold">Loading...</h1>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          path="/"
          element={
            <ProtectedRoute user={user}>
              {user?.is_superadmin ? (
                <SuperAdminDashboardPage />
              ) : user?.role === 'admin' ? (
                <AdminDashboardPage />
              ) : user?.role === 'user' ? (
                <RecruiterDashboardPage user={user} />
              ) : (
                <Navigate to="/login" replace />
              )}
            </ProtectedRoute>
          }
        />

        <Route
          path="/search"
          element={
            <ProtectedRoute user={user}>
              {user ? <SearchPage user={user} /> : <Navigate to="/login" replace />}
            </ProtectedRoute>
          }
        />

        <Route
          path="/roles"
          element={
            <ProtectedRoute user={user}>
              <RolesPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/pipeline"
          element={
            <ProtectedRoute user={user}>
              {user ? <PipelinePage user={user} /> : <Navigate to="/login" replace />}
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
