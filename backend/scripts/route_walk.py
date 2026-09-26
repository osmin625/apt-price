"""단지↔역 도보 경로를 적재하고 Complex의 비정규화 컬럼을 갱신한다.

사용법:
    python -m scripts.route_walk                # TMap 키 있으면 실거리, 없으면 추정치
    python -m scripts.route_walk --limit 200    # 할당량 아껴가며 나눠 실행
    python -m scripts.route_walk --force        # 이미 라우팅된 쌍도 다시
    python -m scripts.route_walk --estimate-only  # 키가 있어도 추정치로

## 왜 최근접역 하나가 아니라 N개인가

도보시간이 가장 짧은 역과 **강남 접근성이 가장 좋은 역이 다를 수 있다.**
광교 단지가 광교중앙역(신분당, 강남 35분)까지 도보 12분이면 총 47분인데,
수인분당선 역까지 도보 4분(강남 58분)인 쪽은 62분이다. 가까운 역만 보면
이 차이를 통째로 놓친다.

후보 = 직선거리 3순위까지 ∪ 직선 2,500m 이내 전부 (최대 5개).

## 폴백 2단계

1. TMap 키 있음 → 실제 보행 경로 (거리·시간·경로 지오메트리)
2. 키 없음 → 직선거리 × 1.25 ÷ 67m/분 (pricing 의 기존 상수 재사용)

역 좌표조차 없으면(카카오 키도 없는 경우) 단지에 이미 저장된
station_name/station_distance_m 으로 쌍 하나만 만든다. 키가 하나도 없어도
전체 파이프라인이 끝까지 돌아가게 하기 위한 장치다.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import pricing  # noqa: E402
from app.clients import tmap  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Complex, ComplexStation, Station  # noqa: E402

NEAREST_N = 3
RADIUS_M = 2500.0
MAX_CANDIDATES = 5


def estimate(straight_m: float) -> tuple[float, int]:
    """직선거리 → (추정 도보거리 m, 추정 소요 초). pricing 의 상수를 그대로 쓴다."""
    dist = straight_m * pricing.WALK_DETOUR_FACTOR
    seconds = int(round(dist / (pricing.WALK_METERS_PER_MIN / 60.0)))
    return dist, seconds


def candidate_pairs(cx: Complex, stations: list[Station]) -> list[tuple[Station, float]]:
    scored = [
        (st, pricing.haversine_m(cx.lat, cx.lng, st.lat, st.lng))
        for st in stations
        if st.lat is not None and st.lng is not None
    ]
    if not scored:
        return []
    scored.sort(key=lambda p: p[1])
    chosen = list(scored[:NEAREST_N])
    seen = {st.id for st, _ in chosen}
    for st, d in scored[NEAREST_N:]:
        if d <= RADIUS_M and st.id not in seen:
            chosen.append((st, d))
            seen.add(st.id)
    return chosen[:MAX_CANDIDATES]


def fallback_pair(cx: Complex, by_name: dict[str, Station]) -> list[tuple[Station, float]]:
    """역 좌표가 없을 때 — 단지에 저장된 역 이름/직선거리로 쌍 하나를 만든다."""
    if not cx.station_name or cx.station_distance_m is None:
        return []
    st = by_name.get(cx.station_name)
    return [(st, float(cx.station_distance_m))] if st else []


def run(limit: int | None, force: bool, estimate_only: bool, sleep: float) -> None:
    use_tmap = tmap.available() and not estimate_only
    mode = "TMap 실거리" if use_tmap else "직선거리 추정치"
    print(f"모드: {mode}")
    if not use_tmap and not estimate_only:
        print("  TMAP_APP_KEY 미설정 — 추정치로 진행합니다. 키를 넣고 --force 로 재실행하면 교체됩니다.")

    with SessionLocal() as db:
        stations = db.execute(select(Station)).scalars().all()
        if not stations:
            print("역 테이블이 비어 있습니다. 먼저 `python -m scripts.seed_stations` 를 실행하세요.")
            return
        by_name = {s.name: s for s in stations}
        with_coords = [s for s in stations if s.lat is not None]
        if not with_coords:
            print(f"역 {len(stations)}곳 모두 좌표가 없습니다 — 단지에 저장된 역 이름으로 폴백합니다.")

        complexes = db.execute(select(Complex)).scalars().all()
        existing = {
            (cs.complex_id, cs.station_id): cs
            for cs in db.execute(select(ComplexStation)).scalars().all()
        }

        routed = reused = skipped = 0
        calls = 0

        for cx in complexes:
            if cx.lat is not None and with_coords:
                pairs = candidate_pairs(cx, with_coords)
            else:
                pairs = fallback_pair(cx, by_name)
            if not pairs:
                skipped += 1
                continue

            for rank, (st, straight) in enumerate(sorted(pairs, key=lambda p: p[1]), 1):
                cs = existing.get((cx.id, st.id))
                if cs is None:
                    cs = ComplexStation(complex_id=cx.id, station_id=st.id)
                    db.add(cs)
                    existing[(cx.id, st.id)] = cs
                cs.straight_distance_m = straight
                cs.rank = rank

                if cs.routed_at is not None and cs.walk_source == "tmap" and not force:
                    reused += 1
                    continue
                if limit is not None and calls >= limit:
                    skipped += 1
                    continue

                if use_tmap and cx.lat is not None and st.lat is not None:
                    try:
                        route = tmap.pedestrian_route(cx.lat, cx.lng, st.lat, st.lng)
                        calls += 1
                    except tmap.TmapError as exc:
                        print(f"  [{cx.name} → {st.name}] {exc}")
                        route = None
                    except Exception as exc:
                        print(f"  [{cx.name} → {st.name}] 경로 실패: {exc}")
                        route = None
                    if route:
                        cs.walk_distance_m = route.distance_m
                        cs.walk_seconds = route.seconds
                        cs.walk_source = "tmap"
                        cs.path_geojson = route.path_geojson
                        cs.routed_at = datetime.now()
                        routed += 1
                        time.sleep(sleep)
                        continue
                    time.sleep(sleep)

                dist, secs = estimate(straight)
                cs.walk_distance_m = dist
                cs.walk_seconds = secs
                cs.walk_source = "estimate"
                cs.path_geojson = None
                cs.routed_at = datetime.now()
                routed += 1

        db.commit()
        refresh_complex_access(db)
        db.commit()

        srcs: dict[str, int] = {}
        for cs in db.execute(select(ComplexStation)).scalars().all():
            srcs[cs.walk_source] = srcs.get(cs.walk_source, 0) + 1
        print(f"\n쌍 {routed}건 적재 / 재사용 {reused} / 건너뜀 {skipped}")
        print(f"출처별: {srcs}")
        print(f"TMap 호출 {calls}회")


def refresh_complex_access(db) -> None:
    """ComplexStation → Complex 비정규화.

    최근접역(도보시간 최소)과 최적접근역(도보+전철 최소)은 서로 다를 수 있으므로
    둘 다 저장한다. 지도·모델 엔드포인트가 조인 없이 바로 읽는다.
    """
    stations = {s.id: s for s in db.execute(select(Station)).scalars().all()}
    rows: dict[int, list[ComplexStation]] = {}
    for cs in db.execute(select(ComplexStation)).scalars().all():
        if cs.walk_seconds is not None:
            rows.setdefault(cs.complex_id, []).append(cs)

    for cx in db.execute(select(Complex)).scalars().all():
        pairs = rows.get(cx.id)
        if not pairs:
            continue

        nearest = min(pairs, key=lambda c: c.walk_seconds)
        cx.nearest_station_id = nearest.station_id
        cx.walk_distance_m = nearest.walk_distance_m
        cx.walk_seconds = nearest.walk_seconds

        best, best_total = None, None
        for cs in pairs:
            gm = stations[cs.station_id].minutes_to_gangnam
            if gm is None:
                continue
            total = cs.walk_seconds / 60.0 + gm
            if best_total is None or total < best_total:
                best, best_total = cs, total
        if best is not None:
            cx.best_access_station_id = best.station_id
            cx.total_access_min = round(best_total, 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="이번 실행의 최대 TMap 호출 수")
    parser.add_argument("--force", action="store_true", help="이미 라우팅된 쌍도 다시 조회")
    parser.add_argument("--estimate-only", action="store_true", help="키가 있어도 추정치 사용")
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()
    run(args.limit, args.force, args.estimate_only, args.sleep)
