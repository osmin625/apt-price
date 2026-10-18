/**
 * '지금이 자기 평균보다 얼마나 위·아래인가' 를 색으로. **탭 공통 규칙**이다.
 *
 * 값은 z — 자기 역사 평균에서 평소 오르내림 폭(표준편차)의 몇 배 떨어져 있나. 평균보다
 * 낮은 쪽은 파랑(`--heat-lo`), 높은 쪽은 빨강(`--heat-hi`), 평균은 칠하지 않는다. 진하기는
 * 평균에서 얼마나 멀리 갔는가이고 2배에서 가장 진하다. 거시 분석의 요인 카드에서 시작했고,
 * 공급 분석의 미분양·가격 분석의 국면 그림이 같은 색을 쓴다.
 *
 * **좋다·나쁘다가 아니고, 오름·내림도 아니다.** 미분양이 많아도, 집값이 높아도 같은 빨강이다.
 * 오름 초록 · 내림 빨강은 부호가 있는 값의 색이고(docs/screens/conventions.md), 이것은 위치의 색이다.
 *
 * 진하기는 **연속**이다. 세 칸으로 끊으면 0.49 와 0.51 이 전혀 다른 색이 된다.
 *
 * 예전 자는 백분위(지금보다 낮았던 달의 몫)였다. 백분위는 사실상 중위가 기준이라 맨 위 요인
 * 합산 카드(평균 기준)와 같은 요인이 다른 말을 했다 — 백엔드 `regime.hist_z` 주석.
 */

// 이만큼 벗어나면 가장 진하다. 정규분포라면 2배 바깥은 5% 남짓이다.
const FULL = 2

/** 카드 배경·왼쪽 띠에 쓰는 CSS 변수 묶음(`PanelCard` 의 `heat`). */
export function heatVars(z) {
  if (z == null || Number.isNaN(z)) return undefined
  const k = Math.min(Math.abs(z) / FULL, 1)
  return {
    '--heat-c': z >= 0 ? 'var(--heat-hi)' : 'var(--heat-lo)',
    // 배경은 최대 22% 만 섞는다 — 더 진하면 다크 모드에서 글자가 묻힌다.
    '--heat-mix': `${Math.round(k * 22)}%`,
    '--heat-edge': `${Math.round(25 + k * 75)}%`,
  }
}

/**
 * 점 하나의 색. 카드와 달리 배경이 아니라 점 자체를 칠하므로 평균을 회색
 * (`--text-muted`)으로 둔다 — 무색으로 두면 점이 사라진다.
 * SVG `fill` 속성이 아니라 `style` 로 넘겨야 `color-mix` 가 먹는다.
 */
export function heatColor(z) {
  if (z == null || Number.isNaN(z)) return 'var(--text-muted)'
  const k = Math.min(Math.abs(z) / FULL, 1)
  const c = z >= 0 ? 'var(--heat-hi)' : 'var(--heat-lo)'
  return `color-mix(in srgb, ${c} ${Math.round(20 + k * 80)}%, var(--text-muted))`
}

/**
 * `v` 가 자기 역사(`values`) 평균에서 표준편차 몇 배인가. + 면 평균보다 높다.
 * **탭 공통의 자** — 백엔드 `regime.hist_z` 와 같은 공식(모집단 표준편차)이다.
 */
export function histZ(values, v) {
  if (!values.length || v == null) return null
  const mu = values.reduce((a, b) => a + b, 0) / values.length
  const sd = Math.sqrt(values.reduce((a, b) => a + (b - mu) ** 2, 0) / values.length)
  return sd ? (v - mu) / sd : 0
}

/**
 * z 를 말로. 맨 위 요인 합산 카드의 '평소 오르내림 폭의 몇 배' 와 같은 말을 쓴다 —
 * 같은 요인이 카드마다 다른 단위로 말하지 않게.
 */
export function zText(z) {
  if (z == null || Number.isNaN(z)) return ''
  if (Math.abs(z) < 0.05) return '평균 수준'
  return `평균보다 ${z > 0 ? '높음' : '낮음'}(평소 폭의 ${Math.abs(z).toFixed(1)}배)`
}
