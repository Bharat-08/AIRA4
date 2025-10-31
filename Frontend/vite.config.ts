// vite.config.ts

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from 'tailwindcss';

export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {
      plugins: [tailwindcss()],
    },
  },

  // --- UPDATED SERVER SECTION ---
  server: {
    proxy: {
      // Forward any /api/* requests to backend
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // keep /api path clean
      },

      // Forward /me requests (used for user session checks or auth)
      '/me': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false, // optional
      },
    },
  },
  // --------------------------------
});
