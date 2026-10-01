import { useEffect, useMemo, useState } from 'react'

import { api } from '../api'
import { fmt, niceTicks, useMeasure, useTooltip } from '../components/Charts'
import Loading from '../components/Loading'

/**
 * 매크로 — 한국부동산원 공표 통계를 경기 남부 17개 시군구로 묶어 본다.
 *
 * ## 왜 만들었나
 *
 * KB부동산 데이터허브에도 같은 통계가 있다. 그런데 거기서 경기 남부만 모아 보려
 * 하면 **차트에 5개까지만 그려지고**, 무엇보다 지역 선택이 URL 에도 공유링크에도
 * 남지 않아 열 때마다 17번을 다시 골라야 했다. 여기서는 17개가 기본이다.
 *
 * ## 이 탭의 성격
 *
 * 다른 탭은 전부 **우리 모델**이 낸 값이다. 이 탭만 바깥에서 가져온 **공표 통계**다.
 * 그래서 모델이 맞는지 보는 바깥 기준이 된다 — 예를 들어 평당 매매가격 순위가
 * 분해 모델의 구 계수 순서와 어긋나면 둘 중 하나를 의심해야 한다.
 *
 * 숫자가 KB 와 다른 것은 정상이다. 조사 주체와 표본이 다르다.
 */
