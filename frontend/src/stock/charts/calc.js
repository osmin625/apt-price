/**
 * 차트 탭의 지표 계산 — 같은 합성 가격(`sample.js`) 위에 지표를 그 정의대로 돌린다(docs/stock/charts.md).
 *
 * 그림을 손으로 그리지 않고 식을 돌리는 까닭은 기법 저장소와 같다(`techniques/synth.js` 머리말): 지표가 늦게 반응하면
 * 그림도 늦게 반응해야 그 지표의 실제 모습이다. 입력은 봉 배열 [{o,h,l,c,v}], 출력은 봉 수와 같은 길이의 배열이고
 * 값을 낼 수 없는 앞쪽은 null 이다.
 *
 * 정의가 여럿인 지표는 흔한 쪽을 골랐고 고른 쪽을 목록(`catalog`)의 '계산' 에 적는다 — 예: ATR 은 와일더 평활(RMA),
 * 모멘텀은 차(C − Cₙ)가 아니라 비율(C ÷ Cₙ × 100, 국내 HTS 관례). 몇 개는 scripts/verify_charts.py 가 파이썬으로 따로
 * 쓴 식과 같은 값을 내는지 본다.
 */

const isNum = (v) => v != null && Number.isFinite(v)
export const col = (b, k) => b.map((x) => x[k])
export const closeOf = (b) => col(b, 'c')

/* ── 평균·기본 ─────────────────────────────────────── */

/** 단순 이동평균 — 창 안에 null 이 있으면 null. */
export function sma(x, n) {
  return x.map((_, i) => {
    if (i < n - 1) return null
    let s = 0
    for (let k = i - n + 1; k <= i; k++) {
      if (!isNum(x[k])) return null
      s += x[k]
    }
    return s / n
  })
}

/** 지수 이동평균 — 첫 값이 나온 뒤 n 개의 단순 평균으로 시작한다. */
export function ema(x, n, alpha = 2 / (n + 1)) {
  const out = Array(x.length).fill(null)
  let prev = null
  let run = []
  for (let i = 0; i < x.length; i++) {
    const v = x[i]
    if (!isNum(v)) {
      if (prev == null) run = []
      out[i] = prev == null ? null : prev
      continue
    }
    if (prev == null) {
      run.push(v)
      if (run.length === n) {
        prev = run.reduce((a, b) => a + b, 0) / n
        out[i] = prev
      }
      continue
    }
    prev = prev + alpha * (v - prev)
    out[i] = prev
  }
  return out
}

/** 와일더 평활(RMA) — 지수 평균의 α 가 1/n. RSI·ATR·ADX 가 쓴다. */
export const rma = (x, n) => ema(x, n, 1 / n)

/** 가중 이동평균 — 최근 값일수록 무게 1…n. */
export function wma(x, n) {
  const den = (n * (n + 1)) / 2
  return x.map((_, i) => {
    if (i < n - 1) return null
    let s = 0
    for (let k = 0; k < n; k++) {
      const v = x[i - n + 1 + k]
      if (!isNum(v)) return null
      s += v * (k + 1)
    }
    return s / den
  })
}

/** 모표준편차(창 n). */
export function stdev(x, n) {
  const m = sma(x, n)
  return x.map((_, i) => {
    if (m[i] == null) return null
    let s = 0
    for (let k = i - n + 1; k <= i; k++) s += (x[k] - m[i]) ** 2
    return Math.sqrt(s / n)
  })
}

export const highest = (x, n) => x.map((_, i) => (i < n - 1 ? null : Math.max(...x.slice(i - n + 1, i + 1))))
export const lowest = (x, n) => x.map((_, i) => (i < n - 1 ? null : Math.min(...x.slice(i - n + 1, i + 1))))
export const shift = (x, k) => x.map((_, i) => (i - k >= 0 && i - k < x.length ? x[i - k] : null))
const zip = (a, b, f) => a.map((v, i) => (isNum(v) && isNum(b[i]) ? f(v, b[i]) : null))
export const sub = (a, b) => zip(a, b, (u, v) => u - v)
const div = (a, b, k = 1) => zip(a, b, (u, v) => (v === 0 ? null : (u / v) * k))
const sum = (x, n) => sma(x, n).map((v) => (v == null ? null : v * n))

