"""단지 좌표를 구하고 최근접 지하철역까지의 거리를 채운다.

사용법:
    python -m scripts.geocode
    python -m scripts.geocode --force
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from sqlalchemy import select

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.clients.kakao import KakaoError, geocode, nearest_station  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Complex  # noqa: E402


def build_address(cx: Complex) -> str:
    parts = ["경기도", cx.sgg_name, cx.umd_nm]
    if cx.jibun:
        parts.append(cx.jibun)
    return " ".join(p for p in parts if p)


def run(force: bool, sleep: float) -> None:
    with SessionLocal() as db:
        stmt = select(Complex)
        if not force:
            stmt = stmt.where(Complex.lat.is_(None))
        targets = db.execute(stmt).scalars().all()
        print(f"대상 단지 {len(targets)}곳")

        ok = failed = 0
        for i, cx in enumerate(targets, 1):
            address = build_address(cx)
            try:
                coords = geocode(address, fallback_keyword=f"{cx.sgg_name} {cx.name}")
            except KakaoError as exc:
                print(exc)
                return
            except Exception as exc:  # 네트워크/쿼터 오류는 건너뛰고 계속
                print(f"  [{cx.name}] 좌표 실패: {exc}")
                failed += 1
                continue

            if not coords:
                print(f"  [{cx.name}] 좌표 없음 ({address})")
                failed += 1
                time.sleep(sleep)
                continue

            cx.lat, cx.lng = coords
            cx.geocoded_at = datetime.now()

            try:
                station = nearest_station(cx.lat, cx.lng)
            except Exception as exc:
                print(f"  [{cx.name}] 역 검색 실패: {exc}")
                station = None

            if station:
                cx.station_name = station.name
                cx.station_line = station.line
                cx.station_distance_m = station.distance_m

            ok += 1
            if i % 20 == 0:
                db.commit()
                print(f"  ...{i}/{len(targets)}")
            time.sleep(sleep)

        db.commit()
        print(f"\n완료: 성공 {ok} / 실패 {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="이미 좌표가 있는 단지도 다시 조회")
    parser.add_argument("--sleep", type=float, default=0.1)
    args = parser.parse_args()
    run(args.force, args.sleep)
