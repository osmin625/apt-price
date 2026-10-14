# 코드 구조

어느 파일이 무엇을 맡는지.

## 파일 배치

```
backend/
  app/
    main.py                 FastAPI 앱 — 라우터 등록, 적합 예열(FIT_WARM), /api/health
    config.py               설정(.env) — DATABASE_URL 로 DB 사본을 걸 수 있다
    db.py                   엔진·세션
    pricing.py              평당가·구간 분류·시점 보정·스플라인 기저·단지명 정규화
                            (의존성 없는 순수 모듈 — 시드와 모델이 공유하는 계약)
    models.py               단지·거래·호가·역·입지·메모 등 테이블
                            (Complex / ComplexDong / ComplexStation / ComplexAmenity /
                             Station / Trade / Listing / Quote / QuoteNote /
                             MemoTagPref / DongTag / RebStat /
                             KaptUnit / KaptRun / BldUnit / BldRun)

    routers/                HTTP 만 맡는다 — 입력 검증, 서비스 호출, 오류를 상태 코드로.
                            해석 규칙·집계는 services 에 둔다(아래 '라우터는 얇게').
    routers/complexes.py    단지 목록·상세·평형·동·민간임대 표시
    routers/analysis.py     구간 기반 기술통계(매물 분석 탭)
    routers/model.py        적합·요인·묶음·두 매물 비교·목록 붙여넣기
    routers/quotes.py       쌓인 호가의 순위·삭제·비고·메모 사전
    routers/map.py          지도 마커·역·도보 경로
    routers/macro.py        한국부동산원 공표 통계
    routers/supply.py       공급 분석
    routers/regime.py       거시 국면

    services/analysis.py    DB → 기술통계 (구간 기반, 기존 3개 탭)
    services/hedonic.py     2단계 헤도닉 회귀 — numpy/statsmodels 를 쓰는 유일한 파일
                            (지연 import — 미설치여도 기존 탭은 정상 동작)
    services/fit_worker.py  적합을 별도 프로세스에서 돌린다(FIT_IN_PROCESS=1 로 끈다)
    services/model_view.py  적합 결과 → 지도 마커·등가격 링·요인 곡선·매물 적정가·비교
    services/listing_parse.py   붙여넣은 텍스트 → 단지명·면적·층·호가·메모 (글자만 읽는다)
    services/listing_match.py   읽은 값 → 우리 단지·실제 거래 평형에 맞추고 순위·저장까지
    services/ranking.py     여러 매물을 한꺼번에 평가·중복 합치기·쌓인 호가 순위
    services/quotes.py      호가 누적·유닛 접기·이력, 메모 원문과 끈 태그 조회
    services/memo_tags.py   중개사 메모 → 키워드 (DB 를 모르는 순수 규칙)
    services/aspect.py      향 프리미엄 측정 — 화면에서는 뺐지만 측정이 자산이라 남김
    services/macro.py       공표 통계를 경기 남부 시군구로 묶기
    services/supply.py      적정 공급(가구 증가+멸실)·파이프라인·착공 선행성
    services/regime.py      요인별 압력(상관·시차)·과거 국면·비슷했던 달
    services/policy.py      부동산 대책·세제 연표 (손으로 쓴 목록 + 출처)
                            (docs/supply.md — 서울은 선행성이 없어 가늠하지 않는다)

    clients/molit.py        국토교통부 실거래가 API
    clients/kakao.py        좌표 변환 + 지하철역 탐색 + 단지 POI 검색
    clients/tmap.py         보행자 경로안내
    clients/sdsc.py         소상공인 상가정보 — 업종 분류로 유흥을 가른다
    clients/ecos.py         한국은행 ECOS — M2 와 기준금리만 (키 없으면 sample 폴백)
    clients/bldrgst.py      건축HUB 건축물대장 표제부 — 0 을 성공으로 받지 않는다
    clients/kapt.py         K-apt 단지 세대수·동수
    clients/reb.py          한국부동산원 R-ONE 공표 통계
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
    verify_listing_parse.py 매물 파서가 주석에 적은 사례를 주석대로 읽는지
    migrate.py              모델에 있는데 DB 에 없는 컬럼 추가
    ingest_reb.py           한국부동산원 공표 통계
    ingest_supply.py        공급 통계(인허가·착공·준공·멸실·가구수) — 시도 단위
    ingest_macro.py         거시 요인(미분양·심리·가계대출·금리·M2·기준금리)
    ingest_kapt.py          K-apt 단지 상세(세대수 등) — 우리 단지에 붙인다
    ingest_kapt_all.py      K-apt 시군구 전수 — 붙이지 않고 담는다(경기 남부 공급)
    ingest_gg_housing.py    경기도기본통계 CSV — 시군구 가구수·주택수(손으로 받음)
    ingest_bldrgst.py       건축물대장 법정동 전수 — 멸실을 직접 관측하려고
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
  src/views/                매물 분석 / 가격 분석 / 공급 분석 / 거시 분석 / 단지 상세
                            / 호가 입력 / 호가 분석 / 지도 / 분해 모델
  src/components/Charts.jsx IQR 범위+중앙값 점, 층 프리미엄 막대, 추이 선
  src/components/ScatterFit.jsx  산점도 + 적합 곡선 + 신뢰밴드 + 시드 참값 점선
  src/components/KakaoMap.jsx    카카오맵 래퍼 (CustomOverlay 마커 → 다크모드 자동)
```

차트 라이브러리는 쓰지 않는다. 백엔드가 곡선을 50점 가까이 조밀하게 보내므로 보간기가
필요 없고, 축·틱·툴팁은 `Charts.jsx` 의 기존 헬퍼를 그대로 쓴다. 마커를 `Marker` 가 아니라
`CustomOverlay`(DOM 노드)로 그리는 것도 같은 이유다 — CSS 커스텀 프로퍼티를 상속해
다크모드가 테마 어댑터 없이 따라온다.

## 라우터는 얇게

라우터는 **요청을 받아 서비스에 넘기고, 서비스의 실패를 상태 코드로 바꾼다.** 해석
규칙·집계·여러 테이블을 엮는 조립은 서비스에 둔다.

한 번 어긋났다. `routers/model.py` 가 붙여넣은 매물을 단지·평형에 맞추는 규칙 260줄을
품고 있었고(`_resolve_area`·`_resolve_by_dong` 등), `routers/quotes.py` 는 쌓인 호가에
비고·메모 태그·민간임대 표시를 붙이는 조립 80줄을 품고 있었다. 면적 맞추는 규칙을
고치려면 HTTP 파일을 열어야 했고, 같은 규칙을 스크립트에서 쓰려면 라우터를 import
해야 했다. 지금은 `services/listing_match.py`·`ranking.rank_saved` 로 옮겼다 — 옮기기
전후 응답 13종(붙여넣기 1,157건 포함)을 바이트 단위로 대조해 같았다.

**한 행을 읽고 쓰는 단순한 CRUD 는 라우터에 둔다**(비고 쓰기, 태그 켜고 끄기, 민간임대
표시). 그것까지 서비스로 옮기면 파일만 늘고 읽을 곳이 둘이 된다. 기준은 '줄 수' 가
아니라 **HTTP 를 몰라도 되는 규칙이 있느냐**다.
