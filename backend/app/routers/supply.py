"""공급 분석 — 적정 공급량과 실제 공급(서울·경기)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clients.reb import SIDO
from ..db import get_db
from ..models import RebStat
from ..services import supply as sp

router = APIRouter(prefix="/api/supply", tags=["supply"])

NOT_INGESTED = (
    "공급 통계가 아직 적재되지 않았습니다. "
    "backend 에서 `python -m scripts.ingest_supply` 를 돌리세요."
)


def _require(db: Session) -> None:
    n = db.scalar(
        select(func.count()).select_from(RebStat)
        .where(RebStat.metric.in_(("done", "households", "demolish")))
    ) or 0
    if n == 0:
        raise HTTPException(status_code=503, detail=NOT_INGESTED)


# 화면은 `overview` 하나만 부른다. 카드별 엔드포인트(`/balance`, `/pipeline`)를
# 같이 만들었다가 지웠다 — 부르는 곳이 없으면 **스펙이 아니라 짐**이다. 필요해지면
# 그때 만든다(`scripts/verify_sync.py` 가 안 쓰는 엔드포인트를 보고한다).
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """한 번에 다 준다.

    카드 네 장이 전부 같은 적재를 본다. 따로 부르면 화면이 네 번 깜빡이고, 양이
    작아서(연 15행 × 2지역) 나눌 이유가 없다.
    """
    _require(db)
    return {
        "regions": [
            {
                **sp.balance(db, sgg),
                "pipeline": sp.pipeline(db, sgg),
                "lead": sp.lead(db, sgg),
            }
            for sgg in SIDO
        ],
        "age_pressure": sp.age_pressure(db),
        "unsold": sp.unsold(db),
        "south_supply": sp.south_supply(db),
        "note": (
            # `{data.note}` 로 **평문** 렌더된다. 마크다운을 쓰면 별표가 그대로 보인다
            # — 학원 노트·joint_note 에서 이미 두 번 겪었다.
            "적정 공급량은 가구 증가 + 멸실로 계산한 값이라 해마다 달라집니다. "
            "서울은 2011~2015 에 46,000~54,000 이었다가 가구 증가가 빨라진 "
            "2019년 이후 올라갔습니다. "
            "미래 입주 예정 물량은 공표 통계에 없습니다(민간 집계입니다)."
        ),
    }