/** 기울기 — 최근 n 개에 맞춘 직선(최소제곱)의 기울기와 끝점. */
export function linreg(x, n) {
  const slope = Array(x.length).fill(null)
  const end = Array(x.length).fill(null)
  const mx = (n - 1) / 2
  const sxx = Array.from({ length: n }, (_, k) => (k - mx) ** 2).reduce((a, b) => a + b, 0)
  for (let i = n - 1; i < x.length; i++) {
    const w = x.slice(i - n + 1, i + 1)
    if (!w.every(isNum)) continue
    const my = w.reduce((a, b) => a + b, 0) / n
    const b = w.reduce((s, v, k) => s + (k - mx) * (v - my), 0) / sxx
    slope[i] = b
    end[i] = my + b * (n - 1 - mx)
  }
  return { slope, end }
}

/* ── 가격 ─────────────────────────────────────────── */

export const typical = (b) => b.map((x) => (x.h + x.l + x.c) / 3)
export const median = (b) => b.map((x) => (x.h + x.l) / 2)
export function trueRange(b) {
  return b.map((x, i) => (i === 0 ? x.h - x.l : Math.max(x.h - x.l, Math.abs(x.h - b[i - 1].c), Math.abs(x.l - b[i - 1].c))))
}
export const atr = (b, n = 14) => rma(trueRange(b), n)
export const roc = (x, n) => x.map((v, i) => (i < n || !isNum(x[i - n]) || !isNum(v) ? null : (v / x[i - n] - 1) * 100))
export const momentum = (x, n) => x.map((v, i) => (i < n ? null : (v / x[i - n]) * 100))

/* ── 오버레이 ─────────────────────────────────────── */

export function bollinger(c, n = 20, k = 2) {
  const m = sma(c, n)
  const s = stdev(c, n)
  return { mid: m, up: zip(m, s, (a, d) => a + k * d), dn: zip(m, s, (a, d) => a - k * d) }
}

export function envelope(c, n = 20, p = 6) {
  const m = sma(c, n)
  return { mid: m, up: m.map((v) => (v == null ? null : v * (1 + p / 100))), dn: m.map((v) => (v == null ? null : v * (1 - p / 100))) }
}

export function keltner(b, n = 20, k = 2, an = 10) {
  const m = ema(closeOf(b), n)
  const a = atr(b, an)
  return { mid: m, up: zip(m, a, (u, v) => u + k * v), dn: zip(m, a, (u, v) => u - k * v) }
}

export function donchian(b, n = 20) {
  const up = highest(col(b, 'h'), n)
  const dn = lowest(col(b, 'l'), n)
  return { up, dn, mid: zip(up, dn, (u, v) => (u + v) / 2) }
}

/** 일목균형표 — 전환선 9·기준선 26·선행 스팬 26 앞으로·후행 스팬 26 뒤로. 그림 밖으로 나가는 앞쪽 26일은 자른다. */
export function ichimoku(b, a = 9, m = 26, s = 52) {
  const h = col(b, 'h')
  const l = col(b, 'l')
  const mid = (n) => zip(highest(h, n), lowest(l, n), (u, v) => (u + v) / 2)
  const tenkan = mid(a)
  const kijun = mid(m)
  const spanA = shift(zip(tenkan, kijun, (u, v) => (u + v) / 2), m)
  const spanB = shift(mid(s), m)
  const lag = closeOf(b).map((_, i) => (i + m < b.length ? b[i + m].c : null))
  return { tenkan, kijun, spanA, spanB, lag }
}

/** 파라볼릭 SAR — 가속 0.02 씩, 최대 0.2. */
export function psar(b, step = 0.02, max = 0.2) {
  const out = Array(b.length).fill(null)
  if (b.length < 2) return out
  let up = b[1].c >= b[0].c
  let sar = up ? b[0].l : b[0].h
  let ep = up ? b[0].h : b[0].l
  let af = step
  for (let i = 1; i < b.length; i++) {
    sar = sar + af * (ep - sar)
    if (up) {
      sar = Math.min(sar, b[i - 1].l, i > 1 ? b[i - 2].l : b[i - 1].l)
      if (b[i].l < sar) {
        up = false
        sar = ep
        ep = b[i].l
        af = step
      } else if (b[i].h > ep) {
        ep = b[i].h
        af = Math.min(max, af + step)
      }
    } else {
      sar = Math.max(sar, b[i - 1].h, i > 1 ? b[i - 2].h : b[i - 1].h)
      if (b[i].h > sar) {
        up = true
        sar = ep
        ep = b[i].h
        af = step
      } else if (b[i].l < ep) {
        ep = b[i].l
        af = Math.min(max, af + step)
      }
    }
    out[i] = sar
  }
  return out
}

