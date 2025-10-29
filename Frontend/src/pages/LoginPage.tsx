import { useAuth } from "../hooks/useAuth";

//
// --- THIS IS THE FIX ---
// Changed "const LoginPage = () => {"
// to "export const LoginPage = () => {"
// This makes it a named export, which is what App.tsx is expecting.
//
export const LoginPage = () => {
  const { user, isLoading } = useAuth();

  const backendLoginUrl = `${
    import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
  }/auth/google/login`;

  if (isLoading) return <div>Loading...</div>;
  if (user) return <div>Already logged in as {user.name}</div>;

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md">
        <h1 className="mb-4 text-2xl font-bold text-center">Login to AIRA</h1>
        <a
          href={backendLoginUrl}
          className="flex items-center justify-center w-full px-4 py-2 font-medium text-gray-700 bg-white border border-gray-300 rounded-md shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
        >
          <svg
            className="w-5 h-5 mr-3"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 48 48"
            width="48px"
            height="48px"
          >
            <path
              fill="#EA4335"
              d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l8.13 6.29C12.02 13.92 17.64 9.5 24 9.5z"
            ></path>
            <path
              fill="#4285F4"
              d="M46.98 24.55c0-1.57-.15-3.09-.42-4.55H24v8.61h13.04c-.58 2.79-2.22 5.17-4.8 6.8l8.13 6.29c4.7-4.32 7.4-10.63 7.4-17.15z"
            ></path>
            <path
              fill="#FBBC05"
              d="M10.69 28.39c-.38-.97-.59-2.02-.59-3.11s.21-2.14.59-3.11L2.56 13.22C.96 16.24 0 19.98 0 24s.96 7.76 2.56 10.78l8.13-6.39z"
            ></path>
            <path
              fill="#34A853"
              d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-8.13-6.29c-2.15 1.45-4.92 2.3-8.02 2.3-6.36 0-11.98-4.4-13.94-10.31l-8.13 6.29C6.51 42.62 14.62 48 24 48z"
            ></path>
            <path fill="none" d="M0 0h48v48H0z"></path>
          </svg>
          Login with Google
        </a>
      </div>
    </div>
  );
};

// We remove the line "export default LoginPage;" from the bottom.
// export default LoginPage;