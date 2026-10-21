import { useEffect, useMemo, useState } from 'react'

import { api } from '../api'
import { fmt, niceTicks, useMeasure } from '../components/Charts'
import Hint from '../components/Hint'
import TimeLines from '../components/TimeLines'

/**
 * 매매 · 전세 · 월세 — 같은 집을 세 방법으로 살 때 매달 얼마가 드는지, 금리가 오를 때 세 가격이
 * 어떤 순서로 움직였는지(2026-10-19 요청).
 *
 * 보려는 연쇄: 금리 인상 → 매매·전세 이자가 무거워져 그쪽 수요가 빠짐 → 월세로 몰려 월세·전환율
 * 상승 → 월세 지출이 이자와 맞붙으면 매매·전세로 돌아감. 그림 넷이 한 단계씩 맡는다 — 비용(①),
 * 금리와 세 가격의 1년 변화(②), 월세 쏠림(③), 인상 시작 달 기준의 순서(④).
 *
 * ## 계산은 화면이 한다
 *
 * 월 비용은 대출 비율에 따라 달라진다. 비율마다 응답을 내보내면 정적 사이트 파일이 비율 수만큼
 * 늘어나므로, 백엔드는 재료(가격·전환율·금리)만 보내고 곱셈은 여기서 한다(`services/tenure.py`).
 *
 * ## 증명이 아니라 지켜보기
 *
 * 월세 통계가 2015년부터라 큰 인상기는 한 번뿐이고 그 뒤 인하와 겹친다. 그림이 연쇄와 맞아도
 * 다른 까닭(대출 규제·전세 사기·입주 물량)이 같이 움직였을 수 있다 — 호버에 적는다.
 */
const C = { sale: 'var(--series-1)', jeonse: 'var(--series-3)', rent: 'var(--series-2)', rate: 'var(--series-4)' }
const ymText = (ym) => `${ym.slice(0, 4)}.${ym.slice(4)}`

export default function TenureView() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [ltv, setLtv] = useState(null)

  useEffect(() => {
    let alive = true
    api
      .tenureOverview()
      .then((d) => {
        if (!alive) return
        setData(d)
        setLtv(d.ltv)
      })
      .catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [])

  if (error || (data && !data.available)) {
    return (
      <section className="card">
        <h2>매매·전세·월세</h2>
        <p className="empty">{error ? error.message : data.note}</p>
      </section>
    )
  }
  if (!data || !ltv) {
    return (
      <section className="card">
        <h2>매매·전세·월세</h2>
        <p className="empty">불러오는 중…</p>
      </section>
    )
  }

  const bands = data.hikes.map((h) => ({ from: h.from, to: h.to }))
  const region = (
    <Hint
      notes={[
        `${data.region} 평균입니다 — 모든 달에 값이 있는 구만 씁니다: ${data.used.join(', ')}.`,
        data.dropped.length
          ? `빠진 구: ${data.dropped.map((d) => d.name).join(', ')} — ${data.dropped[0].why}. 섞으면 구성이 바뀌는 달에 평균이 튑니다.`
          : null,
        '옅은 띠는 기준금리 인상기입니다(첫 인상~마지막 인상, 1년 안에 이어진 인상은 한 번으로 묶음).',
      ]}
    />
  )

  return (
    <>
      <Cost data={data} ltv={ltv} setLtv={setLtv} bands={bands} region={region} />
      <Prices data={data} bands={bands} region={region} />
      <RentTilt data={data} bands={bands} region={region} />
      {data.events.length > 0 && <Order data={data} region={region} />}
    </>
  )
}

