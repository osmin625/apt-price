/**
 * 카카오맵 JS SDK 로더.
 *
 * 함정 세 가지 — 셋 다 실제로 자주 밟는다:
 *
 * 1. `autoload=false` + `kakao.maps.load(cb)` 가 **필수**다. 빼면 script 의
 *    onload 시점에 `window.kakao.maps.Map` 이 아직 undefined 다.
 * 2. 약속(promise)을 **모듈 스코프**에 memoize 한다. ref 에 넣으면 React 18
 *    StrictMode 가 dev 에서 effect 를 두 번 실행해 스크립트가 두 번 주입된다.
 * 3. 카카오 개발자센터 > 플랫폼 > Web 에 `http://localhost:5173` 과
 *    `http://127.0.0.1:5173` 을 **둘 다** 등록해야 한다. 카카오는 origin 을
 *    완전일치로 검사하고 vite 는 127.0.0.1 로 프록시한다.
 */

let promise = null

export function kakaoKeyMissing() {
  return !import.meta.env.VITE_KAKAO_JS_KEY
}

export function loadKakaoMaps() {
  if (promise) return promise

  promise = new Promise((resolve, reject) => {
    const key = import.meta.env.VITE_KAKAO_JS_KEY
    if (!key) {
      reject(new Error('VITE_KAKAO_JS_KEY 가 설정되지 않았습니다'))
      return
    }
    if (window.kakao?.maps?.Map) {
      resolve(window.kakao.maps)
      return
    }

    const script = document.createElement('script')
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${key}&autoload=false`
    script.async = true
    script.onload = () => window.kakao.maps.load(() => resolve(window.kakao.maps))
    script.onerror = () =>
      reject(new Error('카카오맵 SDK를 불러오지 못했습니다. 키와 도메인 등록을 확인하세요.'))
    document.head.appendChild(script)
  })

  // 실패를 캐시하면 재시도가 영원히 막힌다.
  promise.catch(() => {
    promise = null
  })
  return promise
}
