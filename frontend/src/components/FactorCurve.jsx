import { useMemo } from 'react'

import { fmt, niceTicks, useMeasure, useTooltip } from './Charts'

/**
 * 요인 하나의 비선형 효과 곡선.
 *
 * 막대(대표 지점)만 보면 굽은 모양이 보이지 않는다. 이 프로젝트의 요인들은
 * 대부분 선형이 아니다 — 면적·세대수는 로그, 연식은 2차, 도보거리는 스플라인이다.
 * 곡선으로 그려야 "어디서 급하고 어디서 완만한지"가 드러난다.
 *
 * y=0 인 기준선과 기준점 세로선을 함께 그려, 모든 값이 **기준 대비 %**임을
 * 눈으로 알 수 있게 한다.
 */
export default function FactorCurve({
  curve,
  linearCurve = null,
  points = [],
  xLabel = '',
  refX = null,
  height = 150,
}) {
  const [ref, width] = useMeasure()
  const tip = useTooltip()

  const g = useMemo(() => {
    if (!curve?.x?.length) return null
    const M = { top: 10, right: 12, bottom: 22, left: 44 }
    const W = Math.max(width, 220)
    const iw = Math.max(W - M.left - M.right, 10)
    const ih = Math.max(height - M.top - M.bottom, 10)

    const xs = curve.x
    const ys = curve.pct
    const xMin = xs[0]
    const xMax = xs[xs.length - 1]

    const all = [...ys, 0, ...points.map((p) => p.premium_pct)]
    if (linearCurve?.pct) all.push(...linearCurve.pct)
    let yMin = Math.min(...all)
    let yMax = Math.max(...all)
    const pad = (yMax - yMin || 1) * 0.12
    yMin -= pad
    yMax += pad

    const sx = (v) => M.left + ((v - xMin) / (xMax - xMin || 1)) * iw
    const sy = (v) => M.top + ih - ((v - yMin) / (yMax - yMin || 1)) * ih
    const line = (arr) => arr.map((v, i) => `${i ? 'L' : 'M'}${sx(xs[i])},${sy(v)}`).join('')
    const path = line(ys)
    const linPath = linearCurve?.pct ? line(linearCurve.pct) : null

    return { M, W, iw, ih, xMin, xMax, yMin, yMax, sx, sy, path, linPath }
  }, [curve, linearCurve, points, width, height])

  if (!g) return null

  const yTicks = niceTicks(g.yMin, g.yMax, 3)
  const xTicks = niceTicks(g.xMin, g.xMax, 4)

  return (
    <div className="fcurve" ref={ref}>
      <svg width="100%" height={height} role="img" aria-label={xLabel}>
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line
              x1={g.M.left}
              x2={g.M.left + g.iw}
              y1={g.sy(t)}
              y2={g.sy(t)}
              stroke="var(--grid)"
            />
            <text x={g.M.left - 6} y={g.sy(t)} textAnchor="end" dominantBaseline="middle" className="fcurve-axis">
              {t > 0 ? `+${t}` : t}%
            </text>
          </g>
        ))}

        {/* 기준선 0% */}
        <line
          x1={g.M.left}
          x2={g.M.left + g.iw}
          y1={g.sy(0)}
          y2={g.sy(0)}
          className="fcurve-zero"
        />
        {refX != null && refX >= g.xMin && refX <= g.xMax && (
          <line
            x1={g.sx(refX)}
            x2={g.sx(refX)}
            y1={g.M.top}
            y2={g.M.top + g.ih}
            className="fcurve-ref"
          />
        )}

        {/* 비선형항을 뺀 제약 모델의 직선. 곡선과 겹쳐 그려 굽은 정도를 눈으로 보여 준다. */}
        {g.linPath && <path d={g.linPath} className="fcurve-linear" />}
        <path d={g.path} className="fcurve-line" />

        {points.map((p, i) =>
          p.x == null ? null : (
            <circle
              key={i}
              cx={g.sx(p.x)}
              cy={g.sy(p.premium_pct)}
              r={3.2}
              className="fcurve-dot"
              onMouseMove={(e) =>
                tip.show(
                  e,
                  <>
                    <div className="t-title">{p.band}</div>
                    <div className="t-row">
                      {p.premium_pct > 0 ? '+' : ''}
                      {fmt(p.premium_pct, 1)}%
                    </div>
                  </>,
                )
              }
              onMouseLeave={tip.hide}
            />
          ),
        )}

        {xTicks.map((t) => (
          <text key={`x${t}`} x={g.sx(t)} y={height - 6} textAnchor="middle" className="fcurve-axis">
            {fmt(t)}
          </text>
        ))}
      </svg>
      {xLabel && <div className="fcurve-xlabel">{xLabel}</div>}
      {tip.node}
    </div>
  )
}
