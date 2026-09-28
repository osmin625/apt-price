import { useCallback, useLayoutEffect, useRef, useState } from 'react'

const fmt = (n, digits = 0) =>
  n == null ? '—' : n.toLocaleString('ko-KR', { maximumFractionDigits: digits })

/* ── 툴팁 ─────────────────────────────────────────────── */

export function useTooltip() {
  const [tip, setTip] = useState(null)
  const show = useCallback((e, content) => {
    setTip({ x: e.clientX, y: e.clientY, content })
  }, [])
  const hide = useCallback(() => setTip(null), [])
  const node = tip ? (
    <div
      className="chart-tooltip"
      style={{
        left: Math.min(tip.x + 14, window.innerWidth - 220),
        top: Math.max(tip.y - 12, 8),
      }}
    >
      {tip.content}
    </div>
  ) : null
  return { show, hide, node }
}

export function useMeasure() {
  const ref = useRef(null)
  const [width, setWidth] = useState(640)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    setWidth(el.getBoundingClientRect().width)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

export function niceTicks(min, max, count = 4) {
  const span = max - min
  if (span <= 0) return [min]
  const raw = span / count
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
  const start = Math.ceil(min / step) * step
  const out = []
  for (let v = start; v <= max + 1e-9; v += step) out.push(Math.round(v))
  return out
}

/* ── 구간별 평당가: IQR 범위 + 중앙값 점 ────────────────── */

export function RangeDotChart({ rows, unit = '만원/평', emptyText = '표본이 없습니다' }) {
  const tip = useTooltip()
  if (!rows?.length) return <p className="empty">{emptyText}</p>

  const lo = Math.min(...rows.map((r) => r.p25))
  const hi = Math.max(...rows.map((r) => r.p75))
  const pad = (hi - lo || hi * 0.1) * 0.18
  const min = lo - pad
  const max = hi + pad
  const pct = (v) => ((v - min) / (max - min)) * 100
  const ticks = niceTicks(min, max, 4)

  return (
    <div className="rdc">
      {rows.map((r) => (
        <div
          className="rdc-row"
          key={r.band}
          onMouseMove={(e) =>
            tip.show(
              e,
              <>
                <div className="t-title">{r.band}</div>
                <div className="t-row">중앙값 {fmt(r.median)} {unit}</div>
                <div className="t-row">중간 50% {fmt(r.p25)} ~ {fmt(r.p75)}</div>
                <div className="t-row">전체 범위 {fmt(r.min)} ~ {fmt(r.max)}</div>
                <div className="t-row">거래 {fmt(r.count)}건</div>
              </>,
            )
          }
          onMouseLeave={tip.hide}
        >
          <div className="rdc-label" title={r.band}>{r.band}</div>
          <div className="rdc-track">
            {ticks.map((t) => (
              <div className="rdc-grid" key={t} style={{ left: `${pct(t)}%` }} />
            ))}
            <div
              className="rdc-range"
              style={{ left: `${pct(r.p25)}%`, width: `${pct(r.p75) - pct(r.p25)}%` }}
            />
            <div className="rdc-dot" style={{ left: `${pct(r.median)}%` }} />
          </div>
          <div className="rdc-value">{fmt(r.median)}</div>
          <div className="rdc-count">{fmt(r.count)}건</div>
        </div>
      ))}

      <div className="rdc-row rdc-axis">
        <div className="rdc-label" />
        <div className="rdc-track">
          {ticks.map((t) => (
            <span className="rdc-tick" key={t} style={{ left: `${pct(t)}%` }}>
              {fmt(t)}
            </span>
          ))}
        </div>
        <div className="rdc-value rdc-unit">{unit}</div>
        <div className="rdc-count" />
      </div>

      <div className="legend">
        <span className="key"><span className="swatch dot" /> 중앙 평당가</span>
        <span className="key"><span className="swatch wash" /> 중간 50% 구간(하위 25%~75%)</span>
      </div>
      {tip.node}
    </div>
  )
}

/* ── 층 프리미엄: 0%를 기준으로 좌우로 뻗는 막대 ─────────── */

/**
 * 기준 대비 ± 를 발산 막대로.
 *
 * `note` 는 차트 아래 설명이다. 층 프리미엄 전용 문구가 하드코딩돼 있었는데,
 * 같은 컴포넌트를 면적·거리·연식 등에 재사용하면서 엉뚱한 설명이 모든 요인에
 * 반복됐다. 호출하는 쪽이 넘기도록 바꿨고, 안 넘기면 아무것도 그리지 않는다.
 */
export function PremiumBars({
  rows,
  note = null,
  emptyText = '표본이 부족해 계수를 추정하지 못했습니다',
}) {
  const tip = useTooltip()
  if (!rows?.length) return <p className="empty">{emptyText}</p>

  const span = Math.max(4, ...rows.map((r) => Math.abs(r.premium_pct))) * 1.25
  const pct = (v) => 50 + (v / span) * 50

  return (
    <div className="pbar">
      {rows.map((r) => {
        const positive = r.premium_pct >= 0
        const left = positive ? 50 : pct(r.premium_pct)
        const width = Math.abs(pct(r.premium_pct) - 50)
        return (
          <div
            className="pbar-row"
            key={r.band}
            onMouseMove={(e) =>
              tip.show(
                e,
                <>
                  <div className="t-title">{r.band}</div>
                  {/* `factor` 는 구간 통계 경로에만 있다. 회귀에서 온 행(요인별
                      보정계수의 층·노선)에는 없어서 예전에는 호버하는 순간 터졌다. */}
                  <div className="t-row">
                    {positive ? '+' : ''}
                    {r.premium_pct}%
                    {r.factor != null ? ` (보정계수 ${r.factor.toFixed(3)})` : ''}
                  </div>
                  {r.ci_pct && r.ci_pct[0] !== r.ci_pct[1] && (
                    <div className="t-row">
                      95% 신뢰구간 {r.ci_pct[0]} ~ {r.ci_pct[1]}%
                    </div>
                  )}
                  <div className="t-row">같은 단지·같은 평형 중앙값 대비</div>
                </>,
              )
            }
            onMouseLeave={tip.hide}
          >
            <div className="pbar-label">{r.band}</div>
            <div className="pbar-track">
              <div className="pbar-zero" />
              <div
                className={`pbar-fill ${positive ? 'pos' : 'neg'}`}
                style={{ left: `${left}%`, width: `${width}%` }}
              />
            </div>
            <div className={`pbar-value ${positive ? 'pos' : 'neg'}`}>
              {positive ? '+' : ''}
              {r.premium_pct.toFixed(1)}%
            </div>
          </div>
        )
      })}
      {note}
      {tip.node}
    </div>
  )
}

/* ── 월별 평당가 추이 ──────────────────────────────────── */

export function TrendLine({ rows, unit = '만원/평' }) {
  const [ref, width] = useMeasure()
  const [hover, setHover] = useState(null)
  const tip = useTooltip()

  if (!rows?.length) return <p className="empty">표본이 없습니다</p>

  const H = 210
  const M = { top: 14, right: 18, bottom: 26, left: 52 }
  const W = Math.max(width, 320)
  const iw = W - M.left - M.right
  const ih = H - M.top - M.bottom

  const values = rows.map((r) => r.median)
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const pad = (hi - lo || hi * 0.05) * 0.25
  const yMin = lo - pad
  const yMax = hi + pad

  const x = (i) => M.left + (rows.length === 1 ? iw / 2 : (i / (rows.length - 1)) * iw)
  const y = (v) => M.top + ih - ((v - yMin) / (yMax - yMin)) * ih
  const ticks = niceTicks(yMin, yMax, 4)

  const path = rows.map((r, i) => `${i ? 'L' : 'M'}${x(i)},${y(r.median)}`).join(' ')
  const area = `${path} L${x(rows.length - 1)},${M.top + ih} L${x(0)},${M.top + ih} Z`
  const last = rows.length - 1
  const step = Math.max(1, Math.ceil(rows.length / 6))

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const rel = ((e.clientX - box.left) / box.width) * W
    const i = Math.max(0, Math.min(last, Math.round(((rel - M.left) / iw) * last)))
    setHover(i)
    tip.show(
      e,
      <>
        <div className="t-title">{rows[i].month}</div>
        <div className="t-row">중앙 평당가 {fmt(rows[i].median)} {unit}</div>
        <div className="t-row">거래 {fmt(rows[i].count)}건</div>
      </>,
    )
  }

  return (
    <div ref={ref}>
      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        onMouseMove={onMove}
        onMouseLeave={() => {
          setHover(null)
          tip.hide()
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth="1" />
            <text x={M.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--text-muted)">
              {fmt(t)}
            </text>
          </g>
        ))}

        <path d={area} fill="var(--series-1)" opacity="0.1" />
        <path d={path} fill="none" stroke="var(--series-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

        {hover != null && (
          <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={M.top + ih} stroke="var(--axis)" strokeWidth="1" />
        )}
        {hover != null && (
          <circle cx={x(hover)} cy={y(rows[hover].median)} r="5" fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2" />
        )}
        <circle cx={x(last)} cy={y(rows[last].median)} r="4.5" fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth="2" />
        <text
          x={x(last) - 6}
          y={y(rows[last].median) - 10}
          textAnchor="end"
          fontSize="12"
          fontWeight="600"
          fill="var(--text-primary)"
        >
          {fmt(rows[last].median)}
        </text>

        {rows.map((r, i) =>
          i % step === 0 || i === last ? (
            <text key={r.month} x={x(i)} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--text-muted)">
              {r.month.slice(2).replace('-', '.')}
            </text>
          ) : null,
        )}
      </svg>
      {tip.node}
    </div>
  )
}

export { fmt }


/** 만원 단위 정수를 '억' 표기로. 3.9억 / 12.35억. */
export const eok = (manwon) =>
  manwon == null ? '—' : `${(manwon / 10000).toFixed(2).replace(/\.?0+$/, '')}억`

/** 작은 지표 한 칸. 여러 화면이 같은 모양으로 쓴다. */
export function Tile({ label, value, sub }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value sm">{value}</div>
      {sub ? <div className="note">{sub}</div> : null}
    </div>
  )
}
