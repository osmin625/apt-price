import { useEffect, useState } from 'react'

import { api } from '../api'
import { fmt, useMeasure, useTooltip } from '../components/Charts'
import Modal from '../components/Modal'
import PanelCard from '../components/PanelCard'
import HeatLegend from '../components/HeatLegend'
import { heatVars } from '../components/heat'
import TopicModal from '../topics/TopicModal'
import { topicFor } from '../topics/registry'

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
  return (
    <>
      <section className="card">
        <h2>지금 무엇이 가격을 밀고 있나</h2>
        <p className="sub">
          {p.region} 매매가격지수는 {ymText(p.ym)} 기준 전년비{' '}
          <b className={p.yoy >= 0 ? 'tone-pos' : 'tone-neg'}>
            {p.yoy >= 0 ? '+' : ''}
            {p.yoy}%
          </b>{' '}
          입니다. 아래 방향은 <b>각 요인이 과거에 가격과 어떻게 움직였는지를 재서</b>{' '}
          정한 것입니다 — 가장 센 상관도 0.45 라, 어느 하나도 혼자서는 가격을 설명하지
          못합니다.
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
          값이 아니라 <b>자기 역사에서 어디쯤인지</b>로 봅니다. 미분양 14,509호가 많은
          것인지는 경기도 미분양의 지난 25년을 봐야 알 수 있기 때문입니다.
        </p>
        <HeatLegend>카드 색은 자기 역사에서의 위치입니다. 좋고 나쁨이 아닙니다</HeatLegend>
        <div className="macro-grid">
          {data.factors.map((f) => (
            <PanelCard
              key={f.key}
              title={f.label}
              sub={factorSub(f)}
              heat={heatVars(f.percentile)}
              onOpen={() => setOpen({ kind: 'factor', f })}
            >
              <Spark f={f} />
            </PanelCard>
          ))}
        </div>
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
        <div className="macro-grid">
          <PanelCard
            title="과거 국면 표"
            sub={`${data.history.step_months}개월마다 · ${data.history.rows.length}행`}
            onOpen={() => setOpen({ kind: 'history' })}
          >
            <HistoryMini rows={data.history.rows} />
          </PanelCard>
        </div>
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
      {open?.kind === 'history' && (
        <Modal title="과거 국면 표" onClose={() => setOpen(null)} wide>
          <HistoryTable h={data.history} factors={data.factors} />
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
function HistoryMini({ rows }) {
  const list = rows.filter((r) => r.fwd12 != null)
  if (!list.length) return <p className="empty">값이 없습니다</p>
  const span = Math.max(...list.map((r) => Math.abs(r.fwd12))) * 1.1 || 1
  return (
    <div className="pbar">
      {list.map((r) => {
        const pos = r.fwd12 >= 0
        const w = (Math.abs(r.fwd12) / span) * 50
        return (
          <div className="pbar-row" key={r.ym}>
            <div className="pbar-label">{r.ym.slice(2, 4)}.{r.ym.slice(4)}</div>
            <div className="pbar-track">
              <div className="pbar-zero" />
              <div
                className={`pbar-fill ${pos ? 'pos' : 'neg'}`}
                style={{ left: `${pos ? 50 : 50 - w}%`, width: `${w}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function HistoryTable({ h, factors }) {
  const tip = useTooltip()
  const keys = factors.map((f) => f.key)
  const labels = Object.fromEntries(factors.map((f) => [f.key, f.label]))
  return (
    <>
      <p className="sub">{h.note}</p>
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
                        <span
                          className={`rg-state is-${stateTone(c.state)}`}
                          onMouseMove={(e) => tip.show(e, <div className="t-row">{c.v}</div>)}
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

const stateTone = (s) => (s === '높음' ? 'hi' : s === '낮음' ? 'lo' : 'mid')
