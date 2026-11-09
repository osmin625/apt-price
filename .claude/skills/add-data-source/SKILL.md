---
name: add-data-source
description: 새 외부 데이터 출처(API·공표 통계·손으로 받는 CSV)를 붙인다. 새 client·테이블·적재 스크립트를 만들 때, 기존 출처에서 새 계열을 받기 시작할 때, 비공식 출처를 쓸지 정할 때 쓴다.
---

# 새 데이터 출처 붙이기

순서와 끝난 기준만 적는다. 출처마다의 사정은 그 자산의 data 문서에 있다 — 부동산은
[pipeline.md](../../../docs/data/pipeline.md)·[reb.md](../../../docs/data/reb.md).

## 순서

1. **출처를 고른다.** 공식 API(공공데이터포털·한국은행·DART·EDGAR·FRED 등)를 먼저 쓰고,
   비공식(스크래핑 라이브러리)은 **대조용**으로만 둔다. 무엇을 고르고 무엇을 버렸는지를
   data 문서에 적는다.
2. **client** — `backend/app/<자산>/clients/<출처>.py`. 지켜 온 것:
   - 일시 오류는 재시도한다. K-apt 에서 재시도가 없어 시군구 6곳이 통째로 빠졌다.
   - **0 건을 성공으로 받지 않는다**(`realestate/clients/bldrgst.py`). 빈 응답은 조용하다.
   - 키는 `backend/.env` 에서 `core/config.py` 로 읽고, 이름만 `backend/.env.example` 에
     더한다. 값은 출력하지도 커밋하지도 않는다.
3. **테이블** — 그 자산의 `models.py` 에 더하고 `python -m scripts.migrate` 를 돌린다.
   유니크 키 컬럼은 NULL 대신 `0`/`""`.
4. **적재 스크립트** — `backend/scripts/ingest_<출처>.py`. 실험은 DB **사본**에
   `DATABASE_URL` 을 걸어서 하고, 오래 걸리면 백그라운드로 돌려 행 수로 진척을 본다.
   두 번 돌려도 같은 결과여야 한다(덮어쓰기·upsert).
5. **검사를 코드에 넣는다.** 받은 값을 **기억이 아니라 대조로** 확인한다 — 시군구 코드는
   카카오 `b_code` 앞 5자리, 역 이름은 카카오가 돌려주는 이름(`seed_stations.py` 처럼
   매 실행마다). 비공식 출처가 있으면 같은 값을 맞춰 보는 `verify_*` 를 둔다.
6. **신선도** — `scripts/checkup.py` 의 `STALE` 에 임계값을 **근거와 함께** 더한다
   (공표 주기·신고 기한). 숫자만 있으면 다음 사람이 못 고친다.
7. **문서** — data 문서에 출처·주기·함정을, `architecture.md` 배치도에 client·스크립트를
   한 줄씩. 새 문서를 만들었으면 그 자산 지침서의 라우팅 표에 행을 더한다.

## 끝난 기준

- `backend/` 에서 `python -m scripts.checkup --fast` 통과(빠진 목록은 `verify_sync` 가 잡는다)
- 신선도 절에 새 출처가 찍힌다
- 적재를 두 번 돌려 행 수가 그대로다
- 실제 키로 한 번 받아 본 건수와 기간을 커밋 본문에 적었다
