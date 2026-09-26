"""API 키 없이 전체 파이프라인을 돌리기 위한 합성 데이터 생성기.

⚠ 여기서 만들어지는 **가격은 실거래가가 아니다.** 단지명·법정동·좌표·역 정보는
실제 수원시 기준이고, 가격만 시뮬레이션이다. 실제 시세는 scripts/ingest_trades.py 로.

사용법:
    python -m scripts.seed_demo --recreate-schema    # 스키마부터 새로(권장)
    python -m scripts.seed_demo --reset              # 데이터만 새로

## 이전 버전과 무엇이 다른가 — 그리고 왜 중요한가

예전 시드는 단지별 전용평당가(5150, 4620, …)를 **손으로 적어** 두고 역거리도
따로 손으로 적어 뒀다. 가격 생성식에 역거리 항이 없는데도 두 숫자 사이에 강한
상관이 있어(매교역푸르지오 180m/4560 vs 호매실중흥 3200m/2840), 거리→가격
회귀를 돌리면 **가짜로 유의한 계수**가 나왔다. 실제로 확인했다: 통제 없는 스펙에서
도보 1분당 -1.21%가 p<0.05로 나오고, 구 고정효과를 넣으면 사라진다.

그래서 가격 수준을 **생성한다.** 모든 가격은 아래 GROUND_TRUTH 에서 나오고,
회귀가 그 값을 되찾아오는지 scripts/validate_model.py 로 검증할 수 있다.
하드코딩된 수준이 남아 있으면 '참값'이 정의되지 않아 자기검증 자체가 성립하지 않는다.

## 순서가 중요한 이유

시드는 DB에 저장된 walk_seconds 를 읽어 가격을 만든다. 모델이 읽는 바로 그
컬럼이다. 참 경로거리로 만들고 모델이 추정거리를 읽으면 측정오차가 계수를
감쇠시켜, 추정량과 무관한 이유로 검증이 실패한다. 그래서 이 스크립트가
역 적재 → 도보거리 적재 → 거래 생성을 한 번에 순서대로 수행한다.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import pricing  # noqa: E402
from app.config import BASE_DIR  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Complex,
    ComplexStation,
    Listing,
    Station,
    Trade,
)
from scripts import route_walk, seed_stations  # noqa: E402

TRUTH_PATH = BASE_DIR / "data" / "seed_truth.json"

# (단지명, 시군구코드, 시군구명, 법정동, 준공년도, 최고층, 역명, 노선, 직선역거리m,
#  전용면적 타입, 위도, 경도)
#
# 평당가는 여기 없다 — GROUND_TRUTH 에서 생성한다. 이것이 이번 재작성의 핵심이다.
COMPLEXES = [
    # 영통구 — 광교신도시 / 영통동 / 매탄동 / 망포동
    ("광교자연앤힐스테이트", "41117", "수원시 영통구", "이의동", 2012, 29, "광교중앙역", "신분당선", 320, [84, 101], 37.2870, 127.0530),
    ("광교호수마을호반써밋", "41117", "수원시 영통구", "원천동", 2011, 25, "광교중앙역", "신분당선", 880, [84, 115], 37.2795, 127.0610),
    ("자연앤자이2단지", "41117", "수원시 영통구", "이의동", 2012, 24, "광교중앙역", "신분당선", 560, [59, 84], 37.2905, 127.0490),
    ("래미안영통마크원", "41117", "수원시 영통구", "영통동", 2014, 27, "영통역", "수인분당선", 430, [59, 84, 101], 37.2513, 127.0715),
    ("영통황골마을주공1단지", "41117", "수원시 영통구", "영통동", 1997, 20, "영통역", "수인분당선", 620, [49, 59, 74], 37.2540, 127.0690),
    ("벽적골주공8단지", "41117", "수원시 영통구", "영통동", 1997, 18, "청명역", "수인분당선", 350, [49, 59], 37.2478, 127.0630),
    ("매탄위브하늘채", "41117", "수원시 영통구", "매탄동", 2008, 25, "매탄권선역", "수인분당선", 470, [59, 84, 101], 37.2620, 127.0330),
    ("힐스테이트영통", "41117", "수원시 영통구", "망포동", 2017, 29, "망포역", "수인분당선", 390, [59, 84], 37.2455, 127.0565),
    ("영통아이파크캐슬1단지", "41117", "수원시 영통구", "망포동", 2019, 28, "망포역", "수인분당선", 950, [74, 84], 37.2410, 127.0605),
    ("삼성래미안노블클래스", "41117", "수원시 영통구", "원천동", 2009, 22, "수원시청역", "수인분당선", 1350, [84, 114], 37.2705, 127.0450),

    # 팔달구 — 인계동 / 매교동 / 우만동
    ("인계동삼성래미안", "41115", "수원시 팔달구", "인계동", 2003, 23, "수원시청역", "수인분당선", 380, [59, 84, 114], 37.2640, 127.0310),
    ("수원센트럴아이파크자이", "41115", "수원시 팔달구", "교동", 2023, 30, "매교역", "수인분당선", 260, [59, 84], 37.2720, 127.0155),
    ("매교역푸르지오SK뷰", "41115", "수원시 팔달구", "교동", 2022, 30, "매교역", "수인분당선", 180, [59, 74, 84], 37.2735, 127.0170),
    ("우만주공4단지", "41115", "수원시 팔달구", "우만동", 1988, 15, "수원시청역", "수인분당선", 1680, [39, 49, 59], 37.2830, 127.0355),
    ("화서역파크푸르지오", "41115", "수원시 팔달구", "화서동", 2021, 28, "화서역", "1호선", 340, [59, 84], 37.2835, 126.9985),

    # 장안구 — 정자동 / 조원동 / 천천동
    ("정자동SK스카이뷰", "41111", "수원시 장안구", "정자동", 2013, 34, "화서역", "1호선", 920, [59, 84, 101], 37.2965, 126.9925),
    ("한일타운", "41111", "수원시 장안구", "정자동", 1999, 25, "화서역", "1호선", 1450, [59, 84, 114], 37.3010, 126.9975),
    ("조원동한신더휴", "41111", "수원시 장안구", "조원동", 2020, 27, "성균관대역", "1호선", 1820, [59, 84], 37.3095, 127.0155),
    ("천천푸르지오", "41111", "수원시 장안구", "천천동", 2004, 22, "성균관대역", "1호선", 640, [59, 84, 101], 37.2985, 126.9760),
    ("벽산블루밍위브", "41111", "수원시 장안구", "율전동", 2008, 20, "성균관대역", "1호선", 480, [59, 84], 37.2960, 126.9705),

    # 권선구 — 호매실 / 권선동 / 세류동
    ("호매실중흥S클래스", "41113", "수원시 권선구", "호매실동", 2013, 25, "수원역", "1호선", 3200, [59, 84], 37.2605, 126.9490),
    ("금호어울림에듀포레", "41113", "수원시 권선구", "금곡동", 2018, 29, "수원역", "1호선", 3650, [74, 84], 37.2660, 126.9425),
    ("권선자이e편한세상", "41113", "수원시 권선구", "권선동", 2017, 28, "매탄권선역", "수인분당선", 1120, [59, 84, 101], 37.2560, 127.0250),
    ("세류역래미안", "41113", "수원시 권선구", "세류동", 2010, 24, "세류역", "1호선", 420, [59, 84], 37.2455, 127.0100),
    ("아이파크시티2단지", "41113", "수원시 권선구", "세류동", 2015, 30, "세류역", "1호선", 780, [59, 84, 101], 37.2405, 127.0155),
]

# ---------------------------------------------------------------------------
# 참값 — 회귀가 이 숫자들을 되찾아와야 한다
# ---------------------------------------------------------------------------
GROUND_TRUTH: dict = {
    # 기준 단지 = 도보 8분 · 강남 55분 · 연식 10년 · 전용 84㎡ · 중층 · 최신월.
    # 강남 55분은 수인분당선/1호선 수원 단지의 전형값이다. 45분으로 두면 신분당선
    # 단지만 기준에 해당해 나머지가 전부 기준 아래로 깔린다.
    # 모든 효과를 이 기준점 기준으로 중심화하므로 exp(log_base_ppp) 가 곧
    # '전형적인 수원 아파트의 평당가'로 바로 읽힌다. 중심화하지 않으면 기준점이
    # '도보 0분·연식 0년'이라는 존재하지 않는 단지가 되어 값이 해석 불가능해진다.
    "log_base_ppp": 8.17,          # exp(8.17) ≈ 3,530 만원/평
    "walk_ref_min": 8.0,
    "age_ref": 10.0,
    "walk_semi_elast": -0.0140,    # 도보 1분당 -1.40%
    "walk_flatten_after": 18.0,    # 18분 넘어서는 기울기가 25%로 감쇠
    "walk_flatten_ratio": 0.25,
    "gangnam_semi_elast": -0.0090, # 강남 전철 1분당 -0.90%
    "gangnam_ref_min": 55.0,
    "age_linear": -0.0085,
    "age_quad": 0.00012,           # U자형 — 30년대에 재건축 기대로 반등
    "log_area_elast": -0.130,      # 평당가는 면적에 대해 체감(소형이 비싸다)
    "floor_factors": {
        "1층": -0.089, "저층": -0.039, "중층": 0.0, "고층": 0.041, "최상층": 0.012
    },
    "monthly_drift": 0.0035,       # 월 0.35%
    "sigma_complex": 0.070,        # u_c — 잔차 지표가 되찾아야 할 단지 고유효과
    "sigma_trade": 0.032,          # ε
}


def walk_effect(walk_min: float, t: dict) -> float:
    """도보 거리 효과. 18분까지는 선형(=지수감쇠), 그 뒤로는 기울기가 꺾인다.

    로그 공간에서 선형이면 수준 공간에서 exp(-λW), 즉 표준적인 bid-rent 감쇠다.
    꺾임을 넣는 이유: 참값이 정확히 직선이면 검증이 '배관 점검'에 그친다.
    곡선을 넣어야 스플라인이 모양까지 찾아내는지 볼 수 있다.
    """
    lam = t["walk_semi_elast"]
    knee = t["walk_flatten_after"]
    if walk_min <= knee:
        return lam * walk_min
    return lam * knee + lam * t["walk_flatten_ratio"] * (walk_min - knee)


def true_log_ppp_at(walk_min: float, t: dict) -> float:
    """검증·시각화용 — 도보분만 바꿨을 때의 참 log 평당가(다른 항은 상수).

    모델의 곡선은 기준점 대비 '대비'로 나오므로 여기서도 절대 수준은 필요 없다.
    """
    return walk_effect(min(walk_min, pricing.WALK_CAP_MIN), t)


@dataclass
class ComplexSpec:
    """거래 생성에 필요한 단지 정보. DB에서 읽어 채운다."""

    complex_id: int
    name: str
    build_year: int
    max_floor: int
    area_types: list[int]
    walk_min: float       # DB의 walk_seconds 에서 — 모델이 읽는 바로 그 값
    gangnam_min: float
    u_c: float = 0.0      # 단지 고유효과(참값)
    per_month: float = field(default=1.5)


def generate(
    rng: random.Random,
    specs: list[ComplexSpec],
    months: int,
    today: date,
    truth: dict,
) -> tuple[list[dict], dict]:
    """순수 생성 함수 — DB를 건드리지 않는다.

    커버리지 검증(같은 구조를 RNG seed만 바꿔 수십 번 재생성)이 이 함수에 의존한다.
    """
    trades: list[dict] = []
    ref_year = today.year

    for sp in specs:
        sp.u_c = rng.gauss(0.0, truth["sigma_complex"])
        age = ref_year - sp.build_year

        age_ref = truth["age_ref"]
        base = (
            truth["log_base_ppp"]
            + walk_effect(min(sp.walk_min, pricing.WALK_CAP_MIN), truth)
            - walk_effect(truth["walk_ref_min"], truth)
            + truth["gangnam_semi_elast"] * (sp.gangnam_min - truth["gangnam_ref_min"])
            + truth["age_linear"] * (age - age_ref)
            + truth["age_quad"] * (age * age - age_ref * age_ref)
            + sp.u_c
        )

        for back in range(months):
            month_date = today - timedelta(days=30 * back)
            n = max(0, int(rng.gauss(sp.per_month, 0.9)))
            for _ in range(n):
                area = rng.choice(sp.area_types)
                exclusive = round(area + rng.uniform(-0.45, 0.45), 2)
                floor = rng.randint(1, sp.max_floor)
                band = pricing.floor_band(floor, sp.max_floor)

                log_ppp = (
                    base
                    + truth["log_area_elast"] * math.log(exclusive / 84.0)
                    + truth["floor_factors"].get(band, 0.0)
                    - math.log1p(truth["monthly_drift"]) * back
                    + rng.gauss(0.0, truth["sigma_trade"])
                )

                deal_day = rng.randint(1, 28)
                deal_date = date(month_date.year, month_date.month, deal_day)
                if deal_date > today:
                    continue

                amount = int(
                    round(math.exp(log_ppp) * pricing.to_pyeong(exclusive) / 100.0) * 100
                )
                trades.append(
                    {
                        "complex_id": sp.complex_id,
                        "deal_date": deal_date,
                        "deal_ym": f"{deal_date.year:04d}-{deal_date.month:02d}",
                        "exclusive_area": exclusive,
                        "floor": floor,
                        "deal_amount": amount,
                        "build_year": sp.build_year,
                    }
                )

    truth_out = {
        **truth,
        "ref_year": ref_year,
        "u_c": {str(sp.complex_id): round(sp.u_c, 6) for sp in specs},
        "walk_min": {str(sp.complex_id): round(sp.walk_min, 4) for sp in specs},
    }
    return trades, truth_out


def load_specs(db, rng: random.Random) -> list[ComplexSpec]:
    """DB에서 단지별 도보분·강남분을 읽는다. route_walk 가 먼저 돌아 있어야 한다."""
    stations = {s.id: s for s in db.execute(select(Station)).scalars().all()}
    area_by_name = {c[0]: c[9] for c in COMPLEXES}

    specs = []
    missing = []
    for cx in db.execute(select(Complex)).scalars().all():
        if cx.walk_seconds is None:
            missing.append(cx.name)
            continue
        gangnam = None
        if cx.best_access_station_id:
            gangnam = stations[cx.best_access_station_id].minutes_to_gangnam
        if gangnam is None and cx.nearest_station_id:
            gangnam = stations[cx.nearest_station_id].minutes_to_gangnam
        if gangnam is None:
            missing.append(cx.name)
            continue

        specs.append(
            ComplexSpec(
                complex_id=cx.id,
                name=cx.name,
                build_year=cx.build_year or 2010,
                max_floor=cx.max_floor or 25,
                area_types=area_by_name.get(cx.name) or [59, 84],
                walk_min=pricing.walk_minutes_from_seconds(cx.walk_seconds),
                gangnam_min=float(gangnam),
                per_month=rng.uniform(0.8, 2.6),
            )
        )
    if missing:
        print(f"  도보/강남 정보가 없어 제외된 단지 {len(missing)}곳: {', '.join(missing[:5])}")
    return specs


def seed(months: int, reset: bool, recreate: bool, seed_value: int, use_tmap: bool) -> None:
    rng = random.Random(seed_value)

    if recreate:
        # create_all 은 없는 '테이블'만 만들고 기존 테이블에 '컬럼'은 추가하지 않는다.
        # Alembic 없이 스키마를 바꾸려면 통째로 다시 만드는 수밖에 없고, 이 데이터는
        # 몇 초면 재생성되므로 PoC에서는 이게 정답이다.
        print("스키마 재생성 (drop_all → create_all)")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        if reset and not recreate:
            db.query(Listing).delete()
            db.query(Trade).delete()
            db.query(ComplexStation).delete()
            db.query(Complex).delete()
            db.commit()

        # 1) 단지
        existing = {c.name_key for c in db.execute(select(Complex)).scalars().all()}
        added = 0
        for (name, sgg_cd, sgg_name, umd, build_year, max_floor, station, line,
             dist, _areas, lat, lng) in COMPLEXES:
            key = pricing.name_key(name)
            if key in existing:
                continue
            db.add(
                Complex(
                    name=name,
                    name_key=key,
                    sgg_cd=sgg_cd,
                    sgg_name=sgg_name,
                    umd_nm=umd,
                    build_year=build_year,
                    max_floor=max_floor,
                    lat=lat,
                    lng=lng,
                    source="seed",
                    station_name=station,
                    station_line=line,
                    station_distance_m=float(dist),
                )
            )
            added += 1
        db.commit()
        print(f"1/4 단지 {added}곳 생성 (기존 {len(existing)}곳 유지)")

    # 2) 역 (좌표는 카카오 키가 있을 때만)
    print("2/4 역 테이블")
    seed_stations.run(force=False, do_geocode=True, sleep=0.1)

    # 3) 도보거리 — 시드가 읽을 walk_seconds 를 만든다
    print("3/4 도보거리")
    route_walk.run(limit=None, force=False, estimate_only=not use_tmap, sleep=0.15)

    # 4) 거래 생성
    with SessionLocal() as db:
        db.query(Trade).delete()
        db.commit()

        specs = load_specs(db, rng)
        if not specs:
            print("\n거래를 만들 수 없습니다 — 도보/강남 정보가 있는 단지가 없습니다.")
            return

        trades, truth = generate(rng, specs, months, date.today(), GROUND_TRUTH)
        for t in trades:
            db.add(Trade(**t, source="seed"))
        db.commit()

        TRUTH_PATH.write_text(
            json.dumps(
                {"seed": seed_value, "months": months, **truth},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        ppps = [
            pricing.price_per_pyeong(t["deal_amount"], t["exclusive_area"]) for t in trades
        ]
        ppps.sort()
        print(f"\n4/4 거래 {len(trades)}건 생성 (단지 {len(specs)}곳, 합성 데이터)")
        print(f"     평당가 중앙값 {ppps[len(ppps) // 2]:,.0f} 만원/평 "
              f"(최소 {ppps[0]:,.0f} / 최대 {ppps[-1]:,.0f})")
        print(f"     참값 저장: {TRUTH_PATH}")
        print("\n검증: python -m scripts.validate_model")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--reset", action="store_true", help="데이터만 지우고 새로 생성")
    parser.add_argument(
        "--recreate-schema",
        action="store_true",
        help="테이블을 drop 후 재생성 — 스키마를 바꿨다면 필수",
    )
    parser.add_argument("--seed", type=int, default=20260919)
    parser.add_argument("--tmap", action="store_true", help="TMap 키가 있으면 실제 도보 경로 사용")
    args = parser.parse_args()
    seed(args.months, args.reset, args.recreate_schema, args.seed, args.tmap)