/** ① 같은 집 월 주거비 — 매매·전세는 이자(대출 + 자기 돈의 예금 이자), 월세는 전세가 × 전환율. */
function Cost({ data, ltv, setLtv, bands, region }) {
  const series = useMemo(() => {
    const pts = (f) => data.rows.map((r) => ({ ym: r.ym, value: Math.round(f(r)) }))
    return [
      { key: 'sale', label: '매매', color: C.sale, width: 2.4,
        points: pts((r) => (r.sale * (ltv.buy * r.mortgage + (1 - ltv.buy) * r.deposit)) / 1200) },
      { key: 'jeonse', label: '전세', color: C.jeonse,
        points: pts((r) => (r.jeonse * (ltv.jeonse * r.jeonse_loan + (1 - ltv.jeonse) * r.deposit)) / 1200) },
      { key: 'rent', label: '월세', color: C.rent,
        points: pts((r) => (r.jeonse * r.conv) / 1200) },
    ]
  }, [data, ltv])
  const last = data.rows[data.rows.length - 1]
  const now = Object.fromEntries(series.map((s) => [s.key, s.points[s.points.length - 1].value]))
  const cheapest = series.reduce((a, s) => (now[s.key] < now[a.key] ? s : a))

  return (
    <section className="card">
      <h2>
        같은 집, 매달 드는 돈
        <Hint
          wide
          notes={[
            '같은 집을 세 방법으로 살 때의 한 달 비용(만원)입니다.',
            '매매 = 매매가 × (대출 비율 × 주택담보대출 금리 + 나머지 × 정기예금 금리) ÷ 12. 전세 = 전세가 × (대출 비율 × 전세자금대출 금리 + 나머지 × 정기예금 금리) ÷ 12. 대출 아닌 몫은 그 돈을 예금에 넣었으면 받았을 이자로 셉니다.',
            '월세 = 전세가 × 전월세 전환율 ÷ 12 — 같은 집의 전세 보증금을 전부 월세로 바꾼 값입니다. 실제 평균 월세는 소형 위주라 집 크기가 달라 쓰지 않습니다.',
            '세지 않는 것: 집값이 오르내려 생기는 차익·손실, 취득세·보유세, 관리비, 원금 상환. 이자만 견주는 계산입니다.',
            '금리는 한국은행 예금은행 신규취급액 기준(전국), 가격·전세가율·전환율은 한국부동산원입니다.',
          ]}
        />
        {region}
      </h2>
      <div className="tn-ctrl">
        <label>
          매매 대출 비율 <b>{Math.round(ltv.buy * 100)}%</b>
          <input type="range" min="0" max="0.8" step="0.1" value={ltv.buy}
                 onChange={(e) => setLtv({ ...ltv, buy: Number(e.target.value) })} />
        </label>
        <label>
          전세 대출 비율 <b>{Math.round(ltv.jeonse * 100)}%</b>
          <input type="range" min="0" max="0.9" step="0.1" value={ltv.jeonse}
                 onChange={(e) => setLtv({ ...ltv, jeonse: Number(e.target.value) })} />
        </label>
      </div>
      <div className="tn-now">
        {series.map((s) => (
          <span key={s.key} className={s.key === cheapest.key ? 'is-min' : ''}>
            <span className="swatch" style={{ background: s.color }} />
            {s.label} <b>{fmt(now[s.key])}</b>만원
          </span>
        ))}
        <span className="muted small">{ymText(last.ym)} · 같은 집 매매가 {fmt(last.sale)} · 전세가 {fmt(last.jeonse)}만원</span>
      </div>
      <TimeLines series={series} unit="만원" bands={bands} height={300}
                 ariaLabel="매매·전세·월세의 같은 집 월 비용 추이" />
    </section>
  )
}

