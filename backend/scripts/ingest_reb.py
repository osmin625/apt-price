"""한국부동산원 공표 통계를 받아 `reb_stats` 에 넣는다.

## 무엇을 받나

`reb.TABLES` 의 6개 표 × 대상 시군구 17곳. 전부 월간이다.

    매매가격지수 · 전세가격지수 · 전세가율
    평균매매가격 · 중위매매가격 · 평균단위매매가격(㎡당)

## 조용히 틀리지 않게 하는 것들

- **지역 대조.** `reb.fetch_district` 가 받은 값의 `CLS_FULLNM` 이 우리가 기대한
  시·구로 끝나는지 검산한다. 박아 둔 지역코드가 낡으면 오류가 아니라 **남의 지역
  값**이 들어오기 때문이다(화성시 분구 때 실거래 0건으로 겪은 것과 같은 방식).
- **0건을 성공으로 넘기지 않는다.** 표·지역별 건수를 찍고, 하나라도 0건이면
  종료 코드를 1 로 올린다.
- **없는 값을 만들어 내지 않는다.** 결측 월은 행을 만들지 않는다. 0 으로 채우면
  '그 달 지수가 0' 이라는 거짓이 된다.

## 화성시 분구

만세·효행·병점·동탄구는 **2026년 1월부터**다. 분구 시점에 통계가 새로 시작했다.
이건 결손이 아니라 사실이므로 그대로 넣고, 화면에서 그렇게 보여 준다.

## 사용

    python -m scripts.ingest_reb                 # 전체
    python -m scripts.ingest_reb --since 201501  # 그 이후만
    python -m scripts.ingest_reb --table A_2024_00072
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.clients import reb
from app.clients.molit import DISTRICTS
from app.db import SessionLocal
from app.models import RebStat


def upsert(db, points: list[reb.RebPoint], base: str = "") -> int:
    """같은 (시군구·지표·월)이 다시 오면 값을 갱신한다.

    한국부동산원은 공표 후에도 수치를 **수정한다**(잠정치 -> 확정치). 그래서
    '이미 있으면 건너뛴다' 로 두면 옛 잠정치가 영원히 남는다. 덮어쓴다.
    """
    if not points:
        return 0
    rows = [
        {
            "sgg_cd": p.sgg_cd,
            "metric": p.metric,
            "ym": p.ym,
            "value": p.value,
            "region_name": p.region_name[:60],
            "unit": p.unit[:16],
            "base": base[:40],
        }
        for p in points
        if p.ym and p.sgg_cd
    ]
    if not rows:
        return 0

    stmt = sqlite_insert(RebStat).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["sgg_cd", "metric", "ym"],
        set_={
            "value": stmt.excluded.value,
            "region_name": stmt.excluded.region_name,
            "unit": stmt.excluded.unit,
            "base": stmt.excluded.base,
        },
    )
    db.execute(stmt)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="한국부동산원 통계 적재")
    ap.add_argument("--table", action="append", help="통계표 코드(여러 번 가능)")
    ap.add_argument("--since", default=None, help="시작 YYYYMM")
    ap.add_argument("--until", default=None, help="끝 YYYYMM")
    args = ap.parse_args()

    if not reb.available():
        print("REB_SERVICE_KEY 가 없습니다. backend/.env 를 확인하세요.")
        print("  https://www.data.go.kr/data/15134761/openapi.do")
        return 1

    tables = args.table or list(reb.TABLES)
    unknown = [t for t in tables if t not in reb.TABLES]
    if unknown:
        print(f"모르는 통계표: {unknown}")
        return 1

    # 기준시점은 표 메타에 있다. 한 번만 받아 둔다.
    try:
        meta = reb.table_meta()
    except reb.RebError as exc:
        print(f"통계표 메타를 받지 못했습니다: {exc}")
        meta = {}

    total = 0
    problems: list[str] = []

    with SessionLocal() as db:
        for tid in tables:
            metric = reb.TABLES[tid]
            base = str((meta.get(tid) or {}).get("RPSTUI_NM") or "")
            print(f"\n{tid}  {metric}" + (f"  [{base}]" if base else ""))
            got_any = False

            for sgg, name in DISTRICTS.items():
                try:
                    pts = reb.fetch_district(
                        tid, sgg, start_ym=args.since, end_ym=args.until
                    )
                except reb.RebError as exc:
                    print(f"  [X] {name:<14} {exc}")
                    problems.append(f"{metric}/{name}: {exc}")
                    continue

                n = upsert(db, pts, base)
                total += n
                if n:
                    got_any = True
                    print(f"  [O] {name:<14} {n:>4}건  {pts[0].ym}~{pts[-1].ym}")
                else:
                    # 빈 결과는 조용하다. 반드시 적는다.
                    print(f"  [!] {name:<14} 0건")
                    problems.append(f"{metric}/{name}: 0건")

                time.sleep(0.1)  # 공공 API 에 몰아치지 않는다

            db.commit()
            if not got_any:
                problems.append(f"{metric}: 표 전체가 0건")

    print(f"\n총 {total:,}행 반영")
    if problems:
        print(f"\n확인이 필요한 것 {len(problems)}건:")
        for p in problems:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
