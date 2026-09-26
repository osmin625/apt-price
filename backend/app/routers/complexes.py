from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pricing
from ..db import get_db
from ..models import Complex
from ..services import analysis

router = APIRouter(prefix="/api/complexes", tags=["complexes"])


@router.get("")
def list_complexes(
    db: Session = Depends(get_db),
    months: int = Query(12, ge=1, le=120),
    sgg_cd: str | None = None,
    q: str | None = None,
    area_band: str | None = None,
    station_band: str | None = None,
    age_band: str | None = None,
    line: str | None = None,
    station: str | None = None,
    household_band: str | None = None,
    min_trades: int = Query(1, ge=0),
    sort: str = Query("ppp_desc", pattern="^(ppp_desc|ppp_asc|name|trades_desc)$"),
    limit: int = Query(200, ge=1, le=1000),
):
    """단지 목록 + 단지별 전용면적 평당가 요약."""
    points = analysis.load_points(
        db,
        months=months,
        sgg_cd=sgg_cd,
        query=q,
        area_band=area_band,
        station_band=station_band,
        age_band=age_band,
        line=line,
        station=station,
        household_band=household_band,
    )

    grouped: dict[int, list] = {}
    for p in points:
        grouped.setdefault(p.complex_id, []).append(p)

    if not grouped:
        return {"months": months, "count": 0, "items": []}

    index = pricing.market_index(points)
    rows = db.execute(select(Complex).where(Complex.id.in_(grouped))).scalars().all()

    items = []
    for cx in rows:
        pts = grouped[cx.id]
        if len(pts) < min_trades:
            continue
        item = analysis.serialize_complex(cx, pts, index)
        item["trade_count"] = len(pts)
        item["latest_deal_date"] = max(p.deal_date for p in pts)
        items.append(item)

    if sort == "name":
        items.sort(key=lambda x: x["name"])
    elif sort == "trades_desc":
        items.sort(key=lambda x: x["trade_count"], reverse=True)
    else:
        items.sort(
            key=lambda x: x["ppp"]["median"] if x["ppp"] else 0,
            reverse=sort == "ppp_desc",
        )

    return {"months": months, "count": len(items), "items": items[:limit]}


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


@router.get("/{complex_id}/area-types")
def area_types(complex_id: int, db: Session = Depends(get_db)):
    """해당 단지에 존재하는 전용면적 타입 목록 — 매물 입력 시 선택지로 쓴다."""
    cx = db.get(Complex, complex_id)
    if not cx:
        raise HTTPException(404, "단지를 찾을 수 없습니다")

    points = analysis.load_points(db, months=120, complex_id=complex_id)
    keys = sorted({pricing.area_type_key(p.exclusive_area) for p in points})
    return {
        "complex_id": complex_id,
        "max_floor": cx.max_floor,
        "items": [
            {
                "exclusive_area": k,
                "pyeong": round(pricing.to_pyeong(k), 1),
                "area_band": pricing.area_band(k),
            }
            for k in keys
        ],
    }


@router.get("/{complex_id}/dongs")
def dongs(complex_id: int, db: Session = Depends(get_db)):
    """단지 안의 동 목록과 **동별 역까지 도보시간**.

    같은 단지라도 동에 따라 역까지 100~330m 차이난다. 사용자가 동을 직접 타이핑하게
    하면 오타도 나고 그 동이 얼마나 먼지도 모르는데, 목록으로 주면 둘 다 해결된다.
    좌표를 못 잡은 동은 `walk_min` 이 없다 — 그때는 단지 중심점으로 계산한다.
    """
    from ..models import ComplexDong

    if not db.get(Complex, complex_id):
        raise HTTPException(404, "단지를 찾을 수 없습니다")

    rows = db.execute(
        select(ComplexDong).where(ComplexDong.complex_id == complex_id)
    ).scalars().all()

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
    }


@router.get("/{complex_id}/quotes")
def quotes_summary(
    complex_id: int,
    area_key: int | None = Query(None, description="전용면적 반올림(㎡). 주면 그 평형만"),
    dong: str | None = Query(None, description="주면 그 동의 호가 경로도 함께"),
    db: Session = Depends(get_db),
):
    """누적된 **호가** 현황. 실거래가 뜸한 동을 볼 때 실거래 옆에 놓고 읽는다."""
    from ..services import quotes

    if not db.get(Complex, complex_id):
        raise HTTPException(404, "단지를 찾을 수 없습니다")
    out = quotes.summary(db, complex_id, area_key)
    if dong:
        out["history"] = quotes.history(db, complex_id, dong, area_key)
    return out


@router.get("/meta/filters")
def filters(db: Session = Depends(get_db)):
    from ..clients.molit import SUWON_DISTRICTS
    from ..models import Station

    present = db.execute(select(Complex.sgg_cd).distinct()).scalars().all()

    # 노선·역은 고정 목록이 아니라 **실제로 단지가 붙어 있는 역**만 내보낸다.
    # 수원 단지가 하나도 없는 역을 필터에 띄우면 고르는 순간 빈 화면이 된다.
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
            {"code": c, "name": SUWON_DISTRICTS.get(c, c)} for c in sorted(present)
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
