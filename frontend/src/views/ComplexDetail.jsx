import { useEffect, useState } from 'react'

import { api } from '../api'
import { RangeDotChart, fmt } from '../components/Charts'
import Loading from '../components/Loading'

export default function ComplexDetail({ complexId, months, onClose }) {
  const [data, setData] = useState(null)
  const [openType, setOpenType] = useState(null)
  const [dongs, setDongs] = useState(null)

  useEffect(() => {
    setData(null)
    api.complex(complexId, { months }).then(setData).catch(() => setData(null))
  }, [complexId, months])

  // 동 정보는 따로 받는다. 적합이 있으면 동별 프리미엄까지 오고, 없으면 거리만 온다.
  useEffect(() => {
    setDongs(null)
    api.dongs(complexId).then(setDongs).catch(() => setDongs(null))
  }, [complexId])

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

      {dongs && dongs.items.length > 0 && <DongPanel complexId={complexId} data={dongs} onChange={setDongs} />}

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


/* 단지 안의 동.
 *
 * 같은 단지라도 동에 따라 역까지 100~330m 차이난다. 그 차이가 가격에 얼마나
 * 들어가는지는 적합이 있을 때만 알 수 있으므로, 없으면 거리만 보여 준다.
 *
 * ## 민간임대 표시
 *
 * 민간임대 동은 분양 물건과 성격이 달라 같은 평형이어도 시세가 다른데, 국토부
 * 실거래가에는 그 구분이 없다. 그래서 사람이 한 번 표시해 두면 매물 순위의 비고에
 * 자동으로 따라붙는다.
 *
 * 표시는 `dong_tags` 에 따로 저장한다. `complex_dongs` 는 적재로 다시 채워지는
 * 테이블이라 거기 섞으면 적재 한 번에 조용히 날아간다.
 */
function DongPanel({ complexId, data, onChange }) {
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const toggle = async (dong, next) => {
    setBusy(dong)
    setErr(null)
    // 먼저 화면을 바꾸고 서버를 부른다. 실패하면 되돌린다 — 체크박스가 한 박자
    // 늦게 움직이면 눌렸는지 알 수 없다.
    const before = data
    onChange({
      ...data,
      items: data.items.map((i) => (i.dong === dong ? { ...i, rental: next } : i)),
      rental_dongs: next
        ? [...data.rental_dongs, dong].sort()
        : data.rental_dongs.filter((d) => d !== dong),
    })
    try {
      await api.setDongRental(complexId, dong, next)
    } catch (e) {
      onChange(before)
      setErr(`${dong}동 표시를 저장하지 못했습니다.`)
    } finally {
      setBusy(null)
    }
  }

  const hasPrem = data.items.some((i) => i.premium_pct != null)

  return (
    <section className="card">
      <h2>
        동 정보
        <span className="muted small"> {data.items.length}개 동</span>
      </h2>
      <p className="sub">
        같은 단지라도 동에 따라 역까지 거리가 다릅니다
        {data.spread_min != null && <> — 이 단지는 <b>{data.spread_min}분</b> 차이납니다</>}.
        민간임대 동을 표시해 두면 <b>매물 순위의 비고</b>에 자동으로 따라붙습니다.
      </p>
      {err && <p className="paste-warn">{err}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>동</th>
              <th className="num">역까지 도보</th>
              <th className="num">거리</th>
              {hasPrem && <th className="num">동 효과</th>}
              <th>민간임대</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((i) => (
              <tr key={i.dong} className={i.rental ? 'is-rental' : ''}>
                <td>
                  <b>{i.dong}</b>
                </td>
                <td className="num">
                  {i.walk_min == null ? (
                    <span className="muted">—</span>
                  ) : (
                    `${fmt(i.walk_min, 1)}분`
                  )}
                </td>
                <td className="num muted small">
                  {i.walk_distance_m == null ? '—' : `${fmt(i.walk_distance_m)}m`}
                </td>
                {hasPrem && (
                  <td className="num muted small">
                    {i.premium_pct == null
                      ? '—'
                      : `${i.premium_pct > 0 ? '+' : ''}${fmt(i.premium_pct, 1)}%`}
                  </td>
                )}
                <td>
                  <label className="rental-check">
                    <input
                      type="checkbox"
                      checked={!!i.rental}
                      disabled={busy === i.dong}
                      onChange={(e) => toggle(i.dong, e.target.checked)}
                    />
                    {i.rental && <span className="note-tag">민간임대</span>}
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.items.every((i) => i.walk_min == null) && (
        <p className="muted small" style={{ marginTop: 8 }}>
          이 단지는 동별 좌표를 잡지 못해 거리를 비울 수밖에 없습니다. 민간임대 표시는
          그대로 쓸 수 있습니다.
        </p>
      )}
    </section>
  )
}