/** ② 금리와 세 가격 — 지수 1년 변화(왼쪽)와 금리(오른쪽). */
function Prices({ data, bands, region }) {
  const series = useMemo(() => {
    const y = (k) => data.yoy[k].map((p) => ({ ym: p.ym, value: p.v }))
    const r = (k) => data.rates[k].map((p) => ({ ym: p.ym, value: p.v }))
    return [
      { key: 'sale', label: '매매지수', color: C.sale, width: 2.4, points: y('sale_index') },
      { key: 'jeonse', label: '전세지수', color: C.jeonse, points: y('jeonse_index') },
      { key: 'rent', label: '월세지수', color: C.rent, points: y('rent_index') },
      { key: 'base', label: '기준금리', color: C.rate, axis: 'right', dash: true, points: r('base_rate') },
      { key: 'mort', label: '주택담보대출 금리', color: C.rate, axis: 'right', dash: '1 3', points: r('mortgage_rate') },
    ]
  }, [data])
  const months = data.yoy.rent_index.map((p) => p.ym)
  return (
    <section className="card">
      <h2>
        금리와 세 가격
        <Hint
          wide
          notes={[
            '왼쪽 축은 매매·전세·월세 가격지수의 1년 변화율(%), 오른쪽 축은 금리(연%)입니다.',
            '연쇄대로라면 인상기(띠)에 매매·전세 선은 내려가고 월세 선은 버티거나 오릅니다.',
            '같이 움직였다고 원인은 아닙니다 — 같은 시기 대출 규제·입주 물량·전세 사기 같은 일도 겹쳤습니다.',
          ]}
        />
        {region}
      </h2>
      <TimeLines series={series} unit="%" decimals={1} zero rightUnit="%" rightDecimals={1}
                 months={months} bands={bands} height={300}
                 ariaLabel="매매·전세·월세 지수 1년 변화와 금리" />
    </section>
  )
}

/**
 * ③ 월세 쏠림 — 전환율과 각 금리의 **차이**로, 누가 어느 쪽을 고를 유인이 있나.
 *
 * 처음에는 전환율과 금리 넷을 수준 그대로 겹쳤다. 선 넷이 2~5% 사이에서 얽혀 '어느 쪽이
 * 유리한가' 를 읽으려면 두 선의 높낮이를 눈으로 빼야 했다(2026-10-21 요청 — 선호 변화가 더
 * 잘 느껴지게). 그래서 고르는 사람마다 견주는 두 값의 차이를 한 줄씩 두고, 0 위·아래를 그때
 * 유리한 쪽의 색으로 칠한다. 색은 탭 공통(매매 파랑 · 전세 청록 · 월세 주황)이다.
 *
 * 세 줄은 같은 %p 축이다 — 줄마다 축을 따로 잡으면 집주인 줄(폭이 큰)과 세입자 줄의 크기를
 * 견줄 수 없다. 수준 그림은 '금리 수준' 단추로 남겼다.
 */
