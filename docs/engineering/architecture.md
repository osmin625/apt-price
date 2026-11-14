# 코드 구조

어느 파일이 무엇을 맡는지.

## 파일 배치

```
.github/workflows/check.yml CI — checkup --no-db + 프론트 빌드 (머지 관문의 한쪽)
.claude/settings.json       머지 관문 훅 등록 — 모든 셸 명령 앞에서 merge_gate.py
.claude/skills/             되풀이하는 절차(순서·끝난 기준만)
backend/
  app/                      자산(asset)마다 패키지 하나 — 자산끼리는 서로 import 하지 않는다
    main.py                 FastAPI 앱 — 자산 라우터 등록, 적합 예열(FIT_WARM), /api/health
    core/config.py          설정(.env) — DATABASE_URL 로 DB 사본을 걸 수 있다
    core/db.py              엔진·세션 — make_engine 은 DB 파일마다(apt.db·macro.db·stock.db) 같은 설정을 건다
    core/dbfile.py          apt.db 옆 DB 파일 하나 — 없으면 빈 파일을 만들지 않고 DbMissing(macro·stock 이 같이 쓴다)

    macro/                  거시 — 자산을 건너 쓰는 공표 계열. 어느 자산도 import 하지 않는다
    macro/store.py          macro.db(apt.db 옆) 읽기·쓰기 — 파일이 없으면 빈 계열 대신 MacroMissing
    macro/models.py         macro_points — (계열 id, 주기, 시점) 한 줄
    macro/clients/ecos.py   한국은행 ECOS — M2·기준금리·소비자물가·대출/예금 금리·KOSPI 시가총액·PER·국고채 10년·명목 GDP (키 없으면 sample 폴백)
                            fetch_table 은 표 하나를 그대로 — KOSPI 일별도 이것으로 받는다
    macro/clients/fred.py   FRED — 키 없는 CSV. 미국 금리·물가·M2·실업률·시가총액·GDP(SERIES)·S&P 500(SP500, 최근 10년)
    macro/clients/shiller.py   실러 교수의 ie_data.xls — S&P 500 1871~ 월별 주가·이익·물가·10년 금리·CAPE (비공식, 받을 때 FRED 와 대조)

    stock/                  주식 — 지수(다음은 종목)의 월~분기 수익률 구간 예측
    stock/CLAUDE.md         주식 지침서 — 평가 장치가 먼저, 출처는 공식·대조는 비공식
    stock/models.py         bars — (시장, 종목, 날짜) 일봉 종가 한 줄, 현지 통화
    stock/store.py          stock.db(apt.db 옆) 읽기·쓰기
    stock/indices.py        지수 목록과 받는 곳(KOSPI←ECOS, S&P 500←FRED)·각자의 무위험 금리
    stock/forecast.py       후보 넷(무작위 보행·과거 평균·금리+프리미엄·변동성 조정)과 walk-forward·구간 점수·DM 검정
                            (순수 파이썬 — CI 에서도 같은 코드)
    stock/indicators.py     지수 분석의 지표 목록·짝·꼴(diff·growth·level)·발표 시차 — 적재·응답·신선도가 여기서 읽는다
    stock/effects.py        지표 → 지수 영향(평소 폭 막대·등분산 Hansen–Hodrick 95% 범위·시기 나누기·함께 넣은 값)
    stock/service.py        지수 분석 응답 — 지표 영향 + 지금 구간 + 같은 장치로 잰 과거 성적 · 단기 매매 응답
    stock/trading.py        단기 매매 — 종가로 재는 기법 12개를 지수에 돌린 지금 상태·기저율 대비 성적·실제 사례(지그재그 패턴 탐지)
    stock/companies.py      기술주 가치 탭의 종목(티커·CIK) — 알파벳·테슬라·IBM·디웨이브
    stock/clients/alphavantage.py   종목 주가 — 최근 100일 일봉·상장 때부터 월봉 수정 종가(무료 키)
    stock/clients/edgar.py  SEC EDGAR companyfacts — 순이익·매출·영업이익·주식 수(키 없음)
    stock/fundamentals.py   EDGAR 줄 → 분기 값(4분기 = 1년 − 9개월)·지난 12개월·주식 수, 그날 알던 값/지금 아는 값
    stock/scenarios.py      기대 기술 시나리오 기본값(근거 문구 + 가정)
    stock/reflect.py        기술주 반영 분해 — 1년 주가 변화 = 평균 + 거시 여섯·실적 둘의 몫(방향 고정, nnls) + 설명 안 된 몫, 80% 범위
    stock/techvalue.py      기술주 가치 재료 — 지금 주가·주식 수·12개월 이익·베타·10년 국채·월봉 이력
    stock/valuation.py      장기 투자 — 지수 평가 넷(버핏 지표·이익 수익률 vs 국채·CAPE·추세 대비)의 지금 백분위·뒤 5·10년 수익(가짜 경로 범위)
    stock/routers/indices.py   /api/stock/indices · /api/stock/tech-value · /api/stock/long-term · /api/stock/short-term

    realestate/             부동산
    realestate/CLAUDE.md    부동산 지침서 — 이 자산의 라우팅 표와 규칙(아래 '자산 구조')
    realestate/pricing.py   평당가·구간 분류·시점 보정·스플라인 기저·단지명 정규화
                            (의존성 없는 순수 모듈 — 시드와 모델이 공유하는 계약)
    realestate/models.py    단지·거래·호가·역·입지·메모 등 테이블
                            (Complex / ComplexDong / ComplexStation / ComplexAmenity /
                             Station / Trade / Quote / QuoteNote /
                             MemoTagPref / DongTag / RebStat /
                             KaptUnit / KaptRun / BldUnit / BldRun)

    realestate/routers/     HTTP 만 맡는다 — 입력 검증, 서비스 호출, 오류를 상태 코드로.
                            해석 규칙·집계는 services 에 둔다(아래 '라우터는 얇게').
    realestate/routers/complexes.py    단지 상세·동·민간임대 표시·필터 선택지
    realestate/routers/analysis.py     향 프리미엄 측정만 남았다(화면 없음 — realestate/services/aspect.py)
    realestate/routers/model.py        적합·요인·묶음·적합 상태·목록 붙여넣기
    realestate/routers/quotes.py       쌓인 호가의 순위·삭제·비고·메모 사전
    realestate/routers/map.py          지도 마커·역·도보 경로
    realestate/routers/macro.py        한국부동산원 공표 통계
    realestate/routers/supply.py       공급 분석
    realestate/routers/regime.py       거시 국면
    realestate/routers/tenure.py       매매·전세·월세

    realestate/services/analysis.py    DB → 거래 점·단지 상세·실거래 기준 적정가(비교표본 중앙값)
    realestate/services/hedonic.py     2단계 헤도닉 회귀 — numpy/statsmodels 를 쓰는 유일한 파일
                            (지연 import — 미설치여도 기존 탭은 정상 동작)
    realestate/services/fit_worker.py  적합을 별도 프로세스에서 돌린다(FIT_IN_PROCESS=1 로 끈다)
    realestate/services/model_view.py  적합 결과 → 지도 마커·요인 곡선·묶음·매물 요인 기준 적정가
    realestate/services/listing_parse.py   붙여넣은 텍스트 → 단지명·면적·층·호가·메모 (글자만 읽는다)
    realestate/services/listing_match.py   읽은 값 → 우리 단지·실제 거래 평형에 맞추고 순위·저장까지
    realestate/services/ranking.py     여러 매물을 한꺼번에 평가·중복 합치기·쌓인 호가 순위
    realestate/services/quotes.py      호가 누적·유닛 접기·이어 붙이기, 메모 원문과 끈 태그 조회
    realestate/services/memo_tags.py   중개사 메모 → 키워드 (DB 를 모르는 순수 규칙)
    realestate/services/aspect.py      향 프리미엄 측정 — 화면에서는 뺐지만 측정이 자산이라 남김
    realestate/services/macro.py       공표 통계를 경기 남부 시군구로 묶기
    realestate/services/supply.py      적정 공급(가구 증가+멸실)·파이프라인·착공 선행성
                            (docs/analysis/supply.md — 서울은 선행성이 없어 가늠하지 않는다)
    realestate/services/regime.py      요인 위치(z)·그때는·기저율·과거 국면(월별)·반영 분해(방향 고정)
    realestate/services/policy.py      부동산 대책·세제 연표 (손으로 쓴 목록 + 출처)
    realestate/services/tenure.py      매매·전세·월세 재료 — 빈 달 없는 구, 지수로 이은 가격, 금리, 인상기, 인상 뒤 경로
                            (월 비용 곱셈은 화면이 한다 — 대출 비율을 바꾸므로)

    realestate/clients/molit.py        국토교통부 실거래가 API
    realestate/clients/kakao.py        좌표 변환 + 지하철역 탐색 + 단지 POI 검색
    realestate/clients/tmap.py         보행자 경로안내
    realestate/clients/sdsc.py         소상공인 상가정보 — 업종 분류로 유흥을 가른다
    realestate/clients/bldrgst.py      건축HUB 건축물대장 표제부 — 0 을 성공으로 받지 않는다
    realestate/clients/kapt.py         K-apt 단지 세대수·동수
    realestate/clients/reb.py          한국부동산원 R-ONE 공표 통계
  scripts/
    seed_demo.py            합성 데이터 — 참값을 심어 생성 (하드코딩 아님)
    validate_model.py       참값 복원 + 커버리지 검증
    cv_model.py             Stage 2 교차검증 — 요인을 넣을지 정하는 자
    cv_macro.py             거시 합산 모델(화면에서 걷음) — 같은 백테스트 + DM 검정
    cv_reflect.py           반영 분해 — 이론 시차 판과 같은 달 판을 나란히
    verify_supply_cum.py    거시 '누적 공급'(월별) vs 공급 분석 누적 차이(연별) 대조
    verify_reflect.py       반영 분해의 부호 제약 최소제곱(순수 파이썬) vs scipy nnls
    verify_tenure.py        매매·전세·월세의 이어 붙인 가격 수준에 표본 개편 튐이 없는지
    verify_macro_store.py   macro.db 가 없을 때 빈 파일을 만들지 않고 시끄럽게 실패하는지 · 쓴 값 그대로 읽는지
    probe_policy.py         정책 연표의 원문 링크(정책브리핑 보도자료)가 아직 그 부처·제목·날짜인지(네트워크)
    model_status.py         지금 모델·데이터 상태 (문서에 숫자를 박지 않기 위해)
    verify_guard.py         넣어 둔 검사가 실제로 걸리는지 시험
    verify_docs.py          문서 링크·앵커가 가 닿는지 + 라우팅 표가 다 덮는지 + docs 계층
    verify_absorb.py        고정효과 흡수 vs 더미 회귀
    verify_payloads.py      적합 페이로드가 정말 JSON 이 되는지
    verify_spline.py        벡터화한 스플라인 기저 vs pricing.rcs_basis
    verify_name_match.py    단지명 매칭 규칙 변경 전후 전수 대조
    verify_listing_parse.py 매물 파서가 주석에 적은 사례를 주석대로 읽는지
    verify_fit_orphan.py    부모를 강제 종료하면 적합 워커도 끝나는지
    verify_fit_cache_key.py 적합 캐시 키가 표본을 정하는 것(거래·날짜)을 다 담는지
    migrate.py              모델에 있는데 DB 에 없는 컬럼 추가
    ingest_reb.py           한국부동산원 공표 통계
    ingest_supply.py        공급 통계(인허가·착공·준공·멸실·가구수) — 시도 단위
    ingest_macro.py         거시 요인(미분양·심리·가계대출·금리·M2·기준금리·소비자물가)
    ingest_kapt.py          K-apt 단지 상세(세대수 등) — 우리 단지에 붙인다
    ingest_kapt_all.py      K-apt 시군구 전수 — 붙이지 않고 담는다(경기 남부 공급)
    ingest_gg_housing.py    경기도기본통계 CSV — 시군구 가구수·주택수(손으로 받음)
    ingest_bldrgst.py       건축물대장 법정동 전수 — 멸실을 직접 관측하려고
    ingest_stock.py         주식 지수 일봉(stock.db)·FRED 금리(macro.db) — 받을 때마다 종가·하루 변화 검사
    probe_stock_crosscheck.py  지수 종가를 비공식(야후)과 맞춰 본다(네트워크 — 검진 밖)
    verify_lookahead.py     지수 예측이 기점 뒤 값을 바꿔도 그대로인지(미래를 보지 않는지)
    verify_index_effects.py 지표 영향의 95% 범위가 참값을 덮는지·헛짚음·발표 시차 (합성 자료)
    verify_short_rules.py   단기 기법·패턴 신호가 미래를 안 보는지·비용·기저율 범위·지표가 synth.js 와 같은지 (합성 자료)
    verify_stock_reflect.py 종목 반영 분해 — nnls = 부동산 nnls_cd, 몫이 합쳐지는지, 80% 범위가 참값을 80% 안팎 덮는지, 그날 알던 실적
    verify_tech_value.py    12개월 이익(4분기 차·고쳐진 값·빠진 분기)·베타·가치 분해가 파이썬 식 = model.js·역산이 몫을 0 으로
    verify_valuation.py     지수 평가가 미래(발표 시차 포함)를 안 보는지·범위가 5% 안팎인지·CAPE 가 실러 열과 같은지
    export_static.py        정적 사이트용 스냅샷
    build_sgg_shapes.py     행정동 경계 → 시군구 지도 경로(frontend/src/realestate/topics/sgg_shapes.json)
    seed_stations.py        역 테이블 + 강남 접근성 (수기 관리)
    route_walk.py           단지↔역 도보 경로 (TMap, 없으면 추정치)
    ingest_trades.py        실거래 적재
    geocode.py              좌표·역거리 채우기
    geocode_dongs.py        동별 좌표·도보시간
    fetch_complexes.py      카카오 POI 로 단지 목록 채우기
    verify_sync.py          경계를 넘는 싱크(코드↔문서↔데이터↔프론트)
    doc_index.py            지침서(CLAUDE.md)가 어디 있나 — 검사들이 같은 목록을 쓴다
    checkup.py              정기 검진 — 정합성·신선도·군살 (입구 하나). --no-db 는 CI 용
    merge_gate.py           머지 관문 — `gh pr merge` 앞 훅. CI 통과 + PR 워크트리의 checkup --fast
    verify_sync_guard.py    그 싱크 검사가 깨뜨렸을 때 걸리는지
    ingest_amenity.py       단지 주변 입지(학교 거리·학원 수·유흥주점 수)
frontend/
  src/App.jsx               머리말·자산 고르기 — 자산마다의 탭을 조립만 한다(ASSETS)
  src/api.js                API 호출 + 정적 모드의 스냅샷 경로(snapshotPath — export_static 과 같은 규칙)
  src/shared/               자산과 무관한 화면 부품 — 자산 폴더는 여기를 쓰고, 여기는 자산 폴더를 모른다
  src/shared/Charts.jsx     IQR 범위+중앙값 점, 층 프리미엄 막대, 추이 선
  src/shared/heat.js        평균 대비 위치(z)의 색·말 — 탭 공통의 자 (백엔드 regime.hist_z 와 같은 공식)
  src/realestate/CLAUDE.md  백엔드 쪽 부동산 지침서를 `@` 로 가져오는 한 줄
  src/realestate/tabs.jsx   부동산의 탭 — 이름·순서·정적 여부와 각 탭이 그리는 화면(render)이 한 곳에
  src/realestate/views/     매물 분석 / 가격 분석 / 공급 분석 / 거시 분석 / 매매·전세·월세 / 단지 상세
                            / 호가 입력 / 호가 분석 / 지도 / 분해 모델 / 집 구하기
  src/realestate/lib/buyGuide.js            집 구하기 탭의 단계·항목 목록 — 출처와 일부러 안 적은 숫자가 머리 주석에
  src/realestate/components/ScatterFit.jsx   산점도 + 적합 곡선 + 신뢰밴드 + 시드 참값 점선
  src/realestate/components/KakaoMap.jsx     카카오맵 래퍼 (CustomOverlay 마커 → 다크모드 자동)
  src/realestate/components/ModelFormula.jsx 분해 모델 맨 위 수식 — 항을 누르면 그 항의 계수·추정 방법
  src/realestate/topics/    같은 주제는 창 하나 — registry.js 가 주제와 그 집(탭)을 정한다
  src/realestate/topics/RegionMap.jsx        시군구 지도 — 가격 분석 지표를 한 달의 색으로(경계는 sgg_shapes.json)
  src/stock/CLAUDE.md       백엔드 쪽 주식 지침서를 `@` 로 가져오는 한 줄
  src/stock/tabs.jsx        주식의 탭 — 지수 분석(옛 id indices 는 App.jsx TAB_ALIAS)
  src/stock/techniques/      기법 저장소 — long.js·short.js(기법 목록·글·예시), synth.js(합성 가격·지표 계산)
  src/stock/views/TechniqueView.jsx  장기 투자·단기 매매 두 탭이 같이 쓰는 저장소 화면
  src/stock/components/TechniqueModal.jsx  기법 설명 창 · ExampleChart.jsx 예시 그림(선·캔들·띠·표시·아래 칸)
  src/stock/components/LiveSection.jsx    창의 '실제 지수에서' — 지금 상태·신호 뒤 성적·규칙대로 vs 사서 들고 있기
  src/stock/views/TechValueView.jsx   기술주 가치 — 시가총액 분해 막대·기대 기술 표(가정·역산·실현 때 주가)·주가 그림
  src/stock/techvalue/model.js   가치 분해 계산(지금 사업·기술의 지금 값·역산·실현 때 주가) — 화면에서 시나리오를 바꿔 본다
  src/stock/components/ValuationSection.jsx   장기 지수 평가 창의 '실제 지수에서' — 지금 값·역사 백분위·백분위 칸별 뒤 5·10년 수익
  src/stock/components/EffectModal.jsx   지표 카드를 누르면 — 산점도·오른/내린 시기·앞뒤 절반·함께 넣은 값
  src/stock/components/ForecastCard.jsx  접힌 구간 예측 카드(후보별 성적표·실제 대 구간 그림)
  src/stock/views/IndexView.jsx   지표 카드(상식의 방향 · 잰 값과 95% 범위 띠 · 맞는지) + 지수마다 접힌 예측 카드
```

