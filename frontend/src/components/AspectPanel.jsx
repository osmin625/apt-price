import { useEffect, useState } from 'react'

import { api } from '../api'
import AspectCompass from './AspectCompass'
import { fmt } from './Charts'
import Hint from './Hint'

/**
 * 향에 따른 가격.
 *
 * ## 보정계수와 **따로** 둔다
 *
 * 요인별 보정계수는 전부 **실거래**에서 추정한 값이다. 향은 국토교통부 실거래에 없어
 * 그 틈에 끼울 수 없다. 같은 격자에 넣으면 근거가 다른 숫자가 같은 무게로 읽힌다 —
 * 이 저장소가 '추정을 사실처럼 보여 주지 않는다' 로 지켜 온 선이다.
 *
 * 그래서 카드를 따로 두고, 무엇으로 잰 값인지 제목 옆에 적는다.
 *
 * ## 단지를 넘어서 비교하지 않는다
 *
 * 처음에는 향 무리별 괴리율 중위를 그냥 냈다가 '서향이 제일 비싸다'(+14.3%p)를 봤다.
 * 서향 25건 중 18건이 한 단지였고 그 단지의 호가가 전반적으로 높았던 것이다. 같은
 * (단지·평형) 칸 안에서 비교하니 방향이 뒤집혔다. 그래서 칸 안에서만 비교한다.
 */
