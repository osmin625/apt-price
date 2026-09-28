import { useEffect, useState } from 'react'

import { api } from '../api'
import { Tile, fmt } from './Charts'
import Loading from './Loading'
import ScatterFit from './ScatterFit'

/**
 * 역까지 도보거리를 **깊게** 보는 화면. 시장 분석의 도보거리 카드에서 펼친다.
 *
 * ## 왜 분해 모델 탭이 아니라 여기인가
 *
 * 이 두 가지는 도보거리 하나에 대한 이야기다 — 연속 곡선과 산점도, 그리고 같은 단지
 * 안에서만 본 교란 없는 비교. 분해 모델 탭에 두면 거기서만 도보거리가 특별 대우를
 * 받아, 요인 여덟 개를 나란히 보는 그 탭의 성격과 어긋났다.
 *
 * 시장 분석은 요인마다 카드가 하나씩 있다. 도보거리를 더 보고 싶으면 그 카드를
 * 펼치는 것이 자연스럽다.
 *
 * ## 펼칠 때 받아 온다
 *
 * 시장 분석은 `/model/factors` 만 받으면 그려진다. 산점도는 거기에 더해 적합 전체와
 * 지도용 단지 목록(1.2MB)이 필요한데, 대부분의 방문에서 쓰이지 않는다. 그래서 펼친
 * 뒤에 받는다.
 */
export default function WalkDetail({ months, onSelect }) {
  const [fit, setFit] = useState(null)
  const [map, setMap] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setError(null)
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

  if (error) return <p className="empty">{error}</p>
  if (!fit) return <Loading label="도보거리 상세를 불러오는 중" compact />

  const curve = fit.curves.walk_minutes
  const points = (map?.items || []).map((i) => ({
    id: i.id,
    name: i.name,
    walk_min: i.walk_min,
    value: i.partial_pct,
    sub: `${i.station_name ?? '—'} · 거래 ${i.trade_count}건`,
  }))

  return (
    <div className="walk-detail">
      <h3>도보시간과 평당가</h3>
      <p className="muted small">
        거리를 <b>구간으로 자르지 않고</b> 연속 변수로 추정한 곡선입니다. y축은 {curve.note}.
        회색 밴드는 95% 신뢰구간이며, 기준점에서 폭이 0이 되는 것이 정상입니다 — 기준점
        대비 차이를 보는 그래프이기 때문입니다.
      </p>
      <ScatterFit curve={curve} points={points} onSelect={onSelect} height={260} />
      <div className="tiles compact">
        <Tile
          label="도보 1분당"
          value={`${fmt(fit.linear_walk.pct, 2)}%`}
          sub={`SE ${fmt(fit.linear_walk.se * 100, 2)}%p · p=${fit.linear_walk.p}`}
        />
        <Tile label="단지 수" value={fmt(fit.n_complexes)} sub={`거래 ${fmt(fit.n_obs)}건`} />
        {fit.walk_vs_ride_ratio && (
          <Tile
            label="도보 vs 전철"
            value={fit.walk_vs_ride_ratio.label}
            sub="걷는 1분과 앉아 가는 1분의 가치 비"
          />
        )}
      </div>

      {fit.within_walk && (
        <>
          <h3>같은 단지 안에서 본 거리 효과</h3>
          <p className="muted small">
            국토부가 공개하는 <b>동 정보</b>로 동별 좌표를 찾아, 같은 단지 안에서 역에 가까운
            동과 먼 동을 비교한 값입니다. 학군·브랜드·관리상태·연식·구 입지가 모두 같은
            단지이므로 <b>교란이 원천적으로 없습니다</b> — 이 데이터로 얻을 수 있는 가장
            깨끗한 비교입니다. 대신 단지 내 거리 편차가 좁아 넓은 범위로 외삽하면 안 됩니다.
          </p>
          <div className="tiles compact">
            <Tile
              label="같은 단지 안 · 도보 1분당"
              value={`${fmt(fit.within_walk.pct, 2)}%`}
              sub={`SE ${fmt(fit.within_walk.se * 100, 2)}%p · p=${fit.within_walk.p}`}
            />
            <Tile
              label="단지 간 비교 · 도보 1분당"
              value={`${fmt(fit.linear_walk.pct, 2)}%`}
              sub={`SE ${fmt(fit.linear_walk.se * 100, 2)}%p · p=${fit.linear_walk.p}`}
            />
            <Tile
              label="동 정보가 있는 거래"
              value={fmt(fit.within_walk.n_trades)}
              sub={`전체 ${fmt(fit.n_obs)}건 중`}
            />
          </div>
          <p className="muted small">
            두 값이 비슷하면 단지 간 비교에 큰 교란이 없다는 뜻이고, 크게 다르면 단지 간
            추정치에 거리 외의 요인이 섞여 있다는 신호입니다. 어느 하나가 정답이 아니라
            서로 다른 질문의 답입니다.
          </p>
        </>
      )}
    </div>
  )
}