차트 라이브러리는 쓰지 않는다. 백엔드가 곡선을 50점 가까이 조밀하게 보내므로 보간기가
필요 없고, 축·틱·툴팁은 `Charts.jsx` 의 기존 헬퍼를 그대로 쓴다. 마커를 `Marker` 가 아니라
`CustomOverlay`(DOM 노드)로 그리는 것도 같은 이유다 — CSS 커스텀 프로퍼티를 상속해
다크모드가 테마 어댑터 없이 따라온다.

## 자산 구조

부동산 전용으로 자란 저장소에 주식을 더하기 전에 정했다(2026-11). 규모가 커지면
에이전트가 **한 자산 안에서 범위를 좁혀** 일할 수 있어야 하고, 자산끼리 어긋나는 것은
검사가 잡아야 한다.

- **자산마다 패키지 하나, 배치는 대칭.** 백엔드 `app/<자산>/`, 화면 `src/<자산>/`, DB 파일도
  자산마다 하나. 자산끼리는 import 하지 않는다. 같이 쓰는 것은 `app/core`·`src/shared` 에
  둔다. 층별 폴더(`app/routers`·`services`)를 자산이 나눠 쓰던 때는 주식 파일이 부동산 파일
  사이에 끼어 '이 폴더의 무엇이 내 일인가' 를 매번 다시 가려야 했을 것이다.
