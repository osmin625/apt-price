from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import hedonic, listing_match
from ..services import model_view as mv

router = APIRouter(prefix="/api/model", tags=["model"])

DEPS_MISSING = (
    "모델 의존성이 설치되지 않았습니다. "
    "backend 에서 `pip install -r requirements.txt` 를 실행하세요."
)


def _fit(db: Session, months: int, spec: str) -> dict:
    if not hedonic.available():
        raise HTTPException(status_code=503, detail=DEPS_MISSING)
    try:
        return mv.get_fit(db, months=months, spec=spec)
    except hedonic.ModelUnavailable:
        raise HTTPException(status_code=503, detail=DEPS_MISSING)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/fit")
def fit(
    db: Session = Depends(get_db),
    months: int = Query(24, ge=6, le=120),
    spec: str = Query(hedonic.DEFAULT_SPEC),
):
    """역거리↔평당가 헤도닉 회귀 결과.

    구간화(station_band) 없이 연속 도보거리로 추정한 곡선, 신뢰밴드,
    계수표, 스펙 사다리, 진단을 함께 돌려준다.
    """
    return mv.fit_payload(_fit(db, months, spec))


@router.get("/status")
def status(
    db: Session = Depends(get_db),
    months: int = Query(24, ge=6, le=120),
    spec: str = Query(hedonic.DEFAULT_SPEC),
):
    """적합이 이미 계산돼 있는지. **계산하지 않는다**(12ms).

    화면이 로딩 문구를 고르는 데 쓴다 — 처음 계산하는 것과 이미 있는 것을 불러오는
    것은 걸리는 시간이 한 자릿수 다르다.
    """
    if not hedonic.available():
        return {"cached": False, "source": None, "available": False}
    return {**mv.fit_status(db, months=months, spec=spec), "available": True}


@router.get("/factors")
def factors(
    db: Session = Depends(get_db),
    months: int = Query(24, ge=6, le=120),
    spec: str = Query(hedonic.DEFAULT_SPEC),
):
    """요인별 보정계수 — 층 프리미엄과 같은 형식으로 모든 요인을 환산한 값.

    계수를 그대로 내면 단위가 제각각이라 크기를 비교할 수 없다. 같은 기준점 대비
    %로 환산해 한 화면에서 어느 요인이 가격을 더 움직이는지 볼 수 있게 한다.
    """
    return mv.factor_payload(_fit(db, months, spec))


@router.get("/groups")
def groups(
    db: Session = Depends(get_db),
    months: int = Query(24, ge=6, le=120),
    spec: str = Query(hedonic.DEFAULT_SPEC),
    by: str = Query("line"),
):
    """노선·생활권·법정동 등으로 묶어서 본 보정 평당가와 모델 잔차.

    같은 법정동에 두 노선이 걸치는 경우가 있어(수원 원천동) `by=line_umd` 가 필요하다.
    구 FE 로도 법정동 FE 로도 그 차이는 구분되지 않는다.
    """
    if by not in mv.GROUP_BY:
        raise HTTPException(
            status_code=422,
            detail=f"by 는 {', '.join(mv.GROUP_BY)} 중 하나여야 합니다.",
        )
    f = _fit(db, months, spec)
    return mv.group_payload(db, f, by)


class BulkRequest(BaseModel):
    # 20만 자. 재 보니 북마클릿이 추려 낸 매물은 한 건당 92.5자(구분자 포함)라
    # **약 2,100건**이고, 손으로 드래그 복사한 원문은 한 건당 129자라 약 1,550건이다.
    # 실측: 1,058건(13.7만 자)이 4.0초. 이 정도면 한 번에 옮길 일이 거의 없는 양이다.
    #
    # 넘기면 422 가 나는데, 그 메시지가 화면에 닿는지가 더 중요하다. detail 이
    # 배열이라 예전에는 `[object Object]` 만 떴다(api.js 의 detailText 로 고쳤다).
    # 한계에 부딪히는 것은 괜찮다 — 왜 막혔는지 모르는 것이 문제다.
    text: str = Field(
        max_length=200_000,
        description="매물 목록 텍스트. 20만 자(약 2,000건)까지.",
    )
    # 사용자가 직접 고른 '붙여넣은 단지명 -> 단지 id'.
    #
    # 고르는 단위가 **이름**인 이유: 같은 이름이 여럿이라 못 고른 것이므로, 한 번
    # 고르면 그 이름의 매물이 **전부** 풀린다. 실제 붙여넣기에서 '현대' 20건이
    # 한 덩어리였다 — 줄마다 고르게 하면 스무 번을 눌러야 한다.
    name_map: dict[str, int] = Field(default_factory=dict)
    months: int = Field(default=24, ge=6, le=120)
    basis: str = Field(default="market", pattern="^(market|factor)$")


@router.post("/parse-bulk")
def parse_bulk(req: BulkRequest, db: Session = Depends(get_db)):
    """목록을 통째로 붙여넣어 여러 매물을 한 번에 읽고 줄 세운다 — `listing_match.parse_bulk`."""
    try:
        return listing_match.parse_bulk(
            db, req.text, req.name_map, months=req.months, basis=req.basis,
        )
    except listing_match.NoListings as exc:
        raise HTTPException(422, str(exc))
