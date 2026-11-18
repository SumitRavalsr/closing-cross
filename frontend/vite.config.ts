import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'DEV_')
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      watch: { usePolling: env.DEV_FILE_POLLING === 'true' },
      proxy: { '/api': env.DEV_API_TARGET || 'http://127.0.0.1:8000' },
    },
  }
})
