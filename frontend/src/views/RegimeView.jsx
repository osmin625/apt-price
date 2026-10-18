import { useEffect, useState } from 'react'

import { api } from '../api'
import { fmt, useMeasure, useTooltip } from '../components/Charts'
import PanelCard from '../components/PanelCard'
import HeatLegend from '../components/HeatLegend'
import Hint from '../components/Hint'
import { heatVars, zText } from '../components/heat'
import TopicModal from '../topics/TopicModal'
import { homeOf, topicFor } from '../topics/registry'

/**
 * 거시 분석 — 집값에 닿는 거시 요인이 **지금 어떤 상태인지**, 그리고 **과거에 비슷했던 때
 * 그 뒤 집값이 어땠는지**.
 *
 * ## 예측하지 않는다
 *
 * 맨 위에 요인을 합쳐 그 뒤 12개월을 내는 카드와 줄다리기가 있었다. 표본 밖 성적이 과거 평균을
 * 이긴다는 것이 유의하지 않았고(docs/analysis/macro-model.md), 무엇보다 이 탭이 답할 질문이
 * 아니었다(2026-10-18 요청 — "앞으로의 결과를 예측할 필요는 없다"). 요인 카드의 방향 막대도
 * 그 판정을 쓰던 것이라 같이 뺐다.
 *
 * ## 사례는 시기로 세고, 기저율과 나란히 둔다
 *
 * '비슷했던 달 12개 중 12개 상승' 은 재 보니 두 시기였고, 아무 달이나 골라도 그 뒤 1년이 오른
 * 달이 70~85% 였다. 그래서 요인 카드마다 '지금과 비슷한 자리였던 때 몇 번 · 그 뒤 1년 오른 때' 를
 * 기저율과 같이 적고, 요인 전부가 비슷했던 시기는 표와 가격 경로로 보인다. 숫자는 전부 응답이
 * 그 자리에서 센다(regime.factor_then · similar_periods).
 *
 * ## 정책·세금은 방향을 내지 않는다
 *
 * 재 보면 상식과 반대로 나온다 — 규제강화 뒤 12개월 중위가 완화 뒤보다 높다. 정책이 거꾸로
 * 작동해서가 아니라 **오르니까 규제가 나오기 때문**이다. 숫자만 적고 왜 그렇게 보이는지를 적는다.
 */
