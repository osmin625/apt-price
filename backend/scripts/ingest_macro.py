"""거시 요인(미분양·심리·가계대출·금리)을 받아 `reb_stats` 에 넣는다.

사용법:
    python -m scripts.ingest_macro
    python -m scripts.ingest_macro --metric unsold

## 왜 R-ONE 인가

한국은행 ECOS 키를 따로 받아야 하는 줄 알았는데, 공급 표를 찾느라 738개를 훑다가
**금리·가계대출·심리·미분양이 전부 R-ONE 안에** 있는 것을 봤다. 지금 키로 받는다.
ECOS 가 필요한 것은 M2·기준금리·소비자물가뿐이고 그쪽은 `clients/ecos.py` 가
맡는다.

## 지역 수준이 섞인다

- 미분양·심리: 서울·경기(시도)
- 가계대출·금리: 전국(`sgg_cd='00'`)

우리 가격지수는 **경기 남부 17개 구**인데 요인은 더 넓다. 좁힐 수 없어서 그런
것이고(미분양·이동자수 표는 시 단위까지만 온다), 섞어 쓰는 것을 화면에 적는다.
짐작으로 경기 전체를 경기 남부처럼 부르지 않는다.

## 조용히 틀리지 않게

**0건을 성공으로 넘기지 않는다.** 경로를 못 찾으면 `macro_cls_id` 가 끊고, 받아 온
건수가 0이면 종료 코드를 1로 올린다. 공표 통계가 표를 갈아 치우면 오류가 아니라
빈 결과로 지나간다 — 가격 표와 공급 표에서 이미 두 번 겪었다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients import ecos, reb  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from scripts.ingest_supply import upsert  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="거시 요인 적재")
    ap.add_argument("--metric", action="append",
                    choices=sorted(set(reb.MACRO_TABLES) | set(ecos.TABLES)),
                    help="지정하지 않으면 전부")
    args = ap.parse_args()

    if not reb.available():
        print("[X] REB_SERVICE_KEY 가 없습니다. backend/.env 를 보세요.")
        return 1

    metrics = args.metric or sorted(set(reb.MACRO_TABLES) | set(ecos.TABLES))
    bad = 0
    if not ecos.available() and set(metrics) & set(ecos.TABLES):
        print("  [!] ECOS_API_KEY 가 없어 sample 키로 받습니다 — "
              "10행씩이라 느리고 정식 경로가 아닙니다. "
              "backend/.env.example 을 보세요.")
    with SessionLocal() as db:
        for metric in sorted(set(metrics) & set(ecos.TABLES)):
            t0 = time.perf_counter()
            try:
                pts = ecos.fetch(metric)
            except ecos.EcosError as exc:
                print(f"  [X] {metric:<13} 00   {exc}")
                bad += 1
                continue
            # ECOS 점을 RebPoint 모양으로 옮겨 같은 upsert 를 쓴다. 표가 하나면
            # 화면도 한 곳만 보면 된다 — 출처는 `source` 로 구분한다.
            rows = [reb.RebPoint(table_id=ecos.TABLES[metric][0], metric=metric,
                                 sgg_cd="00", cls_id="", region_name="전국",
                                 ym=p.ym, value=p.value, unit=p.unit) for p in pts]
            n = upsert(db, rows, source="ECOS")
            db.commit()
            print(f"      {metric:<13} 00   {n:>4}행  {pts[0].ym}~{pts[-1].ym}"
                  f"  {time.perf_counter() - t0:.1f}s")

        if "unsold" in metrics:
            # 경기 남부 8개 시 합. 공급 표는 시도까지만 오지만 **미분양만 시 단위가
            # 있다** — 738개를 훑어 확인했다. 우리가 보는 지역에 가장 가까운 줄이다.
            t0 = time.perf_counter()
            try:
                pts = reb.fetch_unsold_south()
                n = upsert(db, pts)
                db.commit()
                print(f"      {'unsold':<13} {reb.SOUTH_GG_CODE}  {n:>4}행  "
                      f"{pts[0].ym}~{pts[-1].ym}  {time.perf_counter() - t0:.1f}s")
            except reb.RebError as exc:
                print(f"  [X] unsold        {reb.SOUTH_GG_CODE}  {exc}")
                bad += 1

        for metric in sorted(set(metrics) & set(reb.MACRO_TABLES)):
            for sgg_cd in reb.MACRO_TABLES[metric][2]:
                t0 = time.perf_counter()
                try:
                    pts = reb.fetch_macro(metric, sgg_cd)
                except reb.RebError as exc:
                    print(f"  [X] {metric:<13} {sgg_cd}  {exc}")
                    bad += 1
                    continue
                n = upsert(db, pts)
                db.commit()
                span = f"{pts[0].ym}~{pts[-1].ym}" if pts else "없음"
                mark = "[X]" if not pts else "   "
                print(f"  {mark} {metric:<13} {sgg_cd}  {n:>4}행  {span}"
                      f"  {time.perf_counter() - t0:.1f}s")
                if not pts:
                    bad += 1

    print("\n이상 없음" if not bad else f"\n[X] 비었거나 실패한 것 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
