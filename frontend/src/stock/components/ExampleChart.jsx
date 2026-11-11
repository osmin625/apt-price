import { fmt, useMeasure } from '../../shared/Charts'

/**
 * 기법 저장소의 예시 그림 — 가격(선 또는 캔들) 위에 기법의 선·띠·표시를 얹고, 아래에 보조 지표 칸 하나.
 *
 * 스펙(`techniques/short.js`·`long.js` 의 `example()`)이 그릴 것을 전부 든다:
 *   close | bars        가격 — 선이면 종가 배열, 캔들이면 {o,h,l,c,v} 배열
 *   overlays            가격 축에 겹치는 선 [{label, values, color, dash}]
 *   band                가격 축의 띠 {hi, lo, label} — 볼린저·돈치안 채널
 *   marks               ▲(진입) ▼(청산) [{i, dir, label}] — 규칙을 돌려 얻은 날
 *   lines               주석 선 [{i0, v0, i1, v1, label}] — 목선·추세선·지지선
 *   points              이름 붙은 점 [{i, label}] — 왼쪽 어깨·머리 …
 *   panel               아래 칸 {label, series:[{values, color, bar}], levels, range}
 *   volume              캔들 아래 거래량 막대
 *   callout             캔들 하나를 가리키는 이름 {i, label} — 망치형·도지
 *   priceLabel · log    첫 선의 이름, 로그 눈금
 *   yTicks · yUnit      세로축 눈금 — 수준 자체가 기준인 것(CAPE 배수·금리 %)만
 *   xUnit               가로축 단위('일'·'개월'·'봉(5분)')
 *
 * 가격 축 숫자는 기본으로 적지 않는다 — 합성 가격이라 값에 뜻이 없고, 숫자가 있으면 실제 지수로 읽힌다.
 * 수준이 규칙인 것(RSI 70·30, CAPE 의 평균 배수)만 적는다. 표시 색은 화면 공통 규칙대로 ▲ 초록, ▼ 빨강.
 */
const P = { l: 8, r: 40, t: 10, b: 20 }

