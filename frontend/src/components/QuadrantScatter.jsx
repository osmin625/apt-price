import { useMemo } from 'react'

import { fmt, niceTicks, useMeasure, useTooltip } from './Charts'

/**
 * 이름표가 붙은 산점도. 두 축을 겹쳐야 보이는 것을 보여 주는 용도다.
 *
 * ## 왜 선 17개가 아니라 점 17개인가
 *
 * 매크로 탭은 처음에 17개 시계열을 그려 놓기만 했다. 값은 다 있는데 읽는 일이
 * 통째로 사람 몫이라 "인사이트 없이 값만 보여준다" 는 말을 들었다. 맞는 지적이다.
 *
 * 시계열은 **한 지역이 어떻게 움직였나**에 답하고, 이 그림은 **17곳이 서로 어떻게
 * 다른가**에 답한다. 뒤쪽 질문은 축을 둘 겹쳐야 답이 나온다 — 전고점 대비만으로는
 * 바닥에서 기는 곳과 꺾이는 곳이 구분되지 않고, 최근 3개월만으로는 신고가인지
 * 반등인지 알 수 없다.
 *
 * ## 사분면 이름을 화면에 적는다
 *
 * 점의 위치가 곧 근거이므로 해석 문장을 따로 만들지 않는다. 대신 사분면에 이름을
 * 붙여 **읽는 법만** 적어 둔다. 어느 칸에 있는지는 보는 사람이 확인한다.
 */
