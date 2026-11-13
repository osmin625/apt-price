import { fmt } from '../../shared/Charts'
import Hint from '../../shared/Hint'

/**
 * 장기 투자의 지수 평가 넷을 실제 지수에 돌린 결과 — 지금 상태와 과거 성적(backend/app/stock/valuation.py).
 *
 * 지금 상태는 값과 **역사 백분위**(그달까지의 값 가운데 아래인 비율)다. 과거 성적은 백분위 다섯 칸마다 그 뒤 5·10년
 * 연평균 실질 수익률이고, 범위는 '주가가 평가와 상관없이 움직였다면' 의 95% 다(docs/stock/valuation.md '실제 지수에
 * 돌리는 법'). 판정은 응답의 `verdict` 를 옮길 뿐 화면이 따로 내리지 않는다. '사라·팔아라' 는 쓰지 않는다
 * (2026-11-12 합의) — '비싼 쪽·싼 쪽' 은 그 기법의 정의(높을수록 비싸다고 읽는다)를 옮긴 것이다.
 */
const signed = (v, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`)
const pct = (v, d = 1) => (v == null ? '—' : `${signed(v, d)}%`)
export const ym = (s) => (s.includes('Q') ? `${s.slice(0, 4)} ${s.slice(5)}분기` : `${s.slice(0, 4)}-${s.slice(4, 6)}`)
const value = (m, v) => (m.unit === '%p' || m.id === 'trend-position' ? `${signed(v)}${m.unit}` : `${fmt(v, m.unit === '배' ? 1 : 0)}${m.unit}`)
const side = (m) => (m.high === 'expensive' ? '높을수록 비싼 쪽' : '높을수록 싼 쪽')
const MARK = { above: '▲', below: '▼', inside: '' }

/** 카드에 펼쳐 두는 지수 하나의 지금 상태 — 값과 백분위. */
export function valShort(id, m, by) {
  if (!by || by.missing) return '자료 없음'
  return `${value({ ...m, id }, by.now.value)} · 백분위 ${fmt(by.now.pct, 0)}`
}

function NowLine({ id, m, by, ix }) {
  const n = by.now
  const parts = [`${m.label} ${value({ ...m, id }, n.value)}`]
  if (id === 'fed-model') parts.push(`이익 수익률 ${fmt(n.ey, 1)}% − 10년 국채 ${fmt(n.bond, 2)}%`)
  if (id === 'trend-position' && n.growth != null) parts.push(`추세 기울기 연 ${signed(n.growth)}%(물가 뺌)`)
  parts.push(`역사 백분위 ${fmt(n.pct, 0)}(${ym(n.since)}~ 가운데, ${side(m)})`)
  return (
    <p className="tq-now">
      <b>{ym(n.period)}</b> {ix.label} · {parts.join(' · ')}
    </p>
  )
}

function Cell({ r, minInd }) {
  if (!r || r.mean == null) return <td className="muted">—</td>
  const tone = r.verdict === 'above' ? 'tone-pos' : r.verdict === 'below' ? 'tone-neg' : ''
  return (
    <td>
      <span className={tone}>{MARK[r.verdict] || ''}{pct(r.mean)}</span>
      <div className="muted small">
        {r.verdict ? `${pct(r.lo95)} ~ ${pct(r.hi95)}` : `구간 ${r.n_ind}개 — ${minInd}개 미만`}
      </div>
    </td>
  )
}

function PerfTable({ by, meta }) {
  const [h1, h2] = meta.horizons.map(String)
  const p1 = by.perf[h1]
  const p2 = by.perf[h2]
  if (!p1.n) return <p className="muted small">이 지수에서는 그 뒤 {h1}년이 다 지난 달이 아직 없습니다.</p>
  const now = Math.min(Math.floor(by.now.pct / (100 / meta.buckets)), meta.buckets - 1)
  return (
    <>
      <div className="table-wrap">
        <table className="coef tq-perf">
          <thead>
            <tr>
              <th>역사 백분위</th><th>달</th><th>그 뒤 {h1}년(연)</th><th>그 뒤 {h2}년(연)</th>
            </tr>
          </thead>
          <tbody>
            {p1.rows.map((r, k) => (
              <tr key={r.lo} className={k === now ? 'tq-here' : ''}>
                <td>{r.lo}~{r.hi}{k === now ? ' ← 지금' : ''}</td>
                <td>{r.n}</td>
                <Cell r={r} minInd={meta.min_ind} />
                <Cell r={p2.rows[k]} minInd={meta.min_ind} />
              </tr>
            ))}
            <tr>
              <td>모든 달</td>
              <td>{p1.n}</td>
              <td>{pct(p1.base)}</td>
              <td>{p2.n ? pct(p2.base) : '—'}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted small">
        기점 {ym(p1.first)}~{ym(p1.last)} · 겹치지 않는 {h1}년 {p1.n_ind}개
        {p2.n ? ` · ${h2}년 ${p2.n_ind}개` : ''}
      </p>
    </>
  )
}

/** 창의 '실제 지수에서' 절. */
export default function ValuationSection({ id, live, error, ix, setIx }) {
  if (error) return <p className="empty">{error.message}</p>
  if (!live) return <p className="empty">불러오는 중…</p>
  const m = live.measures[id]
  const index = live.indices.find((x) => x.id === ix) || live.indices[0]
  const by = m.by[index.id]
  return (
    <>
      <h3>
        실제 지수에서
        <Hint
          wide
          notes={[
            by.source ? `계산: ${by.source}.` : null,
            `역사 백분위는 그달까지의 값 가운데 지금 값보다 아래인 비율입니다. ${side(m)}으로 읽습니다.`,
            `그 뒤 수익률은 물가를 뺀 주가(배당 제외, 현지 통화)의 연평균입니다. 표의 각 칸은 그달의 백분위가 그 칸에 들었던 달들의 평균입니다.`,
            `그달에 알 수 없던 값은 쓰지 않았습니다 — 분기 통계(시가총액·GDP)는 분기 끝 ${live.lag_q}달 뒤부터, 미국 이익은 ${live.lag_e}달 묵혀, 추세와 백분위는 그달까지의 자료로만 냈습니다.`,
            `이웃한 달의 ${live.horizons[1]}년은 거의 다 겹칩니다. 그래서 칸마다 겹치지 않는 구간 수를 세고, ${live.min_ind}개 미만이면 범위를 내지 않습니다.`,
            `범위: 실제 월 수익률을 12달 덩어리로 뽑아 이은 가짜 주가 경로 ${live.draws.toLocaleString()}개에서, 같은 달들이 모든 달 평균보다 얼마나 더(덜) 벌었는지의 95% 입니다 — 주가가 이 평가와 상관없이 움직였을 때입니다. 칸 평균이 범위 위면 ▲, 아래면 ▼.`,
            '이 범위는 주가가 몇 년에 걸쳐 평균으로 돌아오는 성질을 따로 빼지 않습니다. 그런 성질이 있다면 그 몫까지 이 평가의 공으로 보일 수 있습니다.',
            '과거 성적이 앞으로를 보장하지 않습니다. 기법 설명이지 투자 권유가 아닙니다.',
          ]}
        />
      </h3>
      <div className="seg" role="tablist" aria-label="지수">
        {live.indices.map((x) => (
          <button key={x.id} role="tab" aria-selected={x.id === index.id} onClick={() => setIx(x.id)}>{x.label}</button>
        ))}
      </div>
      {by.missing ? (
        <p className="muted small">{by.missing}</p>
      ) : (
        <>
          <NowLine id={id} m={m} by={by} ix={index} />
          <PerfTable by={by} meta={live} />
        </>
      )}
    </>
  )
}

/** 예시 자리에 그릴 실제 계열 — ExampleChart 스펙. */
export function realChart(id, m, by) {
  const s = by.series
  const dates = [ym(s.dates[0]), ym(s.dates[s.dates.length - 1])]
  const n = s.values.length
  const flat = (v) => Array(n).fill(v)
  if (id === 'fed-model') {
    return {
      close: s.ey, priceLabel: '이익 수익률', axis: true, yUnit: '%', dates,
      overlays: [{ label: '10년 국채', values: s.bond, color: 'var(--series-2)' }],
      panel: { label: '차이(%p)', series: [{ label: '차이', values: s.values, bar: true }], levels: [0] },
    }
  }
  if (id === 'trend-position') {
    // 가격 선은 맞춘 첫 달보다 앞에서 시작한다 — 편차는 그 길이에 맞춰 앞을 비운다.
    const pad = s.price.length - n
    const lo = Math.min(...s.price)
    const ticks = []
    const hi = Math.max(...s.price)
    for (let v = 10 ** Math.floor(Math.log10(lo)); v <= hi; v *= 10) ticks.push(v)
    return {
      close: s.price, priceLabel: '실질 지수(지금 = 100, 로그 눈금)', log: true, yTicks: ticks, axis: true,
      dates: [ym(s.price_dates[0]), ym(s.price_dates[s.price_dates.length - 1])],
      overlays: [{ label: '지금까지의 자료로 맞춘 추세', values: s.trend, color: 'var(--series-2)', dash: true }],
      panel: { label: '그달까지의 추세 대비(%)', series: [{ label: '편차', values: [...Array(pad).fill(null), ...s.values], bar: true }], levels: [0] },
    }
  }
  const mean = by.now.mean
  const sd = by.now.sd
  return {
    close: s.values, priceLabel: m.label, axis: true, yUnit: m.unit, dates,
    overlays: [{ label: '전체 기간 평균', values: flat(mean), color: 'var(--series-2)', dash: true }],
    band: { hi: flat(mean + sd), lo: flat(mean - sd), label: '평균 ± 1σ' },
  }
}
