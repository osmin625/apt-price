import { useMemo, useState } from 'react'

import ChartLink from '../../shared/ChartLink'
import { fmt } from '../../shared/Charts'
import Hint from '../../shared/Hint'
import TimeLines from '../../shared/TimeLines'

/**
 * 구간 예측 — 다음 1개월·3개월 수익률 80% 구간과, **같은 장치로 잰 과거 성적**. 지수 분석 탭의 아래에
 * **접혀** 있다(2026-11 — 맨 위는 경제지표의 영향이다). 접힌 채로는 제목과 한 줄(구간 점수가 가장 낮은
 * 후보의 다음 1개월 구간)만 보이고, 누르면 아래가 펼쳐진다.
 *
 * 예측만 보여 주면 '얼마나 믿을 만한가' 를 말할 수 없다. 그래서 표 한 줄이 후보 하나이고, 지금 구간
 * 옆에 그 후보가 과거 같은 기점들에서 낸 성적(포함률·폭·구간 점수·기준선 대비 DM 검정)을 같이 둔다.
 * 기준선은 무작위 보행이다. 못 이기면 숫자가 그렇게 말한다 — 판정 문장은 만들지 않는다
 * (CLAUDE.md '값은 계산해 넣어도 판정은 그날에 묶인다'). 상태 한 줄은 응답에서 그 자리에서 센다.
 *
 * 줄을 누르면 그 후보의 과거 구간이 그림에 그려진다. 처음에는 구간 점수가 가장 낮은 후보다.
 */
const ym = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}`
const day = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
const signed = (v, d = 1) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}%`
const tone = (v) => (v > 0 ? 'tone-pos' : v < 0 ? 'tone-neg' : '')
const P_SIG = 0.05
// 0.0005 아래를 소수 셋째 자리로 찍으면 '0' 이 된다 — p 가 0 인 검정은 없다.
const pText = (p) => (p == null ? '—' : p < 0.001 ? '<0.001' : fmt(p, 3))

