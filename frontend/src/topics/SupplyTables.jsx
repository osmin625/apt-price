import { fmt } from '../components/Charts'

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
      <p className="muted small">
        경기 남부는 수원·용인·화성·안양·오산·의왕·군포·과천 8개 시의 합입니다.
        시 단위는 전체보다 한두 달 늦게 공표됩니다.
      </p>
    </>
  )
}

export function PipeTable({ r }) {
  const rows = r.pipeline.series.done || []
  const find = (k, ym) => (r.pipeline.series[k] || []).find((d) => d.ym === ym)?.value
  return (
    <>
      <p className="muted small">
        12개월 누적입니다. 월별은 큰 단지 하나가 들어오는 달에 튀어서 들쭉날쭉하므로
        누적으로 봐야 추세가 읽힙니다. <b>인허가는 연 누계로 공표</b>되어
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
