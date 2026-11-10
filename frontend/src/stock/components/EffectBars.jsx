import { fmt, niceTicks, useMeasure } from '../../shared/Charts'

/**
 * 지표가 줄 선 가로 막대 — 가운데 0, 오른쪽 +, 왼쪽 −. 굵은 막대가 영향(평소 폭만큼 움직일 때 지수
 * 수익률이 평균 몇 % 달랐나), 가는 선이 그 95% 범위다.
 *
 * 색은 화면 공통 규칙대로 부호다(+ `--good`, − `--neg`). 다만 **범위가 0 을 넘으면 무채색**이다 —
 * 방향을 말할 만큼 뚜렷하지 않은 막대를 초록·빨강으로 칠하면 '올렸다·내렸다' 로 읽힌다. 판정은 응답의
 * `verdict` 다(범위로 백엔드가 정한다).
 *
 * 막대마다 단위가 다른 지표가 나란히 서도 길이를 견줄 수 있는 것은 '평소 폭' 으로 맞췄기 때문이다
 * (backend/app/stock/effects.py). 1단위당 값은 줄 오른쪽 글자에 둔다.
 */
const COLOR = { pos: 'var(--good)', neg: 'var(--neg)', none: 'var(--text-muted)' }
const signed = (v, d = 1) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`

export default function EffectBars({ rows, onPick }) {
  const [ref, width] = useMeasure()
  const live = rows.filter((r) => r.n)
  const ext = Math.max(5, ...live.flatMap((r) => [Math.abs(r.lo), Math.abs(r.hi), Math.abs(r.bar)]))
  const W = Math.max(width || 600, 300)
  const narrow = W < 520
  const L = narrow ? 104 : 140
  const R = narrow ? 8 : 130
  const ROW = 38
  const TOP = 8
  const H = TOP + rows.length * ROW + 22
  const x = (v) => L + ((v + ext) / (2 * ext)) * (W - L - R)
  const ticks = niceTicks(-ext, ext, 4).filter((t) => Math.abs(t) <= ext)

  return (
    <div ref={ref}>
      <svg width={W} height={H} role="img" aria-label="지표별 영향 막대">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={TOP} y2={H - 20} stroke="var(--border)"
                  strokeWidth={t === 0 ? 1.4 : 1} strokeDasharray={t === 0 ? '' : '2 3'} />
            <text x={x(t)} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--text-muted)">
              {t > 0 ? `+${t}` : t}%
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cy = TOP + i * ROW + ROW / 2
          if (!r.n) {
            return (
              <g key={r.id}>
                <text x={L - 8} y={cy + 4} textAnchor="end" fontSize="12.5">{r.label}</text>
                <text x={x(0) + 6} y={cy + 4} fontSize="11.5" fill="var(--text-muted)">표본이 짧아 재지 않음</text>
              </g>
            )
          }
          const c = COLOR[r.verdict]
          const per = `${signed(r.slope, 2)}% / 1${r.unit}`
          return (
            <g key={r.id} onClick={() => onPick(r)} style={{ cursor: 'pointer' }}>
              <rect x={0} y={cy - ROW / 2} width={W} height={ROW} fill="transparent" />
              <text x={L - 8} y={cy + 4} textAnchor="end" fontSize="12.5">{r.label}</text>
              <line x1={x(r.lo)} x2={x(r.hi)} y1={cy} y2={cy} stroke={c} strokeWidth={1.5} />
              <line x1={x(r.lo)} x2={x(r.lo)} y1={cy - 5} y2={cy + 5} stroke={c} strokeWidth={1.5} />
              <line x1={x(r.hi)} x2={x(r.hi)} y1={cy - 5} y2={cy + 5} stroke={c} strokeWidth={1.5} />
              <rect x={Math.min(x(0), x(r.bar))} y={cy - 7} width={Math.abs(x(r.bar) - x(0))} height={14}
                    fill={c} opacity={r.verdict === 'none' ? 0.45 : 0.9} />
              {/* 오른쪽 칸은 두 줄 — 값·1단위당 위, '시기에 따라 다름' 아래. 한 줄에 다 넣으면 잘렸다. */}
              {!narrow && (
                <>
                  <text x={W - R + 8} y={r.flip ? cy - 2 : cy + 4} fontSize="12">
                    <tspan fontWeight="600" fill={r.verdict === 'none' ? 'var(--text-muted)' : c}>{signed(r.bar)}%</tspan>
                    <tspan fill="var(--text-muted)" fontSize="11">{`  ${per}`}</tspan>
                  </text>
                  {r.flip && (
                    <text x={W - R + 8} y={cy + 12} fontSize="10.5" fill="var(--warning)">시기에 따라 다름</text>
                  )}
                </>
              )}
              <title>
                {`${r.label}: 평소 폭(1년 ${fmt(r.sd, 2)}${r.unit})만큼 움직일 때 ${signed(r.bar)}% `
                  + `(95% 범위 ${signed(r.lo)} ~ ${signed(r.hi)}%) · ${per} · ${r.n}개월`}
              </title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
