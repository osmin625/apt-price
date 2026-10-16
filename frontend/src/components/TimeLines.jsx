import { useMemo, useState } from 'react'

import { fmt, niceTicks, useMeasure } from './Charts'

/**
 * 창(Modal)에서 쓰는 **자세한** 월별 선 그래프. 카드 축소판과 달리 축 눈금·연도
 * 눈금이 있고, 그림 위에 마우스를 올리면 그 달의 **모든 계열 값**을 한 번에 보여 준다.
 *
 * ## 왜 선마다 호버하지 않나
 *
 * 가격 분석의 17개 선 그래프는 선 위에 올려야 툴팁이 뜬다. 선이 2px 라 맞추기 어렵고,
 * 맞춰도 그 선 하나만 나온다. 파이프라인처럼 계열 셋을 **같은 달에서 견주는** 그림은
 * 세로선 하나로 그 달을 짚는 쪽이 맞다 — "2023년 착공이 줄 때 준공은 어땠나" 가 이
 * 그림이 답할 질문이다.
 *
 * `series`: [{ key, label, color, points: [{ ym, value }], dash? }]. 계열마다 시작
 * 달이 달라도 된다(인허가가 착공보다 길다). x 축은 모든 계열의 달을 합친 것이다.
 */
export default function TimeLines({
  series,
  unit = '',
  decimals = 0,
  height = 280,
  // 0 을 축에 넣을지. 증감률(%)·차이(%p)는 0 선이 기준이라 넣고, 수준값은 넣지 않는다.
  zero = false,
  // 이 값에 가로 점선을 긋는다(예: 심리지수 100).
  refLine = null,
  ariaLabel = '추이',
  // x 축으로 쓸 달 목록. 안 주면 계열들의 달을 합친다. 그림 두 장을 위아래로 놓고
  // **같은 달을 같은 자리에** 두려면 밖에서 같은 목록을 넘긴다('그 뒤 가격과의 관계').
  months: monthsProp = null,
  // 같이 놓인 그림끼리 짚은 달을 나눈다. 넘기면 세로선·점은 이 값을 따르고, 툴팁은
  // 마우스가 올라간 그림에만 뜬다 — 두 장에 다 띄우면 서로 가린다.
  hoverYm = undefined,
  onHoverYm = null,
}) {
  const [ref, width] = useMeasure()
  const [hover, setHover] = useState(null)
  const PAD = { t: 12, r: 14, b: 26, l: 56 }
  const W = Math.max(width || 640, 280)

  const g = useMemo(() => {
    const months = monthsProp
      || [...new Set(series.flatMap((s) => s.points.map((p) => p.ym)))].sort()
    if (!months.length) return null
    const idx = new Map(months.map((m, i) => [m, i]))
    // 축 밖의 달은 그리지 않는다. 목록을 밖에서 받으면 계열이 더 길 수 있다.
    const inAxis = (p) => idx.has(p.ym)
    const iw = W - PAD.l - PAD.r
    const ih = height - PAD.t - PAD.b
    const xOf = (ym) => PAD.l + (idx.get(ym) / Math.max(months.length - 1, 1)) * iw

    const vals = series.flatMap((s) => s.points.filter(inAxis).map((p) => p.value))
      .filter((v) => v != null)
    if (!vals.length) return null
    let lo = Math.min(...vals)
    let hi = Math.max(...vals)
    if (zero) {
      lo = Math.min(lo, 0)
      hi = Math.max(hi, 0)
    }
    if (refLine != null) {
      lo = Math.min(lo, refLine)
      hi = Math.max(hi, refLine)
    }
    const pad = (hi - lo) * 0.06 || 1
    lo -= pad
    hi += pad
    const yOf = (v) => PAD.t + ih - ((v - lo) / (hi - lo || 1)) * ih

    const lookup = series.map((s) => new Map(s.points.map((p) => [p.ym, p.value])))
    const paths = series.map((s) => ({
      ...s,
      d: s.points
        .filter((p) => p.value != null && inAxis(p))
        .map((p, k) => `${k ? 'L' : 'M'}${xOf(p.ym).toFixed(1)},${yOf(p.value).toFixed(1)}`)
        .join(' '),
    }))

    // 연도 눈금 — 해가 많으면 건너뛴다. 25년치를 다 찍으면 글자가 겹친다.
    const years = months.filter((m) => m.endsWith('01'))
    const every = Math.ceil(years.length / Math.max(Math.floor(iw / 56), 1))
    const yearMarks = years.filter((_, i) => i % every === 0)

    return { months, xOf, yOf, iw, ih, lookup, paths, yearMarks, ticks: niceTicks(lo, hi, 5) }
  }, [series, W, height, zero, refLine, monthsProp])

  if (!g) return <p className="empty">값이 없습니다</p>

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    // viewBox 와 화면 폭이 다를 수 있다 — 비율로 되돌린다.
    const x = ((e.clientX - box.left) / box.width) * W
    const t = (x - PAD.l) / g.iw
    const i = Math.round(Math.min(Math.max(t, 0), 1) * (g.months.length - 1))
    setHover({ i, cx: e.clientX, cy: e.clientY })
    onHoverYm?.(g.months[i])
  }
  const onLeave = () => {
    setHover(null)
    onHoverYm?.(null)
  }

  const hm = hoverYm !== undefined ? hoverYm : hover ? g.months[hover.i] : null

  return (
    <div className="macro-chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={ariaLabel}
           onMouseMove={onMove} onMouseLeave={onLeave}>
        {g.ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={g.yOf(t)} y2={g.yOf(t)}
                  stroke="var(--grid)" strokeDasharray={t === 0 && zero ? undefined : '2 3'} />
            <text x={PAD.l - 6} y={g.yOf(t) + 3} textAnchor="end" fontSize="10.5"
                  fill="var(--text-muted)">
              {fmt(t, decimals)}
            </text>
          </g>
        ))}
        {refLine != null && (
          <line x1={PAD.l} x2={W - PAD.r} y1={g.yOf(refLine)} y2={g.yOf(refLine)}
                stroke="var(--axis)" strokeDasharray="5 4" />
        )}
        {g.yearMarks.map((m) => (
          <text key={m} x={g.xOf(m)} y={height - 8} textAnchor="middle" fontSize="10.5"
                fill="var(--text-muted)">
            {m.slice(0, 4)}
          </text>
        ))}
        {g.paths.map((p) => (
          <path key={p.key} d={p.d} fill="none" stroke={p.color} strokeWidth="1.9"
                strokeLinejoin="round" strokeDasharray={p.dash ? '5 4' : undefined} />
        ))}
        {hm && (
          <g pointerEvents="none">
            <line x1={g.xOf(hm)} x2={g.xOf(hm)} y1={PAD.t} y2={height - PAD.b}
                  stroke="var(--text-muted)" strokeDasharray="3 3" />
            {g.paths.map((p, si) => {
              const v = g.lookup[si].get(hm)
              return v == null ? null : (
                <circle key={p.key} cx={g.xOf(hm)} cy={g.yOf(v)} r="3.2" fill={p.color} />
              )
            })}
          </g>
        )}
        {/* 마우스를 받는 판. 선이 얇아 선 위에서만 받으면 맞추기 어렵다. */}
        <rect x={PAD.l} y={PAD.t} width={g.iw} height={g.ih} fill="transparent" />
      </svg>
      {series.length > 1 && (
        <div className="legend">
          {series.map((s) => (
            <span className="key" key={s.key}>
              <span className={`swatch${s.dash ? ' dash' : ''}`}
                    style={s.dash ? { color: s.color, background: 'none' } : { background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      {hm && hover && (
        <div className="chart-tooltip"
             style={{ left: Math.min(hover.cx + 14, window.innerWidth - 220), top: Math.max(hover.cy - 12, 8) }}>
          <div className="t-title">{hm.slice(0, 4)}.{hm.slice(4)}</div>
          {series.map((s, si) => {
            const v = g.lookup[si].get(hm)
            return (
              <div className="t-row" key={s.key}>
                {series.length > 1 && <>{s.label} </>}
                {v == null ? '—' : `${fmt(v, decimals)}${unit ? ` ${unit}` : ''}`}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
