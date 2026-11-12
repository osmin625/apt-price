/**
 * 기법 저장소의 **합성 예시** — 모양을 정해 둔 가짜 가격과, 그 위에 기법의 규칙을 그대로 적용하는 지표 계산.
 *
 * ## 왜 손으로 그리지 않고 규칙을 돌리나
 *
 * 예시 그림의 매수·매도 표시를 손으로 찍으면 '규칙대로라면 여기서 신호가 난다' 가 아니라 '여기서 났으면
 * 좋겠다' 가 된다. 그래서 가격만 모양을 정해 만들고(`path`), 신호는 기법의 규칙(`sma`·`rsi`·`cross` …)을
 * 그 가격에 돌려 얻는다. 규칙이 늦게 반응하면 그림도 늦게 찍힌다 — 그게 그 기법의 실제 모습이다.
 *
 * ## 같은 그림이 매번 나온다
 *
 * 잡음은 씨앗을 정한 난수(mulberry32)다. 열 때마다 그림이 바뀌면 설명 글('두 번째 바닥에서')이 어긋난다.
 *
 * 실제 지수에서 그 모양이 나온 구간은 백엔드가 같은 규칙을 실제 종가에 돌려 붙인다(backend/app/stock/trading.py —
 * 지표 정의가 여기와 같은지는 scripts/verify_short_rules.py 가 본다).
 */

export function rng(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** 표준 정규 하나(박스–뮬러). */
const gauss = (r) => Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r())

/**
 * 꼭짓점 [[날, 값], …] 사이를 잇고 잡음을 얹은 종가. `noise` 는 하루 잡음의 표준편차(값의 비율).
 * 잡음은 서로 이어진다(AR(1), 0.6) — 하루씩 독립이면 톱니처럼 보여 차트 같지 않다.
 */
export function path(points, { seed = 1, noise = 0.006 } = {}) {
  const r = rng(seed)
  const n = points[points.length - 1][0] + 1
  const out = []
  let e = 0
  for (let i = 0, k = 0; i < n; i++) {
    while (k < points.length - 2 && i > points[k + 1][0]) k++
    const [x0, y0] = points[k]
    const [x1, y1] = points[k + 1]
    const base = x1 === x0 ? y1 : y0 + ((y1 - y0) * (i - x0)) / (x1 - x0)
    e = 0.6 * e + gauss(r) * noise
    out.push(base * (1 + e))
  }
  return out
}

/** 종가에서 시가·고가·저가·거래량을 지어낸다 — 캔들·거래량 기법의 예시용. `shape` 로 특정 날의 캔들을 정한다. */
export function bars(close, { seed = 7, vol = 1000, shape = {} } = {}) {
  const r = rng(seed)
  return close.map((c, i) => {
    const o = i ? close[i - 1] * (1 + gauss(r) * 0.002) : c
    const spread = Math.abs(c - o) + c * (0.003 + r() * 0.006)
    let b = { o, c, h: Math.max(o, c) + spread * r() * 0.6, l: Math.min(o, c) - spread * r() * 0.6,
              v: vol * (0.7 + r() * 0.6) * (1 + Math.abs(c - o) / c * 40) }
    if (shape[i]) b = { ...b, ...shape[i](b, close[i - 1] ?? c) }
    return b
  })
}

/* ── 지표 — 기법의 규칙 그대로 ─────────────────────────── */

export function sma(x, n) {
  const out = Array(x.length).fill(null)
  let s = 0
  for (let i = 0; i < x.length; i++) {
    s += x[i]
    if (i >= n) s -= x[i - n]
    if (i >= n - 1) out[i] = s / n
  }
  return out
}

export function ema(x, n) {
  const k = 2 / (n + 1)
  const out = Array(x.length).fill(null)
  let e = null
  for (let i = 0; i < x.length; i++) {
    if (x[i] == null) continue
    e = e == null ? x[i] : x[i] * k + e * (1 - k)
    out[i] = e
  }
  return out
}

export function stdev(x, n) {
  const m = sma(x, n)
  return x.map((_, i) => {
    if (m[i] == null) return null
    let s = 0
    for (let j = i - n + 1; j <= i; j++) s += (x[j] - m[i]) ** 2
    return Math.sqrt(s / n)
  })
}

/** 와일더의 RSI — 평균은 단순 평균이 아니라 와일더 평활(1/n)이다. */
export function rsi(x, n = 14) {
  const out = Array(x.length).fill(null)
  let up = 0
  let dn = 0
  for (let i = 1; i < x.length; i++) {
    const d = x[i] - x[i - 1]
    const u = Math.max(d, 0)
    const w = Math.max(-d, 0)
    if (i <= n) {
      up += u / n
      dn += w / n
    } else {
      up = (up * (n - 1) + u) / n
      dn = (dn * (n - 1) + w) / n
    }
    if (i >= n) out[i] = dn === 0 ? 100 : 100 - 100 / (1 + up / dn)
  }
  return out
}

export function macd(x, fast = 12, slow = 26, sig = 9) {
  const f = ema(x, fast)
  const s = ema(x, slow)
  const line = x.map((_, i) => (i >= slow - 1 ? f[i] - s[i] : null))
  const signal = ema(line, sig)
  return { line, signal, hist: line.map((v, i) => (v == null || signal[i] == null ? null : v - signal[i])) }
}

/** 지난 n일(오늘 제외)의 최고·최저 — 돌파는 '어제까지의' 고점을 오늘 넘는 것이다. */
export function channel(x, n) {
  return x.map((_, i) => {
    if (i < n) return { hi: null, lo: null }
    const w = x.slice(i - n, i)
    return { hi: Math.max(...w), lo: Math.min(...w) }
  })
}

export function stochastic(b, n = 14, d = 3) {
  const k = b.map((_, i) => {
    if (i < n - 1) return null
    const w = b.slice(i - n + 1, i + 1)
    const hi = Math.max(...w.map((x) => x.h))
    const lo = Math.min(...w.map((x) => x.l))
    return hi === lo ? 50 : ((b[i].c - lo) / (hi - lo)) * 100
  })
  const dd = k.map((_, i) => {
    const w = k.slice(Math.max(0, i - d + 1), i + 1)
    return w.length < d || w.some((v) => v == null) ? null : w.reduce((a, v) => a + v, 0) / d
  })
  return { k, d: dd }
}

export function obv(b) {
  let s = 0
  return b.map((x, i) => {
    if (i) s += x.c > b[i - 1].c ? x.v : x.c < b[i - 1].c ? -x.v : 0
    return s
  })
}

/** 장중 VWAP — 그날 처음부터의 (전형가 × 거래량) 합 / 거래량 합. */
export function vwap(b) {
  let pv = 0
  let v = 0
  return b.map((x) => {
    pv += ((x.h + x.l + x.c) / 3) * x.v
    v += x.v
    return pv / v
  })
}

/** a 가 b 를 위로 뚫은 날(+1)·아래로 뚫은 날(−1). */
export function crosses(a, b) {
  const out = []
  for (let i = 1; i < a.length; i++) {
    const bi = typeof b === 'number' ? b : b[i]
    const bp = typeof b === 'number' ? b : b[i - 1]
    if ([a[i], a[i - 1], bi, bp].some((v) => v == null)) continue
    if (a[i - 1] <= bp && a[i] > bi) out.push({ i, dir: 1 })
    if (a[i - 1] >= bp && a[i] < bi) out.push({ i, dir: -1 })
  }
  return out
}