const TILT = [
  { key: 'jeonse', who: '세입자', title: '전세 vs 월세', rate: 'jeonse_loan', rateLabel: '전세자금대출',
    up: { k: 'jeonse', label: '전세 유리' }, down: { k: 'rent', label: '월세 유리' } },
  { key: 'buy', who: '실수요', title: '매매 vs 월세', rate: 'mortgage', rateLabel: '주택담보대출',
    up: { k: 'sale', label: '매매 유리' }, down: { k: 'rent', label: '월세 유리' } },
  { key: 'owner', who: '집주인', title: '월세 vs 전세', rate: 'deposit', rateLabel: '정기예금',
    up: { k: 'rent', label: '월세로 받기 유리' }, down: { k: 'jeonse', label: '전세로 받기 유리' } },
]
const signed = (v, d = 2) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`

function RentTilt({ data, bands, region }) {
  const [view, setView] = useState('gap')
  const [hover, setHover] = useState(null)
  const months = data.rows.map((r) => r.ym)
  const gaps = useMemo(
    () => TILT.map((t) => ({ ...t, vals: data.rows.map((r) => r.conv - r[t.rate]) })),
    [data],
  )
  const series = useMemo(() => {
    const row = (k) => data.rows.map((r) => ({ ym: r.ym, value: r[k] }))
    return [
      { key: 'conv', label: '전월세 전환율', color: C.rent, width: 2.4, points: row('conv') },
      { key: 'jl', label: '전세자금대출 금리', color: C.jeonse, dash: true, points: row('jeonse_loan') },
      { key: 'mort', label: '주택담보대출 금리', color: C.sale, dash: true, points: row('mortgage') },
      { key: 'dep', label: '정기예금 금리', color: C.rate, dash: '1 3', points: row('deposit') },
    ]
  }, [data])
  const all = gaps.flatMap((g) => g.vals)
  const pad = (Math.max(...all) - Math.min(...all)) * 0.08
  // 0 아래를 최소 1.5%p 는 남긴다. 차이가 0 아래로 내려간 때가 드물어(2022년 말 몇 달) 값에만 맞추면
  // 0 선이 바닥에 붙어 '반대쪽이 유리한 영역' 이 있다는 것 자체가 안 보였다.
  const dom = [Math.min(-1.5, Math.min(...all) - pad), Math.max(0, ...all) + pad]
  const hi = hover == null ? null : hover.i
  const r = data.rows[hi ?? data.rows.length - 1]

  return (
    <section className="card">
      <h2>
        월세 쏠림 — 누가 어느 쪽을 고르나
        <Hint
          wide
          notes={[
            '전월세 전환율은 보증금을 월세로 바꿀 때 쓰는 연 이율입니다. 세 줄은 이 전환율에서, 고르는 사람이 견주는 금리를 뺀 값(%p)입니다.',
            '세입자 — 전환율 − 전세자금대출 금리. 0 위면 대출을 받아서라도 전세가 월세보다 싸고(전세 유리), 0 아래면 월세가 쌉니다. 이 줄이 0 쪽으로 내려오는 것이 월세로 몰리는 신호입니다.',
            '실수요 — 전환율 − 주택담보대출 금리. 0 위면 빌려서 사는 이자율이 월세 이율보다 낮습니다(매매 유리). 집값의 오르내림·세금은 빼고 이율만 견줍니다. 같은 집의 실제 월 금액은 맨 위 그림입니다.',
            '집주인 — 전환율 − 정기예금 금리. 0 위면 보증금을 받아 예금에 넣는 것보다 월세로 받는 쪽이 더 법니다. 이 줄이 클수록 전세 매물이 월세로 돌아설 유인이 큽니다.',
            '세 줄은 같은 축(%p)입니다. 칠한 색은 그때 유리한 쪽, 옅은 띠는 기준금리 인상기입니다. 그림 위에 마우스를 올리면 그 달 값이 머리에 나옵니다.',
          ]}
        />
        {region}
      </h2>
      <div className="seg" role="tablist" aria-label="보기">
        <button role="tab" aria-selected={view === 'gap'} onClick={() => setView('gap')}>유리한 쪽</button>
        <button role="tab" aria-selected={view === 'level'} onClick={() => setView('level')}>금리 수준</button>
      </div>
      {view === 'level' ? (
        <TimeLines series={series} unit="%" decimals={1} bands={bands} height={280}
                   ariaLabel="전월세 전환율과 대출·예금 금리" />
      ) : (
        <div className="tilt" onMouseLeave={() => setHover(null)}>
          <p className="muted small">
            {ymText(r.ym)} 전환율 {fmt(r.conv, 2)}% · 전세대출 {fmt(r.jeonse_loan, 2)}% · 주담대 {fmt(r.mortgage, 2)}% · 예금 {fmt(r.deposit, 2)}%
          </p>
          {gaps.map((g, gi) => (
            <TiltRow key={g.key} g={g} months={months} dom={dom} bands={bands} hi={hi}
                     last={gi === gaps.length - 1} onHover={setHover} />
          ))}
        </div>
      )}
    </section>
  )
}

/** 한 줄 — 0 위는 `up` 쪽 색, 아래는 `down` 쪽 색으로 칠한 차이 그림. 마우스는 세 줄이 같이 짚는다. */
function TiltRow({ g, months, dom, bands, hi, last, onHover }) {
  const [ref, width] = useMeasure()
  const W = Math.max(width || 640, 280)
  const H = last ? 112 : 88
  const P = { t: 6, r: 10, b: last ? 24 : 4, l: 40 }
  const iw = W - P.l - P.r
  const ih = H - P.t - P.b
  const n = months.length
  const x = (i) => P.l + (i / Math.max(n - 1, 1)) * iw
  const y = (v) => P.t + ih - ((v - dom[0]) / (dom[1] - dom[0])) * ih
  const y0 = y(0)
  const line = g.vals.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L${x(n - 1).toFixed(1)},${y0.toFixed(1)} L${x(0).toFixed(1)},${y0.toFixed(1)} Z`
  const i = hi ?? n - 1
  const v = g.vals[i]
  const side = v >= 0 ? g.up : g.down
  const step = iw / Math.max(n - 1, 1)
  const shade = bands
    .map((b) => {
      const a = months.findIndex((m) => m >= b.from)
      const z = months.map((m) => m <= b.to).lastIndexOf(true)
      if (a < 0 || z < a) return null
      const x0 = Math.max(P.l, x(a) - step / 2)
      return { key: b.from, x: x0, w: Math.min(P.l + iw, x(z) + step / 2) - x0 }
    })
    .filter(Boolean)
  const years = months.map((m, k) => [m, k]).filter(([m]) => m.endsWith('01'))
  const every = Math.ceil(years.length / Math.max(Math.floor(iw / 56), 1))
  const ticks = [-2, -1, 0, 2, 4].filter((t) => t > dom[0] && t < dom[1])

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * W
    const k = Math.round(((px - P.l) / iw) * (n - 1))
    onHover({ i: Math.min(Math.max(k, 0), n - 1) })
  }

  return (
    <div className="tilt-row" ref={ref}>
      <div className="tilt-head">
        <span><b>{g.who}</b> {g.title} <span className="muted">· 전환율 − {g.rateLabel}</span></span>
        <span className="tilt-now">
          <span className="swatch" style={{ background: C[side.k] }} />
          {side.label} <b>{signed(v)}%p</b>
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" onMouseMove={onMove}
           aria-label={`${g.who} ${g.title} — 전환율에서 ${g.rateLabel} 금리를 뺀 값. 0 위는 ${g.up.label}, 아래는 ${g.down.label}`}>
        <defs>
          <clipPath id={`tilt-up-${g.key}`}><rect x={P.l} y={0} width={iw} height={y0} /></clipPath>
          <clipPath id={`tilt-dn-${g.key}`}><rect x={P.l} y={y0} width={iw} height={H - y0} /></clipPath>
        </defs>
        {/* 영역 바탕 — 위·아래가 각각 누구 편인지 선보다 먼저 보이게 아주 옅게 깐다. */}
        <rect x={P.l} y={P.t} width={iw} height={y0 - P.t} fill={C[g.up.k]} fillOpacity="0.06" />
        <rect x={P.l} y={y0} width={iw} height={P.t + ih - y0} fill={C[g.down.k]} fillOpacity="0.08" />
        {shade.map((b) => <rect key={b.key} x={b.x} y={P.t} width={b.w} height={ih} fill="var(--band)" />)}
        {ticks.map((t) => (
          <g key={t}>
            {t !== 0 && <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeDasharray="2 3" />}
            <text x={P.l - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill="var(--text-muted)">{t > 0 ? `+${t}` : t}</text>
          </g>
        ))}
        <path d={area} fill={C[g.up.k]} fillOpacity="0.3" clipPath={`url(#tilt-up-${g.key})`} />
        <path d={area} fill={C[g.down.k]} fillOpacity="0.45" clipPath={`url(#tilt-dn-${g.key})`} />
        <line x1={P.l} x2={W - P.r} y1={y0} y2={y0} stroke="var(--text-secondary)" />
        <path d={line} fill="none" stroke="var(--text-secondary)" strokeWidth="1.4" strokeLinejoin="round" />
        {/* 영역 이름은 오른쪽 끝, 바탕색 테를 둘러 선과 겹쳐도 읽히게 한다. 왼쪽에 두었더니 2015년 값이
            높아 위쪽 이름이 선에 묻혔다. */}
        <text x={W - P.r - 4} y={P.t + 11} textAnchor="end" fontSize="10.5" fill="var(--text-secondary)"
              stroke="var(--surface-1)" strokeWidth="3" paintOrder="stroke">▲ {g.up.label}</text>
        <text x={W - P.r - 4} y={P.t + ih - 4} textAnchor="end" fontSize="10.5" fill="var(--text-secondary)"
              stroke="var(--surface-1)" strokeWidth="3" paintOrder="stroke">▼ {g.down.label}</text>
        {hi != null && (
          <g pointerEvents="none">
            <line x1={x(hi)} x2={x(hi)} y1={P.t} y2={P.t + ih} stroke="var(--text-muted)" strokeDasharray="3 3" />
            <circle cx={x(hi)} cy={y(v)} r="4" fill={C[side.k]} stroke="var(--surface-1)" strokeWidth="2" />
          </g>
        )}
        {last && years.filter((_, k) => k % every === 0).map(([m, k]) => (
          <text key={m} x={x(k)} y={H - 7} textAnchor="middle" fontSize="10.5" fill="var(--text-muted)">
            {m.slice(0, 4)}
          </text>
        ))}
        <rect x={P.l} y={P.t} width={iw} height={ih} fill="transparent" />
      </svg>
    </div>
  )
}

