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


@router.get("/rings")
def rings(
    db: Session = Depends(get_db),
    months: int = Query(24, ge=6, le=120),
    spec: str = Query(hedonic.DEFAULT_SPEC),
):
    """모델 등가격 링 — 적합 곡선이 -5/-10/-15/-20%를 지나는 지도 반경(m).

    station_band 의 400/800/1200m 고정 링을 모델이 유도한 등고선으로 대체한다.
    역마다 같은 반경을 쓰되, 도보분→반경 변환은 실제 관측된 우회율과 보행속도를 쓴다.
    """
    f = _fit(db, months, spec)
    stats = mv.detour_stats(db)
    return {
        "rings": mv.rings(f, stats),
        "detour_ratio": round(stats["detour_ratio"], 3),
        "meters_per_min": round(stats["meters_per_min"], 1),
        "sample": stats["n"],
        "note": "곡선이 해당 수준을 지나는 도보시간을 관측 보행속도·우회율로 직선반경으로 환산",
    }


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