export default function AspectPanel({ months }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

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

  if (err) return null // 곁가지다. 못 읽어도 탭 전체를 막지 않는다.
  if (!data) return null

  return (
    <section className="card">
      <h2>
        향에 따른 가격
        <span className="muted small"> 호가 기준</span>
        <Hint
          notes={[
            '국토교통부 실거래에는 향이 없습니다. 그래서 이 분석만 붙여넣은 매물(호가)로 합니다 — 받고 싶은 값이지 받은 값이 아닙니다.',
            '같은 (단지·평형) 칸 안에서만 비교합니다. 칸을 넘어 비교하면 단지 차이가 향 차이로 둔갑합니다.',
            '향은 네 무리로 묶습니다. 두 글자면 나쁜 쪽을 남깁니다 — 남서향은 서향, 북동향은 북향입니다.',
          ]}
        />
      </h2>

      {data.empty ? (
        <p className="empty">
          아직 향이 기록된 매물이 없습니다. <b>매물 관리</b> 탭에서 붙여넣으면 쌓입니다.
          <br />
          <span className="muted small">
            향은 최근에 읽기 시작했습니다. 전에 넣어 둔 매물은 같은 목록을 다시
            붙여넣으면 채워집니다.
          </span>
        </p>
      ) : (
        <>
          <p className="sub">
            호가를 <b>같은 단지·같은 평형의 실거래로 낸 적정가</b>와 견주고, 그 차이를
            같은 <b>(단지·평형) 칸 안에서만</b> 비교합니다. 칸을 넘어 비교하면 단지
            차이가 향 차이로 둔갑합니다 — 실제로 그래서 한 번 뒤집혔습니다.
          </p>

          {/* 검출되지 않았으면 **막대를 그리지 않는다.** 0 근처 막대 셋을 그리면
              '향은 가격과 무관' 으로 읽히는데, 실제로는 '이 표본으로는 잴 수 없다' 다.
              동 위치 카드를 뺀 이유와 같은 자리다. */}
          {/* 그림을 먼저. 숫자와 경고보다 모양이 먼저 들어와야 '남쪽이 조금 볼록하다'
              가 한눈에 읽힌다. */}
          <AspectCompass groups={data.groups} />

          {!data.detected && (
            <p className="paste-warn">
              <b>아직 잡히지 않았습니다.</b>{' '}
              {data.floor_pct != null ? (
                <>
                  지금 표본으로 잡을 수 있는 가장 작은 차이가 <b>±{fmt(data.floor_pct, 2)}%p</b>{' '}
                  인데, 아래 값들이 전부 그 안에 있습니다. 향 차이가 없다는 뜻이 아니라{' '}
                  <b>이 표본으로는 잡음과 구분되지 않는다</b>는 뜻입니다.
                </>
              ) : (
                <>
                  향이 둘 이상 섞인 (단지·평형) 칸이 {fmt(data.n_cells)}개뿐이라 구간을
                  낼 수 없습니다.
                </>
              )}
              {data.complexes_needed > 0 && (
                <>
                  {' '}
                  ±{fmt(data.target_floor_pct, 0)}%p 까지 좁히려면 칸이 약{' '}
                  <b>{fmt(data.cells_needed)}개</b> 필요하고, 그건{' '}
                  <b>단지 약 {fmt(data.complexes_needed)}곳</b>에 해당합니다 — 지금은{' '}
                  {fmt(data.n_complexes_mixed)}곳입니다.{' '}
                  <b>같은 단지에서 더 담는 것보다 단지를 더 도는 쪽</b>이 빠릅니다
                  (한 단지가 칸 하나쯤을 보탭니다).
                </>
              )}
            </p>
          )}

          {/* 막대는 **잡혔을 때만** 그린다. 0 근처 막대 셋을 그리면 '향은 가격과
              무관' 으로 읽히는데, 실제로는 '이 표본으로는 잴 수 없다' 다. 대신
              아래 표로 지금 값과 구간을 같이 보여 준다 — 숨기지는 않는다. */}
          {data.detected ? (
            <div className="aspect-bars">
              {data.groups.map((g) => (
                <div className="ab-row" key={g.group}>
                  <span className="ab-label">{g.label}</span>
                  <span className="ab-track">
                    <i className="ab-zero" />
                    <i
                      className={`ab-fill ${g.vs_cell < 0 ? 'neg' : 'pos'}`}
                      style={{
                        width: `${Math.min(Math.abs(g.vs_cell) * 8, 50)}%`,
                        [g.vs_cell < 0 ? 'right' : 'left']: '50%',
                      }}
                    />
                  </span>
                  <span className="ab-value">
                    {g.vs_cell > 0 ? '+' : ''}
                    {fmt(g.vs_cell, 2)}%p
                  </span>
                  <span className="muted small ab-n">
                    {fmt(g.cells)}칸 · {fmt(g.n)}건
                  </span>
                </div>
              ))}
            </div>
          ) : (
            data.groups.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 10 }}>
                <table>
                  <thead>
                    <tr>
                      <th>향</th>
                      <th className="num">칸 중위 대비</th>
                      <th className="num">95% 구간</th>
                      <th className="num">칸</th>
                      <th className="num">매물</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.groups.map((g) => (
                      <tr key={g.group}>
                        <td>{g.label}</td>
                        <td className="num">
                          {g.vs_cell > 0 ? '+' : ''}
                          {fmt(g.vs_cell, 2)}%p
                        </td>
                        <td className="num muted">
                          {g.lo == null
                            ? '—'
                            : `${g.lo > 0 ? '+' : ''}${fmt(g.lo, 2)} ~ ${g.hi > 0 ? '+' : ''}${fmt(g.hi, 2)}`}
                        </td>
                        <td className="num">{fmt(g.cells)}</td>
                        <td className="num">{fmt(g.n)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {/* 컴퍼스는 각 방향을 '칸 중위' 와 견준 그림이라 **두 방향끼리**는 못
              견준다. 그 질문('남향이 서향보다 비싼가')에는 짝 비교가 답한다 —
              두 향이 같은 칸에 함께 있을 때만 골라 뺀 값이다. */}
          {data.pairs?.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>둘을 직접 견주면</th>
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
          )}

          <p className="muted small" style={{ marginTop: 10 }}>
            향이 적힌 매물 <b>{fmt(data.n_quotes)}건</b> 중 적정가를 낼 수 있는{' '}
            {fmt(data.n_scored)}건을 썼고, 그중 향이 둘 이상 섞인 칸은{' '}
            {fmt(data.n_cells)}개입니다. 호가는 <b>받고 싶은 값</b>이지 받은 값이
            아닙니다 — 비싸게 불러도 안 팔릴 수 있습니다.
          </p>
        </>
      )}
    </section>
  )
}
