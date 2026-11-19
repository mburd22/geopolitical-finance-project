import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Forward any request starting with /api to the Python server on port 8000.
    // The React code can then just call fetch('/api/events') without knowing where Python runs.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