export default function RegimeView() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(null)

  useEffect(() => {
    let alive = true
    setError(null)
    api
      .regimeOverview()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [])

  if (error) {
    return (
      <section className="card">
        <h2>거시 분석</h2>
        <p className="empty">{error.message}</p>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="card">
        <h2>거시 분석</h2>
        <p className="empty">거시 요인을 불러오는 중…</p>
      </section>
    )
  }

  return (
    <>
      <section className="card">
        <h2>
          지금 상태 — 요인별로
          <Hint
            wide
            notes={[
              '값이 아니라 자기 평균보다 얼마나 위·아래인지로 봅니다. 미분양 몇 호가 많은 것인지는 그 지역 미분양의 긴 역사에 비춰 봐야 알 수 있기 때문입니다.',
              "'몇 배' 는 평소 오르내림 폭(표준편차)의 몇 배인가입니다.",
              "카드 아래 '비슷했던 때' 는 그 요인이 지금과 비슷한 자리였던 시기의 수와 그 뒤 1년 집값이 오른 시기의 수입니다. 이웃한 달은 한 시기로 묶고, 지금과 이어진 최근은 뺍니다. '기저' 는 같은 기간 아무 달이나 골랐을 때 그 뒤 1년이 오른 비율입니다.",
              '요인 하나만 맞춘 것이라 그때 다른 요인은 전혀 달랐을 수 있습니다 — 요인 전부로 본 것은 아래 비슷했던 시기입니다.',
              data.note,
            ]}
          />
        </h2>
        <HeatLegend>카드 색은 자기 평균에서의 위치입니다. 좋고 나쁨이 아닙니다.</HeatLegend>
        {/* **데이터 하나에 카드 하나.** 준공·미분양·거래량·전세가율은 공급·가격 분석에
            카드가 있어, 여기서 같은 선을 또 그리면 같은 데이터가 두 탭에 카드로 선다.
            그런 요인은 그림 없이 위치만 한 줄로 두고, 누르면 같은 주제 창을 연다.
            어느 요인이 그런지는 `registry.js` 의 `homeOf` 가 정한다. */}
        <div className="macro-grid">
          {data.factors.filter((f) => !homeOf(topicFor('factor', f.key))).map((f) => (
            <PanelCard
              key={f.key}
              title={f.label}
              sub={<>{factorSub(f)}<ThenLine t={f.then} /></>}
              heat={heatVars(f.z)}
              onOpen={() => setOpen({ kind: 'factor', f })}
            >
              <Spark f={f} />
            </PanelCard>
          ))}
        </div>
        {data.factors.some((f) => homeOf(topicFor('factor', f.key))) && (
          <>
            <h3 className="mt16">카드가 다른 탭에 있는 요인</h3>
            <div className="rg-shared">
              {data.factors.filter((f) => homeOf(topicFor('factor', f.key))).map((f) => (
                <button key={f.key} className="rg-shared-row" style={heatVars(f.z)}
                        onClick={() => setOpen({ kind: 'factor', f })} aria-haspopup="dialog">
                  <strong>{f.label}</strong>
                  {/* 값을 같이 둔다. 위치(몇 배)만 있으면 '적정의 몇 % 를 지었나' 같은 값
                      자체를 보려고 창을 열어야 했다. */}
                  <b className="rg-shared-val">
                    {fmt(f.latest.value, f.unit === '호' ? 0 : 1)}{f.unit}
                    <span className="muted small"> {ymText(f.latest.ym)}</span>
                  </b>
                  {/* 무엇의 위치인지 적는다. 공급 분석 미분양 카드는 '호' 의 위치이고
                      여기는 그 전년비의 위치라, 같은 자라도 숫자가 다를 수 있다. */}
                  <span className="muted small">
                    {f.transform_label} · <span className="heat-pos">{zText(f.z)}</span> · {f.region}
                    {f.caveat && <Hint tone="warn" notes={[f.caveat]} />}
                    <ThenLine t={f.then} />
                  </span>
                  <span className="muted small">카드는 {homeOf(topicFor('factor', f.key))}</span>
                  <span className="factor-caret" aria-hidden="true">&#10530;</span>
                </button>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>
          전에도 이런 적이 있었나 — 비슷했던 시기
          {data.similar.note && <Hint notes={[data.similar.note]} />}
        </h2>
        {data.similar.available ? (
          <SimilarPeriods sim={data.similar} factors={data.factors} />
        ) : (
          <p className="empty">{data.similar.note}</p>
        )}
        {/* 표를 **바로 펼쳐 둔다.** 이 섹션이 답하는 것은 '그때 요인들이 어땠나' 다. */}
        <h3 className="mt16">
          과거 국면 표{' '}
          <span className="muted small">
            {data.history.step_months}개월마다 · {data.history.rows.length}행
          </span>
        </h3>
        <HistoryTable h={data.history} factors={data.factors} />
      </section>

      <section className="card">
        <h2>
          정책과 세금
          <Hint
            notes={[
              `API 가 없어 손으로 적은 연표입니다(${data.policy_covers_from} 부터, 한 줄마다 출처를 달았습니다).`,
              '사건 뒤 12개월 가격 변화를 함께 적되, 인과로 읽지 마세요 — 오르니까 규제가 나옵니다.',
            ]}
          />
        </h2>
        <div className="rg-after">
          {data.policy_aftermath.map((a) => (
            <div key={a.kind} className="rg-after-cell">
              <div className="muted small">{a.kind}</div>
              <strong className={a.median >= 0 ? 'tone-pos' : 'tone-neg'}>
                {a.median >= 0 ? '+' : ''}
                {a.median}%
              </strong>
              <div className="muted small">
                {a.n}건 중위 · {a.min}~{a.max}%
              </div>
            </div>
          ))}
        </div>
        <PolicyList rows={data.policy} />
      </section>

      {/* 요인 창 — 주제 창으로 띄운다. 전세가율·거래량·미분양·공급은 가격 분석·공급
          분석에도 카드가 있어, 어디서 열든 같은 창이 그 주제의 전체를 보여 준다. */}
      {open?.kind === 'factor' && (
        <TopicModal topic={topicFor('factor', open.f.key, { title: open.f.label })}
                    onClose={() => setOpen(null)} />
      )}
    </>
  )
}

const ymText = (ym) => `${ym.slice(0, 4)}.${ym.slice(4)}`

function factorSub(f) {
  const v = `${f.latest.value}${f.unit}`
  return (
    <>
      {ymText(f.latest.ym)} {v} · <span className="heat-pos">{zText(f.z)}</span> · {f.region}
    </>
  )
}

/** 계열 한 줄 + 지금 위치. 축소판에는 그림만 둔다(PanelCard 규칙). */
function Spark({ f }) {
  const [ref, width] = useMeasure()
  const s = f.series
  if (!s?.length) return <p className="empty">값이 없습니다</p>
  const vs = s.map((d) => d.v)
  const lo = Math.min(...vs)
  const hi = Math.max(...vs)
  const span = hi - lo || 1
  const H = 76
  const W = Math.max(width, 240)
  const x = (i) => (i / Math.max(s.length - 1, 1)) * W
  const y = (v) => H - ((v - lo) / span) * (H - 8) - 4
  const d = s.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.v).toFixed(1)}`).join(' ')
  const zero = lo < 0 && hi > 0 ? y(0) : null

  return (
    <div ref={ref}>
      <svg width={W} height={H} role="img" aria-label={`${f.label} 추이`}>
        {zero != null && (
          <line x1="0" x2={W} y1={zero} y2={zero} stroke="var(--border)" strokeDasharray="3 3" />
        )}
        <path d={d} fill="none" stroke="var(--series-1)" strokeWidth="1.6" />
        <circle
          cx={x(s.length - 1)}
          cy={y(vs[vs.length - 1])}
          r="3"
          fill="var(--series-1)"
        />
      </svg>
    </div>
  )
}

function PolicyList({ rows }) {
  return (
    <ol className="rg-timeline">
      {rows.map((r) => (
        <li key={r.date}>
          <div className="rg-tl-head">
            <span className={`rg-kind is-${kindTone(r.kind)}`}>{r.kind}</span>
            <strong>{r.name}</strong>
            <span className="muted small">{r.date}</span>
            {r.fwd12 != null && (
              <span className={`rg-tl-after ${r.fwd12 >= 0 ? 'tone-pos' : 'tone-neg'}`}>
                그 뒤 12개월 {r.fwd12 >= 0 ? '+' : ''}
                {r.fwd12}%
              </span>
            )}
          </div>
          <div className="rg-tl-foot">
            <Hint notes={[r.summary, r.note]} />
            <a className="muted small" href={r.source} target="_blank" rel="noopener noreferrer">
              출처 ↗
            </a>
          </div>
        </li>
      ))}
    </ol>
  )
}

const kindTone = (k) => (k.endsWith('강화') ? 'tight' : k === '공급확대' ? 'supply' : 'loose')

/** 축소판: 가격이 오른 구간과 내린 구간만 색으로. */
function HistoryTable({ h, factors }) {
  const tip = useTooltip()
  const keys = factors.map((f) => f.key)
  const labels = Object.fromEntries(factors.map((f) => [f.key, f.label]))
  return (
    <>
      <HeatLegend>
        {h.note}{' '}
        칸 색은 자기 평균에서의 위치(평소 폭의 몇 배)이고, 글자는{' '}
        {(h.levels || []).map((l) =>
          `${l.label}${l.max != null ? ` ${l.max}배 이하` : l.min != null ? ` +${l.min}배 이상` : ''}`,
        ).join(' · ')}
      </HeatLegend>
      <div className="table-wrap">
        <table className="rg-hist">
          <thead>
            <tr>
              <th>시점</th>
              {keys.map((k) => (
                <th key={k}>{labels[k]}</th>
              ))}
              <th>그 뒤 12개월</th>
            </tr>
          </thead>
          <tbody>
            {[...h.rows].reverse().map((r) => (
              <tr key={r.ym}>
                <td>{ymText(r.ym)}</td>
                {keys.map((k) => {
                  const c = r.states[k]
                  return (
                    <td key={k}>
                      {c ? (
                        // 색은 z 그대로(연속), 글자는 다섯 단계. 끊는 것은 읽기 위한
                        // 글자뿐이다 — 색까지 끊으면 0.6배와 1.4배가 같은 칸이 된다.
                        <span
                          className="rg-state"
                          style={heatVars(c.z)}
                          onMouseMove={(e) =>
                            tip.show(e, (
                              <>
                                <div className="t-title">{labels[k]} · {ymText(r.ym)}</div>
                                <div className="t-row">값 {c.v}</div>
                                <div className="t-row">{zText(c.z)}</div>
                              </>
                            ))
                          }
                          onMouseLeave={tip.hide}
                        >
                          {c.state}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  )
                })}
                <td className={r.fwd12 == null ? 'muted' : r.fwd12 >= 0 ? 'tone-pos' : 'tone-neg'}>
                  {r.fwd12 == null ? '—' : `${r.fwd12 >= 0 ? '+' : ''}${r.fwd12}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {tip.node}
    </>
  )
}

const sgn = (v) => (v > 0 ? '+' : '')
const pctText = (v, d = 1) => (v == null ? '—' : `${sgn(v)}${fmt(v, d)}%`)
const periodText = (e) => (e.from === e.to ? ymText(e.from) : `${ymText(e.from)}~${ymText(e.to)}`)
// 시기가 이만큼 이하면 '사례 적음' 을 붙인다. 한두 번 있었던 일은 경향이 아니라 일화다.
const FEW = 2

/**
 * 요인 카드의 '그때는' 한 줄 — 지금과 비슷한 자리였던 **시기** 수, 그 뒤 1년 오른 시기 수, 기저율.
 * 시기마다 무엇이었는지는 호버로. 숫자는 응답(`factor_then`)이 센다.
 */
function ThenLine({ t }) {
  if (!t) return null
  const { episodes, up } = t.summary
  const base = t.base
  if (!episodes) {
    return <span className="rg-then">비슷했던 때 없음 · 기저 {base.up_pct ?? '—'}%</span>
  }
  return (
    <span className="rg-then">
      비슷했던 때 {episodes}번 · 그 뒤 1년 오름 {up}/{episodes}
      {episodes <= FEW && <span data-tone="warn"> · 사례 적음</span>}
      {' '}· 기저 {base.up_pct}%
      <Hint
        notes={[
          ...t.episodes.map((e) => `${periodText(e)} (${e.months}개월) — 그 뒤 1년 ${pctText(e.fwd['12'])}`),
          `기저: ${ymText(base.from)}~${ymText(base.to)} 아무 달이나 골랐을 때 그 뒤 1년이 오른 비율 ${base.up_pct}% · 중위 ${pctText(base.median)}`,
        ]}
      />
    </span>
  )
}

/**
 * 요인 **전부**가 지금과 가까웠던 시기. 표는 시기마다 요인 위치(지금 줄과 견주게)와 그 뒤
 * 6·12·24개월, 그림은 시기 기준 달을 0 에 맞춘 가격 경로다.
 */
function SimilarPeriods({ sim, factors }) {
  const tip = useTooltip()
  const keys = factors.map((f) => f.key).filter((k) => k in sim.now_z)
  const labels = Object.fromEntries(factors.map((f) => [f.key, f.label]))
  const b = sim.base
  const cell = (z, label, when) => (
    <span
      className="rg-state"
      style={heatVars(z)}
      onMouseMove={(e) => tip.show(e, (
        <>
          <div className="t-title">{label} · {when}</div>
          <div className="t-row">{zText(z)}</div>
        </>
      ))}
      onMouseLeave={tip.hide}
    >
      {sgn(z)}{fmt(z, 1)}
    </span>
  )
  return (
    <>
      <p className="muted small">
        비슷했던 시기 {sim.summary.episodes}번 · 그 뒤 1년 오른 시기 {sim.summary.up}/{sim.summary.episodes}
        {sim.summary.episodes <= FEW && <span data-tone="warn"> · 사례 적음</span>}
        {' '}· 기저 {b.up_pct}% (같은 기간 아무 달이나, 중위 {pctText(b.median)})
        <Hint
          notes={[
            `가까운 달 ${sim.params.near_months}개를 고른 뒤 ${sim.params.episode_gap}개월 안에 이어지는 달을 한 시기로 묶고, 시기마다 가장 가까운 달을 기준 달로 삼았습니다.`,
            `지금과 이어진 최근 ${sim.params.exclude_recent}개월은 뺐습니다 — 요인은 천천히 움직여 지난 1~2년이 늘 가장 비슷하게 나옵니다.`,
            `기저: ${ymText(b.from)}~${ymText(b.to)} 의 모든 달 가운데 그 뒤 1년이 오른 비율입니다. 비슷했던 시기의 결과는 이것과 견줘 읽습니다.`,
            '칸의 숫자는 평균에서 평소 폭의 몇 배(z)입니다. 지금 줄과 색이 비슷할수록 그 요인이 그때도 비슷했습니다.',
          ]}
        />
      </p>
      <div className="table-wrap">
        <table className="rg-hist">
          <thead>
            <tr>
              <th>시기 (기준 달)</th>
              {/* 그 뒤를 앞에 둔다. 요인 열이 아홉이라 뒤에 두면 가로로 밀어야 보였다. */}
              <th>6개월 뒤</th>
              <th>1년 뒤</th>
              <th>2년 뒤</th>
              {keys.map((k) => <th key={k}>{labels[k]}</th>)}
            </tr>
          </thead>
          <tbody>
            <tr className="is-current">
              <td><b>지금</b> <span className="muted small">{ymText(sim.now)}</span></td>
              <td className="muted">—</td><td className="muted">—</td><td className="muted">—</td>
              {keys.map((k) => <td key={k}>{cell(sim.now_z[k], labels[k], '지금')}</td>)}
            </tr>
            {sim.episodes.map((e) => (
              <tr key={e.pick}>
                <td>
                  {periodText(e)} <span className="muted small">({ymText(e.pick)})</span>
                </td>
                {['6', '12', '24'].map((h) => (
                  <td key={h} className={e.fwd[h] == null ? 'muted' : e.fwd[h] >= 0 ? 'tone-pos' : 'tone-neg'}>
                    {pctText(e.fwd[h])}
                  </td>
                ))}
                {keys.map((k) => <td key={k}>{cell(e.z[k], labels[k], ymText(e.pick))}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {tip.node}
      <PathChart episodes={sim.episodes} />
    </>
  )
}

// 시기마다 선 하나. 정의된 계열 색이 셋뿐이라 넷째부터는 같은 색을 점선으로 쓴다.
const PATH_STYLE = [
  ['var(--series-1)', null], ['var(--series-2)', null], ['var(--series-3)', null],
  ['var(--series-1)', '4 3'], ['var(--series-2)', '4 3'],
]

/** 시기 기준 달을 0 에 맞춘 가격 경로(기준 달 대비 %). 앞 12개월과 뒤 24개월. */
function PathChart({ episodes }) {
  const [ref, width] = useMeasure()
  const tip = useTooltip()
  const pts = episodes.flatMap((e) => e.path)
  if (!pts.length) return null
  const ks = pts.map((p) => p.k)
  const vs = pts.map((p) => p.v)
  const k0 = Math.min(...ks)
  const k1 = Math.max(...ks)
  const lo = Math.min(0, ...vs)
  const hi = Math.max(0, ...vs)
  const W = Math.max(width, 280)
  const H = 200
  const PAD = { l: 40, r: 10, t: 10, b: 22 }
  const x = (k) => PAD.l + ((k - k0) / (k1 - k0 || 1)) * (W - PAD.l - PAD.r)
  const y = (v) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (H - PAD.t - PAD.b)
  const ticks = [lo, 0, hi].filter((v, i, a) => a.indexOf(v) === i)
  return (
    <div ref={ref} className="mt16">
      <div className="legend">
        {episodes.map((e, i) => (
          <span key={e.pick} className="key">
            <span className="swatch" style={{ background: PATH_STYLE[i % PATH_STYLE.length][0] }} />
            {periodText(e)}
          </span>
        ))}
      </div>
      <svg width={W} height={H} role="img" aria-label="비슷했던 시기의 기준 달 앞뒤 가격 경로">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--grid)"
                  strokeDasharray={v === 0 ? null : '2 3'} />
            <text x={PAD.l - 6} y={y(v) + 4} textAnchor="end" fontSize="10.5" fill="var(--text-muted)">{sgn(v)}{fmt(v, 0)}%</text>
          </g>
        ))}
        <line x1={x(0)} x2={x(0)} y1={PAD.t} y2={H - PAD.b} stroke="var(--text-muted)" />
        {[k0, 0, 12, k1].filter((k, i, a) => a.indexOf(k) === i).map((k) => (
          <text key={k} x={x(k)} y={H - 6} textAnchor="middle" fontSize="10.5" fill="var(--text-muted)">
            {k === 0 ? '기준 달' : `${sgn(k)}${k}개월`}
          </text>
        ))}
        {episodes.map((e, i) => {
          const [c, dash] = PATH_STYLE[i % PATH_STYLE.length]
          const d = e.path.map((p, j) => `${j ? 'L' : 'M'}${x(p.k).toFixed(1)} ${y(p.v).toFixed(1)}`).join(' ')
          return (
            <path key={e.pick} d={d} fill="none" stroke={c} strokeWidth="1.8" strokeDasharray={dash}
                  onMouseMove={(ev) => tip.show(ev, (
                    <>
                      <div className="t-title">{periodText(e)} · 기준 {ymText(e.pick)}</div>
                      <div className="t-row">1년 뒤 {pctText(e.fwd['12'])} · 2년 뒤 {pctText(e.fwd['24'])}</div>
                    </>
                  ))}
                  onMouseLeave={tip.hide} />
          )
        })}
      </svg>
      {tip.node}
    </div>
  )
}
