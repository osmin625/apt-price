import { useEffect, useState } from 'react'

import { api } from '../api'
import { RangeDotChart, fmt } from '../components/Charts'
import Loading from '../components/Loading'

export default function ComplexDetail({ complexId, months, onClose }) {
  const [data, setData] = useState(null)
  const [openType, setOpenType] = useState(null)

  useEffect(() => {
    setData(null)
    api.complex(complexId, { months }).then(setData).catch(() => setData(null))
  }, [complexId, months])

  if (!data) return <Loading label="단지 상세를 불러오는 중" compact />

  const cx = data.complex

  return (
    <>
      <div className="card">
        <button className="ghost" onClick={onClose} style={{ marginBottom: 12 }}>
          ← 목록으로
        </button>
        <h2 style={{ fontSize: 18 }}>{cx.name}</h2>
        <p className="sub">
          {cx.sgg_name} {cx.umd_nm} · {cx.build_year ?? '—'}년 준공 · 최고 {cx.max_floor ?? '—'}층
        </p>

        <div className="tiles">
          <div className="tile">
            <div className="label">전용 중앙 평당가</div>
            <div className="value">
              {fmt(cx.ppp?.median)}
              <span className="unit">만원/평</span>
            </div>
            <div className="note">최근 {data.months}개월 · {data.trade_count}건</div>
          </div>
          <div className="tile">
            <div className="label">입지</div>
            <div className="value" style={{ fontSize: 18 }}>
              {cx.station_name ?? '정보 없음'}
            </div>
            <div className="note">
              {cx.station_distance_m
                ? `${fmt(cx.station_distance_m)}m · 도보 ${cx.walk_minutes}분 · ${cx.station_band}`
                : '역 정보 없음'}
            </div>
          </div>
          <div className="tile">
            <div className="label">매물 컨디션</div>
            <div className="value" style={{ fontSize: 18 }}>
              {cx.age_band}
            </div>
            <div className="note">{cx.build_year ?? '—'}년 준공</div>
          </div>
        </div>
      </div>

      <section className="card">
        <h2>층별 전용 평당가</h2>
        <p className="sub">이 단지 안에서의 층 구간별 분포</p>
        <RangeDotChart rows={data.by_floor} />
      </section>

      <section className="card">
        <h2>평형(전용면적 타입)별 평당가</h2>
        <p className="sub">행을 클릭하면 해당 평형의 층별 분포가 펼쳐집니다</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>전용면적</th>
                <th className="num">평</th>
                <th>면적대</th>
                <th className="num">중앙 평당가</th>
                <th className="num">중간 50%</th>
                <th className="num">거래</th>
              </tr>
            </thead>
            <tbody>
              {data.by_area_type.map((t) => (
                <FragmentRow
                  key={t.exclusive_area}
                  type={t}
                  open={openType === t.exclusive_area}
                  onToggle={() =>
                    setOpenType(openType === t.exclusive_area ? null : t.exclusive_area)
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>실거래 내역</h2>
        <p className="sub">
          시점 보정가는 과거 거래를 최신 월 시세 수준으로 환산한 값입니다 · 단위 만원
        </p>
        <div className="table-wrap" style={{ maxHeight: 420, overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>계약일</th>
                <th className="num">전용면적</th>
                <th className="num">층</th>
                <th>층 구간</th>
                <th className="num">거래금액</th>
                <th className="num">평당가</th>
                <th className="num">시점 보정가</th>
              </tr>
            </thead>
            <tbody>
              {data.trades.map((t, i) => (
                <tr key={i}>
                  <td>{t.deal_date}</td>
                  <td className="num">
                    {t.exclusive_area}㎡
                    <span style={{ color: 'var(--text-muted)' }}> ({t.pyeong}평)</span>
                  </td>
                  <td className="num">{t.floor}</td>
                  <td>
                    <span className="badge">{t.floor_band}</span>
                  </td>
                  <td className="num">{fmt(t.deal_amount)}</td>
                  <td className="num">{fmt(t.ppp)}</td>
                  <td className="num" style={{ color: 'var(--text-secondary)' }}>
                    {fmt(t.adjusted_ppp)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function FragmentRow({ type, open, onToggle }) {
  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td style={{ fontWeight: 600 }}>
          {open ? '▾' : '▸'} {type.exclusive_area}㎡
        </td>
        <td className="num">{type.pyeong}</td>
        <td>
          <span className="badge">{type.area_band}</span>
        </td>
        <td className="num" style={{ fontWeight: 600 }}>
          {fmt(type.stats?.median)}
        </td>
        <td className="num" style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
          {fmt(type.stats?.p25)}~{fmt(type.stats?.p75)}
        </td>
        <td className="num">{type.stats?.count}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} style={{ background: 'var(--page)' }}>
            <div style={{ padding: '10px 4px' }}>
              <RangeDotChart
                rows={type.by_floor}
                emptyText="이 평형은 층별로 나눌 만큼 표본이 없습니다"
              />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
