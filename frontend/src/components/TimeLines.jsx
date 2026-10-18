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
 * `series`: [{ key, label, color, points: [{ ym, value }], dash?, axis?, width? }]. 계열마다
 * 시작 달이 달라도 된다(인허가가 착공보다 길다). x 축은 모든 계열의 달을 합친 것이다.
 *
 * ## 오른쪽 축
 *
 * `axis: 'right'` 인 계열은 오른쪽 축에 그린다. 단위가 다른 두 계열(요인 %p 와 가격
 * 변화 %)을 **한 그림에 겹쳐** 같이 오르내리는지 보려는 것이다. 한 축에 넣으면 단위가
 * 다른 숫자를 같은 눈금으로 읽게 되어 크기 비교가 거짓이 된다. 축 글자는 그 축 계열의
 * 색으로 칠하고, 범례에 어느 축인지 적는다.
 *
 * 두 축이 다 0 을 넣으면(`zero` 와 `rightZero`) **0 선을 같은 높이에** 맞춘다. 증감률끼리
 * 견줄 때 읽는 것은 '둘 다 0 위인가 아래인가' 인데, 0 이 축마다 다른 높이에 있으면
 * 같이 움직이지 않는 두 선도 겹쳐 보인다.
 *
 * ## 띠
 *
 * `bands`: [{ from, to, label? }] — 그 기간을 옅게 칠한다(금리 인상기). 선과 다른 층이라
 * 선 색을 가리지 않게 맨 아래에 깐다. 한 달짜리 띠도 보이도록 양쪽으로 반 달씩 넓힌다.
 */
/* 축 범위 안의 눈금. 0 선을 맞추려고 범위를 늘리면 눈금 계산에서 -0 이 나와 축에
   '-0' 이 찍혔다(미분양 창 오른쪽 축) — 0 으로 바로잡는다. */
function axisTicks([lo, hi]) {
  return niceTicks(lo, hi, 5)
    .filter((t) => t >= lo && t <= hi)
    .map((t) => (Math.abs(t) < 1e-9 ? 0 : t))
}

