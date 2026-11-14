import { useEffect, useMemo, useState } from 'react'

import { api } from '../../api'
import { fmt, useMeasure } from '../../shared/Charts'
import Hint from '../../shared/Hint'
import { baseEarnings, decompose, rate, yearOf } from '../techvalue/model'

/**
 * 기술주 가치 — 시가총액을 '지금 사업 + 기대 기술 + 설명 안 된 몫' 으로 나누고, 기술마다 실현 때 주가를 지금 주가와
 * 견준다(2026-11-14 요청). 계산은 `techvalue/model.js`, 재료는 backend/app/stock/techvalue.py, 규칙은 docs/stock/tech-value.md.
 *
 * 시나리오(실현 해·이익·확률·PER)는 가정이라 화면에서 바꿔 볼 수 있고, 같은 줄에 '지금 주가가 맞으려면' 의 역산을 둔다 —
 * 가정이 틀려도 역산은 주가에서 나온다. 화면 문구에는 숫자를 박지 않는다 — 전부 응답과 계산에서 온다.
 */
// 색 토큰은 넷뿐이다(styles.css --series-1~4). 기술이 넷을 넘으면 다섯째부터 색이 돌아 쓰인다 — 한 종목에 넷을 넘기지 않는다.
const SEG = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']

export function usd(v) {
  if (v == null || !Number.isFinite(v)) return '—'
  if (v === 0) return '$0'
  const a = Math.abs(v)
  const s = v < 0 ? '−' : ''
  if (a >= 1e12) return `${s}$${fmt(a / 1e12, 2)}조`
  if (a >= 1e8) return `${s}$${fmt(a / 1e8, 0)}억`
  return `${s}$${fmt(a / 1e6, 0)}백만`
}
const day = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
const ym = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}`

function Bar({ d }) {
  const parts = [
    { label: '지금 사업', v: d.base, color: 'var(--text-secondary)' },
    ...d.techs.map((t, k) => ({ label: t.name, v: t.pv, color: SEG[k % SEG.length] })),
  ]
  const explained = parts.reduce((a, p) => a + p.v, 0)
  const total = Math.max(d.cap, explained)
  const left = (v) => `${(v / total) * 100}%`
  let x = 0
  return (
    <div className="tv-bar-wrap">
      <div className="tv-bar" role="img" aria-label="시가총액 분해">
        {parts.map((p) => {
          const el = <span key={p.label} style={{ left: left(x), width: left(p.v), background: p.color }} />
          x += p.v
          return el
        })}
        {d.residual > 0 && (
          <span className="tv-rest" style={{ left: left(explained), width: left(d.residual) }} />
        )}
        <i className="tv-cap" style={{ left: left(d.cap) }} />
      </div>
      <div className="tv-legend">
        {parts.map((p) => (
          <span key={p.label}>
            <i className="swatch" style={{ background: p.color }} />
            {p.label} <b>{usd(p.v)}</b> <span className="muted">{fmt((p.v / d.cap) * 100, 0)}%</span>
          </span>
        ))}
        <span>
          <i className="swatch tv-rest-swatch" />
          설명 안 된 몫 <b className={d.residual >= 0 ? '' : 'tone-neg'}>{usd(d.residual)}</b>{' '}
          <span className="muted">{fmt((d.residual / d.cap) * 100, 0)}%</span>
        </span>
      </div>
    </div>
  )
}

function num(v, set, { step = 1, min, max, w = 64 }) {
  return (
    <input className="tv-num" type="number" value={v} step={step} min={min} max={max} style={{ width: w }}
           onChange={(e) => e.target.value !== '' && set(Number(e.target.value))} />
  )
}

function TechTable({ d, co, setTech, r, price }) {
  return (
    <div className="table-wrap">
      <table className="coef tv-table">
        <thead>
          <tr>
            <th>기술</th><th>실현 해</th><th>그해 순이익($십억)</th><th>확률(%)</th><th>그때 PER</th>
            <th>지금 값</th><th>지금 주가가 맞으려면</th><th>실현 때 주가</th>
          </tr>
        </thead>
        <tbody>
          {d.techs.map((t, k) => (
            <tr key={t.id}>
              <td>
                <i className="swatch" style={{ background: SEG[k % SEG.length] }} /> {t.name}
                <Hint notes={[`근거: ${t.source}`, '실현 해·이익·확률·PER 은 이 저장소가 둔 가정입니다. 칸을 바꿔 보세요.']} />
              </td>
              <td>{num(t.year, (v) => setTech(k, { year: v }), { min: 2026, max: 2060, w: 70 })}</td>
              <td>{num(t.profit, (v) => setTech(k, { profit: v }), { step: 0.5, min: 0, w: 70 })}</td>
              <td>{num(Math.round(t.prob * 100), (v) => setTech(k, { prob: Math.min(100, Math.max(1, v)) / 100 }), { min: 1, max: 100, w: 56 })}</td>
              <td>{num(t.pe, (v) => setTech(k, { pe: v }), { min: 5, max: 60, w: 56 })}</td>
              <td>{usd(t.pv)}</td>
              <td>
                {t.gap <= 0 ? <span className="muted">다른 몫으로 이미 넘침</span> : (
                  <>
                    그해 순이익 <b>{usd(t.need * 1e9)}</b>
                    <div className="muted small">
                      {t.needYear == null ? '지금 실현돼도 이 이익으론 모자람' : `이 이익이면 ${Math.round(t.needYear)}년에 실현돼야`}
                    </div>
                  </>
                )}
              </td>
              <td>
                <b>${fmt(t.priceAt, t.priceAt < 20 ? 2 : 0)}</b>
                {t.cagr != null && (
                  <div className={`small ${t.cagr >= r ? 'tone-pos' : 'tone-neg'}`}>
                    지금 ${fmt(price, price < 20 ? 2 : 0)}에서 연 {t.cagr >= 0 ? '+' : '−'}{fmt(Math.abs(t.cagr), 1)}%
                  </div>
                )}
              </td>
            </tr>
          ))}
          {!d.techs.length && (
            <tr><td colSpan={8} className="muted">이 종목에는 시나리오가 아직 없습니다.</td></tr>
          )}
        </tbody>
      </table>
      <p className="muted small">{co.label} 시나리오 {d.techs.length}개 · 할인율 {fmt(r, 1)}%</p>
    </div>
  )
}

function PriceChart({ co, d, r, now }) {
  const [ref, width] = useMeasure()
  const W = Math.max(width || 640, 300)
  const H = 260
  const P = { l: 8, r: 52, t: 12, b: 22 }
  const h = co.history
  const t0 = yearOf(`${h.months[0]}15`)
  const price = co.price.close
  const end = Math.max(now + 1, ...d.techs.map((t) => t.year + 1.5))
  const pts = d.techs.map((t, k) => ({ x: t.year + 0.5, y: t.priceAt, k, ok: t.cagr != null && t.cagr >= r, name: t.name }))
  const req = (x) => price * (1 + r / 100) ** (x - now)
  const ys = [...h.close, price, req(end), ...pts.map((p) => p.y)].filter((v) => v > 0)
  const lo = Math.log(Math.min(...ys)) - 0.1
  const hi = Math.log(Math.max(...ys)) + 0.1
  const sx = (x) => P.l + ((x - t0) / (end - t0)) * (W - P.l - P.r)
  const sy = (v) => P.t + (1 - (Math.log(v) - lo) / (hi - lo)) * (H - P.t - P.b)
  const ticks = []
  for (let e = Math.floor(lo / Math.LN10); e <= Math.ceil(hi / Math.LN10); e++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** e
      if (Math.log(v) >= lo && Math.log(v) <= hi) ticks.push(v)
    }
  }
  const hist = h.months.map((m, i) => `${i ? 'L' : 'M'}${sx(yearOf(`${m}15`)).toFixed(1)},${sy(h.close[i]).toFixed(1)}`).join('')
  const reqLine = [now, end].map((x, i) => `${i ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(req(x)).toFixed(1)}`).join('')
  const years = []
  for (let y = Math.ceil(t0 / 5) * 5; y <= end; y += 5) years.push(y)
  return (
    <div ref={ref}>
      <div className="ex-legend">
        <span><i className="swatch" style={{ background: 'var(--text-primary)' }} />수정 종가(월말)</span>
        <span><i className="swatch is-dash" style={{ color: 'var(--series-2)' }} />지금 주가가 할인율로 자라는 선</span>
        <span><b className="tone-pos">●</b> 실현 때 주가가 선 위 · <b className="tone-neg">●</b> 아래</span>
      </div>
      <svg width={W} height={H} role="img" aria-label={`${co.label} 주가와 기술별 실현 때 주가`}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={P.l} x2={W - P.r} y1={sy(v)} y2={sy(v)} stroke="var(--border)" strokeDasharray="2 3" />
            <text x={W - P.r + 4} y={sy(v) + 4} fontSize="10.5" fill="var(--text-muted)">${fmt(v, v < 10 ? 1 : 0)}</text>
          </g>
        ))}
        {years.map((y) => (
          <text key={y} x={sx(y)} y={H - 6} fontSize="10.5" textAnchor="middle" fill="var(--text-muted)">{y}</text>
        ))}
        <line x1={sx(now)} x2={sx(now)} y1={P.t} y2={H - P.b} stroke="var(--border)" />
        <path d={hist} fill="none" stroke="var(--text-primary)" strokeWidth={1.4} />
        <path d={reqLine} fill="none" stroke="var(--series-2)" strokeWidth={1.4} strokeDasharray="5 4" />
        {pts.map((p) => (
          <g key={p.k}>
            <line x1={sx(now)} y1={sy(price)} x2={sx(p.x)} y2={sy(p.y)} stroke={SEG[p.k % SEG.length]} strokeWidth={1} opacity={0.5} />
            <circle cx={sx(p.x)} cy={sy(p.y)} r={5} fill={p.ok ? 'var(--good)' : 'var(--neg)'} stroke={SEG[p.k % SEG.length]} strokeWidth={2} />
            <text x={sx(p.x) - 7} y={sy(p.y) + 4} fontSize="11" textAnchor="end" fill="var(--text-secondary)">{p.name}</text>
          </g>
        ))}
      </svg>
    </div>
  )
}

export default function TechValueView() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [pick, setPick] = useState(null)
  const [mode, setMode] = useState('op')
  const [erp, setErp] = useState(null)
  const [g, setG] = useState(0)
  const [edits, setEdits] = useState({})

  useEffect(() => {
    let alive = true
    api.stockTechValue().then((d) => alive && setData(d)).catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [])

  const co = data?.companies.find((c) => c.id === pick) || data?.companies[0]
  const techs = co ? edits[co.id] || co.scenarios : []
  const ready = co && !co.missing
  const R = data && ready && co.beta ? rate({ y10: data.rate.y10, beta: co.beta.value, erp: erp ?? data.rate.erp }) : null
  const now = ready ? yearOf(co.price.date) : 0
  const e0 = ready ? baseEarnings(co.ttm, mode, data.rate.tax) : 0
  const args = ready && R != null ? { cap: co.cap, shares: co.shares.value, price: co.price.close, e0, g, now, techs } : null
  const d = useMemo(() => args && decompose({ ...args, r: R }), [JSON.stringify(args), R]) // eslint-disable-line react-hooks/exhaustive-deps
  const up = useMemo(() => args && decompose({ ...args, r: R + 1 }), [JSON.stringify(args), R]) // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <section className="card"><p className="empty">{error.message}</p></section>
  if (!data) return <section className="card"><p className="empty">불러오는 중…</p></section>

  const setTech = (k, patch) => setEdits({ ...edits, [co.id]: techs.map((t, j) => (j === k ? { ...t, ...patch } : t)) })
  const usesOp = mode === 'op' && co.ttm?.operating_income
  const change = (a, b) => (a > 0 ? `${b >= a ? '+' : '−'}${fmt(Math.abs(b / a - 1) * 100, 0)}%` : '—')

  return (
    <>
      <section className="card">
        <h2>
          기술주 가치 — 시가총액을 나누면
          <Hint
            wide
            notes={[
              '시가총액 = 지금 사업의 값 + 기대 기술마다의 지금 값 + 설명 안 된 몫. 지금 사업은 지난 12개월 이익이 앞으로도 그대로(또는 고른 성장률로) 이어질 때의 값이고, 기술은 확률 × (실현 해의 순이익 × 그때 PER) 을 지금으로 할인한 값입니다.',
              '설명 안 된 몫이 크면 주가가 시나리오보다 더 큰 기대를 담고 있다는 뜻이고, 음수면 시나리오가 주가보다 낙관적이라는 뜻입니다.',
              '할인율 = 미국 10년 국채(지수 분석과 같은 월평균) + 베타 × 주식 위험 프리미엄. 베타는 최근 최대 60달 종목 월 수익률을 S&P 500 에 회귀한 기울기입니다. 위험 프리미엄 기본값은 관례이지 잰 값이 아닙니다.',
              '이익 기준: 영업이익 세후(미국 연방 법정 세율)는 영업 밖의 일회성 손익(보유 지분 평가 이익 등)을 뺍니다. 영업이익을 따로 내지 않는 회사는 순이익을 씁니다. 적자면 지금 사업의 값을 0 으로 둡니다 — 적자를 기대 기술에 쓰는 돈으로 봅니다.',
              '주가는 Alpha Vantage, 재무는 미국 SEC EDGAR 입니다. 시나리오의 근거 문구는 발표된 사실이고, 숫자는 가정입니다.',
            ]}
          />
        </h2>
        <div className="seg" role="tablist" aria-label="종목">
          {data.companies.map((c) => (
            <button key={c.id} role="tab" aria-selected={c.id === co.id} onClick={() => setPick(c.id)}>{c.label}</button>
          ))}
        </div>
        {!ready ? <p className="empty">{co.missing}</p> : (
          <>
            <p className="tq-now">
              <b>{day(co.price.date)}</b> {co.symbol} ${fmt(co.price.close, 2)} · 시가총액 {usd(co.cap)}
              {' '}· {co.shares.kind} {fmt(co.shares.value / 1e8, 1)}억 주({ym(co.shares.end)}) · 지난 12개월{' '}
              {usesOp ? '영업이익 세후' : '순이익'} {usd(e0)}({ym((usesOp ? co.ttm.operating_income : co.ttm.net_income).end)})
            </p>
            <div className="tn-ctrl">
              <span className="seg" role="tablist" aria-label="이익 기준">
                <button role="tab" aria-selected={mode === 'op'} onClick={() => setMode('op')}>영업이익 세후</button>
                <button role="tab" aria-selected={mode === 'ni'} onClick={() => setMode('ni')}>순이익</button>
              </span>
              <label>
                위험 프리미엄 <b>{fmt(erp ?? data.rate.erp, 1)}%</b>
                <input type="range" min={data.rate.erp_range[0]} max={data.rate.erp_range[1]} step="0.5"
                       value={erp ?? data.rate.erp} onChange={(e) => setErp(Number(e.target.value))} />
              </label>
              <label>
                지금 사업 성장률 <b>{fmt(g, 1)}%</b>
                <input type="range" min="0" max="4" step="0.5" value={g} onChange={(e) => setG(Number(e.target.value))} />
              </label>
              {edits[co.id] && (
                <button className="chip" onClick={() => setEdits({ ...edits, [co.id]: undefined })}>시나리오 기본값으로</button>
              )}
            </div>
            {R == null ? <p className="empty">베타를 잴 월봉이 모자랍니다.</p> : (
              <>
                <p className="muted small">
                  할인율 <b>{fmt(R, 1)}%</b> = 10년 국채 {fmt(data.rate.y10, 2)}%({ym(data.rate.y10_month)}) + 베타 {fmt(co.beta.value, 2)}
                  ({co.beta.months}달) × 위험 프리미엄 {fmt(erp ?? data.rate.erp, 1)}%
                </p>
                <Bar d={d} />
                <p className="muted small">
                  10년 금리가 1%p 오르면 — 지금 사업 {change(d.base, up.base)} · 기대 기술 {change(d.sum, up.sum)}
                </p>
              </>
            )}
          </>
        )}
      </section>
      {ready && R != null && (
        <>
          <section className="card">
            <h2>
              기대 기술 — 가정과 역산
              <Hint
                wide
                notes={[
                  '칸의 기본값은 이 저장소가 둔 가정입니다. 바꾸면 위 막대와 아래 그림이 바로 바뀝니다. 다른 종목으로 갔다 와도 바꾼 값은 남습니다.',
                  '지금 주가가 맞으려면: 다른 기술은 표대로 두고, 남는 몫을 이 기술 하나가 다 설명한다면 그해 순이익이 얼마여야 하는지, 또는 표의 이익이라면 언제 실현돼야 하는지입니다.',
                  '실현 때 주가 = (지금 사업 이익 + 그 기술 이익) × 그때 PER ÷ 지금 주식 수. 확률은 넣지 않은 \'실현됐다면\' 의 주가이고, 주식 수가 늘면(희석) 더 낮습니다. 지금 주가에서 그 주가까지의 연 수익률이 할인율보다 높으면 초록, 낮으면 빨강입니다.',
                ]}
              />
            </h2>
            <TechTable d={d} co={co} setTech={setTech} r={R} price={co.price.close} />
          </section>
          <section className="card">
            <h2>
              주가 — 지금과 실현 때
              <Hint notes={['로그 눈금입니다. 점선은 지금 주가가 할인율만큼 해마다 자라는 길 — 기대 수익을 받으려면 주가가 가야 할 길입니다. 점이 선 위면 그 기술이 실현됐을 때 할인율보다 더 번다는 뜻입니다(확률은 넣지 않음).']} />
            </h2>
            <PriceChart co={co} d={d} r={R} now={now} />
          </section>
          <ReflectCard co={co} />
        </>
      )}
    </>
  )
}

const pp = (v, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`)

