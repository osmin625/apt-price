"""단지 안 개별 동(101동, 나동…)의 좌표와 역까지 거리를 채운다.

사용법:
    python -m scripts.geocode_dongs                 # 좌표 없는 동만
    python -m scripts.geocode_dongs --limit 500     # 나눠서 실행
    python -m scripts.geocode_dongs --force         # 전부 다시 조회
    python -m scripts.geocode_dongs --dry-run       # 20개만 시험 조회

## 왜 동 단위인가

같은 단지라도 동에 따라 역까지 거리가 100~330m 차이난다(표본 측정값).
단지 중심점 하나만 쓰면 이 편차가 통째로 사라진다.

그런데 정밀도보다 중요한 게 있다. 동 단위 거리가 생기면 **같은 단지 안에서**
역에 가까운 동과 먼 동을 비교할 수 있다. 이 비교에서는 학군·브랜드·관리상태·
단지 연식이 전부 자동으로 통제된다 — 이 데이터로 얻을 수 있는 가장 깨끗한 식별이다.

## 매칭을 어떻게 확인하는가

카카오에 '단지명 101동'을 물으면 그 동을 못 찾았을 때 **단지 대표 좌표를 돌려준다.**
그대로 믿으면 모든 동이 같은 좌표가 되어 동 단위 분석이 조용히 무의미해진다.
그래서 반환된 place_name 에 그 동 번호가 들어 있을 때만 인정한다.
못 찾은 동은 좌표를 비워 두고, 모델이 그 거래에 대해서는 단지 평균을 쓰게 한다.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import pricing  # noqa: E402
from app.clients.kakao import KakaoError, search_keyword  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base, Complex, ComplexDong, Station, Trade  # noqa: E402


def build_query(cx: Complex, dong: str) -> str:
    suffix = f"{dong}동" if dong.isdigit() else dong
    return " ".join(p for p in (cx.sgg_name, cx.umd_nm, cx.name, suffix) if p)


# 한 단지 안의 동은 단지 중심점에서 이 거리 안에 있어야 한다.
# 한국 아파트 단지는 폭이 보통 200~400m 라 여유를 두고 잡은 값이다.
MAX_DONG_OFFSET_M = 500.0


def dong_token(dong: str) -> str:
    """'101' -> '101동', '가' -> '가동'. 토큰 단위 비교용."""
    d = dong.strip()
    return d if d.endswith("동") else f"{d}동"


def pick(
    docs: list[dict], dong: str, cx_lat: float, cx_lng: float
) -> tuple[float, float, str] | None:
    """그 동을 실제로 가리키는 결과만 채택한다. 검사 두 개를 모두 통과해야 한다.

    ## 1) 이름 검사 — 부분 문자열이 아니라 토큰

    처음엔 '반환된 이름에 동 문자열이 들어 있으면 채택'으로 했다. 동이 '가' 인
    단지에서 **가보자식당**이, '나' 인 단지에서 **나의반려견**이 채택됐다.
    한 글자짜리 동 이름에는 부분 문자열 검사가 아무 의미가 없다.
    그래서 '가동', '101동' 처럼 **동 접미사까지 붙은 토큰**으로 비교한다.

    ## 2) 거리 검사 — 이게 진짜 방어선

    이름 검사만으로는 다른 단지의 같은 번호 동을 막지 못한다. 실제로
    수원역푸르지오자이 105동에 **부성리치빌 105동**이, 삼성3차 3동에
    **삼성1차아파트 3동**이 붙었다. 이름 규칙을 아무리 정교하게 만들어도
    이런 건 계속 샌다.

    단지 중심점에서 500m 넘게 떨어진 결과는 그냥 버린다. 이름이 무엇이든
    한 단지 안의 동일 수 없다. 이름 파싱과 달리 이 검사는 우회되지 않는다.
    """
    token = dong_token(dong)
    for doc in docs:
        name = (doc.get("place_name") or "").strip()
        if token not in name.replace(" ", ""):
            continue
        lat, lng = float(doc["y"]), float(doc["x"])
        if pricing.haversine_m(cx_lat, cx_lng, lat, lng) > MAX_DONG_OFFSET_M:
            continue
        return lat, lng, name
    return None


def pairs_to_fetch(db, force: bool) -> list[tuple[Complex, str]]:
    have = {
        (d.complex_id, d.dong)
        for d in db.execute(select(ComplexDong)).scalars().all()
        if d.lat is not None
    }
    complexes = {c.id: c for c in db.execute(select(Complex)).scalars().all()}
    rows = db.execute(
        select(Trade.complex_id, Trade.apt_dong)
        .where(Trade.apt_dong.is_not(None), Trade.apt_dong != "")
        .distinct()
    ).all()

    out = []
    for cid, dong in rows:
        cx = complexes.get(cid)
        if cx is None or cx.lat is None:
            continue
        d = (dong or "").strip()
        if not d:
            continue
        if not force and (cid, d) in have:
            continue
        out.append((cx, d))
    return out


def revalidate() -> None:
    """이미 저장된 행에 현재 기준을 다시 적용한다. API 호출 없음.

    매칭 기준을 고쳤을 때 전부 다시 내려받을 필요가 없다 — 좌표와 이름이
    이미 있으니 그걸로 재판정하면 된다. 탈락한 행은 좌표를 비워 두고,
    나중에 geocode_dongs 를 다시 돌리면 재시도 대상이 된다.
    """
    with SessionLocal() as db:
        complexes = {c.id: c for c in db.execute(select(Complex)).scalars().all()}
        rows = db.execute(select(ComplexDong)).scalars().all()

        kept = dropped = 0
        reasons = {"이름": 0, "거리": 0}
        samples = []

        for d in rows:
            if d.lat is None:
                continue
            cx = complexes.get(d.complex_id)
            if cx is None or cx.lat is None:
                continue

            name = (d.matched_name or "").replace(" ", "")
            token = dong_token(d.dong)
            offset = pricing.haversine_m(cx.lat, cx.lng, d.lat, d.lng)

            bad = None
            if token not in name:
                bad = "이름"
            elif offset > MAX_DONG_OFFSET_M:
                bad = "거리"

            if bad:
                if len(samples) < 12:
                    samples.append((cx.name, d.dong, d.matched_name, offset, bad))
                reasons[bad] += 1
                d.lat = d.lng = None
                d.station_id = None
                d.straight_distance_m = d.walk_distance_m = d.walk_seconds = None
                d.geocoded_at = None
                dropped += 1
            else:
                kept += 1

        db.commit()
        print(f"재판정: 유지 {kept:,} / 탈락 {dropped:,}  "
              f"(이름 불일치 {reasons['이름']:,} · 거리 초과 {reasons['거리']:,})")
        if samples:
            print("\n탈락 예시:")
            for cxn, dong, matched, off, why in samples:
                print(f"  [{why}] {cxn[:20]:22} {dong:>5}동 -> {str(matched)[:30]:32} {off:6.0f}m")

        n = refresh_dong_distance(db)
        db.commit()
        print(f"\n동별 역거리 재계산 {n:,}건")
        report(db)


def run(limit: int | None, force: bool, dry_run: bool, sleep: float) -> None:
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        todo = pairs_to_fetch(db, force)
        if dry_run:
            todo = todo[:20]
        elif limit:
            todo = todo[:limit]

        print(f"대상 (단지, 동) 쌍 {len(todo):,}개")
        if not todo:
            print("모두 조회 완료된 상태입니다.")
            return

        existing = {
            (d.complex_id, d.dong): d
            for d in db.execute(select(ComplexDong)).scalars().all()
        }
        ok = miss = 0

        for i, (cx, dong) in enumerate(todo, 1):
            try:
                docs, _ = search_keyword(build_query(cx, dong), size=3)
            except KakaoError as exc:
                print(exc)
                break
            except Exception as exc:
                print(f"  [{cx.name} {dong}] 실패: {exc}")
                docs = []

            hit = pick(docs, dong, cx.lat, cx.lng)
            row = existing.get((cx.id, dong))
            if row is None:
                row = ComplexDong(complex_id=cx.id, dong=dong)
                db.add(row)
                existing[(cx.id, dong)] = row

            if hit:
                row.lat, row.lng, row.matched_name = hit
                row.geocoded_at = datetime.now()
                ok += 1
            else:
                miss += 1

            if i % 100 == 0:
                db.commit()
                print(f"  ...{i}/{len(todo)}  성공 {ok} / 실패 {miss}")
            time.sleep(sleep)

        db.commit()
        print(f"\n좌표 조회: 성공 {ok} / 실패 {miss} "
              f"({ok / max(ok + miss, 1) * 100:.0f}%)")

        if dry_run:
            print("\n--dry-run: 거리 계산은 건너뜁니다.")
            return

        n = refresh_dong_distance(db)
        db.commit()
        print(f"동별 역거리 갱신 {n:,}건")
        report(db)


def refresh_dong_distance(db) -> int:
    """동 좌표 → 최근접역 도보거리. route_walk 와 같은 추정식을 쓴다."""
    stations = [
        s for s in db.execute(select(Station)).scalars().all() if s.lat is not None
    ]
    if not stations:
        print("역 좌표가 없습니다. 먼저 scripts.seed_stations 를 실행하세요.")
        return 0

    n = 0
    for d in db.execute(select(ComplexDong)).scalars().all():
        if d.lat is None:
            continue
        best, bd = None, None
        for st in stations:
            dist = pricing.haversine_m(d.lat, d.lng, st.lat, st.lng)
            if bd is None or dist < bd:
                best, bd = st, dist
        if best is None:
            continue
        d.station_id = best.id
        d.straight_distance_m = bd
        d.walk_distance_m = bd * pricing.WALK_DETOUR_FACTOR
        d.walk_seconds = int(round(d.walk_distance_m / (pricing.WALK_METERS_PER_MIN / 60)))
        d.walk_source = "estimate"
        n += 1
    return n


def report(db) -> None:
    """단지 안에서 동 간 도보시간이 얼마나 벌어지는지 — 이 작업의 값어치."""
    rows: dict[int, list] = {}
    for d in db.execute(select(ComplexDong)).scalars().all():
        if d.walk_seconds is not None:
            rows.setdefault(d.complex_id, []).append(d)

    spreads = []
    for cid, ds in rows.items():
        if len(ds) < 2:
            continue
        mins = [x.walk_seconds / 60 for x in ds]
        spreads.append((max(mins) - min(mins), cid, len(ds)))
    if not spreads:
        return

    spreads.sort(reverse=True)
    mid = spreads[len(spreads) // 2][0]
    complexes = {c.id: c for c in db.execute(select(Complex)).scalars().all()}
    print(f"\n동이 2개 이상인 단지 {len(spreads)}곳의 단지 내 도보시간 편차")
    print(f"  중앙값 {mid:.1f}분 / 최대 {spreads[0][0]:.1f}분")
    print("  편차가 큰 단지:")
    for sp, cid, nd in spreads[:6]:
        print(f"    {complexes[cid].name[:24]:26} 동 {nd:3}개  최대 {sp:.1f}분 차이")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="좌표가 있어도 다시 조회")
    parser.add_argument("--dry-run", action="store_true", help="20개만 시험 조회")
    parser.add_argument("--sleep", type=float, default=0.08)
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="저장된 행에 현재 매칭 기준을 다시 적용 (API 호출 없음)",
    )
    args = parser.parse_args()
    if args.revalidate:
        revalidate()
    else:
        run(args.limit, args.force, args.dry_run, args.sleep)
