"""매크로 — 한국부동산원 공표 통계(시군구·월)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import macro as mc

router = APIRouter(prefix="/api/macro", tags=["macro"])

NOT_INGESTED = (
    "한국부동산원 통계가 아직 적재되지 않았습니다. "
    "backend 에서 `python -m scripts.ingest_reb` 를 실행하세요."
)


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    """고를 수 있는 지표 목록과 적재 여부."""
    return {"metrics": mc.METRICS, "ingested": mc.available(db)}


@router.get("/series")
def series(
    db: Session = Depends(get_db),
    metric: str = Query("avg_unit_price"),
    since: str | None = Query(None, pattern=r"^\d{6}$", description="YYYYMM"),
):
    """한 지표의 시군구별 월 시계열."""
    if not mc.available(db):
        raise HTTPException(status_code=503, detail=NOT_INGESTED)
    try:
        return mc.series(db, metric, since=since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/latest")
def latest(db: Session = Depends(get_db)):
    """모든 지표의 최신값을 한 표로."""
    if not mc.available(db):
        raise HTTPException(status_code=503, detail=NOT_INGESTED)
    return mc.latest_table(db)
