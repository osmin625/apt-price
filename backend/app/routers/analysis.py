from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import analysis as svc

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/market")
def market(
    db: Session = Depends(get_db),
    months: int = Query(12, ge=1, le=120),
    sgg_cd: str | None = None,
    area_band: str | None = None,
    station_band: str | None = None,
    age_band: str | None = None,
    line: str | None = None,
    station: str | None = None,
    household_band: str | None = None,
    q: str | None = None,
):
    """층별 / 입지(역거리)별 / 연식별 / 면적대별 전용면적 평당가 분포."""
    points = svc.load_points(
        db,
        months=months,
        sgg_cd=sgg_cd,
        area_band=area_band,
        station_band=station_band,
        age_band=age_band,
        line=line,
        station=station,
        household_band=household_band,
        query=q,
    )
    return svc.market_overview(points, months)


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
