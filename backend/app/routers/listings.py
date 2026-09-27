from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pricing
from ..db import get_db
from ..models import Complex, Listing
from ..schemas import ListingInput
from ..services import analysis

router = APIRouter(prefix="/api/listings", tags=["listings"])


def _verdict(gap_pct: float) -> str:
    if gap_pct <= -10:
        return "저평가"
    if gap_pct <= -3:
        return "다소 저렴"
    if gap_pct < 3:
        return "적정"
    if gap_pct < 10:
        return "다소 비쌈"
    return "고평가"


def _calibrate_model(m: dict | None, fair: dict) -> None:
    """모델의 **유닛 단위 보정**을 그 단지 실거래로 교정한다.

    모델은 `α_c + f(면적) + 층` 구조인데 `f` 는 **전 단지 공통 곡선**이다. 어떤 단지의
    40㎡ 가 84㎡ 대비 얼마나 싼지는 단지마다 다른데, 공통 곡선은 그 차이를 못 담는다.
    실제로 수원센트럴아이파크자이 40㎡ 에서는 모델의 시장 기준(46,111만원)이 같은 평형
    실거래 기준(40,532만원)보다 **14% 높게** 나왔다.

    두 값은 같은 질문("이 단지 이 유닛이 지금 얼마에 팔리나")의 답이므로, 어긋난 만큼이
    곧 면적 곡선의 이 단지·이 평형 오차다. 비율로 뽑아 요인 기준에도 똑같이 먹인다 —
    단지 간 펀더멘털(Stage 2)은 그대로 두고, 단지 안에서의 유닛 환산만 고친다.

        보정계수 = 실거래 기준 평당가 / 모델 시장 기준 평당가

    실거래 비교가 없으면 보정할 수 없으므로 원값을 쓰고 그 사실을 남긴다.
    """
    if not m or not m.get("market_ppp") or not fair.get("fair_ppp"):
        return
    k = float(fair["fair_ppp"]) / float(m["market_ppp"])
    # 2배 넘게 벌어지면 교정이 아니라 다른 데가 고장 난 것이다. 손대지 않는다.
    if not (0.5 <= k <= 2.0):
        m["calibration"] = {"applied": False, "factor": round(k, 4),
                            "reason": "실거래 기준과 모델 시장 기준이 2배 넘게 벌어져 교정하지 않았습니다."}
        return
    m["calibration"] = {
        "applied": True,
        "factor": round(k, 4),
        "pct": round((k - 1) * 100, 1),
        "note": (
            "면적 곡선은 전 단지 공통이라 이 단지의 평형 간 격차를 정확히 담지 못합니다. "
            "같은 평형 실거래로 그 차이만큼 교정했습니다 — 단지 간 요인(거리·연식·노선 등)은 "
            "그대로입니다."
        ),
    }
    m["factor_price_adj"] = round(m["factor_price"] * k)
    m["factor_ppp_adj"] = round(m["factor_ppp"] * k, 1)


def _evaluate(db: Session, payload: ListingInput, months: int) -> dict:
    # 동 프리미엄은 적합 결과에 있다. 없으면(첫 요청) 동 보정 없이 간다 —
    # 가벼운 진단이 14초짜리 적합을 기다리게 만들 이유는 없다.
    from ..services import model_view as mv

    cached = mv.peek_fit(db, months=months)
    fair = analysis.estimate_fair_price(
        db,
        complex_id=payload.complex_id,
        exclusive_area=payload.exclusive_area,
        floor=payload.floor,
        months=months,
        dong=(payload.dong or "").strip().removesuffix("동").strip() or None,
        dong_effects=(cached or {}).get("dong_effects"),
    )
    if fair is None:
        raise HTTPException(404, "단지를 찾을 수 없습니다")

    pyeong = pricing.to_pyeong(payload.exclusive_area)
    asking_ppp = payload.asking_price / pyeong

    result = {
        "input": {
            "complex_id": payload.complex_id,
            "label": payload.label,
            "exclusive_area": round(payload.exclusive_area, 2),
            "supply_area": payload.supply_area,
            "exclusive_ratio": (
                round(payload.exclusive_area / payload.supply_area * 100, 1)
                if payload.supply_area
                else None
            ),
            "pyeong": round(pyeong, 2),
            "floor": payload.floor,
            "asking_price": payload.asking_price,
            "asking_ppp": round(asking_ppp, 1),
        },
        "fair": fair,
    }

    # 요인 기준 적정가. 실거래 비교와 **다른 질문**의 답이라 나란히 둔다.
    # 적합이 아직 없으면 생략한다 — 가벼운 진단이 14초를 기다리게 할 이유는 없다.
    result["model"] = None
    if cached:
        try:
            result["model"] = mv.model_price(db, cached, {
                "complex_id": payload.complex_id,
                "exclusive_area": payload.exclusive_area,
                "floor": payload.floor,
                "dong": payload.dong,
            })
        except Exception:
            result["model"] = None

    _calibrate_model(result.get("model"), fair)

    if fair.get("fair_price"):
        gap = payload.asking_price - fair["fair_price"]
        gap_pct = gap / fair["fair_price"] * 100
        result["gap"] = {
            "amount": round(gap),
            "pct": round(gap_pct, 1),
            "verdict": _verdict(gap_pct),
        }
        m = result.get("model")
        if m and m.get("factor_price"):
            # 요인 기준 대비 괴리. 실거래 기준 판정과 갈릴 수 있고, 갈리는 것이 정보다.
            fp = m.get("factor_price_adj") or m["factor_price"]
            result["gap_factor"] = {
                "amount": round(payload.asking_price - fp),
                "pct": round((payload.asking_price - fp) / fp * 100, 1),
                "verdict": _verdict((payload.asking_price - fp) / fp * 100),
            }
    else:
        result["gap"] = None

    return result


