import { useEffect, useState } from 'react'

import { api } from '../api'
import { fmt, useMeasure, useTooltip } from '../components/Charts'
import PanelCard from '../components/PanelCard'
import HeatLegend from '../components/HeatLegend'
import Hint from '../components/Hint'
import { heatVars, zText } from '../components/heat'
import TimeLines from '../components/TimeLines'
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
 * 기저율과 같이 적는다. 숫자는 전부 응답이 그 자리에서 센다(regime.factor_then).
 *
 * ## 요인과 매매지수는 한 그림에
 *
 * '비슷했던 시기'(요인 전부가 가까웠던 시기와 그 뒤 가격 경로)와 요인 창의 '그 뒤 가격과의 관계'
 * 가 있었다. 2026-10-19 요청으로 둘을 걷고, 모든 요인과 매매지수 1년 변화율을 z 로 한 그림에
 * 겹쳤다(`Overlay`). 과거 국면 표는 분기·월로 촘촘하게, 글자 없이 배수만.
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
              '요인 하나만 맞춘 것이라 그때 다른 요인은 전혀 달랐을 수 있습니다 — 요인들이 함께 어땠는지는 아래 한 그림과 과거 국면 표에서 봅니다.',
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
          요인과 매매지수 — 한 그림에
          <Hint
            wide
            notes={[
              '모든 요인과 매매지수를 같은 자로 겹쳤습니다 — 자기 평균에서 평소 오르내림 폭(표준편차)의 몇 배인가. 단위가 호·%·%p·지수로 제각각이라 값 그대로는 한 축에 놓을 수 없습니다.',
              '매매지수는 1년 변화율로 그립니다(굵은 선). 지수 수준은 추세로만 올라, 요인들(대개 증감)과 같은 결로 견주려면 변화율이어야 합니다.',
              '그룹마다 색이 같고 그룹 안에서는 선 모양이 다릅니다. 아래 단추로 그룹을 켜고 끕니다. 그림 위에 마우스를 올리면 그 달의 모든 값이 나옵니다.',
              '같이 움직였다고 원인이라는 뜻은 아닙니다 — 요인들도 서로 얽혀 움직입니다.',
            ]}
          />
        </h2>
        <Overlay factors={data.factors} price={data.price} />
      </section>

      <section className="card">
        <h2>
          과거 국면 표
          <Hint notes={[data.history.note]} />
        </h2>
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
  // 기본은 분기(3·6·9·12월). 달마다 펴면 스무 해가 260줄이 넘는다 — 월은 고를 수 있게 둔다.
  const [step, setStep] = useState('q')
  const tip = useTooltip()
  const keys = factors.map((f) => f.key)
  const labels = Object.fromEntries(factors.map((f) => [f.key, f.label]))
  const rows = [...h.rows].reverse().filter((r) => step === 'm' || ['03', '06', '09', '12'].includes(r.ym.slice(4)))
  return (
    <>
      <div className="seg" role="tablist" aria-label="얼마나 촘촘히">
        {[['q', '분기'], ['m', '월']].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={step === k} onClick={() => setStep(k)}>
            {label}
          </button>
        ))}
      </div>
      <span className="muted small"> {rows.length}행</span>
      <HeatLegend>
        칸의 숫자와 색은 자기 평균에서 평소 폭(표준편차)의 몇 배입니다. 색은 끊지 않고 이어집니다.
      </HeatLegend>
      <div className="table-wrap rg-hist-wrap">
        <table className="rg-hist">
          <thead>
            <tr>
              <th>시점</th>
              <th>그 뒤 12개월</th>
              {keys.map((k) => (
                <th key={k}>{labels[k]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ym}>
                <td>{ymText(r.ym)}</td>
                {/* 그 뒤를 앞에 둔다 — 요인 열이 아홉이라 뒤에 두면 가로로 밀어야 보였다. */}
                <td className={r.fwd12 == null ? 'muted' : r.fwd12 >= 0 ? 'tone-pos' : 'tone-neg'}>
                  {r.fwd12 == null ? '—' : `${r.fwd12 >= 0 ? '+' : ''}${r.fwd12}%`}
                </td>
                {keys.map((k) => {
                  const c = r.states[k]
                  return (
                    <td key={k}>
                      {c ? (
                        // '낮음·매우 낮음' 같은 글자를 적었었다(±0.5·±1.5 에서 끊겨 0.49 와 0.51 이
                        // 다른 말이 됐다). 이제 배수만 적는다 — 색도 숫자도 이어진다.
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
                          {c.z > 0 ? '+' : ''}{fmt(c.z, 1)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  )
                })}
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

// 그룹마다 색 하나, 그룹 안에서는 선 모양으로 가른다. 열 줄을 색 열 개로 가르면 비슷한 색끼리
// 헷갈린다 — 같은 그룹(금리 둘, 통화 둘)이 같은 색이면 '어느 쪽 이야기인가' 가 먼저 읽힌다.
const GROUP_COLOR = {
  공급: 'var(--series-1)', 수요: 'var(--series-2)', 통화량: 'var(--series-3)', 금리: 'var(--series-4)',
}
const DASHES = [null, '6 3', '2 3']

/** 모든 요인(z)과 매매지수 1년 변화율(z)을 한 그림에. 그룹 단추로 켜고 끈다. */
function Overlay({ factors, price }) {
  const groups = [...new Set(factors.map((f) => f.group))]
  const [on, setOn] = useState(() => new Set(groups))
  const toggle = (g) => setOn((prev) => {
    const next = new Set(prev)
    if (next.has(g)) next.delete(g)
    else next.add(g)
    return next
  })
  const seen = {}
  const series = [
    { key: 'price', label: `매매지수 1년 변화(${price.region})`, color: 'var(--text-primary)', width: 3,
      points: (price.yoy_series || []).map((p) => ({ ym: p.ym, value: p.z })) },
    ...factors.filter((f) => on.has(f.group)).map((f) => {
      const n = (seen[f.group] = (seen[f.group] ?? -1) + 1)
      return {
        key: f.key, label: f.label, color: GROUP_COLOR[f.group] || 'var(--text-muted)',
        dash: DASHES[n % DASHES.length], width: 1.5,
        points: f.series.map((p) => ({ ym: p.ym, value: p.z })),
      }
    }),
  ]
  // **매매지수 1년 변화가 시작하는 달부터** 그린다. 처음에는 가장 이른 요인(가계대출 금리,
  // 1997년~)부터 그렸더니 견줄 매매지수가 없는 앞 8년이 그림의 3분의 1을 차지했다. 늦게
  // 시작하는 요인은 그 달부터 나타난다.
  const start = series[0].points[0]?.ym ?? '000000'
  const months = [...new Set(series.flatMap((s) => s.points.map((p) => p.ym)))]
    .filter((ym) => ym >= start).sort()
  return (
    <>
      <div className="seg" role="group" aria-label="그룹 켜고 끄기">
        {groups.map((g) => (
          <button key={g} aria-pressed={on.has(g)} onClick={() => toggle(g)}>
            <span className="swatch" style={{ background: GROUP_COLOR[g] }} /> {g}
          </button>
        ))}
      </div>
      <TimeLines
        series={series}
        unit="배"
        decimals={1}
        zero
        height={340}
        months={months}
        ariaLabel="모든 요인과 매매지수 1년 변화를 평균 대비 배수로 겹친 그림"
      />
    </>
  )
}
