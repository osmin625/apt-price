# 코드 구조

어느 파일이 무엇을 맡는지.

## 파일 배치

```
backend/
  app/
    pricing.py              평당가·구간 분류·시점 보정·스플라인 기저·단지명 정규화
                            (의존성 없는 순수 모듈 — 시드와 모델이 공유하는 계약)
    models.py               단지·거래·호가·역·입지·메모 등 12개 테이블
                            (Complex / ComplexDong / ComplexStation / ComplexAmenity /
                             Station / Trade / Listing / Quote / QuoteNote /
                             MemoTagPref / DongTag / RebStat)
    services/analysis.py    DB → 기술통계 (구간 기반, 기존 3개 탭)
    services/hedonic.py     2단계 헤도닉 회귀 — numpy/statsmodels 를 쓰는 유일한 파일
                            (지연 import — 미설치여도 기존 탭은 정상 동작)
    services/model_view.py  적합 결과 → 지도 마커·등가격 링·참값 오버레이
    clients/molit.py        국토교통부 실거래가 API
    clients/kakao.py        좌표 변환 + 지하철역 탐색 + 단지 POI 검색
    clients/tmap.py         보행자 경로안내
    clients/sdsc.py         소상공인 상가정보 — 업종 분류로 유흥을 가른다
    routers/                complexes / analysis / listings / model / map
  scripts/
    seed_demo.py            합성 데이터 — 참값을 심어 생성 (하드코딩 아님)
    validate_model.py       참값 복원 + 커버리지 검증
    cv_model.py             Stage 2 교차검증 — 요인을 넣을지 정하는 자
    model_status.py         지금 모델·데이터 상태 (문서에 숫자를 박지 않기 위해)
    verify_guard.py         넣어 둔 검사가 실제로 걸리는지 시험
    verify_docs.py          문서 링크·앵커가 가 닿는지 + 라우팅 표가 다 덮는지
    verify_absorb.py        고정효과 흡수 vs 더미 회귀
    verify_payloads.py      적합 페이로드가 정말 JSON 이 되는지
    verify_spline.py        벡터화한 스플라인 기저 vs pricing.rcs_basis
    verify_name_match.py    단지명 매칭 규칙 변경 전후 전수 대조
    migrate.py              모델에 있는데 DB 에 없는 컬럼 추가
    ingest_reb.py           한국부동산원 공표 통계
    ingest_kapt.py          K-apt 단지 상세(세대수 등)
    export_static.py        정적 사이트용 스냅샷
    seed_stations.py        역 테이블 + 강남 접근성 (수기 관리)
    route_walk.py           단지↔역 도보 경로 (TMap, 없으면 추정치)
    ingest_trades.py        실거래 적재
    geocode.py              좌표·역거리 채우기
    geocode_dongs.py        동별 좌표·도보시간
    fetch_complexes.py      카카오 POI 로 단지 목록 채우기
    verify_sync.py          경계를 넘는 싱크(코드↔문서↔데이터↔프론트)
    checkup.py              정기 검진 — 정합성·신선도·군살 (입구 하나)
    verify_sync_guard.py    그 싱크 검사가 깨뜨렸을 때 걸리는지
    ingest_amenity.py       단지 주변 입지(학교 거리·학원 수·유흥주점 수)
frontend/
  src/views/                미시 분석 / 단지 상세 / 매물 관리 / 매물 순위 / 지도 / 분해 모델
  src/components/Charts.jsx IQR 범위+중앙값 점, 층 프리미엄 막대, 추이 선
  src/components/ScatterFit.jsx  산점도 + 적합 곡선 + 신뢰밴드 + 시드 참값 점선
  src/components/KakaoMap.jsx    카카오맵 래퍼 (CustomOverlay 마커 → 다크모드 자동)
```

차트 라이브러리는 쓰지 않는다. 백엔드가 곡선을 50점 가까이 조밀하게 보내므로 보간기가
필요 없고, 축·틱·툴팁은 `Charts.jsx` 의 기존 헬퍼를 그대로 쓴다. 마커를 `Marker` 가 아니라
`CustomOverlay`(DOM 노드)로 그리는 것도 같은 이유다 — CSS 커스텀 프로퍼티를 상속해
다크모드가 테마 어댑터 없이 따라온다.
