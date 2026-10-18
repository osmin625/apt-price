import { useEffect, useState } from 'react'

import { api } from '../api'
import { fmt, useMeasure, useTooltip } from '../components/Charts'
import Modal from '../components/Modal'
import PanelCard from '../components/PanelCard'
import HeatLegend from '../components/HeatLegend'
import { heatVars } from '../components/heat'
import TimeLines from '../components/TimeLines'
import TopicModal from '../topics/TopicModal'
import { homeOf, topicFor } from '../topics/registry'

/**
 * 거시 분석 — 공급·수요·통화량·금리·정책·세금이 지금 어느 쪽으로 미는가.
 *
 * ## 화살표를 크게 그리지 않는다
 *
 * 각 요인과 '그 뒤 12개월 가격 변화' 의 상관을 전부 쟀더니 **가장 센 것도 0.45**
 * 였고, 심리는 18개월 뒤에 부호가 뒤집혔다(과열의 끝). 통화량과 기준금리는 0에
 * 가까웠다. 그래서 방향 배지 옆에 **세기와 근거를 늘 같이** 적고, 눌러서 시차
 * 프로파일을 볼 수 있게 한다. 방향만 큼직하게 띄우면 없는 확신을 파는 셈이다.
 *
 * ## 정책·세금은 방향을 내지 않는다
 *
 * 재 보면 상식과 반대로 나온다 — 규제강화 뒤 12개월 중위 +4.6%, 완화 뒤 +1.5%.
 * 정책이 거꾸로 작동해서가 아니라 **오르니까 규제가 나오기 때문**이다. 화살표를
 * 붙이면 "규제하면 오른다" 로 읽힌다. 그래서 숫자만 적고 왜 그렇게 보이는지를
 * 바로 옆에 쓴다.
 *
 * ## 세 번째 블록이 사실 핵심이다
 *
 * '지금 어느 쪽' 보다 **'전에도 이런 적이 있었나'** 가 더 답할 만한 질문이다.
 * 요인 상태를 백분위로 바꿔 지금과 가장 가까웠던 과거 달을 찾고, 그 뒤 12개월에
 * 무슨 일이 있었는지를 보여 준다. 예측이 아니라 전례다.
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

  const p = data.price
  // 요인 카드 왼쪽 막대의 방향. 맨 위 합산 모델의 판정을 쓴다 — 요인별 `pressure` 는 '보통'(30~70%)·
  // 약한 상관에서 방향을 비워 두어, 같은 화면에서 합산 카드는 '내림' 인데 막대는 회색인 요인이
  // 생겼다(미분양·전세가율·M2). 막대가 맨 위 카드와 다른 말을 하면 막대가 없는 것보다 나쁘다.
  const modelDir = Object.fromEntries((data.model?.used || []).map((u) => [u.key, u.dir]))
  const edgeOf = (f) => modelDir[f.key] || f.pressure.dir
  return (
    <>
      {/* 합쳐 본 결론이 맨 위다. 요인별 방향·카드는 그 근거라 아래로 둔다. */}
      {data.model?.available && <MacroModel m={data.model} price={data.price} />}

      <section className="card">
        <h2>지금 무엇이 가격을 밀고 있나</h2>
        <p className="sub">
          {p.region} 매매가격지수는 {ymText(p.ym)} 기준 전년비{' '}
          <b className={p.yoy >= 0 ? 'tone-pos' : 'tone-neg'}>
            {p.yoy >= 0 ? '+' : ''}
            {p.yoy}%
          </b>{' '}
          입니다. 아래 방향은 <b>각 요인이 과거에 가격과 어떻게 움직였는지를 재서</b>{' '}
          정한 것입니다
          {data.max_abs_r != null && <> — 가장 센 상관도 {data.max_abs_r.toFixed(2)} 라</>}, 어느
          하나도 혼자서는 가격을 설명하지 못합니다.
        </p>

        <div className="rg-groups">
          {data.groups_detail.map((g) => (
            <GroupRow key={g.group} g={g} onOpen={() => setOpen({ kind: 'group', g })} />
          ))}
        </div>
      </section>

      <section className="card">
        <h2>요인별로 하나씩</h2>
        <p className="sub">
          값이 아니라 <b>자기 역사에서 어디쯤인지</b>로 봅니다. 미분양 몇 호가 많은
          것인지는 그 지역 미분양의 긴 역사에 비춰 봐야 알 수 있기 때문입니다.
        </p>
        <HeatLegend>카드 색은 자기 역사에서의 위치입니다. 좋고 나쁨이 아닙니다</HeatLegend>
        <div className="legend">
          <span className="key"><span className="swatch" style={{ background: 'var(--good)' }} />왼쪽 막대 — 가격을 올리는 쪽</span>
          <span className="key"><span className="swatch" style={{ background: 'var(--neg)' }} />내리는 쪽</span>
          <span className="key muted">맨 위 '요인을 합치면' 의 판정과 같습니다</span>
        </div>
        {/* **데이터 하나에 카드 하나.** 준공·미분양·거래량·전세가율은 공급·가격 분석에
            카드가 있어, 여기서 같은 선을 또 그리면 같은 데이터가 두 탭에 카드로 선다.
            그런 요인은 그림 없이 위치만 한 줄로 두고, 누르면 같은 주제 창을 연다.
            어느 요인이 그런지는 `registry.js` 의 `homeOf` 가 정한다. */}
        <div className="macro-grid">
          {data.factors.filter((f) => !homeOf(topicFor('factor', f.key))).map((f) => (
            <PanelCard
              key={f.key}
              title={f.label}
              sub={factorSub(f)}
              heat={heatVars(f.percentile)}
              edge={edgeOf(f)}
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
                <button key={f.key} className="rg-shared-row" style={heatVars(f.percentile)}
                        data-edge={edgeOf(f)}
                        onClick={() => setOpen({ kind: 'factor', f })} aria-haspopup="dialog">
                  <strong>{f.label}</strong>
                  {/* 무엇의 백분위인지 적는다. 공급 분석 미분양 카드는 '호' 의 위치이고
                      여기는 그 전년비의 위치라, 같은 자라도 숫자가 다를 수 있다. */}
                  <span className="muted small">
                    {f.transform_label} · 자기 역사{' '}
                    <span className="heat-pct">{Math.round(f.percentile * 100)}%</span> 지점 · {f.region}
                  </span>
                  <span className="muted small">카드는 {homeOf(topicFor('factor', f.key))}</span>
                  <span className="factor-caret" aria-hidden="true">&#10530;</span>
                </button>
              ))}
            </div>
          </>
        )}
        <p className="muted small">{data.note}</p>
      </section>

      <section className="card">
        <h2>정책과 세금</h2>
        <p className="sub">
          API 가 없어 손으로 적은 연표입니다({data.policy_covers_from} 부터, 한 줄마다
          출처를 달았습니다). 사건 뒤 12개월 가격 변화를 함께 적되,{' '}
          <b>인과로 읽지 마세요</b> — 오르니까 규제가 나옵니다.
        </p>
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

      <section className="card">
        <h2>전에도 이런 적이 있었나</h2>
        {data.similar.available ? (
          <>
            <p className="sub">
              요인 상태가 지금과 가장 가까웠던 달 {data.similar.fwd12.n}개를 찾았습니다.
              그 뒤 12개월 가격 변화는 중위{' '}
              <b className={data.similar.fwd12.median >= 0 ? 'tone-pos' : 'tone-neg'}>
                {data.similar.fwd12.median >= 0 ? '+' : ''}
                {data.similar.fwd12.median}%
              </b>{' '}
              ({data.similar.fwd12.min}~{data.similar.fwd12.max}%), {data.similar.fwd12.n}개
              중 {data.similar.fwd12.up}개가 상승이었습니다.
            </p>
            <div className="rg-similar">
              {data.similar.months.map((m) => (
                <div key={m.ym} className="rg-sim">
                  <div className="muted small">{ymText(m.ym)}</div>
                  <strong className={m.fwd12 >= 0 ? 'tone-pos' : 'tone-neg'}>
                    {m.fwd12 >= 0 ? '+' : ''}
                    {m.fwd12}%
                  </strong>
                </div>
              ))}
            </div>
            <p className="muted small">{data.similar.note}</p>
          </>
        ) : (
          <p className="empty">{data.similar.note}</p>
        )}
        {/* 표를 **바로 펼쳐 둔다.** 예전에는 '그 뒤 12개월' 막대만 있는 카드였고 눌러야
            표가 떴다 — 이 섹션이 답하는 것은 '그때 요인들이 어땠나' 인데 그것이 창 안에만
            있었다. */}
        <h3 className="mt16">
          과거 국면 표{' '}
          <span className="muted small">
            {data.history.step_months}개월마다 · {data.history.rows.length}행
          </span>
        </h3>
        <HistoryTable h={data.history} factors={data.factors} />
      </section>

      {/* 요인 창 — 주제 창으로 띄운다. 전세가율·거래량·미분양·준공은 가격 분석·공급
          분석에도 카드가 있어, 어디서 열든 같은 창이 그 주제의 전체를 보여 준다. */}
      {open?.kind === 'factor' && (
        <TopicModal topic={topicFor('factor', open.f.key, { title: open.f.label })}
                    onClose={() => setOpen(null)} />
      )}
      {open?.kind === 'group' && (
        <Modal title={`${open.g.group} — 어떻게 정했나`} onClose={() => setOpen(null)} wide>
          <GroupDetail g={open.g} />
        </Modal>
      )}
    </>
  )
}

