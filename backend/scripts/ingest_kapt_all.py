"""K-apt 의 의무관리대상 공동주택을 **시군구 전수**로 받아 `kapt_units` 에 담는다.

사용법:
    python -m scripts.ingest_kapt_all              # 17개 구 전부
    python -m scripts.ingest_kapt_all --district 41290
    python -m scripts.ingest_kapt_all --list-only  # 목록만(기본정보 생략)

## `ingest_kapt` 와 무엇이 다른가

`ingest_kapt` 는 K-apt 세대수를 **우리가 가진 단지에 붙인다.** 이름이 정확히 맞는
것만 붙이므로(잘못 붙이면 모델이 조용히 틀어진다) 2,472곳 중 847곳(34%)만
채워져 있다.

이 스크립트는 **붙이지 않는다.** 시군구 코드로 목록을 통째로 받아 그대로 담는다.
공급량을 세는 데는 매칭이 필요 없기 때문이다 — 사용승인 연도별 세대수를 더하면
된다. 경기 남부 17개 구에 1,945곳이 있다(재서 확인했다).

## 왜 두 번 부르나

목록(`getSigunguAptList4`)은 단지 코드와 이름만 준다. 세대수와 사용승인일은
기본정보(`getAphusBassInfoV5`)를 단지마다 따로 불러야 나온다. 1,945곳이면
11~26분이다. 길어서 백그라운드로 돌리고 DB 행 수로 진척을 본다.

## 다시 돌려도 안전하다

`kapt_code` 로 upsert 한다. 중간에 끊겨도 이어서 돌리면 되고, 기본정보가 갱신되면
덮어쓴다. `--list-only` 로 목록만 먼저 채운 뒤 기본정보를 나중에 채울 수도 있다.

## 빈 값을 0 으로 채우지 않는다

분양 중이거나 자료가 덜 들어간 단지는 세대수가 0 으로 온다(과천포레하임 2026년).
0 을 그대로 '0세대' 로 저장하면 집계가 조용히 작아지므로 **비워 둔다**. 집계할 때
몇 곳이 비었는지 같이 센다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.dialects.sqlite import insert as sqlite_insert  # noqa: E402

from app.clients.kapt import KaptError, KaptNotSubscribed, basis_info, list_complexes  # noqa: E402
from app.clients.molit import DISTRICTS  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import KaptUnit  # noqa: E402

# 목록 한 페이지. K-apt 가 100을 넘겨도 받아 주지만 100으로 끊어 받는 쪽이
# 끊겼을 때 다시 받는 양이 적다.
PAGE = 100


def fetch_list(sgg_cd: str) -> list[dict]:
    """한 시군구의 단지 목록 전부.

    `is_last` 를 믿되 **페이지 상한도 둔다** — 끝 판정이 틀리면 무한히 돈다.
    17개 구 중 가장 많은 곳이 233곳이라 20페이지면 넉넉하다.
    """
    out: list[dict] = []
    for page in range(1, 21):
        items, last = list_complexes(sgg_cd, page=page, rows=PAGE)
        out += items
        if last or not items:
            break
    return out


def upsert_list(db, sgg_cd: str, items: list[dict]) -> int:
    rows = [
        {
            "kapt_code": str(it.get("kaptCode") or "").strip(),
            "sgg_cd": sgg_cd,
            "name": str(it.get("kaptName") or "").strip()[:80],
        }
        for it in items
        if it.get("kaptCode")
    ]
    if not rows:
        return 0
    stmt = sqlite_insert(KaptUnit).values(rows)
    # 이름만 갱신한다. 기본정보(세대수 등)는 아래에서 따로 채우므로 여기서
    # 덮어쓰면 **이미 받아 둔 값을 지운다.**
    stmt = stmt.on_conflict_do_update(
        index_elements=["kapt_code"],
        set_={"sgg_cd": stmt.excluded.sgg_cd, "name": stmt.excluded.name},
    )
    db.execute(stmt)
    return len(rows)


def fill_basis(db, codes: list[str], quiet: bool = False) -> tuple[int, int]:
    """단지마다 기본정보를 받아 채운다. (채운 수, 실패 수)"""
    done = bad = 0
    for i, code in enumerate(codes, 1):
        try:
            b = basis_info(code)
        except KaptError as exc:
            bad += 1
            if bad <= 3:
                print(f"    [!] {code} {exc}")
            continue
        if b is None:
            bad += 1
            continue
        db.query(KaptUnit).filter(KaptUnit.kapt_code == code).update({
            # 0 은 '없음' 으로 본다. 분양 중인 단지가 0 으로 온다.
            "household_count": b.household_count or None,
            "dong_count": b.dong_count or None,
            "build_year": b.build_year,
            "apt_type": (b.apt_type or "")[:20],
            "address": (b.address or "")[:160],
            # 이름이 비면 **목록에서 받은 이름을 지키도록** 아예 건드리지 않는다.
            # None 을 넣으면 NOT NULL 에 걸린다.
            **({"name": b.name[:80]} if b.name else {}),
        })
        done += 1
        if done % 100 == 0:
            db.commit()
            if not quiet:
                print(f"    {done}/{len(codes)}곳 · {time.strftime('%H:%M:%S')}")
    db.commit()
    return done, bad


def main() -> int:
    ap = argparse.ArgumentParser(description="K-apt 시군구 전수 적재")
    ap.add_argument("--district", action="append", help="지정하지 않으면 17개 구 전부")
    ap.add_argument("--list-only", action="store_true", help="목록만 받고 기본정보는 생략")
    ap.add_argument("--missing-only", action="store_true",
                    help="사용승인연도가 비어 있는 단지만 (끊긴 뒤 이어받기)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    codes = args.district or list(DISTRICTS)
    t0 = time.perf_counter()
    listed = 0

    with SessionLocal() as db:
        for sgg in codes:
            try:
                items = fetch_list(sgg)
            except KaptNotSubscribed as exc:
                print(f"[X] {exc}")
                return 1
            except KaptError as exc:
                print(f"[X] {DISTRICTS.get(sgg, sgg)}: {exc}")
                return 1
            n = upsert_list(db, sgg, items)
            db.commit()
            listed += n
            print(f"  {DISTRICTS.get(sgg, sgg):<16} {n:>4}곳")
            if not n:
                # 0건은 오류가 아니라 빈 결과로 지나간다. 여기서 끊는다.
                print(f"[X] {DISTRICTS.get(sgg, sgg)} 가 0건입니다. 시군구 코드를 확인하세요.")
                return 1

        print(f"\n목록 {listed}곳 · {time.perf_counter() - t0:.0f}초")
        if args.list_only:
            return 0

        # 끊긴 뒤 다시 돌릴 때 1,945곳을 전부 다시 받으면 20분이 또 간다.
        # **이어받기가 기본이 아닌 이유**: 기본정보는 갱신되므로(세대수 정정 등)
        # 아무것도 안 주면 전수를 다시 받는 쪽이 맞다. 이어받기는 명시로 고른다.
        q = db.query(KaptUnit.kapt_code).filter(KaptUnit.sgg_cd.in_(codes))
        if args.missing_only:
            q = q.filter(KaptUnit.build_year.is_(None))
        todo = [c for (c,) in q.all()]
        print(f"기본정보 {len(todo)}곳 받는 중 — 11~26분 걸립니다")
        done, bad = fill_basis(db, todo, quiet=args.quiet)
        print(f"\n기본정보 {done}곳 채움 · 실패 {bad}곳 · 총 {time.perf_counter() - t0:.0f}초")

        have = db.query(KaptUnit).filter(
            KaptUnit.sgg_cd.in_(codes), KaptUnit.household_count.isnot(None)).count()
        yr = db.query(KaptUnit).filter(
            KaptUnit.sgg_cd.in_(codes), KaptUnit.build_year.isnot(None)).count()
        print(f"세대수 있는 단지 {have}/{listed} · 사용승인연도 있는 단지 {yr}/{listed}")
        # 둘 다 70% 를 못 넘으면 집계를 믿을 수 없다. 조용히 작은 값을 내느니 말한다.
        if listed and (have / listed < 0.7 or yr / listed < 0.7):
            print("[X] 채워진 비율이 낮습니다 — 이 값으로 공급량을 세면 과소집계됩니다.")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
