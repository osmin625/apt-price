import { useEffect, useState } from 'react'

import { api } from '../api'
import { fmt, useMeasure, useTooltip } from '../components/Charts'
import Modal from '../components/Modal'
import PanelCard from '../components/PanelCard'

/**
 * 공급 분석 — 적정 공급량과 실제 공급을 견준다.
 *
 * ## 왜 가격 탭과 따로인가
 *
 * 가격 분석은 **값이 어떻게 움직였나**를 보고, 여기는 **왜 그렇게 될 수밖에
 * 없었나**를 본다. 공급은 2~3년 전에 정해져서 지금 나타나므로, 가격 추이와 같은
 * 축에 놓으면 둘 다 안 읽힌다.
 *
 * ## 적정선을 상수로 두지 않는다
 *
 * '서울 연 5만 호' 는 널리 쓰이는 어림이지만 우리는 **가구 증가 + 멸실**로 계산한다.
 * 해마다 달라지는 값이고(서울은 2011~2015 에 46,000~54,000 이었다가 2019년 이후
 * 올라갔다), 상수로 두면 그 변화가 안 보인다.
 *
 * ## 서울은 앞을 보지 않는다
 *
 * 착공이 준공을 선행하는지 재 보니 경기는 27개월 시차에서 상관 +0.895 인데 서울은
 * 시차 0에서 +0.693 이고 시차가 늘수록 떨어진다. 그래서 경기만 가늠하고 서울은
 * **왜 못 하는지를 적는다.** 빈 카드보다 낫고, 억지로 낸 숫자보다는 훨씬 낫다.
 */
export default function SupplyView() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(null)

  useEffect(() => {
    let alive = true
    setError(null)
    api
      .supplyOverview()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [])

  if (error) {
    return (
      <section className="card">
        <h2>공급 분석</h2>
        <p className="empty">{error.message}</p>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="card">
        <h2>공급 분석</h2>
        <p className="empty">공급 통계를 불러오는 중…</p>
      </section>
    )
  }

  const seoul = data.regions.find((r) => r.sgg_cd === '11')
  const gg = data.regions.find((r) => r.sgg_cd === '41')

  return (
    <>
      <section className="card">
        <h2>공급이 가격을 어디로 미나</h2>
        <p className="sub">
          <b>적정 공급 = 가구 증가 + 멸실</b> 로 계산합니다. 흔히 쓰는 '서울 연 5만 호'
          같은 상수를 쓰지 않았습니다 — 해마다 달라지는 값이기 때문입니다. 공급은 2~3년
          전에 정해져 지금 나타나므로, 지금 부족하면 그 영향은 몇 해 더 갑니다.
        </p>
      </section>

      <section className="card">
        <h2>공급 과부족</h2>
        <p className="sub">
          준공에서 적정 공급을 뺀 값입니다. 음수면 그해 새로 생긴 가구와 없어진 집을
          합친 것보다 덜 지었다는 뜻입니다.
        </p>
        <div className="macro-grid">
          {data.regions.map((r) => (
            <PanelCard
              key={r.sgg_cd}
              title={`${r.region} 과부족`}
              sub={gapSub(r)}
              onOpen={() => setOpen({ kind: 'balance', r })}
            >
              <GapBars rows={r.rows} />
            </PanelCard>
          ))}
          {data.regions.map((r) => (
            <PanelCard
              key={`p-${r.sgg_cd}`}
              title={`${r.region} 파이프라인`}
              sub="인허가 → 착공 → 준공 (12개월 누적)"
              onOpen={() => setOpen({ kind: 'pipeline', r })}
            >
              <PipeLines series={r.pipeline.series} />
            </PanelCard>
          ))}
          <PanelCard
            title="2~3년 뒤 입주 (경기)"
            sub={gg?.lead?.available
              ? `착공 ${gg.lead.lag_months}개월 뒤 · 상관 ${gg.lead.corr?.toFixed(3)}`
              : '가늠할 수 없음'}
            onOpen={() => setOpen({ kind: 'lead' })}
          >
            {gg?.lead?.available ? <LeadMini lead={gg.lead} /> : null}
          </PanelCard>
          <PanelCard
            title="노후 재고 압력"
            sub={`경기 남부 단지 ${fmt(data.age_pressure.total_complexes)}곳 · 30년 초과 ${data.age_pressure.old_pct}%`}
            onOpen={() => setOpen({ kind: 'age' })}
          >
            <AgeBars bands={data.age_pressure.bands} />
          </PanelCard>
        </div>
        <p className="muted small">{data.note}</p>
      </section>

      {open?.kind === 'balance' && (
        <Modal title={`${open.r.region} — 공급 과부족`} onClose={() => setOpen(null)} wide>
          <BalanceTable r={open.r} />
        </Modal>
      )}
      {open?.kind === 'pipeline' && (
        <Modal title={`${open.r.region} — 공급 파이프라인`} onClose={() => setOpen(null)} wide>
          <PipeTable r={open.r} />
        </Modal>
      )}
      {open?.kind === 'lead' && (
        <Modal title="2~3년 뒤 입주" onClose={() => setOpen(null)} wide>
          <LeadDetail seoul={seoul} gg={gg} />
        </Modal>
      )}
      {open?.kind === 'age' && (
        <Modal title="노후 재고 압력" onClose={() => setOpen(null)} wide>
          <AgeDetail age={data.age_pressure} />
        </Modal>
      )}
    </>
  )
}