export default function TimeLines({
  series,
  unit = '',
  decimals = 0,
  height = 280,
  // 0 을 축에 넣을지. 증감률(%)·차이(%p)는 0 선이 기준이라 넣고, 수준값은 넣지 않는다.
  zero = false,
  // 이 값에 가로 점선을 긋는다(예: 심리지수 100). 왼쪽 축 기준.
  refLine = null,
  ariaLabel = '추이',
  // x 축으로 쓸 달 목록. 안 주면 계열들의 달을 합친다. 계열 하나가 더 길 때(가격은
  // 2003~, 요인은 2012~) 다른 계열의 기간으로 자르려면 밖에서 넘긴다.
  months: monthsProp = null,
  // 오른쪽 축 — `axis: 'right'` 계열이 있을 때만 쓴다.
  rightUnit = '',
  rightDecimals = 0,
  rightZero = false,
  bands = [],
}) {
  const [ref, width] = useMeasure()
  const [hover, setHover] = useState(null)
  const hasRight = series.some((s) => s.axis === 'right')
  const PAD = { t: 12, r: hasRight ? 52 : 14, b: 26, l: 56 }
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

    const sideOf = (s) => (s.axis === 'right' ? 'right' : 'left')
    const rangeOf = (side, withZero, ref) => {
      const vals = series.filter((s) => sideOf(s) === side)
        .flatMap((s) => s.points.filter(inAxis).map((p) => p.value))
        .filter((v) => v != null)
      if (!vals.length) return null
      let lo = Math.min(...vals)
      let hi = Math.max(...vals)
      if (withZero) {
        lo = Math.min(lo, 0)
        hi = Math.max(hi, 0)
      }
      if (ref != null) {
        lo = Math.min(lo, ref)
        hi = Math.max(hi, ref)
      }
      const pad = (hi - lo) * 0.06 || 1
      return [lo - pad, hi + pad]
    }
    let L = rangeOf('left', zero, refLine)
    let R = hasRight ? rangeOf('right', rightZero, null) : null
    if (!L && !R) return null
    // 0 선 맞추기. 각 축의 폭으로 나눈 '0 위 몫' 과 '0 아래 몫' 의 큰 쪽을 두 축이 같이
    // 쓴다 — 그러면 두 축 모두 제 값을 다 담으면서 0 이 같은 높이에 온다.
    if (L && R && zero && rightZero) {
      const up = Math.max(L[1] / (L[1] - L[0]), R[1] / (R[1] - R[0]))
      const down = Math.max(-L[0] / (L[1] - L[0]), -R[0] / (R[1] - R[0]))
      const fit = ([lo, hi]) => {
        const span = hi - lo
        return [-down * span, up * span]
      }
      L = fit(L)
      R = fit(R)
    }
    const scale = ([lo, hi]) => (v) => PAD.t + ih - ((v - lo) / (hi - lo || 1)) * ih
    const yL = L ? scale(L) : null
    const yR = R ? scale(R) : null
    const yFor = (s) => (sideOf(s) === 'right' ? yR : yL)

    const lookup = series.map((s) => new Map(s.points.map((p) => [p.ym, p.value])))
    const paths = series.map((s) => ({
      ...s,
      y: yFor(s),
      d: s.points
        .filter((p) => p.value != null && inAxis(p))
        .map((p, k) => `${k ? 'L' : 'M'}${xOf(p.ym).toFixed(1)},${yFor(s)(p.value).toFixed(1)}`)
        .join(' '),
    }))

    // 연도 눈금 — 해가 많으면 건너뛴다. 25년치를 다 찍으면 글자가 겹친다.
    const years = months.filter((m) => m.endsWith('01'))
    const every = Math.ceil(years.length / Math.max(Math.floor(iw / 56), 1))
    const yearMarks = years.filter((_, i) => i % every === 0)

    const step = iw / Math.max(months.length - 1, 1)
    const shade = bands
      .map((b) => {
        const a = months.find((m) => m >= b.from)
        const z = [...months].reverse().find((m) => m <= b.to)
        if (!a || !z || a > z) return null
        const x0 = Math.max(PAD.l, xOf(a) - step / 2)
        const x1 = Math.min(PAD.l + iw, xOf(z) + step / 2)
        return { key: `${b.from}-${b.to}`, x: x0, w: x1 - x0, label: b.label }
      })
      .filter(Boolean)

    return {
      months, xOf, yL, yR, iw, ih, lookup, paths, yearMarks, shade,
      ticksL: L ? axisTicks(L) : [],
      ticksR: R ? axisTicks(R) : [],
    }
  }, [series, W, height, zero, refLine, monthsProp, hasRight, rightZero, bands])

  if (!g) return <p className="empty">값이 없습니다</p>

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    // viewBox 와 화면 폭이 다를 수 있다 — 비율로 되돌린다.
    const x = ((e.clientX - box.left) / box.width) * W
    const t = (x - PAD.l) / g.iw
    const i = Math.round(Math.min(Math.max(t, 0), 1) * (g.months.length - 1))
    setHover({ i, cx: e.clientX, cy: e.clientY })
  }

  const hm = hover ? g.months[hover.i] : null
  // 축 글자 색 — 한 축에 계열이 하나면 그 색으로 칠해 어느 선의 눈금인지 보이게 한다.
  const sideColor = (side) => {
    const ss = series.filter((s) => (s.axis === 'right' ? 'right' : 'left') === side)
    return hasRight && ss.length === 1 ? ss[0].color : 'var(--text-muted)'
  }
  const unitOf = (s) => (s.axis === 'right' ? rightUnit : unit)
  const decOf = (s) => (s.axis === 'right' ? rightDecimals : decimals)

  return (
    <div className="macro-chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={ariaLabel}
           onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {g.shade.map((b) => (
          <rect key={b.key} x={b.x} y={PAD.t} width={b.w} height={g.ih} fill="var(--band)" />
        ))}
        {g.ticksL.map((t) => (
          <g key={`l${t}`}>
            <line x1={PAD.l} x2={W - PAD.r} y1={g.yL(t)} y2={g.yL(t)}
                  stroke="var(--grid)" strokeDasharray={t === 0 && zero ? undefined : '2 3'} />
            <text x={PAD.l - 6} y={g.yL(t) + 3} textAnchor="end" fontSize="10.5"
                  fill={sideColor('left')}>
              {fmt(t, decimals)}
            </text>
          </g>
        ))}
        {/* 오른쪽 축은 눈금 글자만 둔다. 격자선까지 그으면 두 축의 선이 엇갈려 어느
            선이 어느 축인지 더 헷갈린다. */}
        {g.ticksR.map((t) => (
          <text key={`r${t}`} x={W - PAD.r + 6} y={g.yR(t) + 3} textAnchor="start"
                fontSize="10.5" fill={sideColor('right')}>
            {fmt(t, rightDecimals)}
          </text>
        ))}
        {refLine != null && g.yL && (
          <line x1={PAD.l} x2={W - PAD.r} y1={g.yL(refLine)} y2={g.yL(refLine)}
                stroke="var(--axis)" strokeDasharray="5 4" />
        )}
        {g.yearMarks.map((m) => (
          <text key={m} x={g.xOf(m)} y={height - 8} textAnchor="middle" fontSize="10.5"
                fill="var(--text-muted)">
            {m.slice(0, 4)}
          </text>
        ))}
        {g.paths.map((p) => (
          <path key={p.key} d={p.d} fill="none" stroke={p.color} strokeWidth={p.width ?? 1.9}
                strokeLinejoin="round"
                strokeDasharray={typeof p.dash === 'string' ? p.dash : p.dash ? '5 4' : undefined} />
        ))}
        {hm && (
          <g pointerEvents="none">
            <line x1={g.xOf(hm)} x2={g.xOf(hm)} y1={PAD.t} y2={height - PAD.b}
                  stroke="var(--text-muted)" strokeDasharray="3 3" />
            {g.paths.map((p, si) => {
              const v = g.lookup[si].get(hm)
              return v == null ? null : (
                <circle key={p.key} cx={g.xOf(hm)} cy={p.y(v)} r="3.2" fill={p.color} />
              )
            })}
          </g>
        )}
        {/* 마우스를 받는 판. 선이 얇아 선 위에서만 받으면 맞추기 어렵다. */}
        <rect x={PAD.l} y={PAD.t} width={g.iw} height={g.ih} fill="transparent" />
      </svg>
      {series.length > 1 && (
        <div className="legend">
          {/* 점선 표식은 `.swatch.dash` 의 background-image 로 그린다. 예전에 `background: 'none'`
              을 줬더니 그 무늬까지 지워져 점선 계열의 범례만 빈칸이었다 — 색만 빼려면 backgroundColor. */}
          {series.map((s) => (
            <span className="key" key={s.key}>
              <span className={`swatch${s.dash ? ' dash' : ''}`}
                    style={s.dash ? { color: s.color, backgroundColor: 'transparent' } : { background: s.color }} />
              {s.label}
              {hasRight && <span className="muted"> ({s.axis === 'right' ? '오른쪽' : '왼쪽'} 축)</span>}
            </span>
          ))}
        </div>
      )}
      {hm && (
        <div className="chart-tooltip"
             style={{ left: Math.min(hover.cx + 14, window.innerWidth - 220), top: Math.max(hover.cy - 12, 8) }}>
          <div className="t-title">{hm.slice(0, 4)}.{hm.slice(4)}</div>
          {series.map((s, si) => {
            const v = g.lookup[si].get(hm)
            const u = unitOf(s)
            return (
              <div className="t-row" key={s.key}>
                {series.length > 1 && <>{s.label} </>}
                {v == null ? '—' : `${fmt(v, decOf(s))}${u ? ` ${u}` : ''}`}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