/** 슈퍼트렌드 — 중간값 ± k × ATR 띠를 추세 방향으로만 조인다. */
export function supertrend(b, n = 10, k = 3) {
  const a = atr(b, n)
  const out = Array(b.length).fill(null)
  let upper = null
  let lower = null
  let dirUp = true
  for (let i = 0; i < b.length; i++) {
    if (a[i] == null) continue
    const mid = (b[i].h + b[i].l) / 2
    const bu = mid + k * a[i]
    const bl = mid - k * a[i]
    const pc = i ? b[i - 1].c : b[i].c
    upper = upper == null || bu < upper || pc > upper ? bu : upper
    lower = lower == null || bl > lower || pc < lower ? bl : lower
    if (dirUp && b[i].c < lower) dirUp = false
    else if (!dirUp && b[i].c > upper) dirUp = true
    out[i] = dirUp ? lower : upper
  }
  return out
}

/** 피봇 — 전날의 고가·저가·종가로 오늘의 기준선(P)과 1차 저항(R1)·지지(S1). */
export function pivot(b) {
  const p = b.map((_, i) => (i ? (b[i - 1].h + b[i - 1].l + b[i - 1].c) / 3 : null))
  return {
    p,
    r1: p.map((v, i) => (v == null ? null : 2 * v - b[i - 1].l)),
    s1: p.map((v, i) => (v == null ? null : 2 * v - b[i - 1].h)),
  }
}

/** 누적 VWAP — 그림 첫날부터. 장중 차트에서는 날마다 새로 시작한다. */
export function vwap(b) {
  let pv = 0
  let vv = 0
  return b.map((x) => {
    pv += ((x.h + x.l + x.c) / 3) * x.v
    vv += x.v
    return pv / vv
  })
}

/** 선형회귀 채널 — 마지막 n 개에 맞춘 직선 ± k × 잔차 표준편차(그림 끝 구간에만). */
export function regChannel(c, n = 60, k = 2) {
  const N = c.length
  const w = c.slice(N - n)
  const mx = (n - 1) / 2
  const my = w.reduce((a, v) => a + v, 0) / n
  const b = w.reduce((s, v, i) => s + (i - mx) * (v - my), 0) / w.reduce((s, _, i) => s + (i - mx) ** 2, 0)
  const fit = w.map((_, i) => my + b * (i - mx))
  const sd = Math.sqrt(w.reduce((s, v, i) => s + (v - fit[i]) ** 2, 0) / n)
  const pad = Array(N - n).fill(null)
  return { mid: [...pad, ...fit], up: [...pad, ...fit.map((v) => v + k * sd)], dn: [...pad, ...fit.map((v) => v - k * sd)] }
}

/** 지그재그 — p% 넘게 되돌아야 꼭대기·바닥이 확정된다. 확정점 사이를 직선으로 잇는다(마지막 다리는 지금까지). */
export function zigzag(c, p = 5) {
  // 방향은 첫 움직임으로 정하고 시작한다. 처음에 '방향 없음(0)' 으로 두고 극값을 위아래 둘 다 따라가게 했더니,
  // 극값이 늘 오늘 값이 되어 되돌림을 한 번도 못 쟀다 — 점 두 개짜리 직선이 나왔다(카기도 같았다).
  const piv = [[0, c[0]]]
  let dir = c[1] >= c[0] ? 1 : -1
  let ext = [0, c[0]]
  for (let i = 1; i < c.length; i++) {
    const back = dir > 0 ? c[i] <= ext[1] * (1 - p / 100) : c[i] >= ext[1] * (1 + p / 100)
    if (dir > 0 ? c[i] >= ext[1] : c[i] <= ext[1]) ext = [i, c[i]]
    else if (back) {
      if (ext[0] !== piv[piv.length - 1][0]) piv.push(ext)
      dir = -dir
      ext = [i, c[i]]
    }
  }
  piv.push([c.length - 1, c[c.length - 1]])
  const out = Array(c.length).fill(null)
  for (let k = 0; k < piv.length - 1; k++) {
    const [i0, v0] = piv[k]
    const [i1, v1] = piv[k + 1]
    for (let i = i0; i <= i1; i++) out[i] = v0 + ((v1 - v0) * (i - i0)) / Math.max(1, i1 - i0)
  }
  return out
}

/* ── 차트 유형 ───────────────────────────────────── */

export function heikinAshi(b) {
  const out = []
  b.forEach((x, i) => {
    const c = (x.o + x.h + x.l + x.c) / 4
    const o = i ? (out[i - 1].o + out[i - 1].c) / 2 : (x.o + x.c) / 2
    out.push({ o, c, h: Math.max(x.h, o, c), l: Math.min(x.l, o, c), v: x.v })
  })
  return out
}

