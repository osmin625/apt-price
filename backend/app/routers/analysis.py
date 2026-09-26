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
