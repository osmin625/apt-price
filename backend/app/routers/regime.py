"""거시 분석 — 공급·수요·통화량·금리·정책·세금이 지금 어느 쪽으로 미는가."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import RebStat
from ..services import regime as rg

router = APIRouter(prefix="/api/regime", tags=["regime"])

NOT_INGESTED = (
    "거시 요인이 아직 적재되지 않았습니다. "
    "backend 에서 `python -m scripts.ingest_macro` 를 돌리세요."
)


# 화면은 `overview` 하나만 부른다. 카드가 여럿이지만 전부 **같은 가격 계열**을
# 기준으로 상관을 재므로, 나눠 부르면 같은 계산을 여러 번 하게 된다.
# (`routers/supply.py` 에서 카드별 엔드포인트를 만들었다 지운 것과 같은 이유.)
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    n = db.scalar(
        select(func.count()).select_from(RebStat)
        .where(RebStat.metric.in_(("unsold", "sentiment", "loan_rate")))
    ) or 0
    if n == 0:
        raise HTTPException(status_code=503, detail=NOT_INGESTED)
    return rg.overview(db)
