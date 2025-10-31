import React from 'react';
import ReactDOM from 'react-dom/client';
// Use absolute paths from the root, which is common in Vite setups
import App from './App.tsx';
import '/src/index.css';
import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'; // 1. Import the provider and client

// 2. Create a new client instance
const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/* 3. Wrap your entire App component with the provider */}
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);

