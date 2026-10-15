/**
 * '지금이 저점과 고점 사이 어디쯤인가' 를 색으로. **탭 공통 규칙**이다.
 *
 * 0 쪽(저점)은 파랑(`--heat-lo`), 1 쪽(고점)은 빨강(`--heat-hi`), 가운데(0.5)는
 * 칠하지 않는다. 진하기는 가운데에서 얼마나 멀리 갔는가다. 거시 분석 탭의 요인
 * 카드에서 시작했고, 공급 분석의 미분양·가격 분석의 국면 그림이 같은 색을 쓴다 —
 * 탭마다 빨강이 다른 뜻이면 볼 때마다 범례를 다시 읽어야 한다.
 *
 * **좋다·나쁘다가 아니다.** 미분양이 고점이어도, 집값이 고점이어도 같은 빨강이다.
 * 방향(오를지 내릴지)을 색에 실으면 상관이 음수인 요인에서 화살표와 엇갈린다.
 *
 * 진하기는 **연속**이다. 세 칸으로 끊으면 69% 와 71% 가 전혀 다른 색이 된다.
 */

/** 카드 배경·왼쪽 띠에 쓰는 CSS 변수 묶음(`PanelCard` 의 `heat`). */
export function heatVars(p) {
  if (p == null || Number.isNaN(p)) return undefined
  const k = Math.min(Math.abs(p - 0.5) * 2, 1)
  return {
    '--heat-c': p >= 0.5 ? 'var(--heat-hi)' : 'var(--heat-lo)',
    // 배경은 최대 22% 만 섞는다 — 더 진하면 다크 모드에서 글자가 묻힌다.
    '--heat-mix': `${Math.round(k * 22)}%`,
    '--heat-edge': `${Math.round(25 + k * 75)}%`,
  }
}

/**
 * 점 하나의 색. 카드와 달리 배경이 아니라 점 자체를 칠하므로 가운데를 회색
 * (`--text-muted`)으로 둔다 — 무색으로 두면 점이 사라진다.
 * SVG `fill` 속성이 아니라 `style` 로 넘겨야 `color-mix` 가 먹는다.
 */
export function heatColor(p) {
  if (p == null || Number.isNaN(p)) return 'var(--text-muted)'
  const k = Math.min(Math.abs(p - 0.5) * 2, 1)
  const c = p >= 0.5 ? 'var(--heat-hi)' : 'var(--heat-lo)'
  return `color-mix(in srgb, ${c} ${Math.round(20 + k * 80)}%, var(--text-muted))`
}

/** 값 목록 안에서 `v` 가 최저~최고 사이 어디인가(0~1). 폭이 0 이면 판단하지 않는다. */
export function rangePos(values, v) {
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  return hi > lo ? (v - lo) / (hi - lo) : null
}
