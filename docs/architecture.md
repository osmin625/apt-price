# 코드 구조

어느 파일이 무엇을 맡는지.

## 파일 배치

```
backend/
  app/
    pricing.py              평당가·구간 분류·시점 보정·스플라인 기저·단지명 정규화
                            (의존성 없는 순수 모듈 — 시드와 모델이 공유하는 계약)
    models.py               Complex / Trade / Listing / Station / ComplexStation
    services/analysis.py    DB → 기술통계 (구간 기반, 기존 3개 탭)
    services/hedonic.py     2단계 헤도닉 회귀 — numpy/statsmodels 를 쓰는 유일한 파일
                            (지연 import — 미설치여도 기존 탭은 정상 동작)
    services/model_view.py  적합 결과 → 지도 마커·등가격 링·참값 오버레이
    clients/molit.py        국토교통부 실거래가 API
    clients/kakao.py        좌표 변환 + 지하철역 탐색 + 단지 POI 검색
    clients/tmap.py         보행자 경로안내
    routers/                complexes / analysis / listings / model / map
  scripts/
    seed_demo.py            합성 데이터 — 참값을 심어 생성 (하드코딩 아님)
    validate_model.py       참값 복원 + 커버리지 검증
    seed_stations.py        역 테이블 + 강남 접근성 (수기 관리)
    route_walk.py           단지↔역 도보 경로 (TMap, 없으면 추정치)
    ingest_trades.py        실거래 적재
    geocode.py              좌표·역거리 채우기
frontend/
  src/views/                시장 분석 / 단지 비교 / 단지 상세 / 매물 진단 / 지도 / 거리 모델
  src/components/Charts.jsx IQR 범위+중앙값 점, 층 프리미엄 막대, 추이 선
  src/components/ScatterFit.jsx  산점도 + 적합 곡선 + 신뢰밴드 + 시드 참값 점선
  src/components/KakaoMap.jsx    카카오맵 래퍼 (CustomOverlay 마커 → 다크모드 자동)
```

차트 라이브러리는 쓰지 않는다. 백엔드가 곡선을 50점 가까이 조밀하게 보내므로 보간기가
필요 없고, 축·틱·툴팁은 `Charts.jsx` 의 기존 헬퍼를 그대로 쓴다. 마커를 `Marker` 가 아니라
`CustomOverlay`(DOM 노드)로 그리는 것도 같은 이유다 — CSS 커스텀 프로퍼티를 상속해
다크모드가 테마 어댑터 없이 따라온다.
