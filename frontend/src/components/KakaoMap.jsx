import { useEffect, useRef, useState } from 'react'

import { kakaoKeyMissing, loadKakaoMaps } from '../lib/kakaoMap'

/**
 * 카카오맵 명령형 래퍼.
 *
 * 마커를 Marker 가 아니라 **CustomOverlay** 로 그린다:
 *  - Marker 는 색마다 MarkerImage 가 필요해 20개 변형을 만들어야 한다.
 *  - Circle 은 반지름이 미터 단위라 줌에 따라 크기가 변한다.
 *  - CustomOverlay 는 그냥 DOM 노드라 기존 CSS 커스텀 프로퍼티를 상속한다.
 *    styles.css 의 prefers-color-scheme 블록이 그대로 적용되어
 *    **다크모드가 공짜로 따라온다.** 테마 어댑터가 필요 없다.
 */
export default function KakaoMap({
  items = [],
  stations = [],
  colorOf,
  hoveredId = null,
  selectedId = null,
  onHover,
  onSelect,
  rings = [],
  ringCenter = null,
  path = null,
  center = null,
  height = 560,
}) {
  const boxRef = useRef(null)
  const mapRef = useRef(null)
  const overlaysRef = useRef(new Map())
  const stationOverlaysRef = useRef([])
  const shapesRef = useRef([])
  const [error, setError] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    loadKakaoMaps()
      .then((maps) => {
        if (cancelled || !boxRef.current) return
        mapRef.current = new maps.Map(boxRef.current, {
          center: new maps.LatLng(center?.lat ?? 37.2725, center?.lng ?? 127.0269),
          level: 6,
        })
        mapRef.current.addControl(
          new maps.ZoomControl(),
          maps.ControlPosition.RIGHT,
        )
        setReady(true)
      })
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 단지 마커
  useEffect(() => {
    const maps = window.kakao?.maps
    const map = mapRef.current
    if (!ready || !maps || !map) return

    const live = new Set()
    for (const it of items) {
      if (it.lat == null || it.lng == null) continue
      live.add(it.id)
      let ov = overlaysRef.current.get(it.id)
      if (!ov) {
        const el = document.createElement('button')
        el.type = 'button'
        el.className = 'marker'
        el.addEventListener('mouseenter', () => onHover?.(it.id))
        el.addEventListener('mouseleave', () => onHover?.(null))
        el.addEventListener('click', (e) => {
          e.stopPropagation()
          onSelect?.(it.id)
        })
        ov = new maps.CustomOverlay({
          position: new maps.LatLng(it.lat, it.lng),
          content: el,
          yAnchor: 0.5,
          xAnchor: 0.5,
          clickable: true,
        })
        ov.__el = el
        ov.setMap(map)
        overlaysRef.current.set(it.id, ov)
      }
      const el = ov.__el
      el.style.background = colorOf?.(it) ?? 'var(--series-1)'
      el.title = it.name
      el.classList.toggle('is-hovered', hoveredId === it.id)
      el.classList.toggle('is-selected', selectedId === it.id)
    }

    for (const [id, ov] of overlaysRef.current) {
      if (!live.has(id)) {
        ov.setMap(null)
        overlaysRef.current.delete(id)
      }
    }
  }, [ready, items, colorOf, hoveredId, selectedId, onHover, onSelect])

  // 역 마커
  useEffect(() => {
    const maps = window.kakao?.maps
    const map = mapRef.current
    if (!ready || !maps || !map) return

    stationOverlaysRef.current.forEach((o) => o.setMap(null))
    stationOverlaysRef.current = stations
      .filter((s) => s.lat != null)
      .map((s) => {
        const el = document.createElement('div')
        el.className = 'station-marker'
        el.textContent = s.name.replace(/역$/, '')
        el.title = `${s.name} (${s.line}) · 강남 ${s.minutes_to_gangnam ?? '?'}분`
        const ov = new maps.CustomOverlay({
          position: new maps.LatLng(s.lat, s.lng),
          content: el,
          yAnchor: 0.5,
          xAnchor: 0.5,
        })
        ov.setMap(map)
        return ov
      })
  }, [ready, stations])

  // 등가격 링 + 도보 경로
  useEffect(() => {
    const maps = window.kakao?.maps
    const map = mapRef.current
    if (!ready || !maps || !map) return

    shapesRef.current.forEach((s) => s.setMap(null))
    shapesRef.current = []

    if (ringCenter?.lat != null) {
      for (const r of rings) {
        const circle = new maps.Circle({
          center: new maps.LatLng(ringCenter.lat, ringCenter.lng),
          radius: r.radius_m,
          strokeWeight: 1,
          strokeColor: '#6b7cff',
          strokeOpacity: 0.85,
          strokeStyle: 'shortdash',
          fillColor: '#6b7cff',
          fillOpacity: 0.04,
        })
        circle.setMap(map)
        shapesRef.current.push(circle)

        const label = document.createElement('div')
        label.className = 'ring-label'
        label.textContent = r.label
        const ov = new maps.CustomOverlay({
          position: new maps.LatLng(
            ringCenter.lat + r.radius_m / 111000,
            ringCenter.lng,
          ),
          content: label,
          yAnchor: 0.5,
          xAnchor: 0.5,
        })
        ov.setMap(map)
        shapesRef.current.push(ov)
      }
    }

    if (path) {
      const coords = path.path?.coordinates
      const line = coords
        ? coords.map(([lng, lat]) => new maps.LatLng(lat, lng))
        : path.complex_lat != null && path.station_lat != null
          ? [
              new maps.LatLng(path.complex_lat, path.complex_lng),
              new maps.LatLng(path.station_lat, path.station_lng),
            ]
          : null
      if (line) {
        const poly = new maps.Polyline({
          path: line,
          strokeWeight: 4,
          strokeColor: '#f2994a',
          strokeOpacity: 0.95,
          // 추정치 모드에는 실제 경로 지오메트리가 없어 직선이므로 점선으로 구분한다.
          strokeStyle: coords ? 'solid' : 'shortdash',
        })
        poly.setMap(map)
        shapesRef.current.push(poly)
      }
    }
  }, [ready, rings, ringCenter, path])

  // 선택된 단지로 팬
  useEffect(() => {
    const maps = window.kakao?.maps
    const map = mapRef.current
    if (!ready || !maps || !map || selectedId == null) return
    const it = items.find((i) => i.id === selectedId)
    if (it?.lat != null) map.panTo(new maps.LatLng(it.lat, it.lng))
  }, [ready, selectedId, items])

  if (error || kakaoKeyMissing()) {
    return (
      <div className="map-fallback" style={{ height }}>
        <strong>지도를 표시할 수 없습니다</strong>
        <p>{error || 'VITE_KAKAO_JS_KEY 가 설정되지 않았습니다.'}</p>
        <ol>
          <li>
            <a href="https://developers.kakao.com" target="_blank" rel="noreferrer">
              카카오 개발자센터
            </a>
            에서 앱을 만들고 <b>JavaScript 키</b>를 발급받습니다.
          </li>
          <li>
            플랫폼 &gt; Web 에 <code>http://localhost:5173</code> 과{' '}
            <code>http://127.0.0.1:5173</code> 을 <b>둘 다</b> 등록합니다.
          </li>
          <li>
            <code>frontend/.env.local</code> 에{' '}
            <code>VITE_KAKAO_JS_KEY=발급받은키</code> 를 넣고 dev 서버를 재시작합니다.
          </li>
        </ol>
        <p className="muted">
          지도 없이도 <b>모델</b> 탭의 곡선·계수·잔차는 모두 정상 동작합니다.
        </p>
      </div>
    )
  }

  return <div className="map-canvas" ref={boxRef} style={{ height }} />
}