- **겹치면 그때 뽑는다.** 처음부터 공통 계층을 설계하지 않는다. 두 번째 자산이 같은 것을
  실제로 쓰기 시작할 때 뽑는다. 거시 계열(금리·통화량)처럼 두 자산이 같은 원천을 읽게 되면
  두 자산 밖의 패키지로 옮긴다. 거시가 처음이었다 — 한국은행 계열을 `app/macro` 와 `macro.db`
  로 꺼냈다(2026-11). 한국부동산원 계열은 시군구별이고 부동산만 써서 apt.db 에 남겼다.
  옮기기 전후 정적 내보내기를 파일마다 바이트로 견줘 같았다.
- **DB 파일은 apt.db 옆에 둔다.** `MACRO_DATABASE_URL` 이 비면 `DATABASE_URL` 이 가리키는
  apt.db 와 같은 폴더의 macro.db 다. 워크트리·머지 관문은 `DATABASE_URL` 하나로 본 저장소의
  DB 를 가리키는데, 거시만 워크트리의 빈 `data/` 를 보면 화면이 '적재 전' 으로 조용히 빈다.
- **탭은 자산의 `tabs.jsx` 가 정한다.** 이름·순서·정적 여부·화면이 한 곳에 있고 `App.jsx`
  는 조립만 한다. 탭 id 는 자산을 건너 겹치지 않는다 — 주소 `#탭` 만으로 자산이 정해진다.
