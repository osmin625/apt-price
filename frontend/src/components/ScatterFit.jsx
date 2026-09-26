import { useMemo } from 'react'

import { fmt, niceTicks, useMeasure, useTooltip } from './Charts'

/**
 * 역까지 도보시간 ↔ 평당가 — 산점도 + 적합 곡선 + 신뢰밴드 + (합성 데이터면) 참값 점선.
 *
 * y축은 **기준점 대비 %** 다. 점은 원자료가 아니라 부분잔차(partial residual) —
 * 면적·층·연식·강남접근성·구 효과를 걷어내고 도보거리 효과만 남긴 값이라
 * 곡선과 같은 축에서 비교된다. 원자료를 그대로 흩뿌리면 다른 요인 때문에
 * 곡선과 안 맞아 보인다.
 *
 * 차트 라이브러리를 쓰지 않는다: 백엔드가 곡선을 50점 가까이 조밀하게 보내므로
 * 보간기가 필요 없고, 평범한 폴리라인으로 충분히 매끄럽다. 축·틱·툴팁은
 * Charts.jsx 의 기존 헬퍼를 그대로 쓴다.
 */
export default function ScatterFit({
  curve,
  points = [],
  hoveredId = null,
  onHover,
  onSelect,
  height = 260,
  compact = false,
}) {
  const [ref, width] = useMeasure()
  const tip = useTooltip()

  const M = compact
    ? { top: 12, right: 12, bottom: 24, left: 40 }
    : { top: 16, right: 20, bottom: 30, left: 52 }
  const W = Math.max(width, 240)
  const H = height
  const iw = Math.max(W - M.left - M.right, 10)
  const ih = Math.max(H - M.top - M.bottom, 10)

  const geom = useMemo(() => {
    if (!curve?.x?.length) return null
    const xs = curve.x
    const xMin = xs[0]
    const xMax = xs[xs.length - 1]

    const ys = [...curve.lo_pct, ...curve.hi_pct, ...curve.fit_pct]
    for (const p of points) if (p.value != null) ys.push(p.value)
    if (curve.truth_pct) ys.push(...curve.truth_pct)
    let yMin = Math.min(...ys)
    let yMax = Math.max(...ys)
    const pad = (yMax - yMin || 1) * 0.08
    yMin -= pad
    yMax += pad

    const sx = (v) => ((v - xMin) / (xMax - xMin || 1)) * iw
    const sy = (v) => ih - ((v - yMin) / (yMax - yMin || 1)) * ih

    const line = (arr) => arr.map((v, i) => `${i ? 'L' : 'M'}${sx(xs[i])},${sy(v)}`).join('')
    // 밴드: hi 를 정방향으로 그린 뒤 lo 를 역방향으로 이어 닫는다.
    const band =
      line(curve.hi_pct) +
      curve.lo_pct
        .map((v, i) => {
          const j = curve.lo_pct.length - 1 - i
          return `L${sx(xs[j])},${sy(curve.lo_pct[j])}`
        })
        .join('') +
      'Z'

    return { xs, xMin, xMax, yMin, yMax, sx, sy, line, band }
  }, [curve, points, iw, ih])

  if (!geom) {
    return <div className="empty">모델 곡선을 불러오지 못했습니다.</div>
  }

  const yTicks = niceTicks(geom.yMin, geom.yMax, compact ? 3 : 4)
  const xTicks = niceTicks(geom.xMin, geom.xMax, compact ? 4 : 6)

  return (
    <div className="scatter" ref={ref}>
      <svg width="100%" height={H} role="img" aria-label="도보시간 대비 평당가">
        <g transform={`translate(${M.left},${M.top})`}>
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line x1={0} x2={iw} y1={geom.sy(t)} y2={geom.sy(t)} stroke="var(--grid)" />
              <text
                x={-8}
                y={geom.sy(t)}
                textAnchor="end"
                dominantBaseline="middle"
                className="scatter-axis"
              >
                {t > 0 ? `+${t}` : t}%
              </text>
            </g>
          ))}

          {/* 기준선 0% */}
          <line
            x1={0}
            x2={iw}
            y1={geom.sy(0)}
            y2={geom.sy(0)}
            stroke="var(--axis)"
            strokeDasharray="3 3"
          />

          <path d={geom.band} className="scatter-band" />
          {curve.truth_pct && <path d={geom.line(curve.truth_pct)} className="scatter-truth" />}
          <path d={geom.line(curve.fit_pct)} className="scatter-fit" />

          {/* 기준점 — 밴드 폭이 0이 되는 지점 */}
          <line
            x1={geom.sx(curve.reference_x)}
            x2={geom.sx(curve.reference_x)}
            y1={0}
            y2={ih}
            className="scatter-ref"
          />

          {points.map((p) =>
            p.value == null ? null : (
              <circle
                key={p.id}
                cx={geom.sx(Math.min(Math.max(p.walk_min, geom.xMin), geom.xMax))}
                cy={geom.sy(p.value)}
                r={hoveredId === p.id ? 6 : 3.5}
                className={`scatter-dot${hoveredId === p.id ? ' is-hovered' : ''}`}
                onMouseEnter={(e) => {
                  onHover?.(p.id)
                  tip.show(
                    e,
                    <>
                      <strong>{p.name}</strong>
                      <br />
                      도보 {fmt(p.walk_min, 1)}분 · {p.value > 0 ? '+' : ''}
                      {fmt(p.value, 1)}%
                      {p.sub ? (
                        <>
                          <br />
                          {p.sub}
                        </>
                      ) : null}
                    </>,
                  )
                }}
                onMouseLeave={() => {
                  onHover?.(null)
                  tip.hide()
                }}
                onClick={() => onSelect?.(p.id)}
              />
            ),
          )}

          {xTicks.map((t) => (
            <text
              key={`x${t}`}
              x={geom.sx(t)}
              y={ih + 18}
              textAnchor="middle"
              className="scatter-axis"
            >
              {t}분
            </text>
          ))}
        </g>
      </svg>

      {!compact && (
        <div className="scatter-legend">
          <span>
            <i className="sw-fit" /> 적합 곡선
          </span>
          <span>
            <i className="sw-band" /> 95% 신뢰구간
          </span>
          {curve.truth_pct && (
            <span>
              <i className="sw-truth" /> 시드 참값
            </span>
          )}
          <span>
            <i className="sw-dot" /> 단지(부분잔차)
          </span>
        </div>
      )}
      {tip.node}
    </div>
  )
}