/** 렌코 — 종가가 상자 크기만큼 움직일 때마다 벽돌 하나. 시간 축이 아니라 벽돌 순서다. */
export function renko(c, box) {
  const out = []
  let base = c[0]
  for (const v of c) {
    while (v >= base + box) {
      out.push({ o: base, c: base + box, h: base + box, l: base, v: 0 })
      base += box
    }
    while (v <= base - box) {
      out.push({ o: base, c: base - box, h: base, l: base - box, v: 0 })
      base -= box
    }
  }
  return out
}

/** 삼선전환도 — 같은 방향으로 새 고가(저가)면 선을 잇고, 마지막 세 선을 한꺼번에 넘어 되돌면 방향을 바꾼다. */
export function threeLineBreak(c, k = 3) {
  const lines = [{ o: c[0], c: c[0] }]
  for (const v of c.slice(1)) {
    const last = lines[lines.length - 1]
    const up = last.c >= last.o
    if ((up && v > last.c) || (!up && v < last.c)) {
      lines.push({ o: last.c, c: v })
      continue
    }
    const recent = lines.slice(-k)
    const lo = Math.min(...recent.map((x) => Math.min(x.o, x.c)))
    const hi = Math.max(...recent.map((x) => Math.max(x.o, x.c)))
    if (up && v < lo) lines.push({ o: Math.min(last.o, last.c), c: v })
    else if (!up && v > hi) lines.push({ o: Math.max(last.o, last.c), c: v })
  }
  return lines.slice(1).map((x) => ({ ...x, h: Math.max(x.o, x.c), l: Math.min(x.o, x.c), v: 0 }))
}

/** P&F — 상자 크기, 3칸 되돌림. 열 하나를 위(X)·아래(O) 막대로 돌려준다. */
export function pointFigure(c, box, rev = 3) {
  const cols = []
  let dir = 0
  let top = Math.floor(c[0] / box) * box
  let bot = top
  for (const v of c) {
    if (dir >= 0 && v >= top + box) {
      top = Math.floor(v / box) * box
      dir = 1
    } else if (dir <= 0 && v <= bot - box) {
      bot = Math.ceil(v / box) * box
      dir = -1
    } else if (dir === 1 && v <= top - rev * box) {
      cols.push({ o: bot, c: top })
      dir = -1
      bot = Math.ceil(v / box) * box
      top -= box
    } else if (dir === -1 && v >= bot + rev * box) {
      cols.push({ o: top, c: bot })
      dir = 1
      top = Math.floor(v / box) * box
      bot += box
    }
  }
  cols.push(dir >= 0 ? { o: bot, c: top } : { o: top, c: bot })
  return cols.map((x) => ({ ...x, h: Math.max(x.o, x.c), l: Math.min(x.o, x.c), v: 0 }))
}

/** 카기 — 반전 비율(p%) 넘게 되돌 때만 꺾는 선. 꺾인 점들을 잇는다. */
export function kagi(c, p = 4) {
  // 방향은 첫 움직임으로 정한다(지그재그의 주석 — '방향 없음' 으로 시작하면 한 번도 꺾이지 않는다).
  const pts = [c[0]]
  let dir = c[1] >= c[0] ? 1 : -1
  let ext = c[0]
  for (const v of c) {
    if (dir > 0 ? v >= ext : v <= ext) ext = v
    else if (dir > 0 ? v <= ext * (1 - p / 100) : v >= ext * (1 + p / 100)) {
      pts.push(ext)
      dir = -dir
      ext = v
    }
  }
  pts.push(c[c.length - 1])
  return pts
}

/* ── 추세 ─────────────────────────────────────────── */

export function macd(c, f = 12, s = 26, g = 9) {
  const line = sub(ema(c, f), ema(c, s))
  const signal = ema(line, g)
  return { line, signal, hist: sub(line, signal) }
}

export const ppo = (c, f = 12, s = 26) => div(sub(ema(c, f), ema(c, s)), ema(c, s), 100)
export const maOsc = (c, f = 5, s = 20) => sub(sma(c, f), sma(c, s))

