import { fmt } from '../../shared/Charts'
import Hint from '../../shared/Hint'

/**
 * 단기 매매 기법을 실제 지수에 돌린 결과 — 지금 상태와 과거 성적(backend/app/stock/trading.py).
 *
 * 성적은 두 갈래다.
 *   - 신호 뒤 h 거래일 수익률을 **아무 날이나 고른 것**(기저율)과 견준다. 오르는 장에서는 아무 날이나 사도 벌어서,
 *     신호 뒤 평균이 플러스라는 것만으로는 아무것도 말하지 못한다. 범위는 '아무 날 n 개' 를 수천 번 뽑은 95%.
 *   - 진입·청산이 있는 규칙은 규칙대로 사고판 결과를 **사서 들고 있기**와 견준다. 거래 비용을 뺐다.
 *
 * 판정 문구는 응답의 `verdict` 를 옮길 뿐이다 — 화면이 숫자를 보고 따로 판정하지 않는다. '사라·팔아라' 는 쓰지
 * 않는다(2026-11-12 합의). 지금 상태는 '규칙대로라면 들고 있는 구간인가' 다.
 */
export const day = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
const signed = (v, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`)
const pct = (v, d = 1) => (v == null ? '—' : `${signed(v, d)}%`)
const VERDICT = { above: '아무 날보다 높음', below: '아무 날보다 낮음', inside: '아무 날과 구별 안 됨' }
const arrow = (d) => (d > 0 ? '▲' : '▼')

/** 카드에 펼쳐 두는 지수 하나의 지금 상태 — 짧게. */
export function nowShort(rule, by) {
  const n = by.now
  if (rule.kind === 'hold') {
    if (n.fill_pending) return n.holding ? '진입 신호(체결 전)' : '청산 신호(체결 전)'
    return n.holding ? '보유 중' : '쉬는 중'
  }
  if (n.forming) return `${n.forming.kind} 형성 중`
  if (n.last && n.last.ago <= 60) return `${arrow(n.last.dir)} ${n.last.ago}거래일 전`
  return '최근 신호 없음'
}

function NowLine({ rule, by, ix }) {
  const n = by.now
  const parts = []
  if (rule.kind === 'hold') {
    parts.push(nowShort(rule, by))
    if (n.last) parts.push(`마지막 신호 ${arrow(n.last.dir)} ${day(n.last.date)}`)
  } else {
    if (n.forming) {
      const lv = [n.forming.up != null && `${fmt(n.forming.up, 0)} 위로 닫으면 ▲`,
                  n.forming.down != null && `${fmt(n.forming.down, 0)} 아래로 닫으면 ▼`].filter(Boolean)
      parts.push(`${n.forming.kind} 형성 중 — ${lv.join(' · ')}`)
    }
    parts.push(n.last ? `마지막 신호 ${arrow(n.last.dir)} ${n.last.kind} ${day(n.last.date)}` : '신호가 난 적 없음')
  }
  if (n.value) {
    const v = n.value.unit.startsWith('%') ? signed(n.value.value) : fmt(n.value.value, 1)
    parts.push(`${n.value.label} ${v}${n.value.unit}`)
  }
  return (
    <p className="tq-now">
      <b>{day(n.day)}</b> {ix.label} {fmt(n.close, 2)} · {parts.join(' · ')}
    </p>
  )
}

function SignalTable({ rule, by, meta }) {
  const rows = []
  for (const d of [1, -1]) {
    for (const h of meta.horizons) {
      const s = by.signals[`${d > 0 ? 'up' : 'down'}${h}`]
      if (s && s.n) rows.push({ d, h, s })
    }
  }
  if (!rows.length) return <p className="muted small">이 지수에서는 규칙에 맞는 신호가 난 적이 없습니다.</p>
  const name = (d) => (rule.kind === 'hold' ? (d > 0 ? '▲ 진입 뒤' : '▼ 청산 뒤') : d > 0 ? '▲ 오름 신호 뒤' : '▼ 내림 신호 뒤')
  return (
    <div className="table-wrap">
      <table className="coef tq-perf">
        <thead>
          <tr>
            <th>신호</th><th>번</th><th>평균</th><th>오른 비율</th><th>아무 날 평균</th><th>아무 날 95% 범위</th><th>판정</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ d, h, s }) => (
            <tr key={`${d}${h}`}>
              <td>{name(d)} {h}거래일</td>
              <td>{s.n}</td>
              <td className={s.verdict === 'above' ? 'tone-pos' : s.verdict === 'below' ? 'tone-neg' : ''}>{pct(s.mean)}</td>
              <td>{fmt(s.hit, 0)}%</td>
              <td>{pct(s.base_mean)}</td>
              <td>{s.lo == null ? '—' : `${pct(s.lo)} ~ ${pct(s.hi)}`}</td>
              <td className={s.verdict === 'above' ? 'tone-pos' : s.verdict === 'below' ? 'tone-neg' : 'muted'}>
                {s.verdict ? VERDICT[s.verdict] : `표본 적음(${meta.min_n}번 미만)`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StrategyTable({ st }) {
  return (
    <>
      <div className="table-wrap">
        <table className="coef tq-perf">
          <thead>
            <tr><th /><th>연 수익률</th><th>누적</th><th>최대 낙폭</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>규칙대로</td>
              <td className={st.cagr >= st.bh_cagr ? 'tone-pos' : 'tone-neg'}>{pct(st.cagr)}</td>
              <td>{pct(st.total, 0)}</td>
              <td>{pct(st.mdd)}</td>
            </tr>
            <tr>
              <td>사서 들고 있기</td>
              <td>{pct(st.bh_cagr)}</td>
              <td>{pct(st.bh_total, 0)}</td>
              <td>{pct(st.bh_mdd)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted small">
        {day(st.from)}~{day(st.to)} · 매매 {st.trades}번 · 이긴 매매 {st.win == null ? '—' : `${fmt(st.win, 0)}%`} · 평균
        보유 {st.avg_hold == null ? '—' : `${fmt(st.avg_hold, 0)}거래일`} · 시장에 있던 날 {fmt(st.exposure, 0)}%
      </p>
    </>
  )
}

/** 창의 '실제 지수에서' 절. `ix` 는 고른 지수 id, `setIx` 는 단추. */
export default function LiveSection({ rid, live, error, ix, setIx }) {
  if (error) return <p className="empty">{error.message}</p>
  if (!live) return <p className="empty">불러오는 중…</p>
  const rule = live.rules[rid]
  const index = live.indices.find((x) => x.id === ix) || live.indices[0]
  const by = rule.by[index.id]
  return (
    <>
      <h3>
        실제 지수에서
        <Hint
          wide
          notes={[
            `돌린 규칙: ${rule.label}.`,
            `신호가 난 다음 거래일 종가에 사고판 것으로 셉니다 — 그날 종가를 보고서야 신호를 알 수 있어서입니다. 거래 비용은 한 번 사거나 팔 때마다 ${fmt(live.cost, 1)}% 를 뺐습니다(사서 들고 있기는 살 때 한 번).`,
            `아무 날 범위: 신호가 n 번이면 아무 날 n 개를 골라 같은 기간 수익률의 평균을 내는 것을 ${live.draws.toLocaleString()}번 되풀이한 95% 범위입니다. 신호 평균이 이 범위 밖이어야 아무 날이나 산 것과 다르다고 말할 수 있습니다. 오르는 장에서는 아무 날이나 사도 벌기 때문에 신호 뒤 평균이 플러스인 것만으로는 아무것도 말하지 못합니다.`,
            '같은 쪽 신호가 보는 기간 안에 또 나면 하나로 셉니다 — 몰려 난 신호가 한 구간을 여러 번 세면 범위가 실제보다 좁아 보입니다.',
            rule.kind === 'pattern'
              ? `패턴은 정해 둔 규칙으로만 찾습니다. 종가가 꼭짓점에서 ${fmt(live.pivot, 0)}% 되돌아야 꼭대기·바닥으로 확정하고, 확정된 날부터만 씁니다 — 지나고 나서 고른 꼭대기를 그날 안 것처럼 쓰면 패턴이 기막히게 들어맞습니다. '비슷한 높이' 는 ${fmt(live.tol, 0)}% 안입니다.`
              : '보유 중·쉬는 중은 규칙대로라면 지금 들고 있는 구간인지입니다. 쉬는 동안의 수익은 0 으로 셉니다(예금 이자를 넣지 않았습니다).',
            '과거 성적이 앞으로를 보장하지 않습니다. 기법 설명이지 투자 권유가 아닙니다.',
          ]}
        />
      </h3>
      <div className="seg" role="tablist" aria-label="지수">
        {live.indices.map((x) => (
          <button key={x.id} role="tab" aria-selected={x.id === index.id} onClick={() => setIx(x.id)}>{x.label}</button>
        ))}
      </div>
      <NowLine rule={rule} by={by} ix={index} />
      <SignalTable rule={rule} by={by} meta={live} />
      {by.strategy && <StrategyTable st={by.strategy} />}
    </>
  )
}