export default function ForecastCard({ ix }) {
  const [open, setOpen] = useState(false)
  const [h, setH] = useState(ix.horizons[0].h)
  const hz = ix.horizons.find((x) => x.h === h)
  const best = useMemo(
    () => [...hz.models].sort((a, b) => a.interval_score - b.interval_score)[0].id,
    [hz],
  )
  const [pick, setPick] = useState(null)
  const sel = pick && hz.models.some((m) => m.id === pick) ? pick : best
  const selModel = hz.models.find((m) => m.id === sel)
  const bt = hz.backtest
  const beats = hz.models.filter(
    (m) => !m.baseline && m.dm_interval_p != null && m.dm_interval_p < P_SIG && m.dm_interval_t < 0,
  )

  const series = useMemo(() => {
    const pts = (arr) => bt.origins.map((o, i) => ({ ym: o, value: arr[i] }))
    return [
      { key: 'actual', label: `실제 ${h}개월 수익률`, color: 'var(--series-1)', width: 2, points: pts(bt.actual) },
      { key: 'hi', label: `${selModel.label} 상단`, color: 'var(--series-3)', dash: true, points: pts(bt.bands[sel].map((b) => b[1])) },
      { key: 'lo', label: `${selModel.label} 하단`, color: 'var(--series-3)', dash: true, points: pts(bt.bands[sel].map((b) => b[0])) },
    ]
  }, [bt, sel, selModel, h])

  // 접힌 한 줄은 1개월의, 구간 점수가 가장 낮은 후보(기간 단추와 무관하게 고정).
  const one = useMemo(() => {
    const ms = ix.horizons.find((x) => x.h === 1)?.models.filter((m) => m.now) || []
    return [...ms].sort((a, b) => a.interval_score - b.interval_score)[0]
  }, [ix])

  return (
    <section className="card">
      <h2>
        {ix.label} — 다음 1·3개월 범위
        <Hint
          wide
          notes={[
            `${ym(ix.origin)} 말 종가에서 다음 ${h}개월 수익률이 ${Math.round((1 - ix.alpha) * 100)}% 확률로 들어갈 구간입니다. 현지 통화(${ix.currency}) 기준이고 배당은 빠진 가격 지수입니다.`,
            '후보마다 그 기점 전에 알려진 것만으로 매달 다시 예측해 실제와 견줬습니다(시간순 표본 밖). 모든 후보가 같은 기점에서 잽니다.',
            '포함률은 실제가 구간 안에 든 비율로, 목표에 가까울수록 정직한 구간입니다. 넓히기만 해도 포함률은 오르므로 구간 점수(폭 + 벗어난 만큼의 벌점, 낮을수록 좋음)를 같이 봅니다. 폭·점수는 로그 수익률(%p)로 잽니다.',
            'p 는 기준선(무작위 보행)과 같은지를 본 Diebold–Mariano 검정입니다. 작을수록 차이가 우연이 아닙니다 — 방향은 점수가 낮은 쪽입니다.',
            `무위험 금리는 ${ix.rf_label}입니다. 출처: ${ix.source}. 마지막 거래일 ${day(ix.last_day)} — 그 달은 아직 끝나지 않아 기점에서 뺍니다.`,
          ]}
        />
        <ChartLink id={`${ix.id}-forecast`} />
      </h2>
      <p className="muted small">
        다음 1개월 {one ? `${signed(one.now.lo)} ~ ${signed(one.now.hi)}` : '—'} ({one?.label}) ·{' '}
        <button className="linklike" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? '접기' : '후보별 성적 펼치기'}
        </button>
      </p>
      {open && (<>
      <div className="seg" role="tablist" aria-label="기간">
        {ix.horizons.map((x) => (
          <button key={x.h} role="tab" aria-selected={x.h === h} onClick={() => setH(x.h)}>
            {x.h}개월
          </button>
        ))}
      </div>
      <p className="muted small">
        기점 {bt.origins.length}개({ym(bt.origins[0])}~{ym(bt.origins[bt.origins.length - 1])}) · 기준선보다 구간
        점수가 낮고 p&lt;{P_SIG}: {beats.length ? beats.map((m) => m.label).join(', ') : '없음'}
      </p>
      {/* 휴대폰 폭에서는 여덟 칸이 안 들어간다 — 글자를 세로로 쪼개지 말고 표만 옆으로 민다. */}
      <div className="table-wrap">
        <table className="coef" style={{ whiteSpace: 'nowrap' }}>
          <thead>
            <tr>
              <th>후보</th>
              <th>지금 구간</th>
              <th>중심</th>
              <th>포함률</th>
              <th>평균 폭</th>
              <th>구간 점수</th>
              <th>p(구간)</th>
              <th>p(중심)</th>
            </tr>
          </thead>
          <tbody>
            {hz.models.map((m) => (
              <tr key={m.id} className={m.id === sel ? 'is-current' : ''} onClick={() => setPick(m.id)}
                  style={{ cursor: 'pointer' }}>
                <td>{m.label}{m.baseline ? ' (기준선)' : ''}</td>
                <td>{m.now ? `${signed(m.now.lo)} ~ ${signed(m.now.hi)}` : '—'}</td>
                <td className={m.now ? tone(m.now.mid) : ''}>{m.now ? signed(m.now.mid, 2) : '—'}</td>
                <td>{fmt(m.coverage, 1)}%</td>
                <td>{fmt(m.width, 1)}%p</td>
                <td>{fmt(m.interval_score, 1)}</td>
                <td>{m.baseline ? '—' : pText(m.dm_interval_p)}</td>
                <td>{m.baseline ? '—' : pText(m.dm_point_p)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TimeLines series={series} unit="%" decimals={1} zero height={260}
                 ariaLabel={`${ix.label} 실제 ${h}개월 수익률과 ${selModel.label} 구간`} />
      </>)}
    </section>
  )
}
