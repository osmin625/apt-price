import { bars, path } from '../techniques/synth.js'

/**
 * 차트 탭의 예시 가격 — **모든 지표가 같은 가격** 위에 그려진다. 지표를 바꿔 가며 같은 구간에서 어떻게 다르게
 * 반응하는지 견주라는 것이다(오르는 구간 → 옆걸음 → 급락 → 되오름). 실제 종목이 아니라 모양을 정해 만든 가격이라
 * 값에는 뜻이 없다 — 화면이 '합성 가격' 이라고 적는다.
 *
 * 앞 60일은 그리지 않고 계산에만 쓴다. 52일·60일 창을 쓰는 지표(일목 선행 스팬 B, 그물망)가 그림 첫날부터 값이
 * 있어야 지표끼리 같은 구간을 견줄 수 있다.
 */
export const WARM = 60
const close = path(
  [[0, 100], [40, 104], [60, 100], [120, 132], [140, 128], [175, 131], [200, 108], [215, 103], [245, 118], [279, 124]],
  { seed: 20261127, noise: 0.009 },
)
export const BARS = bars(close, { seed: 11, vol: 1000 })
export const N = BARS.length - WARM

/** 계산은 전체, 그림은 앞 WARM 일을 뺀 것. */
export const cut = (x) => x.slice(WARM)

const C = ['var(--series-2)', 'var(--series-3)', 'var(--series-4)', 'var(--series-1)']

/** 가격 위에 선을 얹은 그림. lines: [[이름, 값 배열, 점선?]] — 값 배열은 전체 길이. */
export function over(lines, { candle = true, band = null } = {}) {
  return {
    ...(candle ? { bars: cut(BARS) } : { close: cut(BARS.map((b) => b.c)) }),
    priceLabel: candle ? '가격(캔들)' : '종가',
    overlays: lines.map(([label, values, dash], k) => ({ label, values: cut(values), color: C[k % C.length], dash })),
    ...(band ? { band: { label: band[0], hi: cut(band[1]), lo: cut(band[2]) } } : {}),
  }
}

/** 가격 아래 칸에 지표. series: [[이름, 값 배열, 막대?]]. levels — 읽는 기준선. */
export function osc(label, series, { levels = [], range = null, lines = [] } = {}) {
  return {
    ...over(lines, { candle: false }),
    panel: {
      label,
      series: series.map(([name, values, bar], k) => ({ label: name, values: cut(values), color: C[k % C.length], bar })),
      levels,
      range,
    },
  }
}
