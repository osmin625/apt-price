"""매매 · 전세 · 월세 — 같은 집의 월 비용과, 금리에 따라 수요가 옮겨 가는 흐름."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import RebStat
from ..services import tenure as tn

router = APIRouter(prefix="/api/tenure", tags=["tenure"])

NOT_INGESTED = (
    "월세·금리가 아직 적재되지 않았습니다. "
    "backend 에서 `python -m scripts.ingest_reb` 와 `python -m scripts.ingest_macro` 를 돌리세요."
)


# 그림 넷이 같은 패널(빈 달 없는 구)을 본다 — 나눠 부르면 구를 고르는 일을 네 번 한다.
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    n = db.scalar(
        select(func.count()).select_from(RebStat)
        .where(RebStat.metric.in_(("rent_index", "mortgage_rate")))
    ) or 0
    if n == 0:
        raise HTTPException(status_code=503, detail=NOT_INGESTED)
    return tn.overview(db)
