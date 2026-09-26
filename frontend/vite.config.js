import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 헤도닉 적합은 캐시가 비어 있으면 실거래 3만 건 기준 ~7초가 걸린다.
        // 기본 프록시 타임아웃으로는 백엔드 재시작 직후 첫 요청이 끊긴다.
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
  },
})
