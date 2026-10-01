"""매크로 — 한국부동산원 공표 통계(시군구·월)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import hedonic
from ..services import macro as mc
from ..services import model_view as mv

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


@router.get("/insights")
def insights(
    db: Session = Depends(get_db),
    months: int = Query(12, ge=6, le=120),
):
    """읽을 거리 셋 — 국면 4분면 · 상승의 성격 · 모델과의 어긋남.

    모델 대조는 적합이 **이미 있을 때만** 한다. 여기서 적합을 새로 돌리면 매크로
    탭을 여는 데 수십 초가 걸린다. 없으면 그 그림만 비우고 나머지는 보여 준다 —
    하나 때문에 전부 막지 않는다.
    """
    if not mc.available(db):
        raise HTTPException(status_code=503, detail=NOT_INGESTED)

    # peek_fit 은 **메모리만** 본다. 디스크에 저장된 적합까지 쓰려면 상태를 묻고
    # 캐시가 있을 때만 get_fit 을 부른다(디스크에서 읽는 데 2초 안팎, 새로 돌리면
    # 수십 초다). 없으면 그 그림만 비우고 나머지는 보여 준다.
    fit = None
    if hedonic.available():
        try:
            if mv.fit_status(db, months=months)["cached"]:
                fit = mv.get_fit(db, months=months)
        except Exception:  # noqa: BLE001  못 읽어도 나머지는 보여 준다
            fit = None

    return {
        "cycle": mc.cycle_phase(db),
        "rally": mc.rally_character(db),
        "model_gap": mc.model_gap(db, fit),
        "has_fit": fit is not None,
    }
