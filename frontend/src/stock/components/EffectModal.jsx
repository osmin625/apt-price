import { useMemo } from 'react'

import { fmt, niceTicks, useMeasure } from '../../shared/Charts'
import Hint from '../../shared/Hint'
import Modal from '../../shared/Modal'

/**
 * 지표 하나를 눌렀을 때의 창 — 막대 하나를 네 가지로 풀어 본다.
 *
 * 1. 산점도: 달마다 (지표의 1년 움직임, 지수 수익률). 직선은 이 점들에 맞춘 것이라 막대의 기울기와
 *    거의 같지만 같지는 않다(막대는 로그 수익률로 잰다).
 * 2. 오른 시기 vs 내린 시기: 같은 질문을 '평균 두 개' 로. 나누는 선은 지표의 꼴마다 다르다(`cut`).
 * 3. 앞·뒤 절반: 표본을 시간순으로 반 나눠 다시 잰 막대. 방향이 다르면 한 숫자로 요약하기 어렵다.
 * 4. 함께 넣으면: 다른 지표를 같은 회귀에 넣은 값. 하나씩 볼 때와 크게 다르면 그 막대에는 다른 지표가
 *    섞여 있었다는 뜻이다.
 */
const signed = (v, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`)
const ym = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}`
const tone = (verdict) => (verdict === 'pos' ? 'tone-pos' : verdict === 'neg' ? 'tone-neg' : 'muted')
const VERDICT = { pos: '+ 뚜렷함', neg: '− 뚜렷함', none: '뚜렷하지 않음' }

function sides(r) {
  if (r.kind === 'level') return ['양수인 달', '역전된 달']
  // 상승률은 중앙값으로 나눈다(effects.py). 중앙값이 음수일 수 있어(환율) '빨리 오른' 이라 하지 않는다.
  if (r.kind === 'growth') return [`1년 상승률 ${signed(r.cut, 1)}% 이상(중앙값 위)`, `${signed(r.cut, 1)}% 미만`]
  return ['1년 새 오른 달', '1년 새 내린 달']
}

function Scatter({ points, unit, yLabel }) {
  const [ref, width] = useMeasure()
  const W = Math.max(width || 560, 280)
  const H = 260
  const P = { l: 48, r: 12, t: 10, b: 30 }
  const g = useMemo(() => {
    const xs = points.map((p) => p[1])
    const ys = points.map((p) => p[2])
    const pad = (lo, hi) => [lo - (hi - lo) * 0.05 || lo - 1, hi + (hi - lo) * 0.05 || hi + 1]
    const [x0, x1] = pad(Math.min(...xs), Math.max(...xs))
    const [y0, y1] = pad(Math.min(...ys, 0), Math.max(...ys, 0))
    const mx = xs.reduce((a, b) => a + b, 0) / xs.length
    const my = ys.reduce((a, b) => a + b, 0) / ys.length
    const sxx = xs.reduce((a, v) => a + (v - mx) ** 2, 0)
    const b = sxx ? xs.reduce((a, v, i) => a + (v - mx) * (ys[i] - my), 0) / sxx : 0
    return { x0, x1, y0, y1, line: (x) => my + b * (x - mx) }
  }, [points])
  const sx = (v) => P.l + ((v - g.x0) / (g.x1 - g.x0)) * (W - P.l - P.r)
  const sy = (v) => H - P.b - ((v - g.y0) / (g.y1 - g.y0)) * (H - P.t - P.b)
  return (
    <div ref={ref}>
      <svg width={W} height={H} role="img" aria-label={`지표 움직임과 ${yLabel}`}>
        {niceTicks(g.y0, g.y1, 4).map((t) => (
          <g key={`y${t}`}>
            <line x1={P.l} x2={W - P.r} y1={sy(t)} y2={sy(t)} stroke="var(--border)"
                  strokeDasharray={t === 0 ? '' : '2 3'} />
            <text x={P.l - 6} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="var(--text-muted)">{t}%</text>
          </g>
        ))}
        {(g.x1 - g.x0 >= 4 ? niceTicks(g.x0, g.x1, 5) : [g.x0, (g.x0 + g.x1) / 2, g.x1]).map((t) => (
          <text key={`x${t}`} x={sx(t)} y={H - 10} textAnchor="middle" fontSize="11" fill="var(--text-muted)">
            {fmt(t, g.x1 - g.x0 >= 4 ? 0 : 1)}{unit}
          </text>
        ))}
        {points.map((p) => (
          <circle key={p[0]} cx={sx(p[1])} cy={sy(p[2])} r={2.6} fill="var(--series-1)" opacity={0.45}>
            <title>{`${ym(p[0])} · 지표 ${signed(p[1], 2)}${unit} · ${yLabel} ${signed(p[2])}%`}</title>
          </circle>
        ))}
        <line x1={sx(g.x0)} x2={sx(g.x1)} y1={sy(g.line(g.x0))} y2={sy(g.line(g.x1))}
              stroke="var(--series-2)" strokeWidth={2} />
      </svg>
    </div>
  )
}

export default function EffectModal({ ix, row: r, joint, horizonLabel, onClose }) {
  const [upLabel, downLabel] = sides(r)
  const j = joint?.by?.[r.id]
  const yLabel = `${ix.label} ${horizonLabel} 수익률`
  return (
    <Modal title={`${r.label} → ${ix.label} · ${horizonLabel}`} onClose={onClose} wide>
      <p>
        평소 폭(1년 {fmt(r.sd, 2)}{r.unit})만큼 움직일 때 <strong className={tone(r.verdict)}>{signed(r.bar)}%</strong>
        {' '}(95% 범위 {signed(r.lo)} ~ {signed(r.hi)}%) · 1{r.unit}당 {signed(r.slope, 2)}% ·{' '}
        <span className={tone(r.verdict)}>{VERDICT[r.verdict]}</span>
        <Hint
          notes={[
            `${ym(r.from)}~${ym(r.to)} 의 ${r.n}개월입니다. 달마다 1년 창을 재서 이웃한 달끼리 겹칩니다 — 범위는 그 겹침을 감안해 넓혔습니다.`,
            r.pub_lag
              ? `이 지표는 다음 달에야 발표됩니다. '그 뒤' 는 발표된 달부터 셉니다.`
              : '이 지표는 그날 알려지므로 그 달 말부터 셉니다.',
            r.kind === 'level' ? '장단기 금리차만 1년 변화가 아니라 수준입니다 — 역전(음수) 여부가 신호라서입니다.' : null,
            `출처: ${r.source}.`,
          ]}
        />
      </p>

      <h3>달마다</h3>
      <Scatter points={r.points} unit={r.unit} yLabel={yLabel} />

      <h3>오른 시기 vs 내린 시기</h3>
      <table className="coef">
        <tbody>
          <tr><td>{upLabel}</td><td>{r.up.n}개월</td><td>평균 {signed(r.up.mean)}%</td></tr>
          <tr><td>{downLabel}</td><td>{r.down.n}개월</td><td>평균 {signed(r.down.mean)}%</td></tr>
        </tbody>
      </table>

      <h3>
        앞·뒤 절반
        {r.flip && <span className="small" style={{ color: 'var(--warning)' }}> · 시기에 따라 다름</span>}
      </h3>
      <table className="coef">
        <tbody>
          {r.halves.map((h) => (
            <tr key={h.from}><td>{ym(h.from)}~{ym(h.to)}</td><td>{signed(h.bar)}%</td></tr>
          ))}
        </tbody>
      </table>

      <h3>
        다른 지표를 함께 넣으면
        <Hint notes={['같은 지수의 지표를 모두 한 회귀에 넣어, 다른 지표가 같이 움직인 몫을 뺀 값입니다. 모든 지표가 있는 달만 씁니다.']} />
      </h3>
      {j ? (
        <p>
          <strong className={tone(j.verdict)}>{signed(j.bar)}%</strong> (95% 범위 {signed(j.lo)} ~ {signed(j.hi)}%) ·{' '}
          <span className={tone(j.verdict)}>{VERDICT[j.verdict]}</span> · {ym(joint.from)}~{ym(joint.to)} {joint.n}개월
        </p>
      ) : (
        <p className="muted">표본이 짧아 지표를 함께 넣으면 범위를 잴 수 없습니다.</p>
      )}
    </Modal>
  )
}