@router.post("/evaluate")
def evaluate(
    payload: ListingInput,
    months: int = Query(12, ge=1, le=120),
    db: Session = Depends(get_db),
):
    """저장하지 않고 호가만 평가 — 적정가 대비 괴리율."""
    return _evaluate(db, payload, months)


@router.post("")
def create_listing(
    payload: ListingInput,
    months: int = Query(12, ge=1, le=120),
    db: Session = Depends(get_db),
):
    if not db.get(Complex, payload.complex_id):
        raise HTTPException(404, "단지를 찾을 수 없습니다")

    listing = Listing(**payload.model_dump())
    db.add(listing)
    db.commit()

    result = _evaluate(db, payload, months)
    result["id"] = listing.id
    return result


@router.get("")
def list_listings(
    months: int = Query(12, ge=1, le=120),
    basis: str = Query("market", pattern="^(market|factor)$"),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Listing).order_by(Listing.created_at.desc())).scalars().all()
    out = []
    for row in rows:
        payload = ListingInput(
            complex_id=row.complex_id,
            exclusive_area=row.exclusive_area,
            floor=row.floor,
            # 동을 빼먹으면 저장 시점과 다른 값이 나온다 — 동 보정이 빠지기 때문이다.
            dong=row.dong,
            asking_price=row.asking_price,
            supply_area=row.supply_area,
            label=row.label,
            memo=row.memo,
        )
        item = _evaluate(db, payload, months)
        item["id"] = row.id
        item["memo"] = row.memo
        item["created_at"] = row.created_at.isoformat() if row.created_at else None
        out.append(item)

    # ── 순위 ──────────────────────────────────────────────────────────────
    # **더 저평가된 매물이 이긴다** — 괴리율이 작을수록(음수일수록) 위로 간다.
    #
    # 기준이 둘이라 하나로 줄 세울 수 없다. 둘은 다른 질문의 답이다.
    #   market: 그 단지 같은 평형 시세 대비 싼가 (단지 프리미엄 포함)
    #   factor: 펀더멘털 대비 싼가 (단지 프리미엄 제외)
    # 단지를 넘나들며 고를 때는 factor 가 맞고, 같은 단지 안에서는 market 이 맞다.
    # 그래서 고르게 두고, 표에는 **둘 다** 보여 준다 — 어긋나는 것 자체가 정보다.
    key = (
        (lambda i: (i.get("gap_factor") or {}).get("pct"))
        if basis == "factor"
        else (lambda i: (i.get("gap") or {}).get("pct"))
    )
    ranked = [i for i in out if key(i) is not None]
    unranked = [i for i in out if key(i) is None]
    ranked.sort(key=key)
    for n, item in enumerate(ranked, 1):
        item["rank"] = n
    for item in unranked:
        item["rank"] = None

    return {
        "count": len(out),
        "basis": basis,
        "basis_label": "요인 기준" if basis == "factor" else "실거래 기준",
        "ranked_count": len(ranked),
        "items": ranked + unranked,
    }


@router.delete("/{listing_id}")
def delete_listing(listing_id: int, db: Session = Depends(get_db)):
    row = db.get(Listing, listing_id)
    if not row:
        raise HTTPException(404, "매물을 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return {"ok": True}