/** DMI·ADX — 와일더 정의. */
export function dmi(b, n = 14) {
  const pdm = b.map((x, i) => {
    if (!i) return 0
    const u = x.h - b[i - 1].h
    const d = b[i - 1].l - x.l
    return u > d && u > 0 ? u : 0
  })
  const mdm = b.map((x, i) => {
    if (!i) return 0
    const u = x.h - b[i - 1].h
    const d = b[i - 1].l - x.l
    return d > u && d > 0 ? d : 0
  })
  const tr = rma(trueRange(b), n)
  const pdi = div(rma(pdm, n), tr, 100)
  const mdi = div(rma(mdm, n), tr, 100)
  const dx = zip(pdi, mdi, (p, m) => (p + m === 0 ? 0 : (Math.abs(p - m) / (p + m)) * 100))
  const adx = rma(dx, n)
  return { pdi, mdi, adx, adxr: zip(adx, shift(adx, n), (a, z) => (a + z) / 2) }
}

export function aroon(b, n = 25) {
  const h = col(b, 'h')
  const l = col(b, 'l')
  const since = (x, i, best) => {
    const w = x.slice(i - n, i + 1)
    return n - (w.length - 1 - w.lastIndexOf(best(...w)))
  }
  const up = b.map((_, i) => (i < n ? null : (since(h, i, Math.max) / n) * 100))
  const dn = b.map((_, i) => (i < n ? null : (since(l, i, Math.min) / n) * 100))
  return { up, dn, osc: sub(up, dn) }
}

export function vortex(b, n = 14) {
  const vp = b.map((x, i) => (i ? Math.abs(x.h - b[i - 1].l) : null))
  const vm = b.map((x, i) => (i ? Math.abs(x.l - b[i - 1].h) : null))
  const tr = trueRange(b).map((v, i) => (i ? v : null))
  return { plus: div(sum(vp, n), sum(tr, n)), minus: div(sum(vm, n), sum(tr, n)) }
}

export function trix(c, n = 12, g = 9) {
  const t = ema(ema(ema(c, n), n), n)
  const line = roc(t, 1)
  return { line, signal: ema(line, g) }
}

/** DPO — 가격에서 (n/2 + 1) 일 앞의 이동평균을 뺀다. 추세를 지워 주기만 남긴다. */
export const dpo = (c, n = 20) => sub(c, shift(sma(c, n), Math.floor(n / 2) + 1))
export const disparity = (c, n = 20) => div(c, sma(c, n), 100)
export const sonar = (c, n = 9, k = 9) => sub(ema(c, n), shift(ema(c, n), k))
export function elderRay(b, n = 13) {
  const e = ema(closeOf(b), n)
  return { bull: sub(col(b, 'h'), e), bear: sub(col(b, 'l'), e) }
}
export const qstick = (b, n = 10) => sma(b.map((x) => x.c - x.o), n)
export const coppock = (c, a = 14, b2 = 11, n = 10) => wma(zip(roc(c, a), roc(c, b2), (u, v) => u + v), n)
export function kst(c) {
  const parts = [[10, 10], [15, 10], [20, 10], [30, 15]].map(([r, s]) => sma(roc(c, r), s))
  const line = c.map((_, i) => (parts.every((p) => p[i] != null) ? parts.reduce((t, p, k) => t + p[i] * (k + 1), 0) : null))
  return { line, signal: sma(line, 9) }
}

/** 샤프 추세 주기(STC) — MACD(23,50) 에 스토캐스틱을 두 번, 매번 반만 따라가게(0.5) 다듬는다. */
export function stc(c, f = 23, s = 50, n = 10) {
  const m = sub(ema(c, f), ema(c, s))
  const stoch = (x) => {
    const out = Array(x.length).fill(null)
    let prev = null
    for (let i = 0; i < x.length; i++) {
      const w = x.slice(Math.max(0, i - n + 1), i + 1).filter(isNum)
      if (!isNum(x[i]) || w.length < n) continue
      const lo = Math.min(...w)
      const hi = Math.max(...w)
      const k = hi === lo ? (prev ?? 50) : ((x[i] - lo) / (hi - lo)) * 100
      prev = prev == null ? k : prev + 0.5 * (k - prev)
      out[i] = prev
    }
    return out
  }
  return stoch(stoch(m))
}

/* ── 모멘텀 ───────────────────────────────────────── */

export function rsi(c, n = 14) {
  const d = c.map((v, i) => (i ? v - c[i - 1] : null))
  const up = rma(d.map((v) => (v == null ? null : Math.max(v, 0))), n)
  const dn = rma(d.map((v) => (v == null ? null : Math.max(-v, 0))), n)
  return zip(up, dn, (u, v) => (v === 0 ? 100 : 100 - 100 / (1 + u / v)))
}