/**
 * ④ 순서 확인 — 인상 시작 달을 100 으로 놓고 세 지수가 그 앞뒤로 어떻게 갔나.
 *
 * 연쇄의 '순서' 는 달력이 아니라 **인상 뒤 몇 달째** 로 봐야 인상기끼리 견줄 수 있다. 저점은
 * 시작 뒤 가장 낮았던 달이다 — 그 달이 시작 달이면 '내리지 않음' 이다(월세처럼 계속 오른 선).
 */
function Order({ data, region }) {
  const [pick, setPick] = useState(() => {
    const full = data.events.filter((e) => e.paths.rent_index.length > 24)
    return (full[full.length - 1] || data.events[data.events.length - 1]).start
  })
  const ev = data.events.find((e) => e.start === pick) || data.events[0]
  const lines = [
    { key: 'sale_index', label: '매매지수', color: C.sale, width: 2.4 },
    { key: 'jeonse_index', label: '전세지수', color: C.jeonse },
    { key: 'rent_index', label: '월세지수', color: C.rent },
  ].map((l) => {
    const pts = ev.paths[l.key]
    const after = pts.filter((p) => p.k >= 0)
    const low = after.reduce((a, p) => (p.v < a.v ? p : a), after[0])
    const lastK = pts[pts.length - 1].k
    return { ...l, pts, low: low && low.k > 0 && low.k < lastK ? low : null, lastK }
  })
  const endK = gapMonths(ev.start, ev.end)

  return (
    <section className="card">
      <h2>
        순서 확인 — 인상 뒤 몇 달째에
        <Hint
          wide
          notes={[
            '기준금리 인상 시작 달을 100 으로 놓고, 그 12개월 전부터 48개월 뒤까지 세 지수가 어떻게 갔는지입니다.',
            '세로 실선은 인상 시작, 점선은 마지막 인상 달입니다. 점은 시작 뒤 가장 낮았던 달(저점)입니다.',
            '연쇄대로라면 매매·전세가 먼저 꺾여 저점을 찍고, 월세는 그동안 버티거나 오르며, 시차를 두고 매매·전세가 다시 오릅니다.',
            '인상기가 몇 번 안 됩니다 — 한 번의 경로를 법칙으로 읽지 마세요. 인상 뒤에 인하가 이어지면 반등은 인하 몫과 섞입니다.',
          ]}
        />
        {region}
      </h2>
      <div className="seg" role="tablist" aria-label="인상기 고르기">
        {data.events.map((e) => (
          <button key={e.start} role="tab" aria-selected={e.start === ev.start} onClick={() => setPick(e.start)}>
            {ymText(e.start)} (+{fmt(e.rise, 2)}%p)
          </button>
        ))}
      </div>
      <EventChart lines={lines} span={data.event_span} endK={endK} />
      <div className="tn-lows">
        {lines.map((l) => (
          <span key={l.key}>
            <span className="swatch" style={{ background: l.color }} />
            {l.label}{' '}
            {l.low
              ? <>저점 <b>{l.low.k}개월째</b> ({fmt(l.low.v - 100, 1)}%)</>
              : l.lastK < 24 ? <span className="muted">진행 중</span> : <span className="muted">시작 뒤 내리지 않음</span>}
          </span>
        ))}
      </div>
    </section>
  )
}

