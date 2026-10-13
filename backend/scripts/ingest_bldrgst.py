"""건축물대장 표제부를 법정동 전수로 받아 `bld_units` 에 담는다.

사용법:
    python -m scripts.ingest_bldrgst                 # 17개 구 전부(40분쯤)
    python -m scripts.ingest_bldrgst --district 41290
    python -m scripts.ingest_bldrgst --count-only    # 건수만 세고 적재는 안 한다
    python -m scripts.ingest_bldrgst --resume        # 오늘 안 받은 법정동만

## 왜 받나

멸실이 **시군구로 공표되지 않는다.** R-ONE·KOSIS·통계누리 셋 다 시도 단위다
(통계누리 뷰어의 내부 JSON 을 직접 열어 20행 = 전국·수도권·지방 + 시도 17개인 것을
확인했다). 멸실의 법적 정의가 '건축물대장 말소' 이므로, 전수를 해마다 떠서 사라진
건축물을 세면 우리가 직접 관측할 수 있다.

`ingest_kapt_all` 과 같은 구조이고 범위만 넓다 — K-apt 는 의무관리대상 아파트뿐이라
단독주택 멸실을 못 잡는다(2024년 전국 멸실 85,069호 중 단독이 39,169호, 46%).

## 이 API 는 조용히 0 을 돌려준다 — 그래서 두 번 센다

가장 중요한 성질이다. 간헐적으로 빈 결과를 `resultCode: 00`(정상)과 함께 보낸다.
법정동 439개를 두 번 세었더니 **265,799동과 295,324동**이 나왔다(10% 차이). 수원
권선구 세류동(5,565동)이 어떤 호출에서는 0 이었고, 화성 동탄구는 통째로 0 이 나와
'건축물이 없는 구' 로 보였다.

빈 결과를 성공으로 넘기면 **그만큼이 그대로 멸실로 잘못 세어진다.** 그래서

1. 법정동마다 **먼저 총 건수를 받아 둔다**(`expected`)
2. 받은 뒤 `fetched` 와 대조한다. 다르면 그 법정동을 **비교에서 뺀다**
   (`bld_runs` 에 둘 다 남기므로 나중에 판단할 수 있다)
3. 0 이 오면 쉬었다 다시 묻는다. 끝까지 0 이면 그 쪽은 실패로 올린다

## 하루 한도

응답 헤더가 `x-ratelimit-limit: 10000` 을 준다. 전수 한 번이 약 2,700~3,000콜이라
하루 한 번은 넉넉하다. 남은 수를 찍어 두면 중간에 끊길지 미리 보인다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.clients import bldrgst as br  # noqa: E402
from app.clients.molit import DISTRICTS  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import BldRun, BldUnit  # noqa: E402

MANUAL = Path(__file__).resolve().parent.parent / "data" / "manual"


def load_dongs(codes: list[str]) -> list[tuple[str, str, str]]:
    """법정동 목록. **API 가 주지 않아 파일로 둔다**(행정표준코드관리시스템)."""
    found = sorted(MANUAL.glob("bjdong_*.tsv"))
    if not found:
        raise SystemExit(f"[X] {MANUAL} 에 bjdong_*.tsv 가 없습니다. "
                         f"README.md 의 주소에서 받으세요.")
    rows = []
    for line in found[-1].read_text(encoding="utf-8").splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 3 and f[0] in codes:
            rows.append((f[0], f[1], f[2]))
    return rows


def upsert(db, units: list[br.Building], today: str) -> int:
    if not units:
        return 0
    rows = [{
        "pk": u.pk, "sigungu_cd": u.sigungu_cd, "bjdong_cd": u.bjdong_cd,
        "plat_plc": u.plat_plc, "bld_nm": u.bld_nm, "main_purps": u.main_purps,
        "hhld_cnt": u.hhld_cnt, "tot_area": u.tot_area,
        "use_apr_day": u.use_apr_day, "first_seen": today, "last_seen": today,
    } for u in units]
    # **한 번에 다 넣지 않는다.** SQLite 는 한 문장의 바인딩 변수 수에 상한이 있어
    # (컬럼 11개 × 수천 행) 'too many SQL variables' 로 죽는다. 세류동 5,565동에서
    # 겪었다 — 큰 법정동일수록 터지므로 작은 데서 시험하면 안 걸린다.
    CHUNK = 400
    if len(rows) > CHUNK:
        n = 0
        for i in range(0, len(rows), CHUNK):
            n += _upsert_chunk(db, rows[i:i + CHUNK])
        return n
    return _upsert_chunk(db, rows)


def _upsert_chunk(db, rows: list[dict]) -> int:
    stmt = sqlite_insert(BldUnit).values(rows)
    # `first_seen` 은 건드리지 않는다 — 처음 본 날이 바뀌면 언제부터 있었는지를 잃는다.
    stmt = stmt.on_conflict_do_update(
        index_elements=["pk"],
        set_={k: getattr(stmt.excluded, k) for k in
              ("sigungu_cd", "bjdong_cd", "plat_plc", "bld_nm", "main_purps",
               "hhld_cnt", "tot_area", "use_apr_day", "last_seen")},
    )
    db.execute(stmt)
    return len(rows)


def record(db, sgg: str, bjd: str, today: str, expected: int, fetched: int) -> None:
    stmt = sqlite_insert(BldRun).values(
        [{"sigungu_cd": sgg, "bjdong_cd": bjd, "taken_on": today,
          "expected": expected, "fetched": fetched}])
    stmt = stmt.on_conflict_do_update(
        index_elements=["sigungu_cd", "bjdong_cd", "taken_on"],
        set_={"expected": stmt.excluded.expected, "fetched": stmt.excluded.fetched})
    db.execute(stmt)


def main() -> int:
    ap = argparse.ArgumentParser(description="건축물대장 표제부 전수 적재")
    ap.add_argument("--district", action="append", help="지정하지 않으면 17개 구 전부")
    ap.add_argument("--count-only", action="store_true", help="건수만 센다")
    ap.add_argument("--resume", action="store_true", help="오늘 안 받은 법정동만")
    args = ap.parse_args()

    if not br.available():
        print("[X] MOLIT_SERVICE_KEY 가 없습니다.")
        return 1

    codes = args.district or list(DISTRICTS)
    dongs = load_dongs(codes)
    today = dt.date.today().strftime("%Y%m%d")
    print(f"법정동 {len(dongs)}개 · {today}")

    with SessionLocal() as db:
        if args.resume:
            done = {(a, b) for a, b in db.execute(
                select(BldRun.sigungu_cd, BldRun.bjdong_cd)
                .where(BldRun.taken_on == today)).all()}
            before = len(dongs)
            dongs = [d for d in dongs if (d[0], d[1]) not in done]
            print(f"  이어받기 — 오늘 받은 {before - len(dongs)}곳 건너뜀")

        t0 = time.perf_counter()
        total_units = mismatch = failed = 0
        rem = None
        for i, (sgg, bjd, name) in enumerate(dongs, 1):
            try:
                if args.count_only:
                    expected, rem = br.count(sgg, bjd)
                    fetched = 0
                else:
                    expected, rem = br.count(sgg, bjd)
                    units, rem = (([], rem) if not expected
                                  else br.fetch_dong(sgg, bjd, expect=expected))
                    fetched = upsert(db, units, today)
                    total_units += fetched
            except br.BldError as exc:
                failed += 1
                print(f"  [X] {name} — {exc}")
                db.commit()
                continue

            record(db, sgg, bjd, today, expected, fetched)
            db.commit()
            if not args.count_only and expected != fetched:
                mismatch += 1
                print(f"  [!] {name}: 기대 {expected} vs 받음 {fetched} "
                      f"— 이 법정동은 비교에서 뺍니다")
            if i % 25 == 0:
                el = time.perf_counter() - t0
                print(f"  {i}/{len(dongs)} · 누적 {total_units:,}동 · {el / 60:.1f}분 "
                      f"(남은 예상 {el / i * (len(dongs) - i) / 60:.0f}분) "
                      f"· 호출 남음 {rem}")

        el = time.perf_counter() - t0
        print(f"\n{total_units:,}동 · 어긋난 법정동 {mismatch}곳 · 실패 {failed}곳 "
              f"· {el / 60:.1f}분 · 호출 남음 {rem}")

        # **오늘도 돌린 법정동에서만 센다.** 오늘 안 돌린 곳의 건축물은
        # `last_seen` 이 당연히 옛 날짜라, 그것을 멸실이라 하면 안 돌린 것이
        # 멸실로 둔갑한다. 기대와 받은 수가 어긋난 법정동도 뺀다 — 반쯤 받은
        # 법정동은 그 차이가 그대로 거짓 멸실이 된다.
        prior = {(a, b) for a, b in db.execute(
            select(BldRun.sigungu_cd, BldRun.bjdong_cd)
            .where(BldRun.taken_on < today).distinct()).all()}
        now_ok = {(a, b) for a, b in db.execute(
            select(BldRun.sigungu_cd, BldRun.bjdong_cd)
            .where(BldRun.taken_on == today,
                   BldRun.expected == BldRun.fetched).distinct()).all()}
        both = prior & now_ok
        if both and not args.count_only:
            gone = db.execute(
                select(BldUnit).where(BldUnit.last_seen < today)).scalars().all()
            gone = [u for u in gone if (u.sigungu_cd, u.bjdong_cd) in both]
            seats = sum(u.hhld_cnt or 0 for u in gone)
            house = [u for u in gone if u.main_purps in ("단독주택", "공동주택")]
            print(f"  두 번 돌린 법정동 {len(both)}곳 기준 — 사라진 건축물 "
                  f"{len(gone):,}동(그중 주택 {len(house):,}동 · {seats:,}세대)")
        else:
            print("  첫 스냅샷입니다 — 멸실은 다음 실행부터 셉니다.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
