import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'CREATOROS_')
  const proxy = { '/api': { target: env.CREATOROS_API_URL || 'http://127.0.0.1:8000' } }
  return {
    plugins: [react(), tailwind()],
    build: { license: true },
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
  }
})
