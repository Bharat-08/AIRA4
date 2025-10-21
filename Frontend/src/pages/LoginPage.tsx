// src/pages/LoginPage.tsx
export function LoginPage() {
  return (
    <div className="bg-gray-50 text-gray-800 flex items-center justify-center min-h-screen">
      <div className="text-center p-8 bg-white rounded-xl shadow-lg border border-gray-200">
        <h1 className="text-3xl font-bold text-teal-600">Authentication Required</h1>
        <p className="mt-4 text-gray-600">You need to log in to access the dashboard.</p>
        <a href="api/auth/google/login"
          className="mt-6 inline-block bg-teal-600 text-white font-semibold py-3 px-6 rounded-lg hover:bg-teal-700 transition-colors">
          Login with Google
        </a>
      </div>
    </div>
  );
}