export default function ExampleChart({ spec }) {
  const [ref, width] = useMeasure()
  const W = Math.max(width || 640, 300)
  const candles = spec.bars
  const close = candles ? candles.map((b) => b.c) : spec.close
  const n = close.length
  const mainH = 220
  const panelH = spec.panel || spec.volume ? 92 : 0
  const H = P.t + mainH + (panelH ? panelH + 14 : 0) + P.b

  const vals = [
    ...(candles ? candles.flatMap((b) => [b.h, b.l]) : close),
    ...(spec.overlays || []).flatMap((o) => o.values),
    ...(spec.band ? [...spec.band.hi, ...spec.band.lo] : []),
    ...(spec.lines || []).flatMap((l) => [l.v0, l.v1]),
  ].filter((v) => v != null && Number.isFinite(v))
  const tf = spec.log ? Math.log : (v) => v
  const lo = Math.min(...vals.map(tf), ...(spec.yTicks || []).map(tf))
  const hi = Math.max(...vals.map(tf), ...(spec.yTicks || []).map(tf))
  const pad = (hi - lo) * 0.06 || 1
  const sx = (i) => P.l + (i / Math.max(1, n - 1)) * (W - P.l - P.r)
  const sy = (v) => P.t + mainH - ((tf(v) - (lo - pad)) / (hi - lo + 2 * pad)) * mainH
  const line = (vs, y = sy) =>
    vs.map((v, i) => (v == null ? null : `${sx(i).toFixed(1)},${y(v).toFixed(1)}`))
      .reduce((acc, p) => {
        if (p == null) acc.push([])
        else acc[acc.length - 1].push(p)
        return acc
      }, [[]])
      .filter((seg) => seg.length > 1)
      .map((seg) => `M${seg.join('L')}`)
      .join('')

  const pTop = P.t + mainH + 14
  const pr = spec.panel?.range
  const pVals = spec.panel ? spec.panel.series.flatMap((s) => s.values).filter((v) => v != null) : []
  const p0 = pr ? pr[0] : Math.min(0, ...pVals)
  const p1 = pr ? pr[1] : Math.max(...pVals, 1e-9)
  const py = (v) => pTop + panelH - ((v - p0) / (p1 - p0 || 1)) * panelH
  const vMax = candles ? Math.max(...candles.map((b) => b.v)) : 1
  const bw = Math.max(1, ((W - P.l - P.r) / n) * 0.7)

  const legend = [
    { label: spec.priceLabel || (candles ? '가격(캔들)' : '가격'), color: 'var(--text-primary)' },
    ...(spec.overlays || []).map((o) => ({ label: o.label, color: o.color, dash: o.dash })),
    ...(spec.band ? [{ label: spec.band.label, color: 'var(--series-3)', band: true }] : []),
  ]

  return (
    <div ref={ref} className="ex-chart">
      <div className="ex-legend">
        {legend.map((g) => (
          <span key={g.label}>
            <i className={`swatch${g.dash ? ' is-dash' : ''}`}
               style={{ background: g.band ? 'color-mix(in srgb, var(--series-3) 25%, transparent)' : g.dash ? undefined : g.color,
                        color: g.color }} />
            {g.label}
          </span>
        ))}
        {spec.marks?.some((m) => m.dir > 0) && <span><b className="tone-pos">▲</b> 진입</span>}
        {spec.marks?.some((m) => m.dir < 0) && <span><b className="tone-neg">▼</b> 청산</span>}
      </div>
      <svg width={W} height={H} role="img" aria-label="예시 그림(합성 데이터)">
        <rect x={P.l} y={P.t} width={W - P.l - P.r} height={mainH} fill="none" stroke="var(--border)" />
        {(spec.yTicks || []).map((v) => (
          <g key={`y${v}`}>
            <line x1={P.l} x2={W - P.r} y1={sy(v)} y2={sy(v)} stroke="var(--border)" strokeDasharray="2 3" />
            <text x={W - P.r + 4} y={sy(v) + 4} fontSize="10.5" fill="var(--text-muted)">{fmt(v, 1)}{spec.yUnit}</text>
          </g>
        ))}
        {spec.band && (
          <path
            d={`${line(spec.band.hi)}`}
            fill="none" stroke="var(--series-3)" strokeWidth={1} opacity={0.8}
          />
        )}
        {spec.band && (
          <path d={line(spec.band.lo)} fill="none" stroke="var(--series-3)" strokeWidth={1} opacity={0.8} />
        )}
        {spec.band && (
          <path
            d={(() => {
              const idx = spec.band.hi.map((v, i) => i).filter((i) => spec.band.hi[i] != null && spec.band.lo[i] != null)
              if (idx.length < 2) return ''
              const top = idx.map((i) => `${sx(i)},${sy(spec.band.hi[i])}`)
              const bot = idx.slice().reverse().map((i) => `${sx(i)},${sy(spec.band.lo[i])}`)
              return `M${top.join('L')}L${bot.join('L')}Z`
            })()}
            fill="var(--series-3)" opacity={0.1}
          />
        )}
        {candles
          ? candles.map((b, i) => {
              const up = b.c >= b.o
              const c = up ? 'var(--good)' : 'var(--neg)'
              return (
                <g key={i}>
                  <line x1={sx(i)} x2={sx(i)} y1={sy(b.h)} y2={sy(b.l)} stroke={c} strokeWidth={1} />
                  <rect x={sx(i) - bw / 2} width={bw} y={sy(Math.max(b.o, b.c))}
                        height={Math.max(1, Math.abs(sy(b.o) - sy(b.c)))} fill={c} />
                </g>
              )
            })
          : <path d={line(close)} fill="none" stroke="var(--text-primary)" strokeWidth={1.4} />}
        {(spec.overlays || []).map((o) => (
          <path key={o.label} d={line(o.values)} fill="none" stroke={o.color} strokeWidth={1.6}
                strokeDasharray={o.dash ? '5 4' : ''} />
        ))}
        {(spec.lines || []).map((l, k) => (
          <g key={`l${k}`}>
            <line x1={sx(l.i0)} x2={sx(l.i1)} y1={sy(l.v0)} y2={sy(l.v1)} stroke="var(--series-4)"
                  strokeWidth={1.4} strokeDasharray="6 3" />
            {l.label && (
              <text x={sx(l.i1) + 4} y={sy(l.v1) + 4} fontSize="11" fill="var(--series-4)">{l.label}</text>
            )}
          </g>
        ))}
        {(spec.points || []).map((p) => (
          <g key={`p${p.i}${p.label}`}>
            <circle cx={sx(p.i)} cy={sy(close[p.i])} r={3.5} fill="var(--series-2)" />
            <text x={sx(p.i)} y={sy(close[p.i]) + (p.below ? 16 : -8)} fontSize="11" textAnchor="middle"
                  fill="var(--series-2)">{p.label}</text>
          </g>
        ))}
        {(spec.marks || []).map((m, k) => {
          const y = m.dir > 0 ? sy(candles ? candles[m.i].l : close[m.i]) + 12 : sy(candles ? candles[m.i].h : close[m.i]) - 6
          return (
            <g key={`m${k}`}>
              <text x={sx(m.i)} y={y} fontSize="12" textAnchor="middle" fill={m.dir > 0 ? 'var(--good)' : 'var(--neg)'}>
                {m.dir > 0 ? '▲' : '▼'}
              </text>
              {m.label && (
                <text x={sx(m.i)} y={y + (m.dir > 0 ? 13 : -12)} fontSize="10.5" textAnchor="middle"
                      fill="var(--text-secondary)">{m.label}</text>
              )}
            </g>
          )
        })}

        {spec.callout && candles && (
          <g>
            <line x1={sx(spec.callout.i)} x2={sx(spec.callout.i)} y1={sy(candles[spec.callout.i].h) - 4}
                  y2={sy(candles[spec.callout.i].h) - 18} stroke="var(--series-2)" />
            <text x={sx(spec.callout.i)} y={sy(candles[spec.callout.i].h) - 22} fontSize="11" textAnchor="middle"
                  fill="var(--series-2)">{spec.callout.label}</text>
          </g>
        )}
        {spec.volume && candles && (
          <g>
            <text x={P.l + 4} y={pTop + 11} fontSize="11" fill="var(--text-muted)">거래량</text>
            {candles.map((b, i) => (
              <rect key={i} x={sx(i) - bw / 2} width={bw} y={pTop + panelH - (b.v / vMax) * panelH}
                    height={(b.v / vMax) * panelH}
                    fill={b.c >= b.o ? 'var(--good)' : 'var(--neg)'} opacity={0.45} />
            ))}
          </g>
        )}
        {spec.panel && (
          <g>
            <rect x={P.l} y={pTop} width={W - P.l - P.r} height={panelH} fill="none" stroke="var(--border)" />
            <text x={P.l + 4} y={pTop + 11} fontSize="11" fill="var(--text-muted)">{spec.panel.label}</text>
            {(spec.panel.levels || []).map((v) => (
              <g key={v}>
                <line x1={P.l} x2={W - P.r} y1={py(v)} y2={py(v)} stroke="var(--border)" strokeDasharray="3 3" />
                <text x={W - P.r + 4} y={py(v) + 4} fontSize="10.5" fill="var(--text-muted)">{fmt(v, 2)}</text>
              </g>
            ))}
            {spec.panel.series.map((s) =>
              s.bar ? (
                <g key={s.label}>
                  {s.values.map((v, i) =>
                    v == null ? null : (
                      <rect key={i} x={sx(i) - bw / 2} width={bw} y={Math.min(py(v), py(0))}
                            height={Math.abs(py(v) - py(0))} fill={v >= 0 ? 'var(--good)' : 'var(--neg)'} opacity={0.5} />
                    ),
                  )}
                </g>
              ) : (
                <path key={s.label} d={line(s.values, py)} fill="none" stroke={s.color} strokeWidth={1.4}
                      strokeDasharray={s.dash ? '5 4' : ''} />
              ),
            )}
          </g>
        )}
        <text x={W - P.r} y={H - 5} fontSize="10.5" textAnchor="end" fill="var(--text-muted)">
          {n}{spec.xUnit || '일'} →
        </text>
      </svg>
      {spec.panel?.series.some((s) => !s.bar) && (
        <div className="ex-legend">
          {spec.panel.series.filter((s) => !s.bar).map((s) => (
            <span key={s.label}>
              <i className={`swatch${s.dash ? ' is-dash' : ''}`} style={{ background: s.dash ? undefined : s.color, color: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
