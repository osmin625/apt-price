"""주식 — 지수 분석(영향·구간 예측)과 장기 투자·단기 매매 탭의 실제 지수 계산."""

from fastapi import APIRouter, HTTPException

from ...core.dbfile import DbMissing
from .. import service

router = APIRouter(prefix="/api/stock", tags=["stock"])


# 지수가 둘뿐이고 화면이 둘을 나란히 보여 주므로 한 번에 낸다.
@router.get("/indices")
def indices():
    try:
        return service.overview()
    except DbMissing as exc:
        # 503 — 정적 내보내기는 이것을 실패로 센다(빈 화면이 배포되지 않는다).
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/short-term")
def short_term():
    try:
        return service.short_term()
    except DbMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/long-term")
def long_term():
    try:
        return service.long_term()
    except DbMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
