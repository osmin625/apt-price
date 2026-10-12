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
/**
 * 공표 통계의 '경기' 는 **북부를 포함한다.** 공급 표에 시 단위 분류가 하나도 없어
 * (준공·착공·인허가·가구수·멸실 전부 0개) 좁힐 수가 없다. 화면에 그렇게 적는다 —
 * 경기 전체를 경기 남부처럼 부르지 않는다.
 *
 * 얼마나 다른지는 미분양에서 보인다(그것만 시 단위가 있다). 2026-06 기준 경기
 * 전체가 14,509호인데 **경기 남부 8개 시는 834호**다. 17배 차이다.
 */
const REGION_LABEL = { 서울: '서울', 경기: '경기 전체' }
const regionName = (r) => REGION_LABEL[r] || r

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
          <b>적정 공급 = 가구 증가 + 멸실</b> 로 계산합니다. 해마다 달라지는 값이라
          고정된 목표치를 두지 않았습니다. 공급은 2~3년 전에 정해져 지금 나타나므로,
          지금 부족하면 그 영향은 몇 해 더 갑니다.
        </p>
      </section>

      <section className="card">
        <h2>적정보다 더 지었나, 덜 지었나</h2>
        <p className="sub">
          <b>적정 공급</b>과 <b>준공</b>을 같은 축에 겹쳤습니다. 준공이 아래로 내려가
          붉게 칠해진 해는 그해 새로 생긴 가구와 없어진 집을 합친 것보다 <b>덜 지은 해</b>
          이고, 파랗게 칠해진 해는 <b>더 지은 해</b>입니다. 차이만 그리면 적정이 커진
          것인지 준공이 준 것인지 알 수 없어 두 선을 같이 둡니다.
        </p>
        <p className="sub">
          점선은 <b>해마다의 차이를 더해 온 값</b>입니다(오른쪽 축). 더 지은 해에는
          올라가고 <b>덜 지은 해에는 내려갑니다</b> — 한 방향으로만 쌓이는 값이
          아닙니다. 0 아래로 내려가면 그 기간 전체로 덜 지었다는 뜻입니다.
        </p>
        <div className="macro-grid">
          {data.regions.map((r) => (
            <PanelCard
              key={r.sgg_cd}
              title={`${regionName(r.region)} — 적정 대비 공급`}
              sub={gapSub(r)}
              onOpen={() => setOpen({ kind: 'balance', r })}
            >
              <GapLines rows={r.rows} cumFrom={r.cum_from} />
            </PanelCard>
          ))}
          {data.regions.map((r) => (
            <PanelCard
              key={`p-${r.sgg_cd}`}
              title={`${regionName(r.region)} 파이프라인`}
              sub="인허가 → 착공 → 준공 (12개월 누적)"
              onOpen={() => setOpen({ kind: 'pipeline', r })}
            >
              <PipeLines series={r.pipeline.series} />
            </PanelCard>
          ))}
          <PanelCard
            title="2~3년 뒤 입주 (경기 전체)"
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

      <section className="card">
        <h2>경기 남부는 얼마나 지어졌나</h2>
        <p className="sub">
          공급 통계가 시 단위로 오지 않아, <b>K-apt 의무관리대상 아파트를 17개 구
          전수로 받아</b> 사용승인 연도별로 모았습니다. 위의 '준공' 과는 다른 값입니다
          — 소규모 단지와 비아파트가 빠지고, 철거된 단지가 없어 과거일수록 적게
          잡힙니다. <b>적정 공급에서 빼지 않고 추세만 봅니다.</b>
        </p>
        <div className="macro-grid">
          <PanelCard
            title="경기 남부 아파트 입주 물량"
            sub={southSub(data.south_supply)}
            onOpen={() => setOpen({ kind: 'south' })}
          >
            <SouthBars d={data.south_supply} />
          </PanelCard>
        </div>
      </section>

      {open?.kind === 'south' && (
        <Modal title="경기 남부 아파트 입주 물량" onClose={() => setOpen(null)} wide>
          <SouthTable d={data.south_supply} />
        </Modal>
      )}

      <section className="card">
        <h2>미분양 — 지어 놓고 안 팔린 집</h2>
        <p className="sub">
          공급 지표 가운데 <b>시 단위가 있는 것은 미분양뿐</b>입니다. 그래서 여기서만
          경기 남부를 따로 낼 수 있습니다. 지역마다 자릿수가 달라 한 축에 겹치지 않고
          카드를 나눴습니다.
        </p>
        <div className="macro-grid">
          {data.unsold.regions.map((u) => (
            <PanelCard
              key={u.sgg_cd}
              title={u.region}
              sub={unsoldSub(u)}
              onOpen={() => setOpen({ kind: 'unsold' })}
            >
              <UnsoldLine u={u} />
            </PanelCard>
          ))}
        </div>
        <p className="muted small">{data.unsold.note}</p>
      </section>

      {open?.kind === 'unsold' && (
        <Modal title="미분양" onClose={() => setOpen(null)} wide>
          <UnsoldTable d={data.unsold} />
        </Modal>
      )}
      {open?.kind === 'balance' && (
        <Modal title={`${regionName(open.r.region)} — 적정 대비 공급`} onClose={() => setOpen(null)} wide>
          <BalanceTable r={open.r} />
        </Modal>
      )}
      {open?.kind === 'pipeline' && (
        <Modal title={`${regionName(open.r.region)} — 공급 파이프라인`} onClose={() => setOpen(null)} wide>
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
  // '과부족 +7,997호' 는 읽는 사람이 부호의 뜻을 외워야 한다. 말로 적는다 —
  // "과부족이 부족한 물량 아니냐" 는 물음을 실제로 받았다.
  const word = last.gap >= 0 ? '더 지음' : '덜 지음'
  return `${last.year}년 ${fmt(Math.abs(last.gap))}호 ${word} · 덜 지은 해 ${short}번`
}

/**
 * 적정 공급과 준공을 **같은 축에 두 선**으로 겹친다.
 *
 * 처음에는 과부족(준공 - 적정) 하나만 좌우 막대로 그렸다. 부호는 바로 보였지만
 * **무엇과 무엇의 차이인지가 안 보였다** — "2020년 -36,994호" 를 보고도 적정이
 * 커진 것인지 준공이 준 것인지 알 수 없었다. 실제로 서울 2020년은 둘 다다
 * (적정 115,912 = 가구 증가가 85,900 으로 뛰었고, 준공은 78,918 로 평년 수준).
 *
 * 두 선을 겹치고 사이를 칠한다. 칠한 색이 부족/과잉을 말하고, 선의 높이가
 * 그 이유를 말한다. 막대로는 둘 중 하나밖에 못 했다.
 */
function GapLines({ rows, height = 128, smooth = false, axis = false, cumFrom }) {
  const tip = useTooltip()
  const [ref, width] = useMeasure()
  const list = rows.filter((r) => r.adequate != null && r.done != null)
  if (!list.length) return <p className="empty">값이 없습니다</p>

  const H = height
  const W = Math.max(width, 240)
  // 왼쪽에 눈금 자리를 둔다. 축소판은 숫자를 안 쓰므로 0 이다.
  const PAD_L = axis ? 46 : 0
  const PAD_R = axis ? 44 : 0
  const PAD_B = axis ? 18 : 10
  const PAD_T = 8
  const vals = list.flatMap((r) => [r.adequate, r.done])
  // **0 에서 시작하지 않는다.** 적정과 준공은 둘 다 수만 호대라 0 부터 그리면
  // 두 선이 붙어 버려 차이가 안 보인다. 차이를 보려고 그리는 그림이다.
  const lo = Math.min(...vals) * 0.9
  const hi = Math.max(...vals) * 1.05
  const span = hi - lo || 1
  const x = (i) => PAD_L + (i / Math.max(list.length - 1, 1)) * (W - PAD_L - PAD_R)
  const y = (v) => PAD_T + (1 - (v - lo) / span) * (H - PAD_T - PAD_B)
  const line = (key) =>
    list.map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`).join(' ')

  // 누적 차이는 **다른 종류의 양**이다(호 × 해). 같은 축에 올리면 둘 중 하나가
  // 납작해져 둘 다 못 읽는다. 오른쪽 축을 따로 두고 선도 점선으로 구분한다.
  // 0 을 반드시 축에 포함한다 — 음수로 돌아섰는지가 이 선의 요점이다.
  //
  // **'누계' 라고 적었다가 물음을 받았다** — "누계라는데 내려간다". 맞는 지적이다.
  // 더한 값이 아니라 **더한 것에서 뺀 것**이라 덜 지은 해에는 내려간다(서울·경기
  // 각각 14년 중 6년). 계산은 맞았고 이름이 틀렸다.
  const cums = list.map((r) => r.gap_cum).filter((v) => v != null)
  const c2 = cums.length
    ? { lo: Math.min(0, ...cums) * 1.1, hi: Math.max(0, ...cums) * 1.1 }
    : null
  const y2 = (v) =>
    PAD_T + (1 - (v - c2.lo) / (c2.hi - c2.lo || 1)) * (H - PAD_T - PAD_B)
  const cumLine = c2
    ? list
        .filter((r) => r.gap_cum != null)
        .map((r, i) => `${i ? 'L' : 'M'}${x(list.indexOf(r)).toFixed(1)},${y2(r.gap_cum).toFixed(1)}`)
        .join(' ')
    : ''

  // 부족 구간과 과잉 구간을 따로 칠한다. 한 덩어리로 칠하면 부호가 섞인 해에서
  // 색이 거짓말을 한다.
  const bands = []
  for (let i = 0; i < list.length - 1; i += 1) {
    const a = list[i]
    const b = list[i + 1]
    const short = a.done < a.adequate
    bands.push({
      key: a.year,
      short,
      d: `M${x(i)},${y(a.adequate)} L${x(i + 1)},${y(b.adequate)} `
        + `L${x(i + 1)},${y(b.done)} L${x(i)},${y(a.done)} Z`,
    })
  }

  return (
    <div ref={ref}>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="적정 공급과 준공 비교">
        {bands.map((b) => (
          <path key={b.key} d={b.d} fill={b.short ? 'var(--neg)' : 'var(--series-1)'}
                opacity="0.14" />
        ))}
        {c2 && (
          <>
            {/* 누계 0 선. 여기를 넘나드는 것이 '쌓였다/까먹었다' 다 */}
            <line x1={PAD_L} x2={W - PAD_R} y1={y2(0)} y2={y2(0)}
                  stroke="var(--text-muted)" strokeDasharray="2 4" opacity="0.6" />
            <path d={cumLine} fill="none" stroke="var(--text-secondary)" strokeWidth="1.8"
                  strokeDasharray="6 3" strokeLinejoin="round" />
          </>
        )}
        {axis && c2 && [c2.hi, 0, c2.lo].map((v) => (
          <text key={`c${v}`} x={W - PAD_R + 6} y={y2(v) + 4} fontSize="10"
                fill="var(--text-muted)">
            {v > 0 ? '+' : ''}{Math.round(v / 1000)}천
          </text>
        ))}
        {axis && [hi, (hi + lo) / 2, lo].map((v) => (
          <g key={v}>
            <line x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} stroke="var(--border)" />
            <text x={PAD_L - 6} y={y(v) + 4} textAnchor="end" fontSize="10"
                  fill="var(--text-muted)">
              {Math.round(v / 1000)}천
            </text>
          </g>
        ))}
        <path d={line('adequate')} fill="none" stroke="var(--series-2)" strokeWidth="2"
              strokeLinejoin="round" />
        <path d={line('done')} fill="none" stroke="var(--series-1)" strokeWidth="2"
              strokeLinejoin="round" />
        {smooth && (
          <path
            d={list.filter((r) => r.adequate_smooth != null)
              .map((r, i) => {
                const idx = list.indexOf(r)
                return `${i ? 'L' : 'M'}${x(idx).toFixed(1)},${y(r.adequate_smooth).toFixed(1)}`
              })
              .join(' ')}
            fill="none" stroke="var(--series-2)" strokeWidth="1.2" strokeDasharray="4 3"
            opacity="0.8"
          />
        )}
        {/* 연도마다 투명한 띠를 깔아 **어디에 올려도** 그 해 값이 뜨게 한다.
            선 위에만 반응하게 두면 두 선 사이에서는 아무것도 안 뜬다. */}
        {list.map((r, i) => (
          <rect
            key={r.year}
            x={x(i) - (W - PAD_L - PAD_R) / list.length / 2}
            y={0}
            width={(W - PAD_L - PAD_R) / list.length}
            height={H}
            fill="transparent"
            onMouseMove={(e) =>
              tip.show(
                e,
                <>
                  <div className="t-title">{r.year}년</div>
                  <div className="t-row">적정 {fmt(r.adequate)}호</div>
                  <div className="t-row">준공 {fmt(r.done)}호</div>
                  <div className="t-row">
                    {r.gap >= 0 ? '더 지음' : '덜 지음'} {fmt(Math.abs(r.gap))}호
                  </div>
                  {r.gap_cum != null && (
                    <div className="t-row">
                      누적 차이 {r.gap_cum >= 0 ? '+' : '−'}{fmt(Math.abs(r.gap_cum))}호
                    </div>
                  )}
                </>,
              )
            }
            onMouseLeave={tip.hide}
          />
        ))}
        {axis && list.map((r, i) => (
          i % 2 === 0 ? (
            <text key={r.year} x={x(i)} y={H - 4} textAnchor="middle" fontSize="10"
                  fill="var(--text-muted)">
              {r.year.slice(2)}
            </text>
          ) : null
        ))}
      </svg>
      <div className="legend">
        <span className="key">
          <span className="swatch" style={{ background: 'var(--series-2)' }} />
          적정 공급
        </span>
        <span className="key">
          <span className="swatch" style={{ background: 'var(--series-1)' }} />
          준공
        </span>
        <span className="key">
          <span className="swatch" style={{ background: 'var(--neg)', opacity: 0.3 }} />
          덜 지은 해
        </span>
        {c2 && (
          <span className="key">
            <span className="swatch dash" style={{ background: 'var(--text-secondary)' }} />
            누적 차이{cumFrom ? ` (${cumFrom}년~, 오른쪽 축)` : ''}
          </span>
        )}
      </div>
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

function southSub(d) {
  const done = d.years.filter((y) => y.year < d.partial_from)
  const last = done[done.length - 1]
  if (!last) return `단지 ${fmt(d.coverage.units)}곳`
  return `${last.year}년 ${fmt(last.households)}세대 · 단지 ${fmt(d.coverage.units)}곳 전수`
}

/**
 * 연도별 입주 세대수. **최근 두 해는 흐리게** 그린다.
 *
 * 사용승인이 안 난 단지는 K-apt 에 안 들어온다. 그 해 막대가 짧은 것은 공급이
 * 준 것이 아니라 아직 안 들어온 것인데, 똑같이 그리면 '최근 급감' 으로 읽힌다.
 */
function SouthBars({ d }) {
  const tip = useTooltip()
  const list = d.years
  if (!list.length) return <p className="empty">아직 적재되지 않았습니다</p>
  const max = Math.max(...list.map((y) => y.households)) || 1
  return (
    <div className="pbar">
      {list.slice(-16).map((y) => {
        const partial = d.partial_from && y.year >= d.partial_from
        return (
          <div
            className="pbar-row"
            key={y.year}
            onMouseMove={(e) =>
              tip.show(
                e,
                <>
                  <div className="t-title">{y.year}년</div>
                  <div className="t-row">{fmt(y.households)}세대 · 단지 {y.complexes}곳</div>
                  {partial && <div className="t-row">아직 덜 찬 값입니다</div>}
                </>,
              )
            }
            onMouseLeave={tip.hide}
          >
            <div className="pbar-label">{y.year.slice(2)}</div>
            <div className="pbar-track">
              <div
                className="pbar-fill pos"
                style={{
                  left: 0,
                  width: `${(y.households / max) * 100}%`,
                  opacity: partial ? 0.35 : 1,
                }}
              />
            </div>
          </div>
        )
      })}
      {tip.node}
    </div>
  )
}

function SouthTable({ d }) {
  const c = d.coverage
  return (
    <>
      <p className="sub">{d.note}</p>
      <p className="muted small">
        전수 {fmt(c.units)}곳 가운데 세대수가 있는 단지 {fmt(c.with_households)}곳,
        사용승인 연도가 있는 단지 {fmt(c.with_year)}곳입니다.
      </p>
      <div className="table-wrap">
        <table className="coef">
          <thead>
            <tr>
              <th>연도</th>
              <th className="num">단지</th>
              <th className="num">세대</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {[...d.years].reverse().map((y) => (
              <tr key={y.year}>
                <td>{y.year}</td>
                <td className="num">{y.complexes}</td>
                <td className="num">{fmt(y.households)}</td>
                <td className="muted">
                  {d.partial_from && y.year >= d.partial_from ? '덜 찬 값' : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function unsoldSub(u) {
  const y = u.yoy == null ? '' : ` · 전년비 ${u.yoy > 0 ? '+' : ''}${u.yoy}%`
  return `${fmtYm(u.latest.ym)} ${fmt(u.latest.value)}호${y}`
}

/** 한 지역의 미분양 추이. 최고점을 같이 찍어 지금이 어느 수준인지 보이게 한다. */
function UnsoldLine({ u }) {
  const [ref, width] = useMeasure()
  const s = u.series
  if (!s.length) return <p className="empty">값이 없습니다</p>
  const H = 110
  const W = Math.max(width, 240)
  const hi = Math.max(...s.map((d) => d.value)) * 1.08 || 1
  const x = (i) => (i / Math.max(s.length - 1, 1)) * W
  const y = (v) => H - (v / hi) * (H - 10) - 4
  const d = s.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const pi = s.findIndex((p) => p.ym === u.peak.ym)
  return (
    <div ref={ref}>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`${u.region} 미분양 추이`}>
        <path d={`${d} L${x(s.length - 1)},${H} L0,${H} Z`} fill="var(--series-1)" opacity="0.1" />
        <path d={d} fill="none" stroke="var(--series-1)" strokeWidth="1.8" />
        {pi >= 0 && <circle cx={x(pi)} cy={y(u.peak.value)} r="3" fill="var(--neg)" />}
        <circle cx={x(s.length - 1)} cy={y(s[s.length - 1].value)} r="3" fill="var(--series-1)" />
      </svg>
      <div className="muted small">
        최고 {fmtYm(u.peak.ym)} {fmt(u.peak.value)}호
      </div>
    </div>
  )
}

function UnsoldTable({ d }) {
  return (
    <>
      <p className="sub">{d.note}</p>
      <div className="table-wrap">
        <table className="coef">
          <thead>
            <tr>
              <th>지역</th>
              <th className="num">최근</th>
              <th className="num">전년비</th>
              <th className="num">최고</th>
              <th className="num">최고 대비</th>
            </tr>
          </thead>
          <tbody>
            {d.regions.map((u) => (
              <tr key={u.sgg_cd}>
                <td>{u.region}</td>
                <td className="num">
                  {fmt(u.latest.value)}호<span className="muted"> ({fmtYm(u.latest.ym)})</span>
                </td>
                <td className={`num ${u.yoy == null ? '' : u.yoy > 0 ? 'tone-neg' : 'tone-pos'}`}>
                  {u.yoy == null ? '—' : `${u.yoy > 0 ? '+' : ''}${u.yoy}%`}
                </td>
                <td className="num muted">
                  {fmt(u.peak.value)}호 ({fmtYm(u.peak.ym)})
                </td>
                <td className="num">{Math.round((u.latest.value / u.peak.value) * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        경기 남부는 수원·용인·화성·안양·오산·의왕·군포·과천 8개 시의 합입니다.
        시 단위는 전체보다 한두 달 늦게 공표됩니다.
      </p>
    </>
  )
}

function BalanceTable({ r }) {
  return (
    <>
      {/* 창에서는 3년 이동평균까지 셋을 그린다. 축소판은 둘만 — 카드가 답하는
          질문은 '볼 만한가' 하나다(PanelCard 주석). */}
      <GapLines rows={r.rows} height={210} smooth axis cumFrom={r.cum_from} />
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
              <th className="num">더(+)·덜(−) 지음</th>
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
