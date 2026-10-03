import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // `base` 는 설정 단계에서 정해져야 해서 import.meta.env 로는 못 읽는다.
  // loadEnv 로 .env.<mode> 를 직접 읽는다. `npm run build:static` 이 mode=static.
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  return {
    plugins: [react()],
    // GitHub Pages 는 https://<user>.github.io/<repo>/ 하위에 올라간다. base 를
    // 안 맞추면 빌드 결과가 절대 경로 /assets/... 를 가리켜 전부 404 가 된다.
    // 로컬 개발과 루트 호스팅은 '/' 이므로 .env.static 에서만 바꾼다.
    base: env.VITE_BASE || '/',
    server: {
      // 기본은 localhost 만 듣는다. 같은 Wi-Fi 의 휴대폰에서 보려면
      // `npm run dev:lan` (= vite --host) 으로 **그때만** 연다.
      // 이 앱에는 로그인이 없고 백엔드 키가 .env 에 있으므로, 늘 열어 두지 않는다.
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
  }
})
