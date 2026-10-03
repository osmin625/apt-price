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

/* 단지 안의 동 — **버튼 하나씩만.**
 *
 * 처음에는 동마다 역까지 도보시간·거리·동 효과를 표로 깔았다. 30개 동이면 표가
 * 화면을 반쯤 먹는데, 여기서 실제로 하는 일은 '민간임대인 동을 골라 두는 것'
 * 하나다. 읽을 일이 없는 숫자로 자리를 채우지 않는다.
 *
 * 거리는 지우지 않고 버튼의 `title` 로 내렸다 — 궁금하면 올려 보면 되고, 평소에는
 * 보이지 않는다.
 *
 * ## 민간임대를 왜 표시하나
 *
 * 민간임대 동은 분양 물건과 성격이 달라 같은 단지·같은 평형이어도 시세가 다른데,
 * 국토부 실거래가에는 그 구분이 없다. 한 번 눌러 두면 매물 순위의 비고에 자동으로
 * 따라붙는다(파생이라 끄면 같이 사라진다 — docs/design.md 참조).
 */
function DongPanel({ complexId, data, onChange }) {
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  /* 먼저 화면을 바꾸고 서버를 부른다. 버튼이 한 박자 늦게 움직이면 눌렸는지 알 수 없다.
   *
   * **함수형 갱신을 쓴다.** 예전에는 렌더 시점의 `data` 로 다음 상태를 만들었는데,
   * 그러면 연달아 누를 때 뒤의 것이 앞의 것을 덮는다. 실측으로 잡았다 — 107·119·130
   * 을 연속으로 누르자 서버에는 셋 다 들어갔는데 화면에는 130 만 켜졌다. 사람 손으로는
   * 사이에 렌더가 끼어 잘 안 드러나지만, 드러날 때는 '눌렀는데 안 켜진다' 로 보인다.
   *
   * 되돌릴 때도 마찬가지다. 통째로 복원하면 그 사이 켜 둔 다른 동까지 되돌아간다.
   * 실패한 동 하나만 되돌린다. */
  const patch = (dong, rental) => (d) =>
    d
      ? {
          ...d,
          items: d.items.map((i) => (i.dong === dong ? { ...i, rental } : i)),
          rental_dongs: rental
            ? [...new Set([...d.rental_dongs, dong])].sort()
            : d.rental_dongs.filter((x) => x !== dong),
        }
      : d

  const toggle = async (dong, next) => {
    setBusy(dong)
    setErr(null)
    onChange(patch(dong, next))
    try {
      await api.setDongRental(complexId, dong, next)
    } catch (e) {
      onChange(patch(dong, !next))
      setErr(`${dong}동 표시를 저장하지 못했습니다.`)
    } finally {
      setBusy(null)
    }
  }

  const marked = data.rental_dongs.length

  return (
    <section className="card">
      <h2>
        동<span className="muted small"> {data.items.length}개</span>
      </h2>
      <p className="sub">
        누르면 <b>민간임대</b>로 표시됩니다. 표시한 동의 매물은 매물 순위의 비고에
        자동으로 따라붙습니다.
      </p>
      {err && <p className="paste-warn">{err}</p>}

      <div className="dong-chips">
        {data.items.map((i) => (
          <button
            key={i.dong}
            className={`dong-chip${i.rental ? ' is-rental' : ''}`}
            aria-pressed={!!i.rental}
            disabled={busy === i.dong}
            onClick={() => toggle(i.dong, !i.rental)}
            title={
              i.walk_min != null
                ? `역까지 도보 ${fmt(i.walk_min, 1)}분${
                    i.walk_distance_m ? ` · ${fmt(i.walk_distance_m)}m` : ''
                  }`
                : '동별 좌표 없음'
            }
          >
            {i.dong}
          </button>
        ))}
      </div>

      <p className="muted small" style={{ marginTop: 10 }}>
        {marked > 0 ? (
          <>
            민간임대 <b>{data.rental_dongs.join(' · ')}</b> — 다시 누르면 해제됩니다.
          </>
        ) : (
          '아직 표시한 동이 없습니다. 동 번호에 마우스를 올리면 역까지 도보시간이 보입니다.'
        )}
      </p>
    </section>
  )
}
