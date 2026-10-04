import { useEffect, useState } from 'react'

import { api } from '../api'
import AspectCompass, { AspectCross } from './AspectCompass'
import { fmt } from './Charts'
import Modal from './Modal'
import PanelCard from './PanelCard'

/**
 * 향에 따른 가격.
 *
 * ## 보정계수와 **따로** 둔다
 *
 * 요인별 보정계수는 전부 **실거래**에서 추정한 값이다. 향은 국토교통부 실거래에 없어
 * 그 틈에 끼울 수 없다(필드 32개를 떠서 확인했다). 같은 격자에 넣으면 근거가 다른
 * 숫자가 같은 무게로 읽힌다 — 이 저장소가 '추정을 사실처럼 보여 주지 않는다' 로
 * 지켜 온 선이다. 그래서 제목 옆에 `호가 기준` 이라고 적는다.
 *
 * ## 카드로 접고, 자세한 것은 창으로
 *
 * 매크로 탭과 같은 모양이다(`PanelCard`). 카드가 답할 질문은 **'어느 쪽이 비싼가'**
 * 하나이고, '얼마나 확실한가'·'몇 건인가'·'남향이 서향보다 비싼가' 는 눌러서 묻는다.
 * 표와 경고를 카드에 늘어놓으니 정작 그림이 안 보였다.
 */