const ymText = (ym) => `${ym.slice(0, 4)}.${ym.slice(4)}`

const ARROW = { up: '▲', down: '▼', none: '–' }
const DIRWORD = { up: '상승 압력', down: '하락 압력', none: '방향 없음' }

function factorSub(f) {
  const v = `${f.latest.value}${f.unit}`
  const pct = Math.round(f.percentile * 100)
  return (
    <>
      {ymText(f.latest.ym)} {v} · 자기 역사 <span className="heat-pct">{pct}%</span> 지점 · {f.region}
    </>
  )
}

/** 그룹 한 줄. **배지 혼자 두지 않는다** — 세기와 근거가 늘 붙어 있어야 한다. */
function GroupRow({ g, onOpen }) {
  const isPolicy = g.kind === 'policy'
  return (
    <button className="rg-group" onClick={onOpen} aria-haspopup="dialog">
      <span className={`rg-dir is-${g.dir}`}>{ARROW[g.dir]}</span>
      <span className="rg-name">{g.group}</span>
      <span className="rg-label">{g.label}</span>
      <span className="muted small rg-why">
        {isPolicy
          ? g.latest
            ? `최근 ${g.latest.date} ${g.latest.name}`
            : '적힌 조치가 없습니다'
          : g.members
              .map((m) => `${m.label} ${ARROW[m.dir]}`)
              .join(' · ')}
      </span>
    </button>
  )
}

