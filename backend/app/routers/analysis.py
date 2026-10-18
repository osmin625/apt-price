from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/aspect")
def aspect(
    db: Session = Depends(get_db),
    months: int = Query(12, ge=1, le=120),
):
    """향에 따른 가격 — 호가의 **적정가 대비 괴리율**을 향 무리로 나눈다.

    실거래에는 향이 없어 헤도닉 계수로는 못 낸다. 향이 적힌 자료는 붙여넣은 매물뿐이라
    여기서만 잰다. 자세한 것은 `services/aspect.py` 주석.

    적정가는 **순위표가 쓰는 것과 같은 함수**로 낸다. 여기서 따로 계산하면 두 화면이
    언젠가 다른 말을 한다.
    """
    from ..services import aspect as asp
    from ..services import ranking

    def evaluate(payload):
        return ranking.evaluate_many(db, payload, months=months, basis="market")

    return asp.by_aspect(db, evaluate, months)