- **지침서도 계층이다.** 루트 `CLAUDE.md` 는 자산과 무관한 방식만, 자산 폴더의 `CLAUDE.md`
  는 그 자산의 라우팅 표와 규칙을 든다. 프론트 쪽은 백엔드 쪽을 `@` 로 가져오는 한 줄이다
  — 같은 글을 두 곳에 두면 한쪽만 고쳐진다. `scripts/doc_index.py` 가 지침서 목록을 들고,
  `verify_docs` 가 지침서를 합쳐 docs 를 다 덮는지와 루트에서 닿는지를 본다.
- **자산 이름은 그 자산의 것이다.** 다른 자산에서 같은 낱말을 도메인 개념에 쓰지 않는다
  ([용어집](glossary.md)). `verify_sync` 가 잡는다.
- **`backend/scripts/` 는 옮기지 않았다.** 명령(`python -m scripts.…`)이 문서 곳곳에 있고
  `checkup` 이 경로로 검사를 찾는다. 옮길 때 얻는 것보다 깨지는 것이 많다.
- **테스트 틀(pytest)을 들이지 않는다.** `verify_*` 규약이 이미 '찾아서 돈다' 를 하고 있다.
- **결정 경위는 그 묶음의 문서에 적는다.** 결정 기록(ADR) 폴더를 따로 두지 않는다 — 혼자와
  에이전트가 일하는 저장소라 사람용 절차는 비용만 남는다.