export default function MacroView() {
  const [meta, setMeta] = useState(null)
  const [metric, setMetric] = useState('avg_unit_price')
  const [since, setSince] = useState('202001')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [hidden, setHidden] = useState(() => new Set())

  useEffect(() => {
    api.macroMetrics().then(setMeta).catch(() => setMeta(null))
  }, [])

  useEffect(() => {
    let alive = true
    setError(null)
    setData(null)
    api
      .macroSeries({ metric, since })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [metric, since])

  const toggle = (sgg) =>
    setHidden((h) => {
      const n = new Set(h)
      n.has(sgg) ? n.delete(sgg) : n.add(sgg)
      return n
    })

  if (error) {
    return (
      <div className="card">
        <h2>매크로</h2>
        <p className="empty">{error}</p>
      </div>
    )
  }

  return (
    <>
      <div className="card">
        <h2>경기 남부 17개 시군구를 한 화면에</h2>
        <p className="sub">
          한국부동산원이 공표하는 <b>아파트 통계</b>입니다. 다른 탭은 우리 모델이 낸
          값이지만 이 탭만 바깥에서 가져온 공표 통계라, 모델을 견주어 볼 바깥 기준이
          됩니다. KB 등 다른 기관 수치와 다를 수 있습니다 — 조사 주체와 표본이 다릅니다.
        </p>

        <div className="filters">
          <div className="field">
            <label>지표</label>
            <div className="rank-basis" style={{ margin: 0 }}>
              {(meta?.metrics || []).map((m) => (
                <button
                  key={m.key}
                  className={`chip${metric === m.key ? ' on' : ''}`}
                  onClick={() => setMetric(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <label htmlFor="mc-since">기간</label>
            <select id="mc-since" value={since} onChange={(e) => setSince(e.target.value)}>
              <option value="202401">최근 3년</option>
              <option value="202001">최근 7년</option>
              <option value="201201">전체(2012~)</option>
            </select>
          </div>
        </div>
      </div>

      {!data ? (
        <div className="card">
          <Loading label="공표 통계를 불러오는 중" compact />
        </div>
      ) : (
        <>
          <div className="card">
            <h2>
              {data.label}
              <span className="muted small">
                {' '}
                {data.unit} · 시군구 {data.n_districts}곳 · {data.months[0]}~
                {data.months[data.months.length - 1]}
              </span>
            </h2>
            <p className="muted small">{data.note}</p>
            <MultiLine data={data} hidden={hidden} />
            <Legend data={data} hidden={hidden} onToggle={toggle} />
            {data.items.some((i) => i.partial) && (
              <p className="paste-warn" style={{ marginTop: 8 }}>
                화성시 분구(만세·효행·병점·동탄)는 <b>분구 시점부터</b> 공표가 시작돼
                시계열이 짧습니다. 없는 기간을 채우지 않았으므로 선이 중간에서 시작합니다 —
                긴 추이를 비교할 때는 이 점을 감안해야 합니다.
              </p>
            )}
          </div>

          <div className="card">
            <h2>최신값</h2>
            <p className="muted small">
              {data.label} 기준 · {data.items[0]?.latest_ym} 공표. 변화율은 선택한 기간의
              처음 대비입니다.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>시군구</th>
                    <th className="num">{data.label}</th>
                    <th className="num">기간 변화</th>
                    <th>시작</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((i) => (
                    <tr key={i.sgg_cd}>
                      <td>{i.name}</td>
                      <td className="num">
                        <b>{fmt(i.latest, data.decimals)}</b>
                        <span className="muted small"> {data.unit}</span>
                      </td>
                      <td
                        className={`num ${
                          i.change_pct > 0 ? 'tone-pos' : i.change_pct < 0 ? 'tone-neg' : ''
                        }`}
                      >
                        {i.change_pct == null
                          ? '—'
                          : `${i.change_pct > 0 ? '+' : ''}${fmt(i.change_pct, 1)}%`}
                      </td>
                      <td className="muted small">
                        {i.first_ym}
                        {i.partial ? ' (분구 후)' : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  )
}

/* 17개 선을 한 축에. 색은 순위로 돌린다 — 이름마다 고정색을 주면 17개를 구분할
   만큼 색이 없고, 어차피 범례에서 짚어 보게 된다. */
function MultiLine({ data, hidden }) {
  const [ref, { width }] = useMeasure()
  const tip = useTooltip()
  const H = 300
  const PAD = { t: 12, r: 12, b: 26, l: 52 }

  const shown = data.items.filter((i) => !hidden.has(i.sgg_cd))
  const months = data.months

  const { xOf, yOf, ticks, paths } = useMemo(() => {
    const w = Math.max(width || 640, 320)
    const iw = w - PAD.l - PAD.r
    const ih = H - PAD.t - PAD.b
    const idx = new Map(months.map((m, i) => [m, i]))
    const xOf = (ym) => PAD.l + (idx.get(ym) / Math.max(months.length - 1, 1)) * iw

    let lo = Infinity
    let hi = -Infinity
    shown.forEach((s) =>
      s.points.forEach((p) => {
        if (p.value < lo) lo = p.value
        if (p.value > hi) hi = p.value
      }),
    )
    if (!Number.isFinite(lo)) {
      lo = 0
      hi = 1
    }
    const pad = (hi - lo) * 0.08 || 1
    lo -= pad
    hi += pad
    const yOf = (v) => PAD.t + ih - ((v - lo) / (hi - lo || 1)) * ih

    const paths = shown.map((s) => ({
      ...s,
      d: s.points
        .map((p, k) => `${k ? 'L' : 'M'}${xOf(p.ym).toFixed(1)},${yOf(p.value).toFixed(1)}`)
        .join(' '),
    }))
    return { xOf, yOf, ticks: niceTicks(lo, hi, 4), paths }
  }, [width, shown, months])

  // x축 라벨은 연 단위로만. 월까지 찍으면 겹쳐서 못 읽는다.
  const yearMarks = months
    .map((m, i) => ({ m, i }))
    .filter(({ m }) => m.endsWith('01'))

  return (
    <div className="macro-chart" ref={ref}>
      <svg viewBox={`0 0 ${Math.max(width || 640, 320)} ${H}`} role="img"
           aria-label={`${data.label} 시군구별 추이`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={(width || 640) - PAD.r} y1={yOf(t)} y2={yOf(t)}
                  stroke="var(--border)" strokeDasharray="2 3" />
            <text x={PAD.l - 6} y={yOf(t) + 3} textAnchor="end"
                  fontSize="10" fill="var(--text-muted)">
              {fmt(t, data.decimals)}
            </text>
          </g>
        ))}
        {yearMarks.map(({ m }) => (
          <text key={m} x={xOf(m)} y={H - 8} textAnchor="middle"
                fontSize="10" fill="var(--text-muted)">
            {m.slice(0, 4)}
          </text>
        ))}
        {paths.map((p, i) => (
          <path
            key={p.sgg_cd}
            d={p.d}
            fill="none"
            stroke={colorAt(i, paths.length)}
            strokeWidth="1.8"
            strokeLinejoin="round"
            onMouseEnter={(e) =>
              tip.show(e, (
                <>
                  <div className="t-title">{p.name}</div>
                  <div className="t-row">
                    최신 {fmt(p.latest, data.decimals)} {data.unit}
                  </div>
                  <div className="t-row">
                    {p.first_ym}~{p.latest_ym}
                    {p.change_pct == null
                      ? ''
                      : ` · ${p.change_pct > 0 ? '+' : ''}${fmt(p.change_pct, 1)}%`}
                  </div>
                </>
              ))
            }
            onMouseLeave={tip.hide}
          />
        ))}
      </svg>
      {tip.node}
    </div>
  )
}

function Legend({ data, hidden, onToggle }) {
  const shown = data.items.filter((i) => !hidden.has(i.sgg_cd))
  const indexOfShown = new Map(shown.map((s, i) => [s.sgg_cd, i]))
  return (
    <div className="macro-legend">
      {data.items.map((i) => {
        const off = hidden.has(i.sgg_cd)
        return (
          <button
            key={i.sgg_cd}
            className={`macro-key${off ? ' is-off' : ''}`}
            onClick={() => onToggle(i.sgg_cd)}
            aria-pressed={!off}
            title={off ? '다시 표시' : '숨기기'}
          >
            <i
              style={{
                background: off
                  ? 'var(--text-muted)'
                  : colorAt(indexOfShown.get(i.sgg_cd), shown.length),
              }}
            />
            {i.name}
          </button>
        )
      })}
    </div>
  )
}

/** 순위를 색상환에 고르게 편다. 17개를 구분하려면 고정 팔레트로는 모자란다. */
function colorAt(i, n) {
  if (i == null) return 'var(--text-muted)'
  const hue = Math.round((i / Math.max(n, 1)) * 320)
  return `hsl(${hue} 62% 48%)`
}