/** 스토캐스틱 — %K(n) 를 s 로 다듬고(슬로우), %D 는 그 m 평균. s = 1 이면 패스트. */
export function stochastic(b, n = 14, s = 3, m = 3) {
  const hh = highest(col(b, 'h'), n)
  const ll = lowest(col(b, 'l'), n)
  const raw = b.map((x, i) => (hh[i] == null ? null : hh[i] === ll[i] ? 50 : ((x.c - ll[i]) / (hh[i] - ll[i])) * 100))
  const k = s > 1 ? sma(raw, s) : raw
  return { k, d: sma(k, m) }
}

export function stochRsi(c, n = 14, s = 3, m = 3) {
  const r = rsi(c, n)
  const raw = r.map((v, i) => {
    if (v == null || i < n - 1) return null
    const w = r.slice(i - n + 1, i + 1)
    if (!w.every(isNum)) return null
    const lo = Math.min(...w)
    const hi = Math.max(...w)
    return hi === lo ? 50 : ((v - lo) / (hi - lo)) * 100
  })
  const k = sma(raw, s)
  return { k, d: sma(k, m) }
}

export function williamsR(b, n = 14) {
  const hh = highest(col(b, 'h'), n)
  const ll = lowest(col(b, 'l'), n)
  return b.map((x, i) => (hh[i] == null || hh[i] === ll[i] ? null : ((hh[i] - x.c) / (hh[i] - ll[i])) * -100))
}

/** CCI — (전형가 − 평균) ÷ (0.015 × 평균 절대 편차). */
export function cci(b, n = 20) {
  const tp = typical(b)
  const m = sma(tp, n)
  return tp.map((v, i) => {
    if (m[i] == null) return null
    let md = 0
    for (let k = i - n + 1; k <= i; k++) md += Math.abs(tp[k] - m[i])
    md /= n
    return md === 0 ? 0 : (v - m[i]) / (0.015 * md)
  })
}

export function cmo(c, n = 14) {
  const d = c.map((v, i) => (i ? v - c[i - 1] : null))
  const su = sum(d.map((v) => (v == null ? null : Math.max(v, 0))), n)
  const sd = sum(d.map((v) => (v == null ? null : Math.max(-v, 0))), n)
  return zip(su, sd, (u, v) => (u + v === 0 ? 0 : ((u - v) / (u + v)) * 100))
}

export function ultimate(b, a = 7, m = 14, l = 28) {
  const bp = b.map((x, i) => (i ? x.c - Math.min(x.l, b[i - 1].c) : null))
  const tr = b.map((x, i) => (i ? Math.max(x.h, b[i - 1].c) - Math.min(x.l, b[i - 1].c) : null))
  const avg = (n) => div(sum(bp, n), sum(tr, n))
  const [x, y, z] = [avg(a), avg(m), avg(l)]
  return x.map((v, i) => (v == null || y[i] == null || z[i] == null ? null : ((4 * v + 2 * y[i] + z[i]) / 7) * 100))
}

/** RMI — RSI 의 하루 변화 대신 k 일 변화를 쓴다. */
export function rmi(c, n = 14, k = 5) {
  const d = c.map((v, i) => (i >= k ? v - c[i - k] : null))
  const up = rma(d.map((v) => (v == null ? null : Math.max(v, 0))), n)
  const dn = rma(d.map((v) => (v == null ? null : Math.max(-v, 0))), n)
  return zip(up, dn, (u, v) => (v === 0 ? 100 : 100 - 100 / (1 + u / v)))
}

/** SMI — 종가가 n 일 범위의 가운데에서 얼마나 떨어졌나를 두 번 다듬어 범위의 반으로 나눈다. */
export function smi(b, n = 10, s1 = 3, s2 = 3, g = 3) {
  const hh = highest(col(b, 'h'), n)
  const ll = lowest(col(b, 'l'), n)
  const rel = b.map((x, i) => (hh[i] == null ? null : x.c - (hh[i] + ll[i]) / 2))
  const rng = zip(hh, ll, (u, v) => u - v)
  const line = div(ema(ema(rel, s1), s2), ema(ema(rng, s1), s2).map((v) => (v == null ? null : v / 2)), 100)
  return { line, signal: ema(line, g) }
}

export const psychological = (c, n = 10) =>
  c.map((_, i) => (i < n ? null : (c.slice(i - n + 1, i + 1).filter((v, k) => v > c[i - n + k]).length / n) * 100))

export function tsi(c, r = 25, s = 13, g = 7) {
  const d = c.map((v, i) => (i ? v - c[i - 1] : null))
  const line = div(ema(ema(d, r), s), ema(ema(d.map((v) => (v == null ? null : Math.abs(v))), r), s), 100)
  return { line, signal: ema(line, g) }
}

