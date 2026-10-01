import { useEffect, useMemo, useState } from 'react'

import { api } from '../api'
import { fmt, niceTicks, useMeasure, useTooltip } from '../components/Charts'
import Loading from '../components/Loading'
import QuadrantScatter from '../components/QuadrantScatter'

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

  const [ins, setIns] = useState(null)

  useEffect(() => {
    api.macroMetrics().then(setMeta).catch(() => setMeta(null))
    api.macroInsights().then(setIns).catch(() => setIns(null))
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

      {ins && <Insights ins={ins} />}

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

/* 읽을 거리 셋. 문장을 자동 생성하지 않고 **그림**으로 둔 이유는, 해석 문장이 근거
   숫자와 떨어지면 추정을 사실처럼 보여 주는 것이 되기 때문이다. 점의 위치가 곧 근거다. */
function Insights({ ins }) {
  const { cycle, rally, model_gap: gap, has_fit: hasFit } = ins
  return (
    <>
      <div className="card">
        <h2>
          지금 어느 국면인가
          <span className="muted small"> 시군구 {cycle.items.length}곳</span>
        </h2>
        <p className="muted small">{cycle.note}</p>
        <QuadrantScatter
          items={cycle.items}
          x={(d) => d.from_peak}
          y={(d) => d.m3}
          xLabel={cycle.x_label}
          yLabel={cycle.y_label}
          quadrants={['신고가 경신 중', '바닥에서 반등', '전고점 아래 · 정체/하락', '고점 부근에서 꺾임']}
          xDecimals={0}
          tip={(d) => (
            <>
              <div className="t-title">{d.name}</div>
              <div className="t-row">
                전고점({d.peak_ym}) 대비 {d.from_peak > 0 ? '+' : ''}{fmt(d.from_peak, 1)}%
              </div>
              <div className="t-row">
                저점({d.trough_ym})에서 +{fmt(d.from_trough, 1)}%
              </div>
              <div className="t-row">
                3개월 {d.m3 > 0 ? '+' : ''}{fmt(d.m3, 2)}% · 12개월{' '}
                {d.m12 > 0 ? '+' : ''}{fmt(d.m12, 2)}%
              </div>
              {d.accel != null && (
                <div className="t-row">
                  직전 3개월 대비 {d.accel > 0 ? '가속' : '감속'} {fmt(Math.abs(d.accel), 2)}%p
                </div>
              )}
            </>
          )}
        />
        {cycle.excluded.length > 0 && (
          <p className="paste-warn" style={{ marginTop: 8 }}>
            {cycle.excluded.join(' · ')}는 공표 기간이 24개월이 안 돼 사이클을 판단할 수
            없어 뺐습니다. 분구 시점에 통계가 새로 시작했기 때문입니다.
          </p>
        )}
      </div>

      <div className="card">
        <h2>그 상승을 전세가 받쳐 줬나</h2>
        <p className="muted small">{rally.note}</p>
        <QuadrantScatter
          items={rally.items}
          x={(d) => d.sale_12m}
          y={(d) => d.ratio_12m}
          xLabel={rally.x_label}
          yLabel={rally.y_label}
          quadrants={['오르고 전세도 붙음', '안 올랐는데 전세는 붙음', '안 오르고 전세도 빠짐', '매매만 간 상승']}
          xDecimals={0}
          tip={(d) => (
            <>
              <div className="t-title">{d.name}</div>
              <div className="t-row">
                12개월 매매 {d.sale_12m > 0 ? '+' : ''}{fmt(d.sale_12m, 1)}%
              </div>
              <div className="t-row">
                전세가율 {fmt(d.ratio_now, 1)}% ({d.ratio_12m > 0 ? '+' : ''}
                {fmt(d.ratio_12m, 1)}%p)
              </div>
            </>
          )}
        />
      </div>

      <div className="card">
        <h2>
          모델과 어긋나는 곳
          {gap.spearman != null && (
            <span className="muted small"> 순위상관 {fmt(gap.spearman, 3)}</span>
          )}
        </h2>
        {!hasFit ? (
          <p className="empty">
            적합이 아직 캐시에 없어 비교할 수 없습니다. <b>시장 분석</b> 탭을 한 번 열면
            계산되고, 그 뒤 이 화면으로 돌아오면 보입니다.
          </p>
        ) : (
          <>
            <p className="muted small">{gap.note}</p>
            <QuadrantScatter
              items={gap.items}
              x={(d) => d.rank_reb}
              y={(d) => d.rank_coef}
              xLabel={gap.x_label}
              yLabel={gap.y_label}
              xOrigin={null}
              yOrigin={null}
              invertX
              invertY
              diagonal
              xDecimals={0}
              yDecimals={0}
              tip={(d) => (
                <>
                  <div className="t-title">{d.name}</div>
                  <div className="t-row">
                    부동산원 {d.rank_reb}위 · 평당 {fmt(d.reb, 0)}만원
                  </div>
                  <div className="t-row">
                    모델 {d.rank_coef}위 · 구 계수 {d.coef_pct > 0 ? '+' : ''}
                    {fmt(d.coef_pct, 1)}%{d.is_base ? ' (기준구)' : ''}
                  </div>
                  <div className="t-row">
                    순위 차 {d.rank_gap > 0 ? '+' : ''}{d.rank_gap}
                  </div>
                </>
              )}
            />
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table>
                <thead>
                  <tr>
                    <th>시군구</th>
                    <th className="num">부동산원</th>
                    <th className="num">모델</th>
                    <th className="num">순위 차</th>
                  </tr>
                </thead>
                <tbody>
                  {[...gap.items]
                    .sort((a, b) => Math.abs(b.rank_gap) - Math.abs(a.rank_gap))
                    .slice(0, 5)
                    .map((d) => (
                      <tr key={d.sgg_cd}>
                        <td>{d.name}</td>
                        <td className="num">
                          {d.rank_reb}위 <span className="muted small">{fmt(d.reb, 0)}만원/평</span>
                        </td>
                        <td className="num">
                          {d.rank_coef}위{' '}
                          <span className="muted small">
                            {d.coef_pct > 0 ? '+' : ''}
                            {fmt(d.coef_pct, 1)}%
                          </span>
                        </td>
                        <td className={`num ${d.rank_gap > 0 ? 'tone-neg' : 'tone-pos'}`}>
                          {d.rank_gap > 0 ? '+' : ''}
                          {d.rank_gap}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p className="muted small" style={{ marginTop: 6 }}>
              가장 많이 벌어진 다섯 곳입니다. 어느 쪽이 맞는지는 이 표가 말해 주지
              않습니다 — 그 지역의 평형·연식 구성이 특이해 단순 평균이 끌려갔거나,
              모델이 뭔가를 놓쳤거나입니다. <b>어디를 들여다볼지</b>만 알려 줍니다.
            </p>
          </>
        )}
      </div>
    </>
  )
}
