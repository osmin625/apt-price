import { useEffect, useRef, useState } from 'react'

/**
 * 기다리는 동안 **얼마나 기다렸는지**를 보여 준다.
 *
 * ## 왜 퍼센트가 아니라 경과 시간인가
 *
 * 적합이 얼마나 걸릴지는 시작할 때 알 수 없다. 캐시가 있으면 0.02초, 없으면 데이터
 * 양에 따라 수 초에서 수십 초다. 그런데도 진행 막대를 채우면 그 퍼센트는 거짓말이
 * 된다 — 70%에서 멈춰 있는 막대는 아무 정보도 주지 않으면서 곧 끝날 것처럼 보인다.
 *
 * 그래서 **확실히 아는 것만** 보여 준다: 지금까지 몇 초 걸렸는지. 막대는 진행률이
 * 아니라 '살아 있다' 는 표시라 방향만 있고 끝이 없다.
 *
 * ## 빠를 때는 나타나지 않는다
 *
 * 0.02초짜리 응답에 로딩 표시가 깜빡이면 화면이 더 시끄럽다. `delay` 동안은 아무것도
 * 그리지 않고, 그 안에 끝나면 사용자는 로딩이 있었다는 것도 모른다.
 *
 * `slowAfter` 를 넘기면 `hint` 를 덧붙인다. 오래 걸리는 데 이유가 있으면 그때 말한다 —
 * 처음부터 "30초 걸릴 수 있습니다" 라고 적어 두면 0.02초에 끝나는 대부분의 경우에
 * 괜히 겁을 준다.
 */
export default function Loading({
  label = '불러오는 중',
  hint,
  delay = 400,
  slowAfter = 6,
  compact = false,
}) {
  const [shown, setShown] = useState(false)
  const [sec, setSec] = useState(0)
  const startedAt = useRef(0)

  useEffect(() => {
    startedAt.current = performance.now()
    const show = setTimeout(() => setShown(true), delay)
    const tick = setInterval(
      () => setSec((performance.now() - startedAt.current) / 1000),
      100,
    )
    return () => {
      clearTimeout(show)
      clearInterval(tick)
    }
  }, [delay])

  if (!shown) return null

  const slow = sec >= slowAfter

  return (
    <div className={`loading${compact ? ' is-compact' : ''}`} role="status" aria-live="polite">
      <div className="loading-top">
        <span className="loading-label">{label}</span>
        <span className="loading-sec">{sec.toFixed(1)}초</span>
      </div>
      <div className="loading-bar" aria-hidden="true">
        <span />
      </div>
      {slow && hint && <p className="loading-hint">{hint}</p>}
    </div>
  )
}

/**
 * 적합을 기다리는 화면들이 공유하는 안내. 여러 탭이 **같은 적합**을 쓰므로
 * 설명도 같아야 한다 — 한 곳에서 고치면 전부 따라온다.
 */
export const FIT_HINT =
  '헤도닉 적합은 캐시가 비어 있으면 처음 한 번 오래 걸립니다(거래 11만 건 · 단지 2천 곳). ' +
  '한 번 계산하면 다음부터는 즉시 열리고, 서버를 다시 띄워도 디스크 캐시에서 읽습니다.'
