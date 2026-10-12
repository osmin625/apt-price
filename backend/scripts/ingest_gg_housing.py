"""경기도 시군구별 일반가구수·주택수를 CSV 에서 읽어 `reb_stats` 에 넣는다.

사용법:
    python -m scripts.ingest_gg_housing
    python -m scripts.ingest_gg_housing --file backend/data/manual/gg_housing_YYYYMMDD.csv

## 왜 CSV 인가

한국부동산원 공급 표에는 **시 단위 분류가 하나도 없다**(준공·착공·인허가·가구수·
멸실 전부 0개). 그래서 적정 공급의 분모인 가구 증가를 경기 남부로 내릴 수 없었다.

경기도기본통계(`DT_21002I001`)가 시군구별 일반가구수를 준다. API 는 없고 사람이
내려받아야 한다 — 원자료와 메타자료를 `backend/data/manual/` 에 함께 둔다.

## 받은 값이 맞는지 **매 실행마다** 대조한다

경기 합계 일반가구수를 우리가 이미 가진 R-ONE `households`(시도) 와 맞춰 본다.
같은 통계를 시군구까지 내린 것이므로 **일치해야 한다.** 어긋나면 다른 표를 받아
왔거나 단위가 바뀐 것이다 — 그대로 넣으면 조용히 틀린 값이 들어간다.

## 2021년부터만 넣는다

- 2015~2020 은 시군구 값이 전부 `-` 다(경기 합계만 있다)
- 2008년에 일반가구수 정의가 바뀌고, 2021년에 주택수 출처가 바뀐다

끊긴 구간을 이어 붙이면 가구 증가가 집계 변경을 공급 변화처럼 보이게 한다.
`backend/data/manual/README.md` 에 근거를 적어 두었다.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.clients.molit import DISTRICTS  # noqa: E402
from app.clients.reb import SOUTH_GG_CODE  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import RebStat  # noqa: E402
from scripts.ingest_supply import upsert  # noqa: E402

DEFAULT = Path(__file__).resolve().parent.parent / "data" / "manual"

# 이 해부터만 쓴다. 앞은 정의가 다르거나 비어 있다(위 독스트링 참조).
SINCE = 2021

# CSV 머리글의 지표 코드. 이름이 아니라 코드로 고른다 — 이름에는 단위와 코드가
# 섞여 있어("B001 일반가구수 (14STD03079 가구)") 조금만 바뀌어도 못 찾는다.
HOUSEHOLDS = "B001"
HOUSES = "B002"
APT = "아파트"

# 경기 합계 대조 허용 오차. 같은 통계라 0 이어야 하지만 반올림 한 자리는 봐준다.
TOL_PCT = 0.05


class Point:
    """`upsert` 가 받는 모양(RebPoint)과 같은 필드만 갖춘 가벼운 자리."""

    def __init__(self, metric: str, sgg_cd: str, ym: str, value: float,
                 region_name: str, unit: str) -> None:
        self.metric, self.sgg_cd, self.ym, self.value = metric, sgg_cd, ym, value
        self.region_name, self.unit = region_name, unit


def read_csv(path: Path) -> tuple[list[list[str]], list[str], list[str], list[str]]:
    rows = list(csv.reader(io.StringIO(path.read_bytes().decode("cp949"))))
    if len(rows) < 4:
        raise SystemExit(f"[X] {path} 가 너무 짧습니다({len(rows)}행).")
    return rows, rows[0], rows[1], rows[2]


def pick(years: list[str], metric: list[str], sub: list[str],
         year: str, code: str, want_sub: str = "소계") -> int | None:
    for i in range(2, len(years)):
        if (years[i].endswith(year) and metric[i].startswith(code)
                and (want_sub in sub[i] if want_sub != "소계" else sub[i] == "소계")):
            return i
    return None


def num(row: list[str], i: int | None) -> float | None:
    if i is None or i >= len(row):
        return None
    try:
        return float(row[i].replace(",", ""))
    except ValueError:
        return None  # '-' 와 '...' 가 온다. 0 으로 바꾸지 않는다.


def south_cities() -> list[str]:
    """우리 17개 구가 속한 시. '수원시 영통구' -> '수원시'."""
    return sorted({name.split()[0] for name in DISTRICTS.values()})


def main() -> int:
    ap = argparse.ArgumentParser(description="경기도 시군구 가구수·주택수 적재")
    ap.add_argument("--file", help="지정하지 않으면 manual/ 의 가장 최근 것")
    args = ap.parse_args()

    if args.file:
        path = Path(args.file)
    else:
        found = sorted(DEFAULT.glob("gg_housing_*.csv"))
        if not found:
            print(f"[X] {DEFAULT} 에 gg_housing_*.csv 가 없습니다.")
            return 1
        path = found[-1]
    print(f"  파일 {path.name}")

    rows, years, metric, sub = read_csv(path)
    body = rows[3:]
    cities = south_cities()
    mine = [r for r in body if any(r[1].endswith(c) for c in cities)]
    total = next((r for r in body if r[0].endswith("합계")), None)
    if len(mine) != len(cities) or total is None:
        print(f"[X] 지역 행을 못 찾았습니다 — 우리 시 {len(cities)}개 중 {len(mine)}개, "
              f"합계 행 {'있음' if total else '없음'}")
        return 1

    all_years = sorted({y.split()[1] for y in years[2:] if " " in y})
    use = [y for y in all_years if int(y) >= SINCE]
    print(f"  연도 {all_years[0]}~{all_years[-1]} 중 {use[0]}~{use[-1]} 사용")

    # ── 대조: 경기 합계가 R-ONE 가구수와 같은가 ──────────────────────
    with SessionLocal() as db:
        reb = {ym[:4]: v for ym, v in db.execute(
            select(RebStat.ym, RebStat.value)
            .where(RebStat.metric == "households", RebStat.sgg_cd == "41")).all()}
        bad = 0
        for y in use:
            csv_v = num(total, pick(years, metric, sub, y, HOUSEHOLDS))
            reb_v = reb.get(y)
            if csv_v is None or reb_v is None:
                continue
            gap = abs(csv_v / (reb_v * 1000) - 1) * 100
            mark = "ok" if gap <= TOL_PCT else "[X]"
            print(f"    대조 {y}  CSV {csv_v:>12,.0f} vs R-ONE {reb_v * 1000:>12,.0f}"
                  f"  차이 {gap:.2f}%  {mark}")
            bad += gap > TOL_PCT
        if bad:
            print(f"[X] 경기 합계가 R-ONE 과 어긋납니다({bad}개 연도). "
                  f"다른 통계표를 받았는지 확인하세요.")
            return 1

        # ── 적재: 남부 8개 시 합 ────────────────────────────────────
        name = "경기 남부 " + "·".join(c[:-1] for c in cities)
        points: list[Point] = []
        for y in use:
            for code, sub_want, metric_name, unit in (
                (HOUSEHOLDS, "소계", "households_south", "가구"),
                (HOUSES, "소계", "houses_south", "호"),
                (HOUSES, APT, "houses_apt_south", "호"),
            ):
                i = pick(years, metric, sub, y, code, sub_want)
                vals = [num(r, i) for r in mine]
                if any(v is None for v in vals):
                    missing = [r[1] for r, v in zip(mine, vals) if v is None]
                    print(f"    [!] {y} {metric_name}: 빠진 시 {missing} — 건너뜁니다")
                    continue
                points.append(Point(metric_name, SOUTH_GG_CODE, f"{y}00",
                                    float(sum(vals)), name[:60], unit))
        if not points:
            print("[X] 넣을 값이 없습니다.")
            return 1
        n = upsert(db, points, source="KOSIS")
        db.commit()

    by_metric: dict[str, int] = {}
    for p in points:
        by_metric[p.metric] = by_metric.get(p.metric, 0) + 1
    print(f"\n  {n}행 적재 — " + " · ".join(f"{k} {v}년" for k, v in by_metric.items()))
    print("  이상 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
