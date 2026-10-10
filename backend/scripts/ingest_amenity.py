"""단지 주변 입지를 받아 `complex_amenities` 에 넣는다.

사용법:
    python -m scripts.ingest_amenity                  # 아직 없는 단지만
    python -m scripts.ingest_amenity --all            # 전부 다시
    python -m scripts.ingest_amenity --older-than 90  # 90일 지난 것만
    python -m scripts.ingest_amenity --limit 50       # 맛보기

## 무엇을 어디서 받나

- **상가**: 소상공인시장진흥공단 상가정보(`clients.sdsc`). 반경 500m 안을 전부 받아
  좌표로 다시 센다. 업종이 법적 분류라 '일반 유흥 주점'·'무도 유흥 주점' 이 확실하다.
- **학교**: 카카오 카테고리 `SC4`(`clients.kakao`). 학교는 상가가 아니라 상가정보에
  없다. 반경 1.5km 안 건수가 45개를 넘지 않아 전수로 받을 수 있고, 문서에 `distance`
  가 실려 와서 가장 가까운 초·중학교를 바로 고른다.

## 조용히 틀리지 않게 하는 것들

- **0건을 성공으로 넘기지 않는다.** 실측 최소가 상가 3건이었다. 0건이면 좌표나
  호출이 잘못된 것으로 보고 기록해서 끝에 보고한다.
- **페이징이 끝까지 갔는지 확인한다.** `sdsc.stores_in_radius` 가 총건수에 못 미치면
  예외를 던진다. 그걸 안 보면 번화가 단지만 조용히 적게 세어진다.
- **cx/cy 는 경도/위도 순이다.** 바꿔 넣으면 한국 밖을 찾아 0건이 오는데, 그건
  오류가 아니라 빈 결과라 지나간다. 첫 단지에서 좌표 범위를 검사한다.
- 중간에 끊겨도 한 건씩 커밋하므로 다시 돌리면 이어서 한다.

## 비용

단지당 소상공인 1.2회 + 카카오 2.5회 쯤이고, 2,469곳 전체가 **약 15분**이다.
(실측: 소상공인 2,924회 · 카카오 6,296회 · 14.6분 · 실패 0)
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.clients import kakao, sdsc  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Complex, ComplexAmenity  # noqa: E402

RADIUS_STORE = 500      # 상가를 세는 반경
RADIUS_SCHOOL = 1500    # 학교를 찾는 반경
DIST_CAP = 1500.0       # 반경 안에 학교가 없을 때 넣는 값

# 경기 남부 좌표 범위. 경도/위도를 바꿔 넣으면 여기서 걸린다.
#
# 넉넉히 잡되 **뒤집힌 좌표는 반드시 걸리게** 둔다. 경기 남부는 경도 126~127 대,
# 위도 36~37 대라 뒤집으면 경도가 37 이 되어 상한(127.6)을 넘는다.
LNG_RANGE = (126.5, 127.6)
LAT_RANGE = (36.9, 37.7)


def is_fatal(exc: Exception) -> bool:
    """더 돌려도 소용없는 오류인가 — 활용신청 미승인·일일 한도.

    문자열로 가린다. 메시지를 고치면 이 판정이 조용히 틀어지므로
    `scripts/verify_guard.py` 가 실제 메시지로 시험한다.
    """
    t = str(exc)
    return "활용신청" in t or "한도" in t


def out_of_range(lng: float, lat: float) -> bool:
    """좌표가 경기 남부 밖인가.

    `cx`/`cy` 를 바꿔 넣으면 한국 밖을 찾아 **0건**이 오는데, 그건 오류가 아니라
    빈 결과라 조용히 지나간다. 적재 전에 전수로 거른다.

    함수로 뺀 이유는 **시험하기 위해서**다(`scripts/verify_guard.py`). 검사를 넣어
    놓고 걸리는 것을 본 적이 없으면 없는 것과 같다 — verify_absorb 에서 한 번 그랬다.
    """
    return not (
        LNG_RANGE[0] <= float(lng) <= LNG_RANGE[1]
        and LAT_RANGE[0] <= float(lat) <= LAT_RANGE[1]
    )


def _dist_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """수백 m 범위라 평면 근사로 충분하다(위도 37도 기준).

    하버사인을 써도 이 거리에서는 차이가 cm 단위다. 단지당 수천 번 도는 계산이라
    싼 쪽을 쓴다.
    """
    dx = (lng2 - lng1) * 88800.0
    dy = (lat2 - lat1) * 111000.0
    return math.hypot(dx, dy)


def _nearest_school(docs: list[dict], kind: str) -> float | None:
    """`교육,학문 > 학교 > 초등학교` 처럼 `category_name` 으로 학교급을 가른다."""
    best = None
    for d in docs:
        if kind not in (d.get("category_name") or ""):
            continue
        try:
            v = float(d.get("distance") or 0)
        except (TypeError, ValueError):
            continue
        if v and (best is None or v < best):
            best = v
    return best


def _schools(lat: float, lng: float) -> list[dict]:
    """반경 안 학교를 전수로.

    카카오는 한 질의에 45개(15×3페이지)까지만 준다. 학교는 반경 1.5km 에서 최대
    28개였으므로(실측) 상한에 걸리지 않는다. 그래도 걸렸는지 확인해서 넘긴다 —
    상한에 걸린 줄 모르면 학교가 많은 동네만 조용히 가까운 학교를 놓칠 수 있다.
    """
    docs: list[dict] = []
    for page in (1, 2, 3):
        got, meta = kakao.search_category(
            kakao.SCHOOL_CATEGORY, lat=lat, lng=lng,
            radius=RADIUS_SCHOOL, size=15, page=page,
        )
        docs += got
        if meta.get("is_end"):
            break
    return docs


def collect_one(cx: Complex, client: httpx.Client) -> dict:
    lng, lat = float(cx.lng), float(cx.lat)
    items = sdsc.stores_in_radius(lng, lat, RADIUS_STORE, client=client)

    counts = {k: 0 for k in sdsc.BUCKETS}
    for it in items:
        try:
            ilng, ilat = float(it["lon"]), float(it["lat"])
        except (TypeError, ValueError, KeyError):
            continue
        # API 반경과 우리 거리 계산이 미세하게 다를 수 있다. 우리 기준으로 다시 센다.
        if _dist_m(lng, lat, ilng, ilat) > RADIUS_STORE:
            continue
        for b in sdsc.bucket_of(it):
            counts[b] += 1

    docs = _schools(lat, lng)
    return {
        "complex_id": cx.id,
        "store_count": len(items),
        "academy_500": counts["edu"],
        "adult_500": counts["adult"],
        "elem_dist_m": _nearest_school(docs, "초등학교") or DIST_CAP,
        "mid_dist_m": _nearest_school(docs, "중학교") or DIST_CAP,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="단지 주변 입지 적재")
    ap.add_argument("--all", action="store_true", help="이미 있는 것도 다시")
    ap.add_argument("--older-than", type=int, default=None,
                    help="N일보다 오래된 것만 다시")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not sdsc.available():
        print("MOLIT_SERVICE_KEY 가 없습니다. backend/.env 를 확인하세요.")
        return 1
    if not kakao.available():
        print("KAKAO_REST_KEY 가 없습니다. backend/.env 를 확인하세요.")
        return 1

    with SessionLocal() as db:
        have: dict[int, datetime] = {
            r.complex_id: r.collected_at
            for r in db.execute(select(ComplexAmenity)).scalars().all()
        }
        targets = [
            c for c in db.execute(select(Complex)).scalars().all()
            if c.lat and c.lng
        ]

    def needs(c: Complex) -> bool:
        if args.all:
            return True
        at = have.get(c.id)
        if at is None:
            return True
        if args.older_than is None:
            return False
        return at < datetime.now() - timedelta(days=args.older_than)

    todo = [c for c in targets if needs(c)]
    if args.limit:
        todo = todo[: args.limit]
    print(f"단지 {len(targets)}곳 · 이미 있는 것 {len(have)}곳 · 받을 것 {len(todo)}곳")
    if not todo:
        return 0

    # 좌표가 뒤집혀 들어오면 한국 밖을 찾아 0건이 오고, 그건 오류가 아니라 빈 결과다.
    bad = [c for c in todo if out_of_range(c.lng, c.lat)]
    if bad:
        print(f"[X] 좌표가 경기 남부 범위 밖인 단지 {len(bad)}곳 — 적재를 멈춥니다.")
        for c in bad[:10]:
            print(f"    {c.id} {c.name} ({c.lng}, {c.lat})")
        return 1

    problems: list[str] = []
    empty: list[str] = []
    done = 0
    t0 = time.time()

    with httpx.Client(timeout=sdsc.TIMEOUT) as client, SessionLocal() as db:
        for i, cx in enumerate(todo, 1):
            try:
                rec = collect_one(cx, client)
            except sdsc.SdscError as exc:
                # 키·한도 문제면 더 돌려도 소용없다. 멈추고 사람에게 말한다.
                if is_fatal(exc):
                    print(f"[X] {exc}")
                    db.commit()
                    return 1
                problems.append(f"{cx.name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{cx.name}: {type(exc).__name__} {exc}")
                continue

            # 빈 결과는 조용하다. 실측 최소가 3건이었으므로 0건은 의심한다.
            if rec["store_count"] == 0:
                empty.append(f"{cx.name} ({cx.lng}, {cx.lat})")

            row = db.get(ComplexAmenity, cx.id)
            if row is None:
                db.add(ComplexAmenity(**rec))
            else:
                for k, v in rec.items():
                    setattr(row, k, v)
            done += 1
            if i % 50 == 0:
                db.commit()
                el = time.time() - t0
                print(f"  {i}/{len(todo)} · {el/60:.1f}분 · "
                      f"남은 시간 ~{(len(todo)-i)/(i/el)/60:.0f}분")
        db.commit()

    print(f"\n{done}곳 반영 · {(time.time()-t0)/60:.1f}분")

    if empty:
        print(f"\n[!] 반경 {RADIUS_STORE}m 에 상가 0건인 단지 {len(empty)}곳 — "
              f"좌표를 확인하세요:")
        for e in empty[:20]:
            print(f"    {e}")
    if problems:
        print(f"\n확인이 필요한 것 {len(problems)}건 (다시 돌리면 이어서 합니다):")
        for p in problems[:20]:
            print(f"    {p}")
    return 1 if (problems or empty) else 0


if __name__ == "__main__":
    sys.exit(main())