export const awesome = (b) => sub(sma(median(b), 5), sma(median(b), 34))
export const accel = (b) => sub(awesome(b), sma(awesome(b), 5))

export function connorsRsi(c) {
  let streak = 0
  const st = c.map((v, i) => {
    if (!i) return 0
    if (v > c[i - 1]) streak = streak > 0 ? streak + 1 : 1
    else if (v < c[i - 1]) streak = streak < 0 ? streak - 1 : -1
    else streak = 0
    return streak
  })
  const r1 = roc(c, 1)
  const rank = r1.map((v, i) => {
    if (v == null || i < 100) return null
    const w = r1.slice(i - 100, i)
    return (w.filter((x) => x < v).length / 100) * 100
  })
  const a = rsi(c, 3)
  const bb = rsi(st, 2)
  return a.map((v, i) => (v == null || bb[i] == null || rank[i] == null ? null : (v + bb[i] + rank[i]) / 3))
}

export function fisher(b, n = 10) {
  const m = median(b)
  const hh = highest(m, n)
  const ll = lowest(m, n)
  let v = 0
  let f = 0
  return m.map((x, i) => {
    if (hh[i] == null) return null
    const raw = hh[i] === ll[i] ? 0 : 2 * ((x - ll[i]) / (hh[i] - ll[i]) - 0.5)
    v = Math.max(-0.999, Math.min(0.999, 0.33 * raw + 0.67 * v))
    f = 0.5 * Math.log((1 + v) / (1 - v)) + 0.5 * f
    return f
  })
}

export function demarker(b, n = 14) {
  const mx = b.map((x, i) => (i ? Math.max(x.h - b[i - 1].h, 0) : null))
  const mn = b.map((x, i) => (i ? Math.max(b[i - 1].l - x.l, 0) : null))
  const a = sma(mx, n)
  const z = sma(mn, n)
  return zip(a, z, (u, v) => (u + v === 0 ? 0.5 : u / (u + v)))
}

/** RVI(상대 활력) — (종가 − 시가) 를 (고가 − 저가) 로 나눈 것을 1·2·2·1 로 다듬은 뒤 n 합끼리. */
export function rvigor(b, n = 10) {
  const w4 = (x) => x.map((_, i) => (i < 3 ? null : (x[i] + 2 * x[i - 1] + 2 * x[i - 2] + x[i - 3]) / 6))
  const line = div(sum(w4(b.map((x) => x.c - x.o)), n), sum(w4(b.map((x) => x.h - x.l)), n))
  return { line, signal: w4(line) }
}

export const bop = (b, n = 14) => sma(b.map((x) => (x.h === x.l ? 0 : (x.c - x.o) / (x.h - x.l))), n)

export function imi(b, n = 14) {
  const g = sum(b.map((x) => Math.max(x.c - x.o, 0)), n)
  const l = sum(b.map((x) => Math.max(x.o - x.c, 0)), n)
  return zip(g, l, (u, v) => (u + v === 0 ? 50 : (u / (u + v)) * 100))
}

/* ── 변동성 ───────────────────────────────────────── */

export const natr = (b, n = 14) => div(atr(b, n), closeOf(b), 100)
export function histVol(c, n = 20) {
  const r = c.map((v, i) => (i ? Math.log(v / c[i - 1]) : null))
  return stdev(r.map((v) => v), n).map((v, i) => (v == null || i < n ? null : v * Math.sqrt(252) * 100))
}
export function percentB(c, n = 20, k = 2) {
  const bb = bollinger(c, n, k)
  return c.map((v, i) => (bb.up[i] == null ? null : ((v - bb.dn[i]) / (bb.up[i] - bb.dn[i])) * 100))
}
export function bandwidth(c, n = 20, k = 2) {
  const bb = bollinger(c, n, k)
  return c.map((_, i) => (bb.up[i] == null ? null : ((bb.up[i] - bb.dn[i]) / bb.mid[i]) * 100))
}
export const chaikinVol = (b, n = 10) => roc(ema(b.map((x) => x.h - x.l), n), n)
export function massIndex(b, n = 25) {
  const r = b.map((x) => x.h - x.l)
  const e1 = ema(r, 9)
  return sum(div(e1, ema(e1, 9)), n)
}
export function ulcer(c, n = 14) {
  const hh = highest(c, n)
  const dd = c.map((v, i) => (hh[i] == null ? null : ((v - hh[i]) / hh[i]) * 100) ** 2)
  return sma(dd.map((v, i) => (hh[i] == null ? null : v)), n).map((v) => (v == null ? null : Math.sqrt(v)))
}
export function relVolatility(c, n = 14, s = 10) {
  const sd = stdev(c, s)
  const up = rma(c.map((v, i) => (!i || sd[i] == null ? null : v > c[i - 1] ? sd[i] : 0)), n)
  const dn = rma(c.map((v, i) => (!i || sd[i] == null ? null : v < c[i - 1] ? sd[i] : 0)), n)
  return zip(up, dn, (u, v) => (u + v === 0 ? 50 : (u / (u + v)) * 100))
}
export function chop(b, n = 14) {
  const s = sum(trueRange(b), n)
  const hh = highest(col(b, 'h'), n)
  const ll = lowest(col(b, 'l'), n)
  return s.map((v, i) => (v == null || hh[i] === ll[i] ? null : (100 * Math.log10(v / (hh[i] - ll[i]))) / Math.log10(n)))
}