function gapMonths(a, b) {
  return (Number(b.slice(0, 4)) - Number(a.slice(0, 4))) * 12 + Number(b.slice(4)) - Number(a.slice(4))
}

/** 상대 달(k) 축의 선 그래프. TimeLines 는 달력 축(ym)이라 따로 둔다. */
function EventChart({ lines, span, endK }) {
  const [ref, width] = useMeasure()
  const [hover, setHover] = useState(null)
  const W = Math.max(width || 640, 280)
  const H = 280
  const P = { t: 12, r: 14, b: 26, l: 48 }
  const iw = W - P.l - P.r
  const ih = H - P.t - P.b
  const vals = lines.flatMap((l) => l.pts.map((p) => p.v))
  let lo = Math.min(100, ...vals)
  let hi = Math.max(100, ...vals)
  const pad = (hi - lo) * 0.06 || 1
  lo -= pad
  hi += pad
  const x = (k) => P.l + ((k - span[0]) / (span[1] - span[0])) * iw
  const y = (v) => P.t + ih - ((v - lo) / (hi - lo)) * ih
  const ticks = niceTicks(lo, hi, 5).filter((t) => t >= lo && t <= hi)
  const kTicks = []
  for (let k = span[0]; k <= span[1]; k += 12) kTicks.push(k)

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * W
    const k = Math.round(span[0] + ((px - P.l) / iw) * (span[1] - span[0]))
    setHover({ k: Math.min(Math.max(k, span[0]), span[1]), cx: e.clientX, cy: e.clientY })
  }

  return (
    <div className="macro-chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="인상 시작 달 기준 세 지수 경로"
           onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <rect x={x(0)} y={P.t} width={Math.max(x(endK) - x(0), 2)} height={ih} fill="var(--band)" />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--grid)"
                  strokeDasharray={t === 100 ? undefined : '2 3'} />
            <text x={P.l - 6} y={y(t) + 3} textAnchor="end" fontSize="10.5" fill="var(--text-muted)">{fmt(t)}</text>
          </g>
        ))}
        {kTicks.map((k, i) => (
          <text key={k} x={x(k)} y={H - 8} textAnchor={i === kTicks.length - 1 ? 'end' : 'middle'} fontSize="10.5" fill="var(--text-muted)">
            {k > 0 ? `+${k}` : k}개월
          </text>
        ))}
        <line x1={x(0)} x2={x(0)} y1={P.t} y2={P.t + ih} stroke="var(--text-secondary)" />
        <line x1={x(endK)} x2={x(endK)} y1={P.t} y2={P.t + ih} stroke="var(--text-secondary)" strokeDasharray="4 3" />
        {lines.map((l) => (
          <path key={l.key} fill="none" stroke={l.color} strokeWidth={l.width ?? 1.9} strokeLinejoin="round"
                d={l.pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.k).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')} />
        ))}
        {lines.map((l) => l.low && (
          <circle key={l.key} cx={x(l.low.k)} cy={y(l.low.v)} r="4" fill={l.color} stroke="var(--surface-1)" />
        ))}
        {hover && (
          <line x1={x(hover.k)} x2={x(hover.k)} y1={P.t} y2={P.t + ih} stroke="var(--text-muted)"
                strokeDasharray="3 3" pointerEvents="none" />
        )}
        <rect x={P.l} y={P.t} width={iw} height={ih} fill="transparent" />
      </svg>
      <div className="legend">
        {lines.map((l) => (
          <span className="key" key={l.key}><span className="swatch" style={{ background: l.color }} />{l.label}</span>
        ))}
      </div>
      {hover && (
        <div className="chart-tooltip"
             style={{ left: Math.min(hover.cx + 14, window.innerWidth - 220), top: Math.max(hover.cy - 12, 8) }}>
          <div className="t-title">인상 시작 {hover.k > 0 ? `${hover.k}개월 뒤` : hover.k < 0 ? `${-hover.k}개월 전` : '달'}</div>
          {lines.map((l) => {
            const p = l.pts.find((q) => q.k === hover.k)
            return <div className="t-row" key={l.key}>{l.label} {p ? fmt(p.v, 1) : '—'}</div>
          })}
        </div>
      )}
    </div>
  )
}