function GroupDetail({ g }) {
  if (g.kind === 'policy') {
    return (
      <>
        <p className="sub">{g.why}</p>
        <table>
          <thead>
            <tr>
              <th>종류</th>
              <th>건수</th>
              <th>그 뒤 12개월 중위</th>
              <th>범위</th>
            </tr>
          </thead>
          <tbody>
            {g.aftermath.map((a) => (
              <tr key={a.kind}>
                <td>{a.kind}</td>
                <td>{a.n}</td>
                <td className={a.median >= 0 ? 'tone-pos' : 'tone-neg'}>
                  {a.median >= 0 ? '+' : ''}
                  {a.median}%
                </td>
                <td className="muted">
                  {a.min}~{a.max}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    )
  }
  return (
    <>
      <p className="sub">
        요인별 방향을 <b>상관의 세기로 가중해</b> 합한 값입니다(합 {g.score}). 엇갈리면
        0 쪽으로 가고 '엇갈림' 으로 적습니다. 방향은 <b>상관 부호 × 지금 위치</b>라,
        상관이 음수여도 지금 값이 낮으면 상승 쪽이 됩니다.
      </p>
      <table>
        <thead>
          <tr>
            <th>요인</th>
            <th>방향</th>
            <th>세기</th>
            <th>가격과의 상관</th>
            <th>지금 위치</th>
          </tr>
        </thead>
        <tbody>
          {g.members.map((m) => (
            <tr key={m.label}>
              <td>{m.label}</td>
              <td>
                {ARROW[m.dir]} {DIRWORD[m.dir]}
              </td>
              <td className="muted">{m.strength}</td>
              <td>{m.r == null ? '—' : m.r > 0 ? `+${m.r}` : m.r}</td>
              <td className="muted">{Math.round(m.percentile * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
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
          fill={f.pressure.dir === 'none' ? 'var(--text-muted)' : 'var(--series-1)'}
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
          <div className="muted small">{r.summary}</div>
          {r.note && <div className="muted small">{r.note}</div>}
          <a className="muted small" href={r.source} target="_blank" rel="noopener noreferrer">
            출처 ↗
          </a>
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
      <p className="sub">{h.note}</p>
      <HeatLegend lo="역대 최저" hi="역대 최고">
        칸 색은 자기 역사에서의 위치(백분위)이고, 글자는{' '}
        {(h.levels || []).map((l) =>
          `${l.label}${l.max != null ? ` ≤${Math.round(l.max * 100)}%` : l.min != null ? ` ≥${Math.round(l.min * 100)}%` : ''}`,
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
                        // 색은 백분위 그대로(연속), 글자는 다섯 단계. 끊는 것은 읽기 위한
                        // 글자뿐이다 — 색까지 끊으면 71% 와 99% 가 같은 칸이 된다.
                        <span
                          className="rg-state"
                          style={heatVars(c.pct)}
                          onMouseMove={(e) =>
                            tip.show(e, (
                              <>
                                <div className="t-title">{labels[k]} · {ymText(r.ym)}</div>
                                <div className="t-row">값 {c.v}</div>
                                <div className="t-row">자기 역사 {Math.round(c.pct * 100)}% 지점</div>
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

/** 줄다리기 한쪽의 요인 목록. 센 것부터 — 응답이 이미 세기순이다. */
function TugList({ dir, title, items }) {
  return (
    <div className={`rg-tug-col is-${dir}`}>
      <h4>{title} <span className="muted small">{items.length}개</span></h4>
      {items.length === 0 ? (
        <p className="muted small">없음</p>
      ) : (
        <ul>
          {items.map((u) => (
            <li key={u.key}>
              <div className="rg-tug-name">
                <span>{u.label} <span className="muted small">{u.region}</span></span>
                <span className="rg-push" title="평소 오르내림 폭(표준편차)의 몇 배만큼 벗어났나">
                  {Math.abs(u.z).toFixed(1)}배
                </span>
              </div>
              <div className="small">{u.now_text}</div>
              <div className="muted small">{u.rule_text}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * 요인을 합친 모델 — 그 뒤 12개월 가격 변화. **줄다리기로 보여 주고, 성적표를 같이 둔다.**
 *
 * 예상은 '올리는 쪽 요인들' 과 '내리는 쪽 요인들' 중 어느 쪽이 더 센가에서 나온다. 그래서
 * 그 모양 그대로 그린다 — 양쪽 힘의 비율 막대 하나, 그 아래 양쪽 요인 목록. 요인마다
 * 두 문장(지금 어떤가 · 과거에 그런 때 그 뒤 가격은 어땠나)을 이으면 화살표가 나온다.
 *
 * 앞의 두 판은 읽기 어려웠다. %p 기여 막대는 원인처럼 읽혔고(요인이 얽혀 몫을 나눌 근거가
 * 없다), 그것을 뺀 '과거 관계 · 지금 · 방향' 표는 읽는 사람이 머릿속에서 곱해야 했다. 게다가
 * 방향만 있으면 '내리는 쪽이 여섯인데 왜 평소보다 오르나' 가 설명되지 않았다 — 한 요인이
 * 평소에서 크게 벗어나 있으면 그것 하나가 나머지를 이긴다. 그래서 세기를 같이 둔다 —
 * 처음엔 ●○○ 세 칸이었는데 수치(평소 오르내림 폭의 몇 배)가 더 낫다는 요청으로 바꿨다.
 * 세기는 가격의 몫이 아니라 그 요인이 지금 평소에서 얼마나 벗어났나다.
 *
 * 매달 그때 알려진 자료로만 다시 맞춰 예측해 본 결과(백테스트)와 과거 평균과의 비교를 같은
 * 카드에 둔다. 기준을 못 이기는 모델이면 그것도 그대로 보인다. 문구에는 숫자를 박지 않는다.
 */
function MacroModel({ m, price }) {
  const sign = (v) => (v > 0 ? '+' : '')
  const best = m.table.find((t) => t.key === 'model')
  const mean = m.table.find((t) => t.key === 'mean')
  const beats = best && mean && best.rmse < mean.rmse
  const ups = m.used.filter((u) => u.dir === 'up')
  const downs = m.used.filter((u) => u.dir === 'down')
  const total = m.pull.up + m.pull.down
  const upPct = Math.round(total ? (m.pull.up / total) * 100 : 50)
  const diff = m.pred - m.base
  const upWins = m.pull.up >= m.pull.down
  const top = (upWins ? ups : downs)[0]
  return (
    <section className="card">
      <h2>요인을 합치면 — 그 뒤 12개월</h2>
      <p className="sub">
        요인들이 가격을 올리는 쪽과 내리는 쪽으로 나뉘어 줄다리기를 합니다. 어느 쪽이 더 센지로
        그 뒤 12개월을 예상합니다.
      </p>
      <div className="rg-after">
        <div className="rg-after-cell">
          <div className="muted small">{ymText(m.now)} 기준 그 뒤 12개월 예상</div>
          <strong className={m.pred >= 0 ? 'tone-pos' : 'tone-neg'}>{sign(m.pred)}{fmt(m.pred, 1)}%</strong>
          <div className="muted small">
            과거에 빗나간 폭으로 보면 {sign(m.band[0])}{fmt(m.band[0], 1)} ~ {sign(m.band[1])}{fmt(m.band[1], 1)}%
          </div>
        </div>
        <div className="rg-after-cell">
          <div className="muted small">평소(과거 평균)</div>
          <strong>{sign(m.base)}{fmt(m.base, 1)}%</strong>
          <div className="muted small">{price.region} 매매가격지수 기준</div>
        </div>
      </div>

      <p className="rg-verdict">
        {Math.abs(diff) < 0.05
          ? '올리는 힘과 내리는 힘이 비슷해 평소와 비슷한 쪽입니다.'
          : `${upWins ? '올리는' : '내리는'} 힘이 더 세서 평소보다 ${fmt(Math.abs(diff), 1)}%p ${diff > 0 ? '더 오르는' : '덜 오르는'} 쪽입니다.`}
        {top && top.strength === 3 && (
          <> 가장 센 것은 <b>{top.label}</b> — 지금 평소에서 크게 벗어나 있습니다.</>
        )}
      </p>
      <div className="rg-tug" role="img" aria-label={`내리는 힘 ${100 - upPct}%, 올리는 힘 ${upPct}%`}>
        <div className="rg-tug-side is-down" style={{ flexGrow: 100 - upPct }}>▼ 내리는 힘 {100 - upPct}%</div>
        <div className="rg-tug-side is-up" style={{ flexGrow: upPct }}>▲ 올리는 힘 {upPct}%</div>
      </div>
      <div className="rg-tug-cols">
        <TugList dir="up" title="▲ 올리는 쪽" items={ups} />
        <TugList dir="down" title="▼ 내리는 쪽" items={downs} />
      </div>
      <p className="muted small">
        '몇 배' 는 그 요인이 지금 평소에서 얼마나 벗어나 있는지입니다 — 평소 오르내림 폭(표준편차)의
        몇 배인가. 1배 안쪽은 흔한 범위이고, 많이 벗어난 요인일수록 세게 당깁니다. 막대의 비율이 이
        값들의 합입니다. 요인끼리 얽혀 함께 움직이므로, 요인마다 가격을 몇 %p 바꿨는지로
        나누지는 않습니다.
        {m.excluded.length > 0 && ` 과거 관계가 약해 뺀 요인: ${m.excluded.join(', ')}.`}
      </p>
      <p className="muted small">
        {m.note}
        {beats
          ? ' 과거 평균만 쓸 때보다 덜 빗나갔지만 차이는 크지 않습니다 — 아래 성적표.'
          : ' 과거 평균만 쓸 때보다 덜 빗나가지 않았습니다 — 이 값은 참고로만 보세요.'}
      </p>

      <h3 className="mt16">그때 알려진 것만으로 예측했다면</h3>
      <p className="muted small">
        매달 그 시점에 결과가 알려진 자료(최소 {m.min_train}개월)로만 다시 맞춰 다음 1년을 예측한
        값과 실제를 겹쳤습니다. 이웃한 달은 11개월을 공유해 같이 움직이므로, 점이 많아 보여도
        독립된 시험은 해마다 하나 남짓입니다.
      </p>
      <TimeLines
        series={[
          { key: 'actual', label: '실제 그 뒤 12개월', color: 'var(--series-2)',
            points: m.backtest.map((b) => ({ ym: b.ym, value: b.actual })) },
          { key: 'pred', label: '그때의 예측', color: 'var(--series-1)', dash: true,
            points: m.backtest.map((b) => ({ ym: b.ym, value: b.pred })) },
        ]}
        unit="%"
        decimals={1}
        zero
        height={240}
        ariaLabel="요인 합산 모델의 표본 밖 예측과 실제"
      />
      <div className="table-wrap">
        <table className="coef">
          <thead>
            <tr>
              <th>예측 방법</th>
              <th className="num">평균 오차(RMSE)</th>
              <th className="num">절대 오차</th>
              <th className="num">방향 적중</th>
              <th className="num">과거 평균 대비</th>
              <th className="num">12월만 RMSE</th>
            </tr>
          </thead>
          <tbody>
            {m.table.map((t) => (
              <tr key={t.key} className={t.key === 'model' ? 'is-current' : ''}>
                <td>{t.label}</td>
                <td className="num">{fmt(t.rmse, 1)}%p</td>
                <td className="num">{fmt(t.mae, 1)}%p</td>
                <td className="num">{t.hit_pct}%</td>
                <td className="num">{t.key === 'mean' ? '기준' : `${sign(t.r2_vs_mean)}${fmt(t.r2_vs_mean, 2)}`}</td>
                <td className="num muted">{t.rmse_dec == null ? '—' : `${fmt(t.rmse_dec, 1)} (n=${t.n_dec})`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        '과거 평균 대비' 는 1 − (오차 ÷ 과거 평균의 오차)² 입니다. 0 보다 크면 아무 요인도 안 쓴
        예측보다 나았다는 뜻입니다. 방향 적중은 오를지 내릴지를 맞힌 비율인데, 이 기간은 대체로
        올라서 '늘 오른다' 만으로도 높게 나옵니다. 요인이 가격을 움직였다는 뜻이 아닙니다 —
        요인들은 서로 얽혀 있고, 이것은 과거에 같이 움직인 방식을 그대로 옮긴 것입니다.
      </p>
    </section>
  )
}

