import { useMemo } from 'react'

import { fmt, niceTicks, useMeasure, useTooltip } from '../components/Charts'

/**
 * 시군구 17곳을 한 축에 — 가격 분석의 지표(매매지수·전세가율·거래량 …).
 *
 * 카드 축소판(`compact`)은 가격 분석 탭이, 전체는 주제 창(`TopicModal`)이 쓴다.
 * 원래 `views/MacroView.jsx` 안에 있던 것을 그대로 옮겼다.
 */

/* 17개 선을 한 축에. 색은 순위로 돌린다 — 이름마다 고정색을 주면 17개를 구분할
   만큼 색이 없고, 어차피 범례에서 짚어 보게 된다. */
export function MultiLine({ data, hidden, compact = false }) {
  const [ref, width] = useMeasure()
  const tip = useTooltip()
  const H = compact ? 150 : 300
  const PAD = compact ? { t: 8, r: 8, b: 14, l: 28 } : { t: 12, r: 12, b: 26, l: 52 }

  const shown = data.items.filter((i) => !hidden.has(i.sgg_cd))
  const months = data.months

  const { xOf, yOf, ticks, paths } = useMemo(() => {
    const w = Math.max(width || 640, compact ? 200 : 320)
    const iw = w - PAD.l - PAD.r
    const ih = H - PAD.t - PAD.b
    const idx = new Map(months.map((m, i) => [m, i]))
    const xOf = (ym) => PAD.l + (idx.get(ym) / Math.max(months.length - 1, 1)) * iw

    let lo = Infinity
    let hi = -Infinity
    shown.forEach((s) =>
      s.points.forEach((p) => {
        if (p.value < lo) lo = p.value
        if (p.value > hi) hi = p.value
      }),
    )
    if (!Number.isFinite(lo)) {
      lo = 0
      hi = 1
    }
    const pad = (hi - lo) * 0.08 || 1
    lo -= pad
    hi += pad
    const yOf = (v) => PAD.t + ih - ((v - lo) / (hi - lo || 1)) * ih

    const paths = shown.map((s) => ({
      ...s,
      d: s.points
        .map((p, k) => `${k ? 'L' : 'M'}${xOf(p.ym).toFixed(1)},${yOf(p.value).toFixed(1)}`)
        .join(' '),
    }))
    return { xOf, yOf, ticks: niceTicks(lo, hi, 4), paths }
  }, [width, shown, months, compact])

  // x축 라벨은 연 단위로만. 월까지 찍으면 겹쳐서 못 읽는다.
  const yearMarks = months
    .map((m, i) => ({ m, i }))
    .filter(({ m }) => m.endsWith('01'))

  return (
    <div className="macro-chart" ref={ref}>
      <svg viewBox={`0 0 ${Math.max(width || 640, compact ? 200 : 320)} ${H}`} role="img"
           aria-label={`${data.label} 시군구별 추이`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={(width || 640) - PAD.r} y1={yOf(t)} y2={yOf(t)}
                  stroke="var(--border)" strokeDasharray="2 3" />
            {!compact && (
              <text x={PAD.l - 6} y={yOf(t) + 3} textAnchor="end"
                    fontSize="10" fill="var(--text-muted)">
                {fmt(t, data.decimals)}
              </text>
            )}
          </g>
        ))}
        {!compact && yearMarks.map(({ m }) => (
          <text key={m} x={xOf(m)} y={H - 8} textAnchor="middle"
                fontSize="10" fill="var(--text-muted)">
            {m.slice(0, 4)}
          </text>
        ))}
        {paths.map((p, i) => (
          <path
            key={p.sgg_cd}
            d={p.d}
            fill="none"
            stroke={colorAt(i, paths.length)}
            strokeWidth={compact ? 1.2 : 1.8}
            strokeLinejoin="round"
            onMouseEnter={(e) =>
              tip.show(e, (
                <>
                  <div className="t-title">{p.name}</div>
                  <div className="t-row">
                    최신 {fmt(p.latest, data.decimals)} {data.unit}
                  </div>
                  <div className="t-row">
                    {p.first_ym}~{p.latest_ym}
                    {p.change_pct == null
                      ? ''
                      : ` · ${p.change_pct > 0 ? '+' : ''}${fmt(p.change_pct, 1)}%`}
                  </div>
                </>
              ))
            }
            onMouseLeave={tip.hide}
          />
        ))}
      </svg>
      {tip.node}
    </div>
  )
}

export function Legend({ data, hidden, onToggle }) {
  const shown = data.items.filter((i) => !hidden.has(i.sgg_cd))
  const indexOfShown = new Map(shown.map((s, i) => [s.sgg_cd, i]))
  return (
    <div className="macro-legend">
      {data.items.map((i) => {
        const off = hidden.has(i.sgg_cd)
        return (
          <button
            key={i.sgg_cd}
            className={`macro-key${off ? ' is-off' : ''}`}
            onClick={() => onToggle(i.sgg_cd)}
            aria-pressed={!off}
            title={off ? '다시 표시' : '숨기기'}
          >
            <i
              style={{
                background: off
                  ? 'var(--text-muted)'
                  : colorAt(indexOfShown.get(i.sgg_cd), shown.length),
              }}
            />
            {i.name}
          </button>
        )
      })}
    </div>
  )
}

/** 순위를 색상환에 고르게 편다. 17개를 구분하려면 고정 팔레트로는 모자란다. */
export function colorAt(i, n) {
  if (i == null) return 'var(--text-muted)'
  const hue = Math.round((i / Math.max(n, 1)) * 320)
  return `hsl(${hue} 62% 48%)`
}

export function FullTable({ data }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>시군구</th>
            <th className="num">{data.label}</th>
            <th className="num">기간 변화</th>
            <th>시작</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((i) => (
            <tr key={i.sgg_cd}>
              <td>{i.name}</td>
              <td className="num">
                <b>{fmt(i.latest, data.decimals)}</b>
                <span className="muted small"> {data.unit}</span>
              </td>
              <td
                className={`num ${
                  i.change_pct > 0 ? 'tone-pos' : i.change_pct < 0 ? 'tone-neg' : ''
                }`}
              >
                {i.change_pct == null
                  ? '—'
                  : `${i.change_pct > 0 ? '+' : ''}${fmt(i.change_pct, 1)}%`}
              </td>
              <td className="muted small">
                {i.first_ym}
                {i.partial ? ' (분구 후)' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
