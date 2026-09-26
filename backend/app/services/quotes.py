"""호가 누적 — 실거래가 못 잡는 것을 잡는다.

실거래는 **팔린 것만** 남긴다. 값을 못 받는 매도자는 싸게 파는 대신 물건을 거둬들이므로,
거래가 뜸한 동의 관측 거래가는 위로 편향된다. 내려간 물건은 거래가 아니라 호가에만 있다.

그래서 붙여넣기마다 호가를 쌓아, 거래가 뜸한 동의 **선행지표**로 실거래 옆에 놓는다.
실거래를 대체하지 않는다 — 호가는 희망가와 급매가 섞여 있고 성사 여부를 모른다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import pricing
from ..models import Quote

# 이보다 오래된 호가는 '현재 호가' 집계에서 뺀다. 매물은 팔리거나 내려가는데
# 우리는 내려간 걸 알 방법이 없어서, 시간으로 끊는 수밖에 없다.
ACTIVE_DAYS = 90


def record(db: Session, *, complex_id: int, dong: str | None, exclusive_area: float,
           floor: int | None, floor_band: str | None, asking_price: int) -> str:
    """호가 하나를 기록한다. 반환값은 'created' | 'seen' — 화면에 알려 주려고 구분한다.

    같은 (단지·동·평형·층·호가) 면 새로 쌓지 않고 마지막 목격 시각만 올린다.
    **가격이 다르면 새 행**이 된다 — 그 변화가 보고 싶은 신호다.
    """
    key = (dong or "").strip().removesuffix("동").strip()
    area_key = pricing.area_type_key(exclusive_area)
    fl = int(floor) if floor else 0

    row = db.execute(
        select(Quote).where(
            Quote.complex_id == complex_id,
            Quote.dong == key,
            Quote.area_key == area_key,
            Quote.floor == fl,
            Quote.asking_price == asking_price,
        )
    ).scalar_one_or_none()

    if row is not None:
        row.last_seen_at = datetime.now()
        row.seen_count += 1
        db.commit()
        return "seen"

    db.add(Quote(
        complex_id=complex_id, dong=key, area_key=area_key,
        exclusive_area=round(float(exclusive_area), 2), floor=fl,
        floor_band=floor_band or pricing.floor_band(floor, None),
        asking_price=int(asking_price),
    ))
    db.commit()
    return "created"


def summary(db: Session, complex_id: int, area_key: int | None = None) -> dict:
    """단지의 호가 현황. 동별로 나눠 본다 — 그게 이 데이터를 쌓는 이유다.

    평당가는 **전용 기준**이다(이 서비스의 모든 평당가와 같다).
    """
    since = datetime.now() - timedelta(days=ACTIVE_DAYS)
    stmt = select(Quote).where(Quote.complex_id == complex_id, Quote.last_seen_at >= since)
    if area_key is not None:
        stmt = stmt.where(Quote.area_key == area_key)
    rows = db.execute(stmt).scalars().all()

    by_dong: dict[str, list[Quote]] = {}
    for q in rows:
        by_dong.setdefault(q.dong or "미상", []).append(q)

    def pack(arr: list[Quote]) -> dict:
        ppps = sorted(pricing.price_per_pyeong(q.asking_price, q.exclusive_area) for q in arr)
        prices = sorted(q.asking_price for q in arr)
        return {
            "n": len(arr),
            "median_price": prices[len(prices) // 2],
            "min_price": prices[0],
            "max_price": prices[-1],
            "median_ppp": round(median(ppps), 1),
            "latest": max(q.last_seen_at for q in arr).date().isoformat(),
        }

    dongs = {d: pack(a) for d, a in sorted(by_dong.items()) if a}
    return {
        "complex_id": complex_id,
        "area_key": area_key,
        "active_days": ACTIVE_DAYS,
        "total": len(rows),
        "by_dong": dongs,
        "overall": pack(rows) if rows else None,
        "note": (
            f"최근 {ACTIVE_DAYS}일 안에 확인된 호가만 집계합니다. 호가는 희망가와 급매가 "
            "섞여 있고 성사 여부를 모르므로 실거래를 대체하지 않습니다 — 거래가 뜸한 동의 "
            "선행지표로 실거래 옆에 놓고 보세요."
        ),
    }


def history(db: Session, complex_id: int, dong: str, area_key: int | None = None) -> list[dict]:
    """그 동 호가의 시간 경로. 같은 층이 값을 내렸는지 보는 용도다."""
    key = (dong or "").strip().removesuffix("동").strip()
    stmt = select(Quote).where(Quote.complex_id == complex_id, Quote.dong == key)
    if area_key is not None:
        stmt = stmt.where(Quote.area_key == area_key)
    rows = db.execute(stmt.order_by(Quote.first_seen_at)).scalars().all()
    return [
        {
            "floor": q.floor or None,
            "floor_band": q.floor_band,
            "exclusive_area": q.exclusive_area,
            "asking_price": q.asking_price,
            "ppp": round(pricing.price_per_pyeong(q.asking_price, q.exclusive_area), 1),
            "first_seen": q.first_seen_at.date().isoformat(),
            "last_seen": q.last_seen_at.date().isoformat(),
            "seen_count": q.seen_count,
        }
        for q in rows
    ]


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Quote)) or 0
