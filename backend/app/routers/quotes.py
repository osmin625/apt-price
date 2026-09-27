"""붙여넣어 쌓인 매물(호가)의 순위.

`Quote` 테이블은 붙여넣기마다 중복 없이 쌓인다. 그러니 **지금까지 본 모든 매물**의
순위는 따로 저장할 것 없이 여기서 언제든 다시 계산할 수 있다. 기간을 바꾸면 그
기간의 실거래로 전부 다시 계산된다.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Complex, Quote
from ..services import quotes as quotes_svc
from ..services import ranking

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("/ranking")
def ranking_all(
    months: int = Query(24, ge=6, le=120),
    basis: str = Query("market", pattern="^(market|factor)$"),
    days: int | None = Query(None, ge=1, le=3650, description="최근 N일 안에 본 매물만"),
    complex_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """쌓인 매물 전체를 평가해 **더 저평가된 순서**로 돌려준다."""
    from datetime import datetime, timedelta

    stmt = select(Quote)
    if days:
        # 확인일자 기준이다. `last_seen_at` 은 우리가 붙여넣은 시각이라 전부 오늘이
        # 되어 버려 거르는 의미가 없었다. 날짜를 못 읽은 매물은 남긴다 — 읽기
        # 실패를 '오래된 매물' 로 바꿔 조용히 숨기면 안 된다.
        cut = (datetime.now() - timedelta(days=days)).date()
        stmt = stmt.where(or_(Quote.confirmed_on.is_(None), Quote.confirmed_on >= cut))
    if complex_id:
        stmt = stmt.where(Quote.complex_id == complex_id)
    rows = db.execute(stmt).scalars().all()

    # 한 (단지·동·평형·층)당 한 줄. 값이 바뀐 이력도, 동시에 올라와 있는 매물도
    # 대표 한 줄로 접고 나머지는 호버로 내린다 — `quotes_svc.display_units` 참조.
    units = quotes_svc.display_units(rows)

    names = {
        c.id: c.name
        for c in db.execute(select(Complex)).scalars().all()
    }
    rep_of = {q.id: q for q in rows}
    payload = []
    for u in units:
        q = rep_of[u["quote_id"]]
        payload.append({
            **u,
            "complex_id": q.complex_id,
            "complex_name": names.get(q.complex_id, ""),
            "dong": q.dong or None,
            "exclusive_area": q.exclusive_area,
            "floor": q.floor or None,
        })

    out = ranking.evaluate_many(db, payload, months=months, basis=basis)
    out["months"] = months
    out["total_quotes"] = len(rows)
    out["revised_units"] = sum(1 for p in payload if p["revisions"] > 1)
    out["grouped_away"] = sum(len(p["quote_ids"]) for p in payload) - len(payload)
    out["days"] = days
    return out


@router.delete("/{quote_id}")
def delete_quote(
    quote_id: int,
    unit: bool = Query(True, description="같은 집의 지난 호가까지 함께 지운다"),
    db: Session = Depends(get_db),
):
    """매물 하나를 지운다.

    순위표의 한 줄은 행 하나가 아니라 **그 (단지·동·평형·층)에 묶인 전부**다.
    지난 호가와 동시에 올라온 매물이 함께 접혀 있다. 대표 행만 지우면 나머지가
    다음 조회에서 각자 한 줄로 되살아나 지운 것처럼 보이지 않는다.
    """
    q = db.get(Quote, quote_id)
    if not q:
        return {"ok": True, "deleted": 0}

    targets = [q]
    if unit:
        siblings = db.execute(
            select(Quote).where(
                Quote.complex_id == q.complex_id,
                Quote.dong == q.dong,
                Quote.area_key == q.area_key,
                Quote.floor == q.floor,
            )
        ).scalars().all()
        ids = {x.id for x in siblings}
        if quote_id in ids:
            targets = siblings

    for x in targets:
        db.delete(x)
    db.commit()
    return {"ok": True, "deleted": len(targets)}


@router.delete("")
def clear_quotes(db: Session = Depends(get_db)):
    """전부 비운다. 잘못 붙여넣은 목록을 통째로 되돌릴 때 쓴다."""
    n = quotes_svc.count(db)
    db.query(Quote).delete()
    db.commit()
    return {"deleted": n}
