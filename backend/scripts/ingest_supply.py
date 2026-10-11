"""공급 통계(인허가·착공·준공·멸실·가구수)를 받아 `reb_stats` 에 넣는다.

사용법:
    python -m scripts.ingest_supply
    python -m scripts.ingest_supply --metric done --metric start

## 왜 시도 단위인가

가격 표는 시군구까지 오지만 **공급 표는 대부분 시도까지만** 온다(738개 표를 훑어
확인했다. 미분양만 시군구가 있다). 서울·경기 두 줄로 본다 — 수도권 공급이 넘치면
서울 외곽부터 빠지므로 둘을 같이 봐야 한다.

## 테이블을 새로 만들지 않는다

`reb_stats` 가 (지역, 지표, 시점) long 구조라 그대로 들어간다. 시도는 `sgg_cd` 에
`11`(서울)·`41`(경기)로, 연 단위는 `ym` 을 `YYYY00` 으로 둔다 — 6자리를 지키면서
월과 섞이지 않고 문자열 정렬이 그대로 시간 순서가 된다.

## 조용히 틀리지 않게

- **0건을 성공으로 넘기지 않는다.** 지표·지역별 건수를 찍고 하나라도 0이면 종료
  코드를 1로 올린다. 공표 통계가 표를 갈아 치우면 경로가 안 맞아 0건이 되는데,
  그건 오류가 아니라 빈 결과로 지나간다(가격 표에서 이미 겪었다).
- 경로는 박지 않고 `sido_cls_id` 가 표마다 조회한다. 후보가 없으면 실패시킨다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.clients import reb  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import RebStat  # noqa: E402


def upsert(db, points: list[reb.RebPoint], base: str = "", source: str = "REB") -> int:
    """같은 (지역·지표·시점)이 다시 오면 값을 갱신한다.

    공표 통계는 공표 후에도 수정된다(잠정 → 확정). '있으면 건너뛴다' 로 두면 옛
    잠정치가 영원히 남는다 — `ingest_reb` 와 같은 이유, 같은 방식이다.
    """
    rows = [
        {
            "sgg_cd": p.sgg_cd, "metric": p.metric, "ym": p.ym, "value": p.value,
            "region_name": p.region_name[:60], "unit": p.unit[:16], "base": base[:40],
            "source": source,
        }
        for p in points if p.ym and p.sgg_cd
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
    ap = argparse.ArgumentParser(description="공급 통계 적재")
    ap.add_argument("--metric", action="append", help="지표 이름(반복 가능)")
    args = ap.parse_args()

    if not reb.available():
        print("REB_SERVICE_KEY 가 없습니다. backend/.env 를 확인하세요.")
        return 1

    want = set(args.metric or [])
    todo = [
        (tid, meta) for tid, meta in reb.SUPPLY_TABLES.items()
        if not want or meta[0] in want
    ]
    if want and not todo:
        print(f"모르는 지표: {sorted(want)} — "
              f"있는 것: {sorted(m[0] for m in reb.SUPPLY_TABLES.values())}")
        return 1

    total = 0
    problems: list[str] = []
    with SessionLocal() as db:
        for tid, (metric, _itm, cycle) in todo:
            print(f"\n{metric}  ({cycle})")
            for sgg, name in reb.SIDO.items():
                try:
                    pts = reb.fetch_sido(tid, sgg)
                except reb.RebError as exc:
                    print(f"  [X] {name:<4} {exc}")
                    problems.append(f"{metric}/{name}: {exc}")
                    continue
                n = upsert(db, pts)
                total += n
                if n:
                    lo = min(p.ym for p in pts)
                    hi = max(p.ym for p in pts)
                    print(f"  [O] {name:<4} {n:>4}건  {lo}~{hi}  ({pts[0].unit})")
                else:
                    # 빈 결과는 조용하다. 반드시 적는다.
                    print(f"  [!] {name:<4} 0건")
                    problems.append(f"{metric}/{name}: 0건")
                time.sleep(0.1)
            db.commit()

    print(f"\n총 {total:,}행 반영")
    if problems:
        print(f"\n확인이 필요한 것 {len(problems)}건:")
        for p in problems:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
