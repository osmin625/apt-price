import { useEffect, useRef, useState } from 'react'

import { STATIC_MODE } from '../api'
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

  // 도보 경로
  useEffect(() => {
    const maps = window.kakao?.maps
    const map = mapRef.current
    if (!ready || !maps || !map) return

    shapesRef.current.forEach((s) => s.setMap(null))
    shapesRef.current = []

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
  }, [ready, path])

  // 선택된 단지로 팬
  useEffect(() => {
    const maps = window.kakao?.maps
    const map = mapRef.current
    if (!ready || !maps || !map || selectedId == null) return
    const it = items.find((i) => i.id === selectedId)
    if (it?.lat != null) map.panTo(new maps.LatLng(it.lat, it.lng))
  }, [ready, selectedId, items])

  if (error || kakaoKeyMissing()) {
    /*
       안내는 **지금 보고 있는 주소**를 기준으로 적는다.

       예전에는 `http://localhost:5173` 과 "dev 서버를 재시작합니다" 를 박아 두었다.
       그런데 정적 사이트(4173 미리보기, github.io)에서 이 화면이 뜨면 그 안내는
       전부 틀린 말이 된다 — 등록해야 하는 origin 도 다르고, 고쳐야 하는 파일도
       다르고, 재시작할 dev 서버도 없다.

       틀린 원인·틀린 처방을 단정하는 안내는 없는 안내보다 나쁘다. 어제 "pip
       install 하세요" 가 멀쩡한 환경을 의심하게 만든 것과 같은 종류다.
       origin 은 브라우저에서 읽고, 고칠 파일은 빌드 모드로 가른다.
    */
    const origin = typeof window === 'undefined' ? '' : window.location.origin
    const envFile = STATIC_MODE ? 'frontend/.env.static.local' : 'frontend/.env.local'

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
            플랫폼 &gt; Web 에 <code>{origin}</code> 을 등록합니다. 카카오는 origin 을{' '}
            <b>완전일치</b>로 검사하므로 포트까지 그대로여야 합니다.
            {!STATIC_MODE && (
              <>
                {' '}
                개발 중에는 <code>http://127.0.0.1:5173</code> 도 같이 등록하면
                편합니다 — 같은 서버인데 카카오는 다른 origin 으로 봅니다.
              </>
            )}
          </li>
          <li>
            <code>{envFile}</code> 에 <code>VITE_KAKAO_JS_KEY=발급받은키</code> 를 넣고{' '}
            {STATIC_MODE ? (
              <>
                <code>VITE_STATIC_MAP=1</code> 과 함께 다시 내보냅니다
                (<code>sync_static.ps1</code>).
              </>
            ) : (
              'dev 서버를 재시작합니다.'
            )}
          </li>
        </ol>
        <p className="muted">
          지도만 카카오를 씁니다. 나머지 탭의 곡선·계수·순위는 모두 정상 동작합니다.
        </p>
      </div>
    )
  }

  return <div className="map-canvas" ref={boxRef} style={{ height }} />
}