/* ── 거래량 ───────────────────────────────────────── */

export const vol = (b) => col(b, 'v')
export function obv(b) {
  let s = 0
  return b.map((x, i) => {
    if (i) s += x.c > b[i - 1].c ? x.v : x.c < b[i - 1].c ? -x.v : 0
    return s
  })
}
export function vr(b, n = 20) {
  const up = b.map((x, i) => (!i ? null : x.c > b[i - 1].c ? x.v : x.c === b[i - 1].c ? x.v / 2 : 0))
  const dn = b.map((x, i) => (!i ? null : x.c < b[i - 1].c ? x.v : x.c === b[i - 1].c ? x.v / 2 : 0))
  return div(sum(up, n), sum(dn, n), 100)
}
const clv = (x) => (x.h === x.l ? 0 : (x.c - x.l - (x.h - x.c)) / (x.h - x.l))
export function adl(b) {
  let s = 0
  return b.map((x) => (s += clv(x) * x.v))
}
export const chaikinOsc = (b) => sub(ema(adl(b), 3), ema(adl(b), 10))
export const cmf = (b, n = 20) => div(sum(b.map((x) => clv(x) * x.v), n), sum(vol(b), n))
export function mfi(b, n = 14) {
  const tp = typical(b)
  const pos = tp.map((v, i) => (!i ? null : v > tp[i - 1] ? v * b[i].v : 0))
  const neg = tp.map((v, i) => (!i ? null : v < tp[i - 1] ? v * b[i].v : 0))
  return zip(sum(pos, n), sum(neg, n), (p, q) => (q === 0 ? 100 : 100 - 100 / (1 + p / q)))
}
export function pvt(b) {
  let s = 0
  return b.map((x, i) => (i ? (s += ((x.c - b[i - 1].c) / b[i - 1].c) * x.v) : 0))
}
/** NVI·PVI — 거래량이 준 날(NVI)·는 날(PVI)의 수익률만 쌓는다. 1000 에서 시작. */
function vi(b, neg) {
  let s = 1000
  return b.map((x, i) => {
    if (i && (neg ? x.v < b[i - 1].v : x.v > b[i - 1].v)) s *= x.c / b[i - 1].c
    return s
  })
}
export const nvi = (b) => vi(b, true)
export const pvi = (b) => vi(b, false)
export const force = (b, n = 13) => ema(b.map((x, i) => (i ? (x.c - b[i - 1].c) * x.v : null)), n)
export function eom(b, n = 14) {
  const raw = b.map((x, i) => {
    if (!i || x.h === x.l) return null
    const move = (x.h + x.l) / 2 - (b[i - 1].h + b[i - 1].l) / 2
    return move / (x.v / 1e4 / (x.h - x.l))
  })
  return sma(raw, n)
}
export const volOsc = (b, f = 5, s = 20) => div(sub(ema(vol(b), f), ema(vol(b), s)), ema(vol(b), s), 100)
export const vroc = (b, n = 12) => roc(vol(b), n)
export function klinger(b, f = 34, s = 55, g = 13) {
  const tp = typical(b)
  const vf = b.map((x, i) => (!i ? null : (tp[i] >= tp[i - 1] ? 1 : -1) * x.v))
  const line = sub(ema(vf, f), ema(vf, s))
  return { line, signal: ema(line, g) }
}
export function williamsAD(b) {
  let s = 0
  return b.map((x, i) => {
    if (!i) return 0
    const pc = b[i - 1].c
    if (x.c > pc) s += x.c - Math.min(x.l, pc)
    else if (x.c < pc) s += x.c - Math.max(x.h, pc)
    return s
  })
}
export const amount = (b) => b.map((x) => x.c * x.v)
