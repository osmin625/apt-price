import { fmt, useMeasure, useTooltip } from '../components/Charts'
import Hint from '../components/Hint'

/**
 * 공급 분석의 표 둘 — 미분양·파이프라인.
 *
 * 원래 `views/SupplyView.jsx` 의 창 안에 있던 것을 그대로 옮겼다. 이제 주제 창
 * (`TopicModal`)이 그래프와 함께 띄운다.
 */

function fmtYm(ym) {
  if (!ym || ym.length !== 6) return ym || '—'
  return `${ym.slice(0, 4)}.${ym.slice(4)}`
}

export function UnsoldTable({ d }) {
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
                <td className={`num ${u.yoy == null ? '' : u.yoy > 0 ? 'tone-pos' : u.yoy < 0 ? 'tone-neg' : ''}`}>
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
      <p className="muted small"><Hint pill wide label="설명">
        경기 남부는 수원·용인·화성·안양·오산·의왕·군포·과천 8개 시의 합입니다.
        시 단위는 전체보다 한두 달 늦게 공표됩니다.
      </Hint></p>
    </>
  )
}

export function PipeTable({ r }) {
  const rows = r.pipeline.series.done || []
  const find = (k, ym) => (r.pipeline.series[k] || []).find((d) => d.ym === ym)?.value
  return (
    <>
      <p className="muted small"><Hint pill wide label="설명">
        12개월 누적입니다. 월별은 큰 단지 하나가 들어오는 달에 튀어서 들쭉날쭉하므로
        누적으로 봐야 추세가 읽힙니다. <b>인허가는 연 누계로 공표</b>되어
        적재할 때 월별로 되돌렸습니다.
      </Hint></p>
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

/**
 * 덜 지은 해인가 — **3년평균 적정 대비**. 카드 부제·그림의 띠·창의 표가 모두
 * 이것 하나로 판정한다. 기준을 3년평균으로 두는 까닭은 GapLines 주석에 있다.
 */
export const isShort = (x) => x.gap_smooth < 0

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
export function GapLines({ rows, height = 128, smooth = false, axis = false, cumFrom }) {
  const tip = useTooltip()
  const [ref, width] = useMeasure()
  // **3년 평균을 기준으로 쓴다.** 단년 적정은 집계 기준이 바뀐 해에 튄다 —
  // 서울 2016년 가구 증가가 +200 이라 그해만 '공급 과잉 +45,764' 로 혼자 솟는다.
  // 그 한 점 때문에 화면을 읽는 사람이 없는 사건을 보게 된다.
  // 단년은 지우지 않고 옅은 선으로 남긴다. 평균은 2년을 끌고 다니므로 원래 값이
  // 어디였는지 볼 수 있어야 한다.
  //
  // 적정을 못 내는 해(`need_missing` — 가구수·멸실이 아직 공표되지 않은 해)도
  // 준공이 있으면 넣는다. 준공 점만 찍고 띠·누계는 그리지 않는다. 빼 버리면
  // 12개월이 다 찬 준공이 화면에서 사라지고, 0 으로 채우면 '크게 더 지음' 이 된다.
  const list = rows.filter(
    (r) => r.done != null && (r.adequate_smooth != null || r.need_missing))
  if (!list.length) return <p className="empty">값이 없습니다</p>
  const partial = list.some((r) => r.need_missing)

  const H = height
  const W = Math.max(width, 240)
  // 왼쪽에 눈금 자리를 둔다. 축소판은 숫자를 안 쓰므로 0 이다.
  const PAD_L = axis ? 46 : 0
  // 끝 해가 '준공만 있는 해' 면 그 점이 오른쪽 끝에 걸려 반이 잘린다.
  const PAD_R = axis ? 44 : partial ? 5 : 0
  const PAD_B = axis ? 18 : 10
  const PAD_T = 8
  const vals = list.flatMap((r) => [r.adequate_smooth, r.adequate, r.done])
    .filter((v) => v != null)
  // **0 에서 시작하지 않는다.** 적정과 준공은 둘 다 수만 호대라 0 부터 그리면
  // 두 선이 붙어 버려 차이가 안 보인다. 차이를 보려고 그리는 그림이다.
  const lo = Math.min(...vals) * 0.9
  const hi = Math.max(...vals) * 1.05
  const span = hi - lo || 1
  const x = (i) => PAD_L + (i / Math.max(list.length - 1, 1)) * (W - PAD_L - PAD_R)
  const y = (v) => PAD_T + (1 - (v - lo) / span) * (H - PAD_T - PAD_B)
  const line = (key) =>
    list
      .map((r, i) => (r[key] == null ? null : `${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`))
      .filter(Boolean)
      .map((p, i) => `${i ? 'L' : 'M'}${p}`)
      .join(' ')

  // 누적 차이는 **다른 종류의 양**이다(호 × 해). 같은 축에 올리면 둘 중 하나가
  // 납작해져 둘 다 못 읽는다. 오른쪽 축을 따로 두고 선도 점선으로 구분한다.
  // 0 을 반드시 축에 포함한다 — 음수로 돌아섰는지가 이 선의 요점이다.
  //
  // **'누계' 라고 적었다가 물음을 받았다** — "누계라는데 내려간다". 맞는 지적이다.
  // 더한 값이 아니라 **더한 것에서 뺀 것**이라 덜 지은 해에는 내려간다(그 무렵
  // 단년 기준으로 서울·경기 각각 14년 중 6년). 계산은 맞았고 이름이 틀렸다.
  const cums = list.map((r) => r.gap_cum_smooth).filter((v) => v != null)
  const c2 = cums.length
    ? { lo: Math.min(0, ...cums) * 1.1, hi: Math.max(0, ...cums) * 1.1 }
    : null
  const y2 = (v) =>
    PAD_T + (1 - (v - c2.lo) / (c2.hi - c2.lo || 1)) * (H - PAD_T - PAD_B)
  const cumLine = c2
    ? list
        .filter((r) => r.gap_cum_smooth != null)
        .map((r, i) =>
          `${i ? 'L' : 'M'}${x(list.indexOf(r)).toFixed(1)},${y2(r.gap_cum_smooth).toFixed(1)}`)
        .join(' ')
    : ''

  // 부족 구간과 과잉 구간을 따로 칠한다. 한 덩어리로 칠하면 부호가 섞인 해에서
  // 색이 거짓말을 한다.
  //
  // **두 선이 구간 안에서 엇갈리면 교차점에서 띠를 둘로 가른다.** 예전에는 i→i+1
  // 띠를 시작 해(i)의 부호 하나로 칠했다. 서울 2019(+5,945) → 2020(−7,427) 은
  // 준공선이 적정선 위에서 아래로 내려가는데, 꼬인 사각형 하나가 통째로 파랗게
  // 칠해져 2020 쪽 절반이 '더 지음' 으로 보였다. 위 문장을 지키지 못한 것이다.
  //
  // 교차점은 선형 보간이다. 두 선이 직선으로 그려지므로 그 사이 차이(준공 − 적정)도
  // 구간 안에서 직선이고, 0 이 되는 자리가 그림 위 교차점과 정확히 같다. 차이는
  // 백엔드의 `gap_smooth`(= 준공 − 3년평균 적정)를 그대로 써서 색 판정(isShort)과
  // 같은 값에서 나오게 한다. 반올림 탓에 선 위 교차와 1호 안쪽으로 어긋날 수 있으나
  // 그림에서는 안 보인다.
  //
  // 이렇게 가르면 **어느 해든 제 자리의 색이 제 부호다** — 끝 해(적정이 있는 마지막
  // 해, 다음 해는 need_missing)도 왼쪽 구간의 오른쪽 끝이 제 부호로 칠해진다.
  // 그래서 끝 해 오른쪽으로 띠를 따로 늘리지 않는다. 다음 해에는 적정이 없어 늘릴
  // 근거가 없고, 늘리면 없는 비교를 그린 셈이 된다.
  const bands = []
  for (let i = 0; i < list.length - 1; i += 1) {
    const a = list[i]
    const b = list[i + 1]
    if (a.adequate_smooth == null || b.adequate_smooth == null) continue
    const xa = x(i)
    const xb = x(i + 1)
    const quad = (key, short, x0, a0, d0, x1, a1, d1) => ({
      key,
      short,
      d: `M${x0},${y(a0)} L${x1},${y(a1)} L${x1},${y(d1)} L${x0},${y(d0)} Z`,
    })
    if (isShort(a) === isShort(b)) {
      bands.push(quad(a.year, isShort(a), xa, a.adequate_smooth, a.done,
        xb, b.adequate_smooth, b.done))
      continue
    }
    // 부호가 다르니 gap_smooth 둘은 0 이 아니거나(음수 쪽) 서로 다르다 — 분모는 0 이 아니다.
    const t = a.gap_smooth / (a.gap_smooth - b.gap_smooth)
    const xc = xa + t * (xb - xa)
    const ac = a.adequate_smooth + t * (b.adequate_smooth - a.adequate_smooth)
    // 교차점에서는 두 선이 만나므로 왼쪽·오른쪽 조각 모두 그 한 점으로 모인다(삼각형).
    bands.push(quad(a.year, isShort(a), xa, a.adequate_smooth, a.done, xc, ac, ac))
    bands.push(quad(`${a.year}x`, isShort(b), xc, ac, ac, xb, b.adequate_smooth, b.done))
  }

  return (
    <div ref={ref}>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="적정 공급과 준공 비교">
        {bands.map((b) => (
          <path key={b.key} d={b.d} fill={b.short ? 'var(--neg)' : 'var(--good)'}
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
        {/* 키를 값으로 두면 누계가 한 번도 0 밑으로 안 가는 지역에서 lo 도 0 이라 겹친다 */}
        {axis && c2 && [c2.hi, 0, c2.lo].map((v, i) => (
          <text key={`c${i}`} x={W - PAD_R + 6} y={y2(v) + 4} fontSize="10"
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
        {/* 단년 적정 — 옅게. 평균이 어디서 왔는지 보이라고 둔다 */}
        <path d={line('adequate')} fill="none" stroke="var(--series-2)" strokeWidth="1"
              strokeLinejoin="round" opacity="0.35" />
        <path d={line('adequate_smooth')} fill="none" stroke="var(--series-2)"
              strokeWidth="2" strokeLinejoin="round" />
        <path d={line('done')} fill="none" stroke="var(--series-1)" strokeWidth="2"
              strokeLinejoin="round" />
        {/* 집계가 튄 해. 점을 찍어 두고 까닭은 호버와 창에서 말한다 */}
        {list.map((r, i) => (r.growth_odd ? (
          <circle key={`odd-${r.year}`} cx={x(i)} cy={y(r.adequate)} r="3.5"
                  fill="none" stroke="var(--warning)" strokeWidth="2" />
        ) : null))}
        {/* 적정이 없는 해의 준공. 선 끝만으로는 '여기부터 비교가 없다' 가 안 보인다 */}
        {list.map((r, i) => (r.need_missing ? (
          <circle key={`only-${r.year}`} cx={x(i)} cy={y(r.done)} r="3.5"
                  fill="var(--surface-1)" stroke="var(--series-1)" strokeWidth="2" />
        ) : null))}
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
                  {r.need_missing ? (
                    <>
                      <div className="t-row">준공 {fmt(r.done)}호</div>
                      <div className="t-row">
                        가구수·멸실이 아직 공표되지 않아 적정 공급을 못 냅니다
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="t-row">적정(3년평균) {fmt(r.adequate_smooth)}호</div>
                      <div className="t-row">적정(단년) {fmt(r.adequate)}호</div>
                      <div className="t-row">준공 {fmt(r.done)}호</div>
                      <div className="t-row">
                        {(r.gap_smooth ?? r.gap) >= 0 ? '더 지음' : '덜 지음'}{' '}
                        {fmt(Math.abs(r.gap_smooth ?? r.gap))}호
                      </div>
                    </>
                  )}
                  {r.growth_odd && (
                    <div className="t-row">가구 증가가 앞뒤와 크게 어긋난 해입니다</div>
                  )}
                  {r.gap_cum != null && (
                    <div className="t-row">
                      누적 차이 {r.gap_cum_smooth >= 0 ? '+' : '−'}
                      {fmt(Math.abs(r.gap_cum_smooth ?? r.gap_cum))}호
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
          적정 공급(3년평균)
        </span>
        <span className="key">
          <span className="swatch" style={{ background: 'var(--series-1)' }} />
          준공
        </span>
        <span className="key">
          <span className="swatch" style={{ background: 'var(--neg)', opacity: 0.3 }} />
          덜 지은 해
        </span>
        <span className="key">
          <span className="swatch" style={{ background: 'var(--good)', opacity: 0.3 }} />
          더 지은 해
        </span>
        {c2 && (
          <span className="key">
            <span className="swatch dash" style={{ background: 'var(--text-secondary)' }} />
            누적 차이{cumFrom ? ` (${cumFrom}년~, 오른쪽 축)` : ''}
          </span>
        )}
        {partial && (
          <span className="key">
            <span className="swatch dot"
                  style={{ background: 'none', border: '2px solid var(--series-1)' }} />
            준공만 있는 해
          </span>
        )}
      </div>
      {tip.node}
    </div>
  )
}

export function BalanceTable({ r }) {
  return (
    <>
      {/* 창에서는 3년 이동평균까지 셋을 그린다. 축소판은 둘만 — 카드가 답하는
          질문은 '볼 만한가' 하나다(PanelCard 주석). */}
      <GapLines rows={r.rows} height={210} smooth axis cumFrom={r.cum_from} />
      <p className="muted small"><Hint pill wide label="설명">
        적정 공급은 <b>가구 증가 + 멸실</b>입니다. 가구수는 '천' 단위로 공표되어
        1,000을 곱했습니다. 단년 증가분은 집계 기준이 바뀐 해에 튀므로 그림에서는{' '}
        <b>3년 이동평균을 기준선으로</b> 쓰고 단년은 옅게 겹칩니다. 중위 증가의 25%
        에 못 미치는 해를 '튄 해' 로 보아 그림에 테두리만 있는 점으로 표시합니다.
      </Hint></p>
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
              <th className="num">더(+)·덜(−) 단년</th>
              <th className="num">더(+)·덜(−) 3년평균</th>
              <th />
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
                {/* 색은 3년평균 쪽에만 칠한다. 카드 부제·그림이 그 기준이라, 단년에도
                    칠하면 서울 끝 해처럼 부호가 갈리는 해에 붉고 파란 칸이 나란히 선다. */}
                <td className="num muted">
                  {x.gap == null ? '—' : `${x.gap > 0 ? '+' : ''}${fmt(x.gap)}`}
                </td>
                <td className={`num ${x.gap_smooth == null ? '' : isShort(x) ? 'tone-neg' : 'tone-pos'}`}>
                  {x.gap_smooth == null ? '—'
                    : `${x.gap_smooth > 0 ? '+' : ''}${fmt(x.gap_smooth)}`}
                </td>
                <td className="muted">
                  {x.need_missing ? '가구수·멸실 미공표'
                    : x.growth_odd ? '집계 기준 변경으로 보임' : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small"><Hint pill wide label="설명">
        준공은 <b>12개월이 다 있는 해만</b> 셉니다. 올해는 아직 안 끝나서 빠집니다 —
        몇 달 치만 더해 '올해 공급이 급감했다'고 적으면 거짓이 됩니다.
      </Hint></p>
      <NeedEnd r={r} />
    </>
  )
}

/**
 * 적정 공급이 준공보다 **먼저 끝나는** 까닭을 적는다.
 *
 * 준공은 월별로 빨리 나오고 가구수·멸실은 연 단위로 늦게 나온다. 예전 문구는
 * '올해라 빠진다' 고만 해서, 12개월이 다 찬 해가 빠진 진짜 까닭(적정을 낼 재료가
 * 없음)을 말하지 않았다. 연도는 **데이터에서** 읽는다 — 박으면 적재가 따라잡는
 * 순간 문구가 거짓이 된다.
 */
function NeedEnd({ r }) {
  const only = r.rows.filter((x) => x.need_missing).map((x) => x.year)
  if (!only.length || !r.adequate_to) return null
  const span = only.length > 1 ? `${only[0]}~${only[only.length - 1]}년` : `${only[0]}년`
  const src = r.households_to === r.demolish_to
    ? `가구수·멸실은 ${r.households_to}년까지라`
    : `가구수는 ${r.households_to}년, 멸실은 ${r.demolish_to}년까지라`
  return (
    <p className="muted small"><Hint pill wide label="설명">
      {src} 적정 공급도 <b>{r.adequate_to}년까지</b>입니다. {span}은 준공만 있어 점만
      찍고 적정·차이 칸은 비워 둡니다. 누적 차이도 {r.adequate_to}년에서 멈춥니다.
    </Hint></p>
  )
}
