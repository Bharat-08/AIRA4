// vite.config.ts

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Correct v3 Import: Imports directly from 'tailwindcss'
import tailwindcss from 'tailwindcss'

export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {
      plugins: [tailwindcss()],
    },
  },
})