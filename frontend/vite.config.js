import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Proxy /api calls to FastAPI during local development
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
