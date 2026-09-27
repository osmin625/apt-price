import { useCallback, useEffect, useState } from 'react'

import { api } from '../api'
import { fmt } from '../components/Charts'
import FitLoading from '../components/FitLoading'
import KakaoMap from '../components/KakaoMap'

/* 지도는 **모델 잔차**만 칠한다.
 *
 * 평당가 자체(보정·중앙)를 칠하면 비싼 동네가 비싸게 나올 뿐이라 지도로 볼 이유가
 * 적다. 그건 단지 비교 탭의 표가 더 잘 답한다. 지도에서만 보이는 것은 '요인으로
 * 설명되지 않는 값이 어디에 뭉쳐 있나' 이고, 그게 잔차다. */
const METRIC = 'residual_shrunk_pct'

/** 값 → 0..1. 발산 지표는 0을 중앙으로 두고 좌우 대칭 범위를 쓴다. */
function normalize(v, meta) {
  if (v == null || !meta) return 0.5
  if (meta.scale === 'diverging') {
    const span = Math.max(Math.abs(meta.min ?? 0), Math.abs(meta.max ?? 0)) || 1
    return Math.max(0, Math.min(1, (v / span + 1) / 2))
  }
  const lo = meta.min ?? 0
  const hi = meta.max ?? 1
  return Math.max(0, Math.min(1, (v - lo) / (hi - lo || 1)))
}

export default function MapView({ months, onSelect }) {
  const [data, setData] = useState(null)
  const [stations, setStations] = useState([])
  const [fit, setFit] = useState(null)

  const [hoveredId, setHoveredId] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [path, setPath] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setError(null)
    Promise.all([
      api.mapComplexes({ months }),
      api.stations(),
      api.modelFit({ months }),
    ])
      .then(([m, s, f]) => {
        if (!alive) return
        setData(m)
        setStations(s.items || [])
        setFit(f)
      })
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [months])

  useEffect(() => {
    if (selectedId == null) {
      setPath(null)
      return
    }
    let alive = true
    api
      .walkPath(selectedId)
      .then((p) => alive && setPath(p))
      .catch(() => alive && setPath(null))
    return () => {
      alive = false
    }
  }, [selectedId])

  const meta = data?.metrics?.[METRIC]

  const colorOf = useCallback(
    (item) => {
      const t = normalize(item[METRIC], meta)
      if (meta?.scale === 'diverging') {
        // 기존 .pbar-fill.pos/.neg 관례와 동일: 파랑 = 저평가, 빨강 = 고평가
        return t < 0.5
          ? `color-mix(in srgb, var(--series-1) ${(1 - t * 2) * 85 + 15}%, var(--surface-1))`
          : `color-mix(in srgb, var(--neg) ${((t - 0.5) * 2) * 85 + 15}%, var(--surface-1))`
      }
      return `color-mix(in srgb, var(--series-1) ${t * 85 + 15}%, var(--surface-1))`
    },
    [meta],
  )

  const selected = data?.items?.find((i) => i.id === selectedId)

  if (error) return <div className="card empty">{error}</div>
  if (!data || !fit)
    return (
      <div className="card">
        <FitLoading months={months} what="지도와 모델을" />
      </div>
    )

  return (
    <>
      <div className="card">
        <div className="map-toolbar">
          <strong className="map-metric">모델 잔차</strong>
          <div className="map-scale" aria-hidden="true">
            <span>{fmt(meta?.min, 1)}</span>
            <i className={meta?.scale === 'diverging' ? 'grad-div' : 'grad-seq'} />
            <span>{fmt(meta?.max, 1)}</span>
            <small>{meta?.unit}</small>
          </div>
        </div>
        {meta?.note && <p className="muted small">{meta.note}</p>}

        <div className="map-wrap">
          <KakaoMap
            items={data.items}
            stations={stations}
            colorOf={colorOf}
            hoveredId={hoveredId}
            selectedId={selectedId}
            onHover={setHoveredId}
            onSelect={(id) => setSelectedId((cur) => (cur === id ? null : id))}
            path={path}
            center={
              data.bounds
                ? {
                    lat: (data.bounds.sw[0] + data.bounds.ne[0]) / 2,
                    lng: (data.bounds.sw[1] + data.bounds.ne[1]) / 2,
                  }
                : null
            }
          />
        </div>

        {selected ? (
          <div className="map-detail">
            <div>
              <strong>{selected.name}</strong>
              <span className="muted"> · {selected.umd_nm}</span>
            </div>
            <div className="tiles compact">
              <Tile label="보정 평당가" value={`${fmt(selected.normalized_ppp)} 만원/평`} />
              <Tile
                label="모델 예측"
                value={
                  selected.predicted_ppp ? `${fmt(selected.predicted_ppp)} 만원/평` : '—'
                }
              />
              <Tile
                label="모델 잔차"
                value={`${selected.residual_shrunk_pct > 0 ? '+' : ''}${fmt(
                  selected.residual_shrunk_pct,
                  1,
                )}%`}
                tone={selected.residual_shrunk_pct > 0 ? 'neg' : 'pos'}
              />
              <Tile
                label="역까지"
                value={`${selected.station_name ?? '—'} 도보 ${fmt(selected.walk_min, 1)}분`}
                sub={selected.walk_source === 'tmap' ? '실제 보행 경로' : '직선거리 추정'}
              />
              <Tile
                label="강남 접근"
                value={
                  selected.total_access_min ? `${fmt(selected.total_access_min, 0)}분` : '—'
                }
                sub={selected.best_station_name ?? ''}
              />
            </div>
            <div className="map-detail-actions">
              <button className="ghost" onClick={() => onSelect?.(selected.id)}>
                단지 상세 보기
              </button>
              <button className="ghost" onClick={() => setSelectedId(null)}>
                선택 해제
              </button>
            </div>
          </div>
        ) : (
          <p className="muted small">
마커를 클릭하면 그 단지에서 최근접역까지의 도보 경로가 표시됩니다.
          </p>
        )}
      </div>
    </>
  )
}

function Tile({ label, value, sub, tone }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className={`value sm${tone ? ` tone-${tone}` : ''}`}>{value}</div>
      {sub ? <div className="note">{sub}</div> : null}
    </div>
  )
}
