import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The backend runs on 8000. Proxying keeps the frontend origin-agnostic,
    // so the same build works locally and when deployed behind one domain.
    proxy: {
      // No rewrite: the backend serves the same routes under /api, so the
      // path the browser requests is identical in dev and in production.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
