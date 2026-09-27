import { useEffect, useState } from 'react'

import { FilterBar } from '../App'
import { api } from '../api'
import { fmt } from '../components/Charts'
import Loading from '../components/Loading'

const SORTS = [
  { id: 'ppp_desc', label: '평당가 높은 순' },
  { id: 'ppp_asc', label: '평당가 낮은 순' },
  { id: 'trades_desc', label: '거래 많은 순' },
  { id: 'name', label: '단지명 순' },
]

export default function ComplexesView({ filters, setFilters, meta, onSelect }) {
  const [rows, setRows] = useState([])
  // 서버는 상위 `limit` 개만 돌려주고 전체 개수는 따로 알려 준다.
  // 대상 지역을 경기 남부로 넓히며 단지가 2,469곳이 됐는데, 그중 200곳만
  // 말없이 보여 주면 목록이 전부인 줄 알게 된다.
  const [total, setTotal] = useState(0)
  const [limit, setLimit] = useState(200)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('ppp_desc')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const timer = setTimeout(() => {
      api
        .complexes({ ...filters, q, sort, limit })
        .then((d) => {
          setRows(d.items)
          setTotal(d.count ?? d.items.length)
        })
        .catch(() => {
          setRows([])
          setTotal(0)
        })
        .finally(() => setLoading(false))
    }, 250)
    return () => clearTimeout(timer)
  }, [filters, q, sort, limit])

  return (
    <>
      <div className="card">
        <FilterBar
          filters={filters}
          setFilters={setFilters}
          meta={meta}
          extra={
            <>
              <div className="field">
                <label htmlFor="f-q">단지명 검색</label>
                <input
                  id="f-q"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="예: 광교"
                />
              </div>
              <div className="field">
                <label htmlFor="f-sort">정렬</label>
                <select id="f-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
                  {SORTS.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            </>
          }
        />
      </div>

      <section className="card">
        <h2>단지별 전용 평당가 비교</h2>
        <p className="sub">
          행을 클릭하면 평형별·층별 상세를 볼 수 있습니다 · 단위 만원/평 (전용면적 기준)
        </p>
        {total > rows.length && (
          <p className="muted small" style={{ margin: '0 0 8px' }}>
            조건에 맞는 단지 {fmt(total)}곳 중 <b>{fmt(rows.length)}곳</b>만 보고 있습니다.{' '}
            <button className="ghost" onClick={() => setLimit((n) => Math.min(n + 300, 1000))}>
              더 보기
            </button>
          </p>
        )}

        {loading ? (
          <Loading label="단지를 불러오는 중" />
        ) : rows.length === 0 ? (
          <p className="empty">조건에 맞는 단지가 없습니다.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>단지</th>
                  <th>법정동</th>
                  <th className="num">준공</th>
                  <th>컨디션</th>
                  <th>가까운 역</th>
                  <th className="num">거리</th>
                  <th>입지 등급</th>
                  <th className="num">세대수</th>
                  <th className="num">중앙 평당가</th>
                  <th className="num">중간 50%</th>
                  <th className="num">거래</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="clickable" onClick={() => onSelect(r.id)}>
                    <td style={{ fontWeight: 600 }}>{r.name}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>{r.umd_nm}</td>
                    <td className="num">{r.build_year ?? '—'}</td>
                    <td>
                      <span className="badge">{r.age_band}</span>
                    </td>
                    <td>
                      {r.station_name ?? '—'}
                      {r.station_line && (
                        <span style={{ color: 'var(--text-muted)', fontSize: 11.5 }}>
                          {' '}
                          {r.station_line}
                        </span>
                      )}
                    </td>
                    <td className="num">
                      {r.station_distance_m ? `${fmt(r.station_distance_m)}m` : '—'}
                      {r.walk_minutes && (
                        <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                          도보 {r.walk_minutes}분
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="badge">{r.station_band}</span>
                    </td>
                    <td className="num">
                      {r.household_count ? fmt(r.household_count) : '—'}
                      {r.household_count && (
                        <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                          {r.household_band?.split('(')[0]}
                        </div>
                      )}
                    </td>
                    <td className="num" style={{ fontWeight: 600 }}>
                      {fmt(r.ppp?.median)}
                    </td>
                    <td className="num" style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                      {fmt(r.ppp?.p25)}~{fmt(r.ppp?.p75)}
                    </td>
                    <td className="num">{r.trade_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
