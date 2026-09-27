"""DB의 실거래를 평당가 분석 결과로 가공하는 서비스 계층."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pricing
from ..models import Complex, Station, Trade
from ..pricing import TradePoint


def _cutoff(months: int) -> date:
    return date.today() - timedelta(days=int(months * 30.44))


def load_points(
    db: Session,
    *,
    months: int = 12,
    sgg_cd: str | None = None,
    complex_id: int | None = None,
    area_band: str | None = None,
    station_band: str | None = None,
    age_band: str | None = None,
    line: str | None = None,
    station: str | None = None,
    household_band: str | None = None,
    query: str | None = None,
) -> list[TradePoint]:
    """필터를 걸어 거래를 읽는다.

    노선·역 생활권은 **큐레이션한 Station 테이블**을 기준으로 한다.
    Complex.station_line 은 카카오가 준 분류명('수도권1호선')이라 표기가 달라
    필터 값과 맞지 않는다. 화면에 보이는 값과 필터가 어긋나면 안 되므로
    양쪽 모두 Station 을 쓴다.
    """
    stmt = (
        select(Trade, Complex)
        .join(Complex, Trade.complex_id == Complex.id)
        .where(Trade.deal_date >= _cutoff(months))
    )
    if sgg_cd:
        stmt = stmt.where(Complex.sgg_cd == sgg_cd)
    if complex_id:
        stmt = stmt.where(Complex.id == complex_id)
    if query:
        stmt = stmt.where(Complex.name.contains(query))

    if line or station:
        stmt = stmt.join(Station, Complex.nearest_station_id == Station.id)
        if line:
            stmt = stmt.where(Station.line == line)
        if station:
            stmt = stmt.where(Station.name == station)

    ref_year = date.today().year
    points: list[TradePoint] = []
    for trade, cx in db.execute(stmt).all():
        if area_band and pricing.area_band(trade.exclusive_area) != area_band:
            continue
        if station_band and pricing.station_band(cx.station_distance_m) != station_band:
            continue
        if age_band and pricing.age_band(cx.build_year or trade.build_year, ref_year) != age_band:
            continue
        if household_band and pricing.household_band(cx.household_count) != household_band:
            continue
        points.append(
            TradePoint(
                complex_id=cx.id,
                complex_name=cx.name,
                deal_ym=trade.deal_ym,
                deal_date=trade.deal_date.isoformat(),
                exclusive_area=trade.exclusive_area,
                floor=trade.floor,
                deal_amount=trade.deal_amount,
                build_year=cx.build_year or trade.build_year,
                max_floor=cx.max_floor,
                station_distance_m=cx.station_distance_m,
                apt_dong=(trade.apt_dong or "").strip() or None,
            )
        )
    return points


def market_overview(points: list[TradePoint], months: int) -> dict:
    """층별 / 입지별 / 연식별 / 면적대별 평당가 분포를 한 번에 낸다."""
    ref_year = date.today().year
    index = pricing.market_index(points)
    factors = pricing.estimate_floor_factors(points, index)

    all_ppp = [pricing.adjusted_ppp(p, index) for p in points]

    # 추이 선은 구성 편향을 제거한 지수 기준 가격 수준을 쓴다.
    # 원시 중앙값은 참고용으로 함께 내보낸다.
    anchor = median(all_ppp) if all_ppp else 0.0
    monthly = []
    buckets: dict[str, list[float]] = {}
    for p in points:
        buckets.setdefault(p.deal_ym, []).append(p.ppp)
    for ym in sorted(buckets):
        vals = buckets[ym]
        monthly.append(
            {
                "month": ym,
                "count": len(vals),
                "median": round(anchor * index[ym], 1) if ym in index else round(median(vals), 1),
                "raw_median": round(median(vals), 1),
            }
        )

    return {
        "months": months,
        "trade_count": len(points),
        "complex_count": len({p.complex_id for p in points}),
        "overall": pricing.describe(all_ppp),
        "by_floor": pricing.group_stats(
            points, lambda t: pricing.floor_band(t.floor, t.max_floor),
            pricing.FLOOR_BANDS, index,
        ),
        "by_station": pricing.group_stats(
            points, lambda t: pricing.station_band(t.station_distance_m),
            pricing.STATION_BANDS, index,
        ),
        "by_age": pricing.group_stats(
            points, lambda t: pricing.age_band(t.build_year, ref_year),
            pricing.AGE_BANDS, index,
        ),
        "by_area": pricing.group_stats(
            points, lambda t: pricing.area_band(t.exclusive_area),
            pricing.AREA_BANDS, index,
        ),
        "floor_factors": [
            {"band": b, "factor": factors[b], "premium_pct": round((factors[b] - 1) * 100, 1)}
            for b in pricing.FLOOR_BANDS
            if b in factors
        ],
        "monthly": monthly,
    }


def complex_overview(db: Session, complex_id: int, months: int) -> dict | None:
    cx = db.get(Complex, complex_id)
    if not cx:
        return None

    points = load_points(db, months=months, complex_id=complex_id)
    ref_year = date.today().year
    index = pricing.market_index(load_points(db, months=months, sgg_cd=cx.sgg_cd))

    by_type: list[dict] = []
    groups: dict[int, list[TradePoint]] = {}
    for p in points:
        groups.setdefault(pricing.area_type_key(p.exclusive_area), []).append(p)

    for key in sorted(groups):
        rows = groups[key]
        vals = [pricing.adjusted_ppp(r, index) for r in rows]
        by_type.append(
            {
                "exclusive_area": key,
                "pyeong": round(pricing.to_pyeong(key), 1),
                "area_band": pricing.area_band(key),
                "stats": pricing.describe(vals),
                "by_floor": pricing.group_stats(
                    rows, lambda t: pricing.floor_band(t.floor, t.max_floor),
                    pricing.FLOOR_BANDS, index,
                ),
            }
        )

    return {
        "complex": serialize_complex(cx, points, index),
        "months": months,
        "trade_count": len(points),
        "by_area_type": by_type,
        "by_floor": pricing.group_stats(
            points, lambda t: pricing.floor_band(t.floor, t.max_floor),
            pricing.FLOOR_BANDS, index,
        ),
        "trades": [
            {
                "deal_date": p.deal_date,
                "exclusive_area": round(p.exclusive_area, 2),
                "pyeong": round(pricing.to_pyeong(p.exclusive_area), 1),
                "floor": p.floor,
                "floor_band": pricing.floor_band(p.floor, p.max_floor),
                "deal_amount": p.deal_amount,
                "ppp": round(p.ppp, 1),
                "adjusted_ppp": round(pricing.adjusted_ppp(p, index), 1),
            }
            for p in sorted(points, key=lambda x: x.deal_date, reverse=True)
        ],
        "age_band": pricing.age_band(cx.build_year, ref_year),
        "station_band": pricing.station_band(cx.station_distance_m),
    }


def serialize_complex(
    cx: Complex, points: list[TradePoint] | None = None, index: dict | None = None
) -> dict:
    ref_year = date.today().year
    stats = None
    if points:
        stats = pricing.describe([pricing.adjusted_ppp(p, index or {}) for p in points])
    return {
        "id": cx.id,
        "name": cx.name,
        "sgg_cd": cx.sgg_cd,
        "sgg_name": cx.sgg_name,
        "umd_nm": cx.umd_nm,
        "jibun": cx.jibun,
        "build_year": cx.build_year,
        "max_floor": cx.max_floor,
        "lat": cx.lat,
        "lng": cx.lng,
        # 표시용은 큐레이션 Station 을 우선한다 — 필터가 쓰는 값과 같아야 한다.
        "station_name": (cx.nearest_station.name if cx.nearest_station else cx.station_name),
        "station_line": (cx.nearest_station.line if cx.nearest_station else cx.station_line),
        "household_count": cx.household_count,
        "household_band": pricing.household_band(cx.household_count),
        "apt_type": cx.apt_type,
        "station_distance_m": round(cx.station_distance_m) if cx.station_distance_m else None,
        "walk_minutes": pricing.walk_minutes(cx.station_distance_m),
        "station_band": pricing.station_band(cx.station_distance_m),
        "age_band": pricing.age_band(cx.build_year, ref_year),
        "ppp": stats,
    }


def _own_dong_estimate(sample, index, factors, dong, target_factor, pyeong):
    """그 동 거래만 쓴 추정치. 없으면 None.

    층은 단지 전체에서 추정한 계수로 중립화한다 — 동 하나로 층 계수까지 뽑을 만큼
    거래가 있는 경우는 없다. 시점 보정은 단지 전체 지수를 쓴다.
    """
    if not dong:
        return None
    own = [p for p in sample if (p.apt_dong or "") == dong]
    if not own:
        return None
    neutral = []
    for p in own:
        f = factors.get(pricing.floor_band(p.floor, p.max_floor), 1.0) or 1.0
        neutral.append(pricing.adjusted_ppp(p, index) / f)
    base = median(neutral)
    ppp = base * target_factor
    return {
        "n": len(own),
        "base_ppp": round(base, 1),
        "fair_ppp": round(ppp, 1),
        "fair_price": round(ppp * pyeong),
        "latest_date": max(p.deal_date for p in own),
        "oldest_date": min(p.deal_date for p in own),
    }


def _dong_factors(dong_effects, complex_id: int) -> dict[str, float]:
    """그 단지의 {동: 배수}. 적합 결과가 없으면 빈 dict — 동 보정 없이 간다."""
    if not dong_effects:
        return {}
    import math

    return {
        d: math.exp(v["coef"])
        for (c, d), v in dong_effects.items()
        if c == complex_id
    }


def estimate_fair_price(
    db: Session,
    *,
    complex_id: int,
    exclusive_area: float,
    floor: int | None,
    months: int = 12,
    dong: str | None = None,
    dong_effects: dict | None = None,
    ctx: dict | None = None,
) -> dict | None:
    """실거래 기반 적정 시세 추정.

    1) 같은 단지·같은 평형의 거래를 우선 표본으로 삼고, 부족하면 범위를 단계적으로 넓힌다.
    2) 각 거래를 시점 보정(월별 지수) + 층 보정(층 계수로 나눔)해 '층 중립 기준 평당가'로 환산한다.
    3) 그 중앙값에 대상 매물의 층 계수를 곱해 적정 평당가를 만든다.
    """
    cx = db.get(Complex, complex_id)
    if not cx:
        return None

    ref_year = date.today().year
    # 구 단위 표본·시점지수·층계수는 (구, 기간)마다 같다. 목록을 한 번에 평가할 때
    # 매물 수만큼 다시 만들면 46건에 12초가 든다 — 호출자가 `ctx` 를 넘기면 공유한다.
    ck = ("district", cx.sgg_cd, months)
    if ctx is not None and ck in ctx:
        district_points, index, factors = ctx[ck]
    else:
        district_points = load_points(db, months=months, sgg_cd=cx.sgg_cd)
        index = pricing.market_index(district_points)
        factors = pricing.estimate_floor_factors(district_points, index)
        if ctx is not None:
            ctx[ck] = (district_points, index, factors)

    own = [p for p in district_points if p.complex_id == complex_id]
    target_band = pricing.area_band(exclusive_area)

    same_type = [p for p in own if abs(p.exclusive_area - exclusive_area) <= 1.5]
    same_band = [p for p in own if pricing.area_band(p.exclusive_area) == target_band]

    if len(same_type) >= 3:
        sample, basis = same_type, "동일 단지 · 동일 평형 실거래"
    elif len(same_band) >= 3:
        sample, basis = same_band, "동일 단지 · 동일 면적대 실거래"
    elif len(own) >= 3:
        sample, basis = own, "동일 단지 전체 실거래"
    else:
        peer_station = pricing.station_band(cx.station_distance_m)
        peer_age = pricing.age_band(cx.build_year, ref_year)
        sample = [
            p
            for p in district_points
            if pricing.area_band(p.exclusive_area) == target_band
            and pricing.station_band(p.station_distance_m) == peer_station
            and pricing.age_band(p.build_year, ref_year) == peer_age
        ]
        basis = "유사 입지(역거리) · 유사 연식 · 동일 면적대 단지 실거래"

    if not sample:
        return {
            "complex": serialize_complex(cx),
            "basis": "표본 없음",
            "sample_count": 0,
            "fair_price": None,
            "message": f"최근 {months}개월 내 비교 가능한 실거래가 없습니다.",
        }

    target_floor_band = pricing.floor_band(floor, cx.max_floor)

    # 동 프리미엄을 층과 **같은 방식**으로 다룬다. 비교 표본은 여러 동에서 나오므로,
    # 각 거래에서 그 동의 효과를 먼저 빼 '동 중립' 기준선을 만든 뒤 대상 동의 효과를
    # 다시 곱한다. 빼지 않고 곱하기만 하면 기준선에 이미 섞인 동 효과를 두 번 세게 된다.
    dong_f = _dong_factors(dong_effects, complex_id)
    target_dong_factor = dong_f.get((dong or "").strip(), 1.0) if dong else 1.0

    neutral = []
    for p in sample:
        f = factors.get(pricing.floor_band(p.floor, p.max_floor), 1.0) or 1.0
        d = dong_f.get(p.apt_dong or "", 1.0)
        neutral.append(pricing.adjusted_ppp(p, index) / f / d)

    base_ppp = median(neutral)
    target_factor = factors.get(target_floor_band, 1.0) or 1.0
    fair_ppp = base_ppp * target_factor * target_dong_factor

    spread = pricing.describe(neutral) or {}
    pyeong = pricing.to_pyeong(exclusive_area)

    n = len(sample)
    confidence = "높음" if n >= 10 else "보통" if n >= 5 else "낮음"
    # 동을 지정했는데 그 동 거래가 거의 없으면, 표본이 아무리 많아도 **그 동에 대해서는**
    # 아는 게 적다. 단지 전체 표본 수로 '높음' 을 주면 확신을 과장하게 된다.
    own_n = sum(1 for p in sample if dong and (p.apt_dong or "") == dong) if dong else None
    confidence_note = None
    if dong:
        if own_n == 0:
            confidence = "낮음"
            confidence_note = (
                f"{dong}동 거래가 표본에 없습니다. 같은 평형 다른 동의 시세로 대신한 값이라, "
                "이 동만의 프리미엄·디스카운트는 반영되지 않았습니다."
            )
        elif own_n < 5:
            # 거래 1건의 표준편차가 7%대라 n=3 이면 SE 가 4%p 를 넘는다.
            # 단지 전체 표본이 아무리 많아도 이 동에 대해서는 '높음' 이 아니다.
            confidence = "보통" if confidence == "높음" else confidence
            confidence_note = (
                f"{dong}동 거래는 {own_n}건뿐입니다. 나머지는 같은 평형 다른 동 거래로 채웠습니다."
            )

    return {
        "complex": serialize_complex(cx),
        "basis": basis,
        "sample_count": n,
        "confidence": confidence,
        "confidence_note": confidence_note,
        "exclusive_area": round(exclusive_area, 2),
        "pyeong": round(pyeong, 2),
        "floor": floor,
        "floor_band": target_floor_band,
        "floor_factor": round(target_factor, 4),
        "floor_premium_pct": round((target_factor - 1) * 100, 1),
        "dong": (dong or None),
        "dong_factor": round(target_dong_factor, 4),
        "dong_premium_pct": round((target_dong_factor - 1) * 100, 1),
        "dong_known": bool(dong and (dong or "").strip() in dong_f),
        "base_ppp": round(base_ppp, 1),
        "fair_ppp": round(fair_ppp, 1),
        "fair_price": round(fair_ppp * pyeong),
        "fair_price_low": round(
            spread.get("p25", base_ppp) * target_factor * target_dong_factor * pyeong
        ),
        "fair_price_high": round(
            spread.get("p75", base_ppp) * target_factor * target_dong_factor * pyeong
        ),
        # **그 동 거래만으로** 낸 별도 추정. 단지 전체 기준값과 나란히 두면
        # "이 평형 실거래가 사실상 다른 동 것 아니냐" 를 사용자가 직접 확인할 수 있다.
        # 거래가 적어 단독으로 쓸 수는 없지만, 두 값이 벌어지면 그게 곧 신호다.
        "own_dong": _own_dong_estimate(sample, index, factors, dong, target_factor, pyeong),
        # 표본에 동 정보가 얼마나 있는지. 국토부는 소유권이전등기가 끝난 거래만 동을
        # 공개해서 **최근 거래일수록 비어 있다** — 그런데 최근 거래가 가격을 좌우하므로,
        # 비율을 알려 주지 않으면 "왜 우리 동 거래는 몇 건뿐인데 적정가가 이렇지" 가 된다.
        "dong_coverage": {
            "known": sum(1 for p in sample if p.apt_dong),
            "total": n,
            "same_dong": (
                sum(1 for p in sample if p.apt_dong == dong) if dong else None
            ),
        },
        "comparables": [
            {
                "complex_name": p.complex_name,
                "deal_date": p.deal_date,
                "dong": p.apt_dong,
                "exclusive_area": round(p.exclusive_area, 2),
                "floor": p.floor,
                "floor_band": pricing.floor_band(p.floor, p.max_floor),
                "deal_amount": p.deal_amount,
                "ppp": round(p.ppp, 1),
                "adjusted_ppp": round(pricing.adjusted_ppp(p, index), 1),
            }
            for p in sorted(sample, key=lambda x: x.deal_date, reverse=True)[:40]
        ],
    }