/** 지난 1년 주가 변화를 거시·실적·설명 안 된 몫으로(backend/app/stock/reflect.py). 시나리오와 달리 잰 값이다. */
function ReflectCard({ co }) {
  const rf = co.reflect
  const head = (
    <h2>
      주가 1년 변화 — 요인별로 나누면
      <Hint
        wide
        notes={[
          '1년 주가 변화 = 모든 요인이 평균일 때 + 요인별 몫 + 설명 안 된 몫. 같은 달에 같이 움직인 크기이지 원인의 크기가 아닙니다. 예측도 아닙니다.',
          '거시 요인은 지수 분석의 미국 지표 그대로이고, 오를 때 주가가 같이 가는지 거꾸로 가는지(방향)는 재기 전에 상식으로 정했습니다. 크기만 데이터로 재고, 데이터가 그 방향과 반대로 움직였으면 크기가 0(반영 안 보임)이 됩니다.',
          '실적 요인은 지난 12개월 매출 상승률과 이익률 변화입니다. 그달 말까지 처음 제출된 값만 씁니다 — 나중에 고쳐진 숫자로 과거를 설명하지 않습니다.',
          rf?.available
            ? `범위는 ${rf.boot.block}달 덩어리 부트스트랩 ${rf.boot.n}번의 ${Math.round(rf.boot.q[0] * 100)}~${Math.round(rf.boot.q[1] * 100)}% 입니다. 합성 자료에 참값을 심어 재 보니 이 범위가 참값을 80% 안팎 덮었습니다 — 그래서 '80% 범위' 라고 부릅니다.`
            : null,
          rf?.available
            ? `기간을 반으로 나눠 맞추면 설명력이 ${rf.halves.map((h) => `${ym(h.from)}~ ${fmt(h.r2, 2)}`).join(', ')} 입니다. 반쪽마다 크기가 크게 다르면 얽힌 요인끼리 몫을 주고받는 것입니다.`
            : null,
        ]}
      />
    </h2>
  )
  if (!rf?.available) {
    return <section className="card">{head}<p className="empty">{rf?.note || '자료가 없습니다.'}</p></section>
  }
  const sum = (g) => rf.factors.filter((f) => f.group === g).reduce((a, f) => a + f.contrib, 0)
  return (
    <section className="card">
      {head}
      <p className="tq-now">
        <b>{ym(rf.now)}</b> {co.label} 1년 변화 <b className={rf.actual >= 0 ? 'tone-pos' : 'tone-neg'}>{pp(rf.actual)}%</b>
        {' '}= 평균일 때 {pp(rf.base)} · 거시 {pp(sum('거시'))} · 실적 {pp(sum('실적'))} · 설명 안 된 몫{' '}
        <b>{pp(rf.residual)}</b>%p
      </p>
      <p className="muted small">{ym(rf.from)}~{ym(rf.now)} {rf.months}달 · 설명력(R²) {fmt(rf.r2, 2)}</p>
      <div className="table-wrap">
        <table className="coef tv-table">
          <thead>
            <tr><th>요인</th><th>방향</th><th>지금 움직임</th><th>위치(σ)</th><th>지금의 몫(%p)</th><th>1σ 당(%p)</th></tr>
          </thead>
          <tbody>
            {rf.factors.map((f) => (
              <tr key={f.key}>
                <td>{f.label} <span className="muted small">{f.group}</span></td>
                <td>{f.sign > 0 ? '▲ 정방향' : '▼ 역방향'}</td>
                <td>{pp(f.x, 2)}{f.unit}</td>
                <td>{pp(f.z, 2)}</td>
                <td>
                  {f.b > 0 ? <b className={f.contrib >= 0 ? 'tone-pos' : 'tone-neg'}>{pp(f.contrib)}</b> : <span className="muted">반영 안 보임</span>}
                  <div className="muted small">80% 범위 {pp(f.lo)} ~ {pp(f.hi)}</div>
                </td>
                <td>
                  {fmt(f.b, 1)}
                  <div className="muted small">{f.b_lo === 0 ? `0 이 된 비율 ${f.zero_pct}%` : `${fmt(f.b_lo, 1)}~${fmt(f.b_hi, 1)}`}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ReflectChart s={rf.series} />
    </section>
  )
}

function ReflectChart({ s }) {
  const [ref, width] = useMeasure()
  const W = Math.max(width || 640, 300)
  const H = 200
  const P = { l: 8, r: 44, t: 10, b: 20 }
  const fitted = s.actual.map((_, i) => s.base + s.macro[i] + s.fund[i])
  const vals = [...s.actual, ...fitted, 0]
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const n = s.months.length
  const sx = (i) => P.l + (i / Math.max(1, n - 1)) * (W - P.l - P.r)
  const sy = (v) => P.t + (1 - (v - lo) / (hi - lo || 1)) * (H - P.t - P.b)
  const path = (vs) => vs.map((v, i) => `${i ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join('')
  const step = [10, 20, 50, 100, 200, 500].find((k) => (hi - lo) / k <= 5) || 1000
  const ticks = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v)
  return (
    <div ref={ref}>
      <div className="ex-legend">
        <span><i className="swatch" style={{ background: 'var(--text-primary)' }} />실제 1년 변화</span>
        <span><i className="swatch" style={{ background: 'var(--series-1)' }} />거시·실적으로 맞춘 값</span>
      </div>
      <svg width={W} height={H} role="img" aria-label="1년 주가 변화와 요인으로 맞춘 값">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={P.l} x2={W - P.r} y1={sy(v)} y2={sy(v)} stroke="var(--border)" strokeDasharray={v === 0 ? '' : '2 3'} />
            <text x={W - P.r + 4} y={sy(v) + 4} fontSize="10.5" fill="var(--text-muted)">{v}%</text>
          </g>
        ))}
        <path d={path(fitted)} fill="none" stroke="var(--series-1)" strokeWidth={1.6} />
        <path d={path(s.actual)} fill="none" stroke="var(--text-primary)" strokeWidth={1.4} />
        <text x={P.l} y={H - 5} fontSize="10.5" fill="var(--text-muted)">{ym(s.months[0])}</text>
        <text x={W - P.r} y={H - 5} fontSize="10.5" textAnchor="end" fill="var(--text-muted)">{ym(s.months[n - 1])}</text>
      </svg>
    </div>
  )
}
