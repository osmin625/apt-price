from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import hedonic
from ..services import model_view as mv
from .model import _fit

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("/complexes")
def complexes(
    db: Session = Depends(get_db),
    months: int = Query(24, ge=6, le=120),
    spec: str = Query(hedonic.DEFAULT_SPEC),
):
    """지도 마커용 경량 페이로드 + 지표별 색상 스케일 범위."""
    f = _fit(db, months, spec)
    payload = mv.map_payload(db, f)
    payload["months"] = months
    payload["spec"] = f["spec"]
    return payload


@router.get("/stations")
def stations(db: Session = Depends(get_db)):
    """역 목록 — 좌표, 강남 소요시간, 최근접 단지 수."""
    return mv.station_payload(db)


@router.get("/walk-path/{complex_id}")
def walk_path(
    complex_id: int,
    db: Session = Depends(get_db),
    station_id: int | None = None,
):
    """단지→역 실제 도보 경로(LineString).

    추정치 모드(TMap 키 없음)에서는 경로 지오메트리가 없으므로 path 가 null 이다.
    프론트는 그때 점선 직선으로 대체한다.
    """
    out = mv.walk_path(db, complex_id, station_id)
    if out is None:
        raise HTTPException(status_code=404, detail="도보 경로 정보가 없습니다.")
    return out
