from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pricing
from ..db import get_db
from ..models import Complex
from ..services import analysis

router = APIRouter(prefix="/api/complexes", tags=["complexes"])


@router.get("/{complex_id}")
def get_complex(
    complex_id: int,
    months: int = Query(12, ge=1, le=120),
    db: Session = Depends(get_db),
):
    result = analysis.complex_overview(db, complex_id, months)
    if not result:
        raise HTTPException(404, "단지를 찾을 수 없습니다")
    return result


@router.get("/{complex_id}/dongs")
def dongs(complex_id: int, db: Session = Depends(get_db)):
    """단지 안의 동 목록과 **동별 역까지 도보시간**.

    같은 단지라도 동에 따라 역까지 100~330m 차이난다. 사용자가 동을 직접 타이핑하게
    하면 오타도 나고 그 동이 얼마나 먼지도 모르는데, 목록으로 주면 둘 다 해결된다.
    좌표를 못 잡은 동은 `walk_min` 이 없다 — 그때는 단지 중심점으로 계산한다.
    """
    from ..models import ComplexDong, DongTag

    if not db.get(Complex, complex_id):
        raise HTTPException(404, "단지를 찾을 수 없습니다")

    rows = db.execute(
        select(ComplexDong).where(ComplexDong.complex_id == complex_id)
    ).scalars().all()

    # 사람이 표시한 것. 적재로 다시 채워지는 complex_dongs 와 섞지 않는다.
    tags = {
        t.dong: t
        for t in db.execute(
            select(DongTag).where(DongTag.complex_id == complex_id)
        ).scalars().all()
    }

    # 동별 가격 프리미엄은 적합 결과에 들어 있다. 적합이 아직 없으면(첫 요청) 비워
    # 두고 거리만 준다 — 이 엔드포인트가 14초짜리 적합을 기다리게 만들 이유는 없다.
    prem: dict[str, dict] = {}
    try:
        from ..services import model_view as mv

        fit = mv.peek_fit(db)
        if fit:
            prem = {
                d: v for (c, d), v in (fit.get("dong_effects") or {}).items()
                if c == complex_id
            }
    except Exception:
        prem = {}

    def sort_key(r):
        # '101' 은 숫자로, '가' 는 글자로 정렬한다.
        return (0, int(r.dong), "") if r.dong.isdigit() else (1, 0, r.dong)

    items = [
        {
            "dong": r.dong,
            "walk_min": (
                round(pricing.walk_minutes_from_seconds(r.walk_seconds), 1)
                if r.walk_seconds is not None
                else None
            ),
            "walk_distance_m": round(r.walk_distance_m) if r.walk_distance_m else None,
            "premium_pct": (prem.get(r.dong) or {}).get("pct"),
            "premium_n": (prem.get(r.dong) or {}).get("n"),
            "rental": bool(getattr(tags.get(r.dong), "rental", False)),
        }
        for r in sorted(rows, key=sort_key)
    ]
    known = [i["walk_min"] for i in items if i["walk_min"] is not None]
    prems = [i["premium_pct"] for i in items if i["premium_pct"] is not None]
    return {
        "complex_id": complex_id,
        "items": items,
        "premium_spread_pct": round(max(prems) - min(prems), 1) if len(prems) > 1 else None,
        # 동 사이 편차가 크면 동 선택이 그만큼 중요하다는 신호다.
        "spread_min": round(max(known) - min(known), 1) if len(known) > 1 else None,
        "rental_dongs": sorted(d for d, t in tags.items() if t.rental),
    }


@router.get("/meta/filters")
def filters(db: Session = Depends(get_db)):
    from ..clients.molit import DISTRICTS
    from ..models import Station

    present = db.execute(select(Complex.sgg_cd).distinct()).scalars().all()

    # 노선·역은 고정 목록이 아니라 **실제로 단지가 붙어 있는 역**만 내보낸다.
    # 단지가 하나도 안 붙은 역을 필터에 띄우면 고르는 순간 빈 화면이 된다.
    used = db.execute(
        select(Station.line, Station.name, Station.minutes_to_gangnam)
        .join(Complex, Complex.nearest_station_id == Station.id)
        .distinct()
    ).all()
    lines = sorted({line for line, _, _ in used})
    stations = sorted(
        ({"name": n, "line": ln, "minutes_to_gangnam": g} for ln, n, g in used),
        key=lambda s: (s["line"], s["minutes_to_gangnam"] or 999, s["name"]),
    )

    return {
        "districts": [
            {"code": c, "name": DISTRICTS.get(c, c)} for c in sorted(present)
        ],
        "area_bands": pricing.AREA_BANDS,
        "station_bands": pricing.STATION_BANDS[:-1],
        "age_bands": pricing.AGE_BANDS[:-1],
        "floor_bands": pricing.FLOOR_BANDS[:-1],
        "household_bands": pricing.HOUSEHOLD_BANDS[:-1],
        "lines": lines,
        "stations": stations,
        "reference_year": date.today().year,
    }


class RentalIn(BaseModel):
    rental: bool


@router.put("/{complex_id}/dongs/{dong}/rental")
def set_rental(
    complex_id: int, dong: str, body: RentalIn, db: Session = Depends(get_db)
):
    """동을 민간임대로 표시하거나 해제한다.

    표시를 끄면 행을 지운다. `rental=False` 행을 남겨 두면 '표시한 적 없음' 과
    '표시했다가 껐음' 이 구분되지 않는데, 그 구분에 쓸 데가 없다.
    """
    from ..models import DongTag

    if not db.get(Complex, complex_id):
        raise HTTPException(404, "단지를 찾을 수 없습니다")

    row = db.execute(
        select(DongTag).where(DongTag.complex_id == complex_id, DongTag.dong == dong)
    ).scalar_one_or_none()

    if not body.rental:
        if row:
            db.delete(row)
            db.commit()
        return {"dong": dong, "rental": False}

    if row:
        row.rental = True
    else:
        db.add(DongTag(complex_id=complex_id, dong=dong, rental=True))
    db.commit()
    return {"dong": dong, "rental": True}