export default function AspectPanel({ months }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    setErr(null)
    setData(null)
    api
      .aspect({ months })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setErr(e.message))
    return () => {
      alive = false
    }
  }, [months])

  if (err || !data) return null // 곁가지다. 못 읽어도 탭 전체를 막지 않는다.

  if (data.empty) {
    return (
      <p className="empty">
        아직 향이 기록된 매물이 없습니다. <b>매물 관리</b> 탭에서 붙여넣으면 쌓입니다.
      </p>
    )
  }

  // 카드 한 줄 요약. 가장 비싼 쪽과 '가를 수 있나' 만 말한다.
  const solid = data.groups.filter((g) => !g.thin)
  const top = solid.length ? solid.reduce((a, b) => (a.vs_cell >= b.vs_cell ? a : b)) : null
  const sub = top
    ? `${top.label}이 가장 비싸게 — ${top.vs_cell > 0 ? '+' : ''}${fmt(top.vs_cell, 2)}%p · ${
        data.detected ? '가름' : `아직 못 가름 (한계 ±${fmt(data.floor_pct, 2)}%p)`
      }`
    : '자료가 모자랍니다'

  return (
    <>
      <PanelCard title="향에 따른 가격" sub={sub} onOpen={() => setOpen(true)}>
        <AspectCross groups={data.groups} />
      </PanelCard>

      {open && (
        <Modal title="향에 따른 가격" onClose={() => setOpen(false)} wide>
          <p className="muted small">
            국토교통부 실거래에는 <b>향이 없습니다</b>(필드 32개를 떠서 확인했습니다).
            향이 적힌 자료는 붙여넣은 매물뿐이라 이 분석만 <b>호가</b>로 합니다 — 받고
            싶은 값이지 받은 값이 아닙니다.
          </p>

          <AspectCompass groups={data.groups} />

          <p className="muted small ac-legend">
            점선 원이 <b>그 단지·평형의 보통 호가</b>입니다. 바깥이면 더 비싸게, 안쪽이면
            싸게 부른다는 뜻이고 눈금 간격은 1%p.
            <br />
            가로지르는 선은 <b>95% 구간</b>입니다 — 그 선이 점선 원을 넘나들면{' '}
            <b>아직 가를 수 없다</b>는 뜻입니다.
          </p>

          {!data.detected && (
            <p className="paste-warn">
              <b>아직 잡히지 않았습니다.</b>{' '}
              {data.floor_pct != null ? (
                <>
                  지금 표본으로 잡을 수 있는 가장 작은 차이가{' '}
                  <b>±{fmt(data.floor_pct, 2)}%p</b> 인데 아래 값들이 전부 그 안에 있습니다.
                  향 차이가 없다는 뜻이 아니라 <b>이 표본으로는 잡음과 구분되지 않는다</b>는
                  뜻입니다.
                </>
              ) : (
                <>향이 둘 이상 섞인 칸이 {fmt(data.n_cells)}개뿐이라 구간을 낼 수 없습니다.</>
              )}
              {data.complexes_needed > 0 && (
                <>
                  {' '}
                  ±{fmt(data.target_floor_pct, 0)}%p 까지 좁히려면 칸이 약{' '}
                  <b>{fmt(data.cells_needed)}개</b> 필요하고, 그건{' '}
                  <b>단지 약 {fmt(data.complexes_needed)}곳</b>입니다(지금{' '}
                  {fmt(data.n_complexes_mixed)}곳). <b>같은 단지에서 더 담는 것보다 단지를
                  더 도는 쪽</b>이 빠릅니다.
                </>
              )}
            </p>
          )}

          <h3 className="mt16">방향별</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>향</th>
                  <th className="num">보통 호가 대비</th>
                  <th className="num">95% 구간</th>
                  <th className="num">칸</th>
                  <th className="num">매물</th>
                </tr>
              </thead>
              <tbody>
                {data.groups.map((g) => (
                  <tr key={g.group} className={g.thin ? 'is-muted' : undefined}>
                    <td>{g.label}</td>
                    <td className="num">
                      {g.vs_cell > 0 ? '+' : ''}
                      {fmt(g.vs_cell, 2)}%p
                    </td>
                    <td className="num muted">
                      {g.lo == null
                        ? '자료 부족'
                        : `${g.lo > 0 ? '+' : ''}${fmt(g.lo, 2)} ~ ${g.hi > 0 ? '+' : ''}${fmt(g.hi, 2)}`}
                    </td>
                    <td className="num">{fmt(g.cells)}</td>
                    <td className="num">{fmt(g.n)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.pairs?.length > 0 && (
            <>
              <h3 className="mt16">둘을 직접 견주면</h3>
              <p className="muted small">
                위 표는 각 방향을 <b>칸 중위와</b> 견준 것이라 두 방향끼리는 못 견줍니다.
                여기서는 두 향이 <b>같은 칸에 함께 있을 때만</b> 골라 뺐습니다.
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>비교</th>
                      <th className="num">차이</th>
                      <th className="num">95% 구간</th>
                      <th className="num">칸</th>
                      <th>판정</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pairs.map((p) => (
                      <tr key={`${p.a}${p.b}`}>
                        <td>{p.label}</td>
                        <td className="num">
                          {p.diff == null ? '—' : `${p.diff > 0 ? '+' : ''}${fmt(p.diff, 2)}%p`}
                        </td>
                        <td className="num muted">
                          {p.lo == null
                            ? '—'
                            : `${p.lo > 0 ? '+' : ''}${fmt(p.lo, 2)} ~ ${p.hi > 0 ? '+' : ''}${fmt(p.hi, 2)}`}
                        </td>
                        <td className="num">{fmt(p.cells)}</td>
                        <td>
                          <span className="verdict" data-tone={p.sig ? 'good' : 'mid'}>
                            {p.sig ? '가름' : '못 가름'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <p className="muted small mt16">
            호가를 <b>같은 단지·같은 평형의 실거래로 낸 적정가</b>와 견주고, 그 차이를 같은
            (단지·평형) 칸 안에서만 비교합니다. 칸을 넘어 비교하면 단지 차이가 향 차이로
            둔갑합니다 — 실제로 그래서 한 번 뒤집혔습니다. 향이 적힌 매물{' '}
            <b>{fmt(data.n_quotes)}건</b> 중 적정가를 낼 수 있는 {fmt(data.n_scored)}건을
            썼고, 향이 둘 이상 섞인 칸은 {fmt(data.n_cells)}개입니다.
          </p>
        </Modal>
      )}
    </>
  )
}
