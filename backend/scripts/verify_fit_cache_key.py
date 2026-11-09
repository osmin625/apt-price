"""적합 캐시 키가 적합 표본을 정하는 것을 전부 담는지.

사용법:
    python -m scripts.verify_fit_cache_key

## 왜 있나

캐시 키가 표본을 정하는 것 중 하나라도 빠뜨리면, 그것이 바뀌어도 **옛 적합**이
나간다 — 오류 없이, 화면도 멀쩡히. 두 번 그랬다.

- 날짜. 표본은 `date.today() - 31*months` 로 자르는데 키에 날짜가 없어, 실거래 적재가
  멈춘 2026-10-16 ~ 11-08 동안 옛 창의 적합이 나갔다.
- 거래 밖의 입력. 날짜를 넣은 뒤에도 키는 거래만 봐서, 새 단지 8곳에 도보경로·입지를
  채워도 그 단지가 빠진 적합이 나갔다(2026-11-09, 표본 67,504 vs 67,531). 이 검사의
  첫 판은 그것을 못 봤다 — 거래와 날짜만 시험했기 때문이다.

## 무엇을 보나

1. 키가 날짜를 받는다.
2. **메모리 SQLite 에 행을 넣고** 적재가 하는 일을 하나씩 해 본다 — 거래 추가, 거래 유형
   채우기, 좌표·도보시간 채우기, 입지 행 추가, 동 도보시간 채우기, 역의 강남 접근 고치기.
   그때마다 키가 바뀌어야 한다. 아무것도 안 바꾸면 키가 같아야 한다(캐시가 쓸모 있으려면).
3. `hedonic.load_rows` 가 읽는 `모델.열` 을 소스에서 뽑아, `input_stamp` 가 그 열을 담거나
   `STAMP_SKIP` 에 이유와 함께 있는지 본다. 열을 더하고 도장을 잊으면 여기서 걸린다.
4. `hedonic` 이 여전히 오늘 날짜로 표본을 자르는지(키가 날짜를 담는 이유).
"""

from __future__ import annotations

NEEDS_DB = False  # 메모리 SQLite 에 씨앗을 심어 본다 — checkup --no-db(CI)가 이것으로 거른다

import inspect
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, update  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.realestate.models import (  # noqa: E402
    Base, Complex, ComplexAmenity, ComplexDong, Station, Trade,
)
from app.realestate.services import hedonic, model_view  # noqa: E402

D1, D2 = date(2026, 11, 8), date(2026, 11, 9)


def _seed(db: Session) -> None:
    db.add(Station(id=1, name="역", line="1호선", minutes_to_gangnam=40))
    db.add(Complex(id=1, name="가", name_key="가", sgg_cd="41117", lat=37.1, lng=127.1, walk_seconds=600,
                   nearest_station_id=1, household_count=500))
    db.add(Complex(id=2, name="나", name_key="나", sgg_cd="41117"))  # 새 단지 — 좌표·도보·입지가 아직 없다
    db.add(Trade(id=1, complex_id=1, deal_date=D1, deal_ym="202611", exclusive_area=84.9,
                 deal_amount=90000))
    db.add(ComplexDong(complex_id=1, dong="101동"))
    db.commit()


# 적재가 실제로 하는 일. 각각 키를 바꿔야 한다.
STEPS = [
    ("거래가 추가됨", lambda db: db.add(Trade(id=2, complex_id=2, deal_date=D1, deal_ym="202611",
                                         exclusive_area=59.9, deal_amount=60000))),
    ("거래 유형을 나중에 채움", lambda db: db.execute(update(Trade).values(deal_type="중개거래"))),
    ("새 단지에 좌표를 채움", lambda db: db.execute(
        update(Complex).where(Complex.id == 2).values(lat=37.2, lng=127.2))),
    ("새 단지에 도보시간을 채움", lambda db: db.execute(
        update(Complex).where(Complex.id == 2).values(walk_seconds=900))),
    ("새 단지에 입지 행을 더함", lambda db: db.add(
        ComplexAmenity(complex_id=2, elem_dist_m=300, mid_dist_m=700, academy_500=5, adult_500=0))),
    ("동 도보시간을 채움", lambda db: db.execute(
        update(ComplexDong).values(walk_seconds=420))),
    ("역의 강남 접근을 고침", lambda db: db.execute(
        update(Station).values(minutes_to_gangnam=35))),
]


def check_steps() -> list[tuple[str, bool]]:
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    out = []
    with Session(eng) as db:
        _seed(db)
        key = lambda d=D1: model_view._cache_key(db, 12, "m", d)  # noqa: E731
        out.append(("같은 날·같은 입력이면 키가 같다", key() == key()))
        out.append(("날짜가 바뀌면 키가 다르다", key(D1) != key(D2)))
        for name, step in STEPS:
            before = key()
            step(db)
            db.commit()
            out.append((name, key() != before))
    return out


def check_columns() -> tuple[bool, list[str]]:
    """load_rows 가 읽는 `모델.열` 이 도장에 있거나 이유와 함께 빠졌는지."""
    models = r"(Trade|Complex|ComplexAmenity|ComplexDong|Station)"
    read = set(re.findall(models + r"\.(\w+)", inspect.getsource(hedonic.load_rows)))
    # 엔티티째 읽는 표(`select(Station)` 등)는 load_rows 가 쓰는 속성으로 본다
    read |= {("Station", a) for a in re.findall(r"stations\[\w+\]\.(\w+)|near\.(\w+)",
                                                  inspect.getsource(hedonic.load_rows))
             for a in a if a}
    read |= {("ComplexAmenity", a) for a in re.findall(r"a\.(\w+)",
                                                         inspect.getsource(hedonic.load_rows))
             if a != "complex_id"}
    read |= {("ComplexDong", a) for a in re.findall(r"d\.(\w+)",
                                                      inspect.getsource(hedonic.load_rows))
             if a not in {"complex_id", "dong"}}
    stamp_src = inspect.getsource(hedonic.input_stamp)
    missing = sorted(f"{m}.{c}" for m, c in read
                     if c not in {"id", "complex_id"}
                     and f"{m}.{c}" not in stamp_src and f"{m}.{c}" not in hedonic.STAMP_SKIP)
    return not missing, missing


def main() -> int:
    if "today" not in inspect.signature(model_view._cache_key).parameters:
        print("  날짜를 받는다                                     실패")
        print("\n[X] model_view._cache_key 가 날짜를 받지 않습니다 — 날짜가 바뀌어도 옛 창의 적합이 나갑니다")
        return 1
    if not hasattr(hedonic, "input_stamp"):
        print("\n[X] hedonic.input_stamp 가 없습니다 — 캐시 키가 거래 밖의 입력을 보지 않습니다")
        return 1

    checks = check_steps()
    cols_ok, missing = check_columns()
    checks.append(("load_rows 가 읽는 열을 도장이 다 담는다", cols_ok))
    checks.append(("hedonic 이 오늘 날짜로 표본을 자른다(키가 날짜를 담는 이유)",
                   "date.today() - timedelta(days=31 * months)" in inspect.getsource(hedonic)))
    ok = True
    for name, good in checks:
        print(f"  {name:<40} {'통과' if good else '실패'}")
        ok &= good
    for m in missing:
        print(f"      도장에 없음: {m} — input_stamp 에 넣거나 STAMP_SKIP 에 이유를")
    if not ok:
        print("\n[X] 적합 캐시 키가 표본을 정하는 것을 다 담지 않습니다 — hedonic.input_stamp")
        return 1
    print("\n전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