function gapSub(r) {
  const last = [...r.rows].reverse().find((x) => x.gap != null)
  if (!last) return '—'
  const short = r.rows.filter((x) => x.gap != null && x.gap < 0).length
  return `${last.year}년 ${last.gap > 0 ? '+' : ''}${fmt(last.gap)}호 · 부족했던 해 ${short}번`
}

/** 0을 기준으로 좌우로 뻗는 막대. 과부족은 부호가 전부다. */
function GapBars({ rows }) {
  const tip = useTooltip()
  const list = rows.filter((r) => r.gap != null)
  if (!list.length) return <p className="empty">값이 없습니다</p>
  const span = Math.max(...list.map((r) => Math.abs(r.gap))) * 1.1 || 1
  return (
    <div className="pbar">
      {list.map((r) => {
        const pos = r.gap >= 0
        const w = (Math.abs(r.gap) / span) * 50
        return (
          <div
            className="pbar-row"
            key={r.year}
            onMouseMove={(e) =>
              tip.show(
                e,
                <>
                  <div className="t-title">{r.year}년</div>
                  <div className="t-row">적정 {fmt(r.adequate)}호</div>
                  <div className="t-row">준공 {fmt(r.done)}호</div>
                  <div className="t-row">
                    과부족 {r.gap > 0 ? '+' : ''}{fmt(r.gap)}호
                  </div>
                </>,
              )
            }
            onMouseLeave={tip.hide}
          >
            <div className="pbar-label">{r.year.slice(2)}</div>
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
      {tip.node}
    </div>
  )
}

/** 인허가·착공·준공 세 줄. 값의 자릿수가 비슷해 한 축에 둔다. */
function PipeLines({ series }) {
  const [ref, width] = useMeasure()
  const keys = ['permit', 'start', 'done']
  const all = keys.flatMap((k) => (series[k] || []).map((d) => d.value))
  if (!all.length) return <p className="empty">값이 없습니다</p>
  const max = Math.max(...all) * 1.08
  const H = 120
  const W = Math.max(width, 240)
  const n = Math.max(...keys.map((k) => (series[k] || []).length))
  const x = (i) => (i / Math.max(n - 1, 1)) * W
  const y = (v) => H - (v / max) * H

  return (
    <div ref={ref}>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
        {keys.map((k, ki) => {
          const s = series[k] || []
          if (!s.length) return null
          const off = n - s.length
          const d = s
            .map((p, i) => `${i ? 'L' : 'M'}${x(i + off)},${y(p.value)}`)
            .join(' ')
          return (
            <path
              key={k}
              d={d}
              fill="none"
              stroke={`var(--series-${ki + 1})`}
              strokeWidth="2"
              strokeLinejoin="round"
            />
          )
        })}
      </svg>
      <div className="legend">
        {['인허가', '착공', '준공'].map((name, i) => (
          <span className="key" key={name}>
            <span className="swatch" style={{ background: `var(--series-${i + 1})` }} />
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}

function LeadMini({ lead }) {
  const last = lead.series[lead.series.length - 1]
  if (!last) return null
  return (
    <div className="tile">
      <div className="label">{fmtYm(last.expect_ym)} 무렵</div>
      <div className="value sm">{fmt(last.value)}호</div>
      <div className="note">최근 12개월 착공 기준</div>
    </div>
  )
}

function AgeBars({ bands }) {
  const max = Math.max(...bands.map((b) => b.pct)) || 1
  return (
    <div className="pbar">
      {bands.map((b) => (
        <div className="pbar-row" key={b.band}>
          <div className="pbar-label">{b.band}</div>
          <div className="pbar-track">
            <div
              className={`pbar-fill ${b.band.startsWith('3') || b.band.startsWith('4') ? 'neg' : 'pos'}`}
              style={{ left: 0, width: `${(b.pct / max) * 100}%` }}
            />
          </div>
          <div className="pbar-value">{b.pct}%</div>
        </div>
      ))}
    </div>
  )
}

function BalanceTable({ r }) {
  return (
    <>
      <p className="muted small">
        적정 공급은 <b>가구 증가 + 멸실</b>입니다. 가구수는 '천' 단위로 공표되어
        1,000을 곱했습니다. 단년 증가분은 등록센서스 집계가 바뀐 해에 튀므로
        <b> 3년 이동평균</b>도 같이 둡니다.
      </p>
      <div className="table-wrap">
        <table className="coef">
          <thead>
            <tr>
              <th>연도</th>
              <th className="num">가구 증가</th>
              <th className="num">멸실</th>
              <th className="num">그중 아파트</th>
              <th className="num">적정 공급</th>
              <th className="num">적정(3년평균)</th>
              <th className="num">준공</th>
              <th className="num">과부족</th>
            </tr>
          </thead>
          <tbody>
            {r.rows.map((x) => (
              <tr key={x.year}>
                <td>{x.year}</td>
                <td className="num">{fmt(x.household_growth)}</td>
                <td className="num">{fmt(x.demolish)}</td>
                <td className="num">{fmt(x.demolish_apt)}</td>
                <td className="num">{fmt(x.adequate)}</td>
                <td className="num">{x.adequate_smooth == null ? '—' : fmt(x.adequate_smooth)}</td>
                <td className="num">{x.done == null ? '—' : fmt(x.done)}</td>
                <td className={`num ${x.gap == null ? '' : x.gap < 0 ? 'tone-neg' : 'tone-pos'}`}>
                  {x.gap == null ? '—' : `${x.gap > 0 ? '+' : ''}${fmt(x.gap)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        준공은 <b>12개월이 다 있는 해만</b> 셉니다. 올해는 아직 안 끝나서 빠집니다 —
        8월까지만 더해 '올해 공급이 급감했다'고 적으면 거짓이 됩니다.
      </p>
    </>
  )
}

function PipeTable({ r }) {
  const rows = r.pipeline.series.done || []
  const find = (k, ym) => (r.pipeline.series[k] || []).find((d) => d.ym === ym)?.value
  return (
    <>
      <p className="muted small">
        12개월 누적입니다. 월별은 들쭉날쭉해서(서울 착공이 7월 6,386호인데 8월
        1,172호) 누적으로 봐야 추세가 읽힙니다. <b>인허가는 연 누계로 공표</b>되어
        적재할 때 월별로 되돌렸습니다.
      </p>
      <div className="table-wrap">
        <table className="coef">
          <thead>
            <tr>
              <th>시점</th>
              <th className="num">인허가</th>
              <th className="num">착공</th>
              <th className="num">준공</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(-24).reverse().map((d) => (
              <tr key={d.ym}>
                <td>{fmtYm(d.ym)}</td>
                <td className="num">{fmt(find('permit', d.ym))}</td>
                <td className="num">{fmt(find('start', d.ym))}</td>
                <td className="num">{fmt(d.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function LeadDetail({ seoul, gg }) {
  return (
    <>
      {gg?.lead?.available && (
        <>
          <p className="muted small">{gg.lead.note}</p>
          <div className="table-wrap">
            <table className="coef">
              <thead>
                <tr>
                  <th>착공 시점</th>
                  <th className="num">12개월 착공</th>
                  <th>입주 예상</th>
                </tr>
              </thead>
              <tbody>
                {gg.lead.series.slice(-12).reverse().map((d) => (
                  <tr key={d.ym}>
                    <td>{fmtYm(d.ym)}</td>
                    <td className="num">{fmt(d.value)}</td>
                    <td>{fmtYm(d.expect_ym)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="paste-warn" style={{ marginTop: 12 }}>
        <b>서울은 가늠하지 않습니다.</b> {seoul?.lead?.note}
      </p>
      <p className="muted small">
        미래 입주 예정 물량은 공표 통계에 없습니다 — 준공실적은 이미 지어진 것이고,
        예정치는 민간 집계입니다. 여기 값은 <b>착공으로 미룬 추정</b>이지 확정된
        입주 물량이 아닙니다.
      </p>
    </>
  )
}

function AgeDetail({ age }) {
  return (
    <>
      <p className="muted small">{age.note}</p>
      <div className="table-wrap">
        <table className="coef">
          <thead>
            <tr>
              <th>연식</th>
              <th className="num">단지</th>
              <th className="num">비중</th>
              <th className="num">세대</th>
            </tr>
          </thead>
          <tbody>
            {age.bands.map((b) => (
              <tr key={b.band}>
                <td>{b.band}</td>
                <td className="num">{fmt(b.complexes)}</td>
                <td className="num">{b.pct}%</td>
                <td className="num">{fmt(b.households)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">{age.as_of_year}년 기준.</p>
    </>
  )
}

function fmtYm(ym) {
  if (!ym || ym.length !== 6) return ym || '—'
  return `${ym.slice(0, 4)}.${ym.slice(4)}`
}
