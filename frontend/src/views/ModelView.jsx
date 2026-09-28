import { useEffect, useState } from 'react'

import { api } from '../api'
import { Tile, fmt } from '../components/Charts'
import CoefTable from '../components/CoefTable'
import CoefUsage from '../components/CoefUsage'
import FitLoading from '../components/FitLoading'
import ScatterFit from '../components/ScatterFit'

export default function ModelView({ months, onSelect }) {
  const [fit, setFit] = useState(null)
  const [map, setMap] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setError(null)
    setFit(null)
    Promise.all([api.modelFit({ months }), api.mapComplexes({ months })])
      .then(([f, m]) => {
        if (!alive) return
        setFit(f)
        setMap(m)
      })
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [months])

  if (error) return <div className="card empty">{error}</div>
  if (!fit)
    return (
      <div className="card">
        <FitLoading months={months} what="분해 모델을" />
      </div>
    )

  const curve = fit.curves.walk_minutes
  const points = (map?.items || []).map((i) => ({
    id: i.id,
    name: i.name,
    walk_min: i.walk_min,
    value: i.partial_pct,
    sub: `${i.station_name ?? '—'} · 거래 ${i.trade_count}건`,
  }))

  const residuals = [...(map?.items || [])]
    .filter((i) => i.residual_shrunk_pct != null)
    .sort((a, b) => a.residual_shrunk_pct - b.residual_shrunk_pct)

  return (
    <>
      {fit.synthetic && (
        <div className="notice">
          <strong>합성 데이터입니다.</strong> 아래 점선은 시드가 심어 둔 <b>참값</b>이고,
          실선은 모델이 데이터만 보고 추정한 곡선입니다. 둘이 겹칠수록 추정이 잘 된 것입니다.
          실거래가를 적재하면 점선은 사라집니다.
        </div>
      )}

      <CoefUsage />

      <div className="card">
        <h2>통제를 늘려가면 계수가 어떻게 변하는가</h2>
        <p className="muted">
          통제 변수를 하나씩 더하며 같은 모델을 다시 적합한 결과입니다. 계수가 스펙에 따라
          얼마나 움직이는지가 곧 <b>그 추정치를 얼마나 믿을 수 있는지</b>입니다.
          M0·M1은 입지가 좋은 동네일수록 역도 가깝다는 교란이 섞여 있고, M2는 구 단위까지
          통제해 그걸 걷어냅니다. M3은 <b>같은 법정동 안에서 역에 더 가까운 단지끼리만</b>{' '}
          비교한 값이라 학군·상권 교란이 사라지는 대신 표본이 적은 동에서 불안정해집니다.
          헤드라인은 균형점인 M2이지만, 둘을 같이 보는 것이 맞습니다.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>스펙</th>
                <th>통제 변수</th>
                <th className="num">도보 1분당</th>
                <th className="num">SE</th>
                <th className="num">R²</th>
                <th>유의</th>
              </tr>
            </thead>
            <tbody>
              {fit.spec_ladder.map((s) => (
                <tr key={s.spec} className={s.spec === fit.spec ? 'is-current' : ''}>
                  <td>
                    <b>{s.spec}</b>
                    {s.spec === fit.spec ? ' ★' : ''}
                  </td>
                  <td>{s.label}</td>
                  {s.identified === false ? (
                    <td className="muted" colSpan={4}>
                      {s.note}
                    </td>
                  ) : (
                    <>
                      <td className="num">{fmt(s.walk_pct, 2)}%</td>
                      <td className="num">{fmt(s.se, 5)}</td>
                      <td className="num">{fmt(s.r2, 3)}</td>
                      <td>
                        <span className={`badge ${s.significant ? 'good' : ''}`}>
                          {s.significant ? '유의' : '비유의'}
                        </span>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>계수</h2>
          <p className="muted small">{fit.dep_var} · 기준 {fit.stage1.reference}</p>
          <CoefTable fit={fit} />
          <p className="muted small">
            월 상승률 {fmt(fit.stage1.month_trend_pct, 3)}%/월 · Stage1 within-R²{' '}
            {fmt(fit.stage1.within_r2, 3)}
          </p>
        </div>

      </div>

      <GroupCompare months={months} />

        <div className="card">
          <h2>진단</h2>
          <ul className="muted">
            {fit.diagnostics.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}

function GroupCompare({ months }) {
  const [by, setBy] = useState('line')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setError(null)
    api
      .groups({ months, by })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [months, by])

  if (error) return <div className="card empty">{error}</div>

  return (
    <div className="card">
      <h2>노선·생활권으로 묶어 보기</h2>
      <p className="muted">
        비교에 쓰는 값은 원자료 평당가가 아니라 <b>보정 평당가</b>(전용 84㎡·중층·최신월
        환산)입니다. 면적·층·시점 구성이 제거돼 있어야 그룹 간 비교가 성립합니다.{' '}
        <b>잔차</b>는 도보거리·연식·면적·층·구를 모두 통제한 뒤에도 남는 차이라, 모델에
        없는 무언가(노선 가치, 신도시 계획, 학군)의 크기를 나타냅니다.
      </p>

      <div className="seg" role="tablist" aria-label="묶는 기준">
        {(data?.options || []).map((o) => (
          <button
            key={o.key}
            role="tab"
            aria-selected={by === o.key}
            onClick={() => setBy(o.key)}
          >
            {o.label}
          </button>
        ))}
      </div>

      {by === 'line_umd' && (
        <p className="muted small" style={{ marginTop: 8 }}>
          같은 법정동에 두 노선이 걸치는 경우가 있습니다. 수원 원천동이 그렇고, 신분당선
          쪽과 수인분당선 쪽의 보정 평당가가 2배 차이납니다 — <b>구 FE로도 법정동 FE로도
          구분되지 않는 차이</b>라 노선을 함께 묶습니다.
        </p>
      )}

      {!data ? (
        <div className="empty">불러오는 중…</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{data.label}</th>
                <th className="num">단지</th>
                <th className="num">거래</th>
                <th className="num">보정 평당가</th>
                <th className="num">중간 50%</th>
                <th className="num">모델 잔차</th>
                <th className="num">도보</th>
                <th className="num">연식</th>
                <th className="num">강남</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((g) => (
                <tr key={g.group}>
                  <td>{g.group}</td>
                  <td className="num">{g.complex_count}</td>
                  <td className="num muted">{fmt(g.trade_count)}</td>
                  <td className="num">
                    <b>{fmt(g.normalized_ppp)}</b>
                  </td>
                  <td className="num muted">
                    {fmt(g.p25)} ~ {fmt(g.p75)}
                  </td>
                  <td className={`num ${g.residual_pct > 0 ? 'tone-neg' : 'tone-pos'}`}>
                    {g.residual_pct > 0 ? '+' : ''}
                    {fmt(g.residual_pct, 1)}%
                  </td>
                  <td className="num muted">{fmt(g.walk_min, 1)}분</td>
                  <td className="num muted">{fmt(g.age, 0)}년</td>
                  <td className="num muted">
                    {g.gangnam_min == null ? '—' : `${g.gangnam_min}분`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