export default function QuadrantScatter({
  items,
  x,
  y,
  label = (d) => d.name,
  xLabel,
  yLabel,
  quadrants,          // [우상, 좌상, 좌하, 우하] 라벨
  // 기준선. null 이면 선을 그리지 않고 **축 범위에도 넣지 않는다** — 순위처럼 0 이
  // 의미 없는 축에서 0 을 범위에 넣으면 점이 구석에 뭉친다(실제로 그랬다).
  xOrigin = 0,
  yOrigin = 0,
  diagonal = false,   // 45도선 (순위 비교용)
  invertY = false,    // 순위처럼 작을수록 좋은 축
  invertX = false,
  xDecimals = 1,
  yDecimals = 1,
  tip: renderTip,
  height = 340,
}) {
  const [ref, { width }] = useMeasure()
  const tip = useTooltip()
  const W = Math.max(width || 640, 320)
  const PAD = { t: 16, r: 18, b: 38, l: 52 }

  const g = useMemo(() => {
    const iw = W - PAD.l - PAD.r
    const ih = height - PAD.t - PAD.b
    const xs = items.map(x).filter((v) => v != null)
    const ys = items.map(y).filter((v) => v != null)
    if (!xs.length || !ys.length) return null

    // 기준선이 범위 안에 들어오도록 넓힌다. 사분면이 보이려면 0 이 화면에 있어야 한다.
    // origin 이 null 이면 넓히지 않는다.
    const span = (arr, origin) => {
      const base = origin == null ? arr : [...arr, origin]
      let lo = Math.min(...base)
      let hi = Math.max(...base)
      const pad = (hi - lo) * 0.12 || 1
      return [lo - pad, hi + pad]
    }
    const [x0, x1] = span(xs, xOrigin)
    const [y0, y1] = span(ys, yOrigin)

    const sx = (v) =>
      PAD.l + ((invertX ? x1 - v : v - x0) / (x1 - x0 || 1)) * iw
    const sy = (v) =>
      PAD.t + ih - ((invertY ? y1 - v : v - y0) / (y1 - y0 || 1)) * ih

    // 이름표가 겹치면 아래로 민다. 17개를 다 적으려면 이 정도는 필요하다.
    const placed = []
    const pts = items
      .filter((d) => x(d) != null && y(d) != null)
      .map((d) => {
        const px = sx(x(d))
        const py = sy(y(d))
        // 겹치면 아래로 밀되 **그림 안에 가둔다.** 예전에는 무한정 밀어서 이름표가
        // SVG 밖으로 흘러 아래 표를 덮었다.
        const top = PAD.t + 9
        const bottom = PAD.t + ih - 2
        let ly = Math.min(Math.max(py - 7, top), bottom)
        for (let k = 0; k < 24; k++) {
          const clash = placed.some(
            (p) => Math.abs(p.x - px) < 52 && Math.abs(p.y - ly) < 11,
          )
          if (!clash) break
          ly += 11
          if (ly > bottom) { ly = top; }
        }
        placed.push({ x: px, y: ly })
        return { d, px, py, ly }
      })

    return {
      pts,
      sx,
      sy,
      xTicks: niceTicks(x0, x1, 4),
      yTicks: niceTicks(y0, y1, 4),
      iw,
      ih,
    }
  }, [items, W, height, xOrigin, yOrigin, invertX, invertY])

  if (!g) return <p className="empty">그릴 값이 없습니다.</p>

  const hasOx = xOrigin != null
  const hasOy = yOrigin != null
  const ox = hasOx ? g.sx(xOrigin) : PAD.l
  const oy = hasOy ? g.sy(yOrigin) : PAD.t + g.ih

  return (
    <div className="quad-chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={`${xLabel} 대 ${yLabel}`}>
        {/* 사분면 바탕 — 아주 옅게만. 점을 읽는 데 방해가 되면 안 된다 */}
        {hasOx && hasOy && (
          <>
            <rect x={ox} y={PAD.t} width={Math.max(W - PAD.r - ox, 0)} height={Math.max(oy - PAD.t, 0)}
                  fill="var(--series-1)" opacity="0.045" />
            <rect x={ox} y={oy} width={Math.max(W - PAD.r - ox, 0)} height={Math.max(PAD.t + g.ih - oy, 0)}
                  fill="var(--neg)" opacity="0.045" />
          </>
        )}

        {g.yTicks.map((t) => (
          <g key={`y${t}`}>
            <line x1={PAD.l} x2={W - PAD.r} y1={g.sy(t)} y2={g.sy(t)}
                  stroke="var(--border)" strokeDasharray="2 3" />
            <text x={PAD.l - 6} y={g.sy(t) + 3} textAnchor="end" fontSize="10"
                  fill="var(--text-muted)">{fmt(t, yDecimals)}</text>
          </g>
        ))}
        {g.xTicks.map((t) => (
          <text key={`x${t}`} x={g.sx(t)} y={height - 20} textAnchor="middle" fontSize="10"
                fill="var(--text-muted)">{fmt(t, xDecimals)}</text>
        ))}

        {/* 기준선 */}
        {hasOx && (
          <line x1={ox} x2={ox} y1={PAD.t} y2={PAD.t + g.ih} stroke="var(--text-muted)" strokeWidth="1" />
        )}
        {hasOy && (
          <line x1={PAD.l} x2={W - PAD.r} y1={oy} y2={oy} stroke="var(--text-muted)" strokeWidth="1" />
        )}
        {diagonal && (
          <line x1={PAD.l} y1={PAD.t + g.ih} x2={W - PAD.r} y2={PAD.t}
                stroke="var(--text-muted)" strokeDasharray="4 4" opacity="0.7" />
        )}

        {quadrants && (
          <>
            <text x={W - PAD.r - 4} y={PAD.t + 11} textAnchor="end" fontSize="10.5"
                  fill="var(--text-muted)">{quadrants[0]}</text>
            <text x={PAD.l + 4} y={PAD.t + 11} fontSize="10.5"
                  fill="var(--text-muted)">{quadrants[1]}</text>
            <text x={PAD.l + 4} y={PAD.t + g.ih - 4} fontSize="10.5"
                  fill="var(--text-muted)">{quadrants[2]}</text>
            <text x={W - PAD.r - 4} y={PAD.t + g.ih - 4} textAnchor="end" fontSize="10.5"
                  fill="var(--text-muted)">{quadrants[3]}</text>
          </>
        )}

        {g.pts.map(({ d, px, py, ly }) => (
          <g key={d.sgg_cd}
             onMouseEnter={(e) => tip.show(e, renderTip ? renderTip(d) : <div className="t-title">{label(d)}</div>)}
             onMouseLeave={tip.hide}>
            <circle cx={px} cy={py} r="4.5" fill="var(--series-1)" opacity="0.85" />
            <text x={px + 7} y={ly} fontSize="10" fill="var(--text-secondary)">{label(d)}</text>
          </g>
        ))}

        <text x={W / 2} y={height - 5} textAnchor="middle" fontSize="10.5"
              fill="var(--text-muted)">{xLabel}</text>
        <text x={12} y={PAD.t + g.ih / 2} fontSize="10.5" fill="var(--text-muted)"
              transform={`rotate(-90 12 ${PAD.t + g.ih / 2})`} textAnchor="middle">{yLabel}</text>
      </svg>
      {tip.node}
    </div>
  )
}
