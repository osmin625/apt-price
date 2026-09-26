"""카카오 로컬 API로 수원시 실제 아파트 단지를 수집한다.

사용법:
    python -m scripts.fetch_complexes --dry-run     # 저장 없이 결과만 검수
    python -m scripts.fetch_complexes               # DB 저장
    python -m scripts.fetch_complexes --max 300     # 상한

## 왜 필요한가

시드에 손으로 적은 25곳으로는 2단계 회귀 표본이 너무 적다. 특히 강남접근성 항은
유효 클러스터가 4개 수준이라 해석이 안 된다. 단지 250~300곳이면 도보 곡선과
접근성 항 모두 쓸 만해진다.

**단지의 정체성과 지리는 실제여야 한다.** 이름·좌표·최근접역이 진짜라야 지오코딩과
도보 라우팅 결과가 나중에 실거래가로 바꿔 끼울 때 그대로 재사용된다. 가격만 합성이다.

## 왜 법정동 목록이 아니라 공간 타일링인가

동 이름 목록을 코드에 박으면 하나를 잘못 적거나 빠뜨렸을 때 그 동 단지가 통째로
사라지는데, 결과만 봐서는 알아채기 어렵다. 반면 bbox 를 격자로 훑으면 이름을 몰라도
빠지지 않고, 법정동·시군구는 카카오가 돌려주는 주소에서 **정확하게** 파싱된다.

카카오 키워드 검색은 한 질의당 최대 45건(size≤15 × page≤3)이므로, 45건이 꽉 찬
타일은 4등분해 재귀적으로 더 잘게 훑는다.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import pricing  # noqa: E402
from app.clients.kakao import KakaoError, search_keyword  # noqa: E402
from app.clients.molit import SUWON_DISTRICTS  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Complex  # noqa: E402

# 수원시 대략 bbox — 경계 밖은 주소 파싱 단계에서 걸러지므로 넉넉히 잡는다.
SW = (37.208, 126.916)
NE = (37.344, 127.112)

TILE_M = 900          # 최초 격자 한 변
MIN_TILE_M = 220      # 이보다 작아지면 더 쪼개지 않는다
FULL_PAGE = 45        # 카카오 한 질의 상한 — 꽉 차면 잘렸다는 뜻

# 카카오 POI 분류 경로. '부동산 > 주거시설 > 아파트' 가 신뢰할 수 있는 필터다.
CATEGORY_OK = "아파트"
NAME_REJECT = re.compile(
    r"상가|관리사무소|경비실|정문|후문|주차장|어린이집|유치원|경로당|"
    r"부동산|공인중개|분양|모델하우스|주민센터|커뮤니티"
)

# 카카오가 주는 주소: "경기 수원시 영통구 영통동 123-4"
ADDR = re.compile(r"경기(?:도)?\s+수원시\s+(\S+구)\s+(\S+(?:동|가|리))\s*(\S*)")

SGG_BY_NAME = {name.split()[-1]: code for code, name in SUWON_DISTRICTS.items()}

# 카카오는 준공년도·최고층을 주지 않는다. 동네별 개발 시기로 시뮬레이션하고
# 국토부 적재 시 실제 값으로 덮어쓴다(ingest_trades / refresh_complex_stats).
BUILD_YEAR_BY_UMD = {
    "이의동": (2009, 2013), "원천동": (2008, 2014), "광교동": (2010, 2015),
    "망포동": (2015, 2021), "영통동": (1995, 2005), "매탄동": (2000, 2012),
    "호매실동": (2011, 2018), "금곡동": (2012, 2019), "권선동": (2005, 2018),
    "우만동": (1988, 1999), "정자동": (1996, 2014), "천천동": (1998, 2010),
    "율전동": (1997, 2012), "조원동": (1994, 2021), "세류동": (2008, 2018),
    "교동": (2019, 2024), "인계동": (1998, 2010), "화서동": (2000, 2021),
}
DEFAULT_BUILD_RANGE = (1998, 2018)


def tiles(sw, ne, size_m):
    """bbox 를 size_m 격자로 나눈 (lat, lng, radius) 목록."""
    dlat = size_m / 111_000
    dlng = size_m / (111_000 * 0.795)  # 위도 37도에서 경도 1도 ≈ 88.6km
    out = []
    lat = sw[0]
    while lat < ne[0]:
        lng = sw[1]
        while lng < ne[1]:
            out.append((lat + dlat / 2, lng + dlng / 2, size_m))
            lng += dlng
        lat += dlat
    return out


def parse_address(doc: dict) -> tuple[str, str, str, str] | None:
    """(sgg_cd, sgg_name, umd_nm, jibun). 수원시 4개 구가 아니면 None."""
    for key in ("address_name", "road_address_name"):
        m = ADDR.search(doc.get(key) or "")
        if not m:
            continue
        gu, umd, jibun = m.group(1), m.group(2), m.group(3)
        code = SGG_BY_NAME.get(gu)
        if code:
            return code, f"수원시 {gu}", umd, jibun
    return None


def keep(doc: dict) -> bool:
    cat = doc.get("category_name") or ""
    name = (doc.get("place_name") or "").strip()
    if CATEGORY_OK not in cat:
        return False
    if NAME_REJECT.search(name):
        return False
    return len(name) >= 2


def crawl(sleep: float, verbose: bool) -> dict[str, dict]:
    found: dict[str, dict] = {}
    queue = list(tiles(SW, NE, TILE_M))
    calls = 0
    split = 0

    while queue:
        lat, lng, size = queue.pop()
        got = 0
        truncated = False
        for page in (1, 2, 3):
            try:
                docs, is_end = search_keyword(
                    "아파트", page=page, size=15, x=lng, y=lat,
                    radius=int(size * 0.75), sort="distance",
                )
            except KakaoError as exc:
                print(exc)
                return found
            except Exception as exc:
                print(f"  타일({lat:.4f},{lng:.4f}) p{page} 실패: {exc}")
                break
            calls += 1
            got += len(docs)
            for d in docs:
                if d.get("id") and keep(d):
                    found.setdefault(d["id"], d)
            time.sleep(sleep)
            if is_end:
                break
        else:
            # for-else: break 없이 3페이지를 다 돌았다는 뜻 = 카카오가 더 있다고 본다.
            truncated = got >= FULL_PAGE

        # 45건이 꽉 찼으면 잘린 것 — 4등분해 더 촘촘히 훑는다.
        if truncated and size / 2 >= MIN_TILE_M:
            half = size / 2
            q = half / 2
            dlat = q / 111_000
            dlng = q / (111_000 * 0.795)
            for dy in (-dlat, dlat):
                for dx in (-dlng, dlng):
                    queue.append((lat + dy, lng + dx, half))
            split += 1

        if verbose and calls % 60 == 0:
            print(f"  ...호출 {calls}회 · 후보 {len(found)}곳 · 남은 타일 {len(queue)}")

    print(f"카카오 호출 {calls}회 · 세분화 {split}회 · POI {len(found)}곳")
    return found


def to_rows(found: dict[str, dict], rng) -> tuple[list[dict], list[str]]:
    rows: dict[str, dict] = {}
    rejected: list[str] = []
    for doc in found.values():
        # crawl() 도 keep() 을 걸지만 여기서 한 번 더 본다. 이 함수만 따로 호출해도
        # 상가·관리사무소가 단지로 들어가지 않아야 한다.
        if not keep(doc):
            rejected.append(f"{doc.get('place_name')} (분류/이름 제외)")
            continue
        parsed = parse_address(doc)
        if parsed is None:
            rejected.append(f"{doc.get('place_name')} ({doc.get('address_name')})")
            continue
        sgg_cd, sgg_name, umd, jibun = parsed
        name = (doc.get("place_name") or "").strip()
        key = pricing.name_key(name)
        if not key or key in rows:
            continue

        lo, hi = BUILD_YEAR_BY_UMD.get(umd, DEFAULT_BUILD_RANGE)
        rows[key] = {
            "name": name,
            "name_key": key,
            "sgg_cd": sgg_cd,
            "sgg_name": sgg_name,
            "umd_nm": umd,
            "jibun": jibun or None,
            "road_address": doc.get("road_address_name") or None,
            "lat": float(doc["y"]),
            "lng": float(doc["x"]),
            "kakao_place_id": doc.get("id"),
            "source": "kakao",
            "build_year": rng.randint(lo, hi),
            "max_floor": rng.choice([15, 18, 20, 22, 25, 27, 29, 30, 34]),
        }
    return list(rows.values()), rejected


def run(dry_run: bool, max_complexes: int | None, sleep: float, seed: int) -> None:
    import random

    rng = random.Random(seed)
    found = crawl(sleep, verbose=True)
    if not found:
        print("수집된 단지가 없습니다. KAKAO_REST_KEY 를 확인하세요.")
        return

    rows, rejected = to_rows(found, rng)

    by_umd: dict[str, int] = {}
    for r in rows:
        by_umd[r["umd_nm"]] = by_umd.get(r["umd_nm"], 0) + 1

    print(f"\n필터 통과 {len(rows)}곳 / 수원시 밖·주소 파싱 실패 {len(rejected)}곳")
    print("\n법정동별 단지 수 (상위 20)")
    for umd, n in sorted(by_umd.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {umd:10} {n:4}")
    if rejected:
        print(f"\n제외된 POI 예시 ({min(len(rejected), 8)}건)")
        for r in rejected[:8]:
            print(f"  {r}")

    if max_complexes and len(rows) > max_complexes:
        # 법정동 커버리지를 유지하며 줄인다 — 한 동만 남으면 구 FE 가 무의미해진다.
        rows.sort(key=lambda r: r["umd_nm"])
        buckets: dict[str, list[dict]] = {}
        for r in rows:
            buckets.setdefault(r["umd_nm"], []).append(r)
        trimmed, i = [], 0
        while len(trimmed) < max_complexes:
            added = False
            for b in buckets.values():
                if i < len(b) and len(trimmed) < max_complexes:
                    trimmed.append(b[i])
                    added = True
            if not added:
                break
            i += 1
        rows = trimmed
        print(f"\n{max_complexes}곳으로 제한 (법정동 균형 유지)")

    if dry_run:
        print(f"\n--dry-run: 저장하지 않았습니다. 대상 {len(rows)}곳")
        print("샘플 5곳:")
        for r in rows[:5]:
            print(f"  {r['name']:26} {r['umd_nm']:8} {r['build_year']} "
                  f"({r['lat']:.4f}, {r['lng']:.4f})")
        return

    with SessionLocal() as db:
        existing = {
            c.name_key: c for c in db.execute(select(Complex)).scalars().all()
        }
        created = updated = 0
        for r in rows:
            cx = existing.get(r["name_key"])
            if cx is None:
                db.add(Complex(**r))
                created += 1
            else:
                # 이미 있는 단지는 좌표·식별자만 보강하고 이름·출처는 건드리지 않는다.
                if cx.lat is None:
                    cx.lat, cx.lng = r["lat"], r["lng"]
                if cx.kakao_place_id is None:
                    cx.kakao_place_id = r["kakao_place_id"]
                updated += 1
        db.commit()
        total = len(db.execute(select(Complex)).scalars().all())
        print(f"\n저장 완료: 신규 {created} / 기존 보강 {updated} / 전체 {total}곳")
        print("다음: python -m scripts.seed_stations --force")
        print("      python -m scripts.route_walk")
        print("      python -m scripts.seed_demo   (거래 재생성)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    parser.add_argument("--max", type=int, default=300, dest="max_complexes")
    parser.add_argument("--sleep", type=float, default=0.06)
    parser.add_argument("--seed", type=int, default=20260919)
    args = parser.parse_args()
    run(args.dry_run, args.max_complexes, args.sleep, args.seed)