## 라우터는 얇게

라우터는 **요청을 받아 서비스에 넘기고, 서비스의 실패를 상태 코드로 바꾼다.** 해석
규칙·집계·여러 테이블을 엮는 조립은 서비스에 둔다.

한 번 어긋났다. `realestate/routers/model.py` 가 붙여넣은 매물을 단지·평형에 맞추는 규칙 260줄을
품고 있었고(`_resolve_area`·`_resolve_by_dong` 등), `realestate/routers/quotes.py` 는 쌓인 호가에
비고·메모 태그·민간임대 표시를 붙이는 조립 80줄을 품고 있었다. 면적 맞추는 규칙을
고치려면 HTTP 파일을 열어야 했고, 같은 규칙을 스크립트에서 쓰려면 라우터를 import
해야 했다. 지금은 `realestate/services/listing_match.py`·`ranking.rank_saved` 로 옮겼다 — 옮기기
전후 응답 13종(붙여넣기 1,157건 포함)을 바이트 단위로 대조해 같았다.

**한 행을 읽고 쓰는 단순한 CRUD 는 라우터에 둔다**(비고 쓰기, 태그 켜고 끄기, 민간임대
표시). 그것까지 서비스로 옮기면 파일만 늘고 읽을 곳이 둘이 된다. 기준은 '줄 수' 가
아니라 **HTTP 를 몰라도 되는 규칙이 있느냐**다.
