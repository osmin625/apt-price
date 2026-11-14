/**
 * 기술주 가치 분해 — 시가총액 = 지금 사업 + Σ 기대 기술(확률 × 실현 때 값을 지금으로 할인) + 설명 안 된 몫.
 *
 * 화면에서 시나리오를 바꿔 보려면 계산이 브라우저에 있어야 해서 여기 둔다(정적 사이트에는 서버가 없다). 재료는
 * backend/app/stock/techvalue.py 가 낸다. 같은 계산을 파이썬으로 따로 써서 scripts/verify_tech_value.py 가 대조한다.
 * 규칙과 이유는 docs/stock/tech-value.md.
 *
 * 단위: 금액은 달러, 이익 시나리오(profit)는 십억 달러, 금리·성장률·할인율은 %.
 *
 *   지금 사업 = E0 / (r − g)              E0 는 지난 12개월 이익. 적자면 0 — 적자를 영원히 이어 가는 값으로 빼지 않는다
 *                                         (그 적자는 기대 기술에 쓰는 돈으로 본다)
 *   기술 k 의 지금 값 = p · (P · PER) / (1 + r)^t     t = 실현 해의 한가운데까지 남은 해
 *   설명 안 된 몫 = 시가총액 − 지금 사업 − Σ 기술
 *
 * 역산은 '다른 기술은 시나리오대로 두고, 남는 몫을 이 기술 하나가 다 설명한다면' 이다.
 *   필요 이익 P* = (시가총액 − 지금 사업 − 다른 기술) · (1 + r)^t / (p · PER)
 *   필요 시점   t* = ln(p · P · PER / 남는 몫) / ln(1 + r)   — 그 이익이라면 언제 실현돼야 하나
 *
 * 실현 때 주가 = (그때의 지금 사업 이익 + 기술 이익) × PER / 주식 수. 확률은 넣지 않는다(실현됐다면).
 * 지금 주가에서 그 주가까지의 연 수익률을 할인율과 견준다 — 할인율보다 낮으면 그 기술만으로는 지금 주가가 안 맞는다.
 *
 * 가치는 실적 발표 때에만 다시 잰다(backend/app/stock/earnings.py). 그래서 할인의 기준 시점 `now` 는 마지막 발표일이고,
 * 연 수익률의 기준 `pnow` 는 지금 주가의 날이다(없으면 now).
 */

export const MID = 0.5

/** 날짜 'YYYYMMDD' → 연 단위 수(2026-07-02 ≈ 2026.5). */
export function yearOf(d) {
  const y = +d.slice(0, 4)
  const start = Date.UTC(y, 0, 1)
  const t = Date.UTC(y, +d.slice(4, 6) - 1, +d.slice(6, 8))
  return y + (t - start) / (Date.UTC(y + 1, 0, 1) - start)
}

export function rate({ y10, beta, erp }) {
  return y10 + beta * erp
}

/** 지금 사업의 이익(달러) — 'op' 면 영업이익 × (1 − 세율), 없거나 'ni' 면 순이익. */
export function baseEarnings(ttm, mode, tax) {
  if (mode === 'op' && ttm.operating_income) return ttm.operating_income.value * (1 - tax / 100)
  return ttm.net_income ? ttm.net_income.value : 0
}

export function decompose({ cap, shares, price, e0, g, r, now, pnow, techs }) {
  const R = r / 100
  const G = g / 100
  const base = e0 > 0 && R > G ? e0 / (R - G) : 0
  const rows = techs.map((t) => {
    const dt = Math.max(t.year + MID - now, 0)
    const value = t.profit * 1e9 * t.pe
    const pv = (t.prob * value) / (1 + R) ** dt
    return { ...t, dt, value, pv }
  })
  const sum = rows.reduce((a, t) => a + t.pv, 0)
  const residual = cap - base - sum
  for (const t of rows) {
    const gap = cap - base - (sum - t.pv)
    t.gap = gap
    t.need = gap > 0 ? (gap * (1 + R) ** t.dt) / (t.prob * t.pe) / 1e9 : 0
    // 그 이익이라면 언제 실현돼야 하나 — 지금 실현돼도 모자라면 null
    t.needYear = gap > 0 && t.prob * t.value > gap ? now + Math.log((t.prob * t.value) / gap) / Math.log(1 + R) - MID : null
    const eT = Math.max(e0, 0) * (1 + G) ** t.dt + t.profit * 1e9
    t.priceAt = (eT * t.pe) / shares
    const dp = t.year + MID - (pnow ?? now)
    t.cagr = dp > 0 ? ((t.priceAt / price) ** (1 / dp) - 1) * 100 : null
  }
  return { cap, base, techs: rows, sum, residual, r }
}

/**
 * 실적 발표 하나 때의 주당 가치 — 그 발표 때 알던 이익·주식 수·10년 국채·베타로 같은 분해를 한다. 시나리오는 지금 것이다.
 * 그림의 주가가 수정 종가라 같은 눈금에 놓으려고 수정 종가 ÷ 종가를 곱한다(분할 전 주식 수로 나눈 값은 분할 전 주가 단위다).
 * 재료가 모자라면(베타를 잴 월봉이 24달이 안 되는 등) null.
 */
export function valueAt(rel, { mode, tax, erp, g, techs }) {
  if (rel.pending || !rel.shares || !rel.close || !rel.adj || rel.beta == null || rel.y10 == null) return null
  const ttm = Object.fromEntries(Object.entries(rel.ttm).map(([k, v]) => [k, v == null ? null : { value: v }]))
  const e0 = baseEarnings(ttm, mode, tax)
  const r = rate({ y10: rel.y10, beta: rel.beta, erp })
  const d = decompose({ cap: rel.close * rel.shares, shares: rel.shares, price: rel.close, e0, g, r, now: yearOf(rel.date), techs })
  const k = rel.adj / rel.close / rel.shares
  return { base: d.base * k, total: (d.base + d.sum) * k, r }
}
