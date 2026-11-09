# 부동산 — 지침서

경기 남부 아파트의 실거래·호가·공급·거시를 다루는 자산이다. 루트
[CLAUDE.md](../../../CLAUDE.md) 의 방식(추측하지 말고 잰다·대조한다·화면 문구는 시간이 지나도
맞는 것만 …)은 그대로 따르고, 여기에는 **이 자산에만 있는 것**을 적는다.

코드는 이 폴더(`backend/app/realestate/`)와 `frontend/src/realestate/` 에 있다. 프론트
쪽 CLAUDE.md 는 이 파일을 가져오기만 한다 — 같은 글을 두 곳에 두지 않는다.

## 문서를 먼저 고른다

| 묶음 | 하려는 일 | 읽을 것 |
|---|---|---|
| `screens/` 화면 | 화면·기능 동작을 바꾼다 | [screens/design.md](../../../docs/screens/design.md) |
| | 호가를 읽거나 줄 세우는 것을 바꾼다 | [screens/quotes.md](../../../docs/screens/quotes.md) |
| | 그 화면이 왜 그렇게 됐는지 찾는다 | [screens/ui-log.md](../../../docs/screens/ui-log.md) |
| `model/` 추정 | 모델에 요인을 더하거나 뺀다 | [model/factors.md](../../../docs/model/factors.md) |
| | 추정 방법·수식을 건드린다 | [model/method.md](../../../docs/model/method.md) |
| `data/` 출처 | 데이터를 채우거나 지역을 넓힌다 | [data/pipeline.md](../../../docs/data/pipeline.md) |
| | 공표 통계(한국부동산원·한국은행)를 건드린다 | [data/reb.md](../../../docs/data/reb.md) |
| | 경기 남부 공급·멸실을 직접 세는 자료(K-apt·건축물대장 전수, 스냅샷)를 건드린다 | [data/south-supply.md](../../../docs/data/south-supply.md) |
| | 붙여넣은 매물을 단지·평형에 맞추거나 메모를 읽는 규칙을 바꾼다 | [data/listings.md](../../../docs/data/listings.md) |
| `analysis/` 공급·거시·점유 탭 | 공급량 분석을 건드린다 | [analysis/supply.md](../../../docs/analysis/supply.md) |
| | 거시 요인(수요·통화·금리·정책)을 건드린다 | [analysis/macro.md](../../../docs/analysis/macro.md) |
| | 거시 요인을 합친 모델 — 반영 분해(방향 고정)를 바꾸거나, 걷은 예측을 다시 세우려 한다 | [analysis/macro-model.md](../../../docs/analysis/macro-model.md) |
| | 매매·전세·월세 탭(같은 집 월 비용·금리와 세 가격·월세 쏠림·순서)을 건드린다 | [analysis/tenure.md](../../../docs/analysis/tenure.md) |

탭 id 와 화면 이름이 어긋난 곳(`macro` 가 '가격 분석' 이다), 단지 안의 동과 법정동처럼
헷갈리는 이름은 [용어집](../../../docs/engineering/glossary.md) 에 있다.

## 합치는 것보다 못 합치는 게 낫다

단지·매물을 동일시할 때는 보수적으로 간다. 잘못 합치면 남의 거래가 섞여 시세가 통째로
망가지지만, 안 합치면 줄이 하나 더 생길 뿐이다.

- 단지명 유사도 매칭은 **실측으로 폐기했다**(발동한 10건이 전부 오답). 근접 후보는
  기록만 하고 합치지 않는다.
- 두 글자 단지명은 첫 줄에서 동을 뗀 나머지와 **정확히 같을 때만** 인정하고, 같은 이름이
  여럿이면 자동 선택하지 않는다.
- 호가 분석은 같은 층대 매물을 **접을 뿐 합치지 않는다.** 건수 배지와 호버로 전부 보인다.

## 순수 모듈을 지킨다

`realestate/pricing.py` 는 의존성이 없다. 시드 생성기와 회귀 모델이 **같은 함수**를 써야 참값
복원 검증이 성립하기 때문이다. 여기에 DB·numpy 의존을 들이지 말 것.

`realestate/services/hedonic.py` 는 numpy/statsmodels 를 쓰는 유일한 파일이고 지연 import 한다.
미설치 환경에서도 나머지 탭은 동작해야 한다.

## 스키마 변경

`scripts/migrate.py` 가 빠진 컬럼만 `ALTER TABLE ADD COLUMN` 으로 채운다. 모델에 컬럼을
추가했으면 이것을 돌린다. SQLite 의 `UNIQUE` 는 NULL 끼리를 서로 다른 값으로 보므로,
유니크 키에 들어가는 컬럼은 NULL 대신 `0`/`""` 를 쓴다.

## 이름 — 재고는 `housing_stock`

`stock` 은 주식 자산의 이름이다. 주택 재고는 `housing_stock` 으로 쓴다. 이 폴더와
`frontend/src/realestate/` 에서 맨 `stock` 이름이 나오면 `verify_sync` 가 잡는다.
