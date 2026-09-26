from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import pricing
from ..db import get_db
from ..services import hedonic
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


class ListingSide(BaseModel):
    complex_id: int
    exclusive_area: float = Field(gt=0, le=400)
    floor: int | None = Field(default=None, ge=-5, le=100)
    asking_price: int | None = Field(default=None, gt=0)  # 만원
    # 있으면 역까지 도보를 **그 동 좌표 기준**으로 잡는다. 없으면 단지 중심점.
    dong: str | None = Field(default=None, max_length=20)


class CompareRequest(BaseModel):
    a: ListingSide
    b: ListingSide
    months: int = Field(default=24, ge=6, le=120)
    spec: str = hedonic.DEFAULT_SPEC


@router.post("/compare")
def compare(req: CompareRequest, db: Session = Depends(get_db)):
    """매물 두 개를 요인별로 분해해 비교한다.

    평당가 차이를 면적·층·거리·연식·세대수·노선·구 기여로 쪼개고,
    합계(모델 예상 차이)를 실제 호가 차이와 견줘 어느 쪽이 싼지 판정한다.
    """
    f = _fit(db, req.months, req.spec)
    out = mv.compare_listings(db, f, req.a.model_dump(), req.b.model_dump())
    if out.get("error"):
        raise HTTPException(status_code=422, detail=out["error"])
    return out


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


@router.get("/residuals")
def residuals(
    db: Session = Depends(get_db),
    months: int = Query(24, ge=6, le=120),
    spec: str = Query(hedonic.DEFAULT_SPEC),
    sort: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
):
    """모델이 설명하지 못한 단지별 편차.

    '저평가'가 아니라 '모델 잔차'다 — 학군·브랜드·조망·재건축 기대가 전부 여기 섞여 있다.
    정렬은 축소(shrinkage)한 값으로 한다. 축소 없이 정렬하면 상위권이 전부
    거래 3건짜리 단지로 채워진다.
    """
    f = _fit(db, months, spec)
    payload = mv.map_payload(db, f)
    items = [i for i in payload["items"] if i["residual_shrunk_pct"] is not None]
    items.sort(key=lambda i: i["residual_shrunk_pct"], reverse=(sort == "desc"))
    return {
        "months": months,
        "spec": f["spec"],
        "count": len(items),
        "tau_pct": f["tau_pct"],
        "note": payload["metrics"]["residual_shrunk_pct"]["note"],
        "items": items[:limit],
    }


class ParseRequest(BaseModel):
    text: str = Field(max_length=4000)
    # 이름이 애매해 후보를 직접 고른 경우. 단지가 정해져야 max_floor 를 알 수 있고,
    # 그래야 '고층' 같은 표기를 층으로 옮기고 면적을 실제 평형에 맞출 수 있다.
    complex_id: int | None = None


@router.post("/parse-listing")
def parse_listing(req: ParseRequest, db: Session = Depends(get_db)):
    """붙여넣은 매물 텍스트에서 단지·면적·층·호가를 뽑는다.

    링크가 아니라 텍스트를 받는 이유는 `services/listing_parse` 의 모듈 주석 참조.
    단지가 확정되면 그 단지에 **실제로 존재하는 전용면적 목록**을 함께 돌려주고,
    뽑아낸 면적을 가장 가까운 타입으로 맞춰 준다. 네이버는 84.97 로 쓰고
    실거래가는 84.9 로 들어오는 식이라, 글자 그대로 쓰면 비교 대상이 비어 버린다.
    """
    from sqlalchemy import select

    from ..models import Complex, ComplexStation
    from ..services import analysis
    from ..services import listing_parse

    cxs = db.execute(select(Complex)).scalars().all()
    out = listing_parse.parse_listing(req.text, cxs).as_dict()

    if req.complex_id:
        picked = db.get(Complex, req.complex_id)
        if not picked:
            raise HTTPException(404, "단지를 찾을 수 없습니다")
        out["complex_id"] = picked.id
        out["complex_name"] = picked.name
        # 이름이 안 맞는다는 경고는 사용자가 직접 고른 순간 의미가 없다.
        out["warnings"] = [w for w in out["warnings"] if "단지명" not in w]

    cid = out.get("complex_id")
    if cid:
        points = analysis.load_points(db, months=120, complex_id=cid)
        keys = sorted({pricing.area_type_key(p.exclusive_area) for p in points})
        out["area_options"] = [
            {"exclusive_area": k, "pyeong": round(pricing.to_pyeong(k), 1)} for k in keys
        ]
        # 동을 알면 역까지 도보가 그 동 기준으로 바뀐다. 얼마나 달라지는지
        # 보여 줘야 사용자가 값이 왜 바뀌었는지 안다.
        _, dong_walk = mv._dong_walk(db, cid, out.get("dong"))
        out["dong_walk_min"] = round(dong_walk, 1) if dong_walk is not None else None
        cs = db.execute(
            select(ComplexStation)
            .where(ComplexStation.complex_id == cid)
            .order_by(ComplexStation.walk_seconds)
        ).scalars().first()
        center = pricing.walk_minutes_from_seconds(cs.walk_seconds) if cs else None
        out["complex_walk_min"] = round(center, 1) if center is not None else None
        if dong_walk is not None and center is not None and abs(dong_walk - center) >= 0.5:
            out["warnings"].append(
                f"{out['dong']}동 기준 역까지 도보 {dong_walk:.1f}분입니다"
                f"(단지 중심점 {center:.1f}분). 이 동 좌표로 계산합니다."
            )
        elif out.get("dong") and dong_walk is None:
            out["warnings"].append(
                f"{out['dong']}동의 좌표가 없어 역거리는 단지 중심점 기준으로 계산합니다."
            )

        cx = db.get(Complex, cid)
        # '8/15층' 처럼 매물에 총 층수가 적혀 있으면 그쪽이 맞다. DB 의 max_floor 는
        # **거래에서 관측된** 최고층이라 거래가 적은 단지에서는 실제보다 낮다.
        out["max_floor"] = out.get("total_floor") or (cx.max_floor if cx else None)

        # 층은 숫자가 없고 '중층' 같은 표기만 오는 경우가 흔하다. 모델이 실제로 쓰는
        # 것은 **층 구간**뿐이므로(`pricing.floor_band`), 그 구간에 들어가는 대표 층을
        # 찾아 채워 주면 결과는 정확히 같다. 사용자가 굳이 층수를 물어볼 필요가 없다.
        if out.get("floor") is None and out.get("floor_band") and out.get("max_floor"):
            mf = int(out["max_floor"])
            want = out["floor_band"]
            hits = [f for f in range(1, mf + 1) if pricing.floor_band(f, mf) == want]
            if hits:
                out["floor"] = hits[len(hits) // 2]
                out["warnings"].append(
                    f"'{want}' 표기를 {out['floor']}층으로 봤습니다"
                    f"(총 {mf}층 기준 — 모델은 층 구간만 쓰므로 결과는 같습니다)."
                )

        area = out.get("exclusive_area")
        if area and keys:
            counts: dict[int, int] = {}
            for pt in points:
                k = pricing.area_type_key(pt.exclusive_area)
                counts[k] = counts.get(k, 0) + 1
            _resolve_area(out, area, keys, counts, explicit=out.get("area_is_explicit"))
    else:
        out["area_options"] = []
        out["max_floor"] = None
        out["dong_walk_min"] = None
        out["complex_walk_min"] = None

    # 호가를 쌓는다. 붙여넣는 것만으로 모이게 해야 실제로 모인다 — 따로 '저장' 을
    # 누르게 하면 아무도 안 누른다. 같은 호가 재입력은 중복으로 쌓이지 않는다.
    out["quote_recorded"] = None
    if out.get("complex_id") and out.get("exclusive_area") and out.get("asking_price"):
        from ..services import quotes

        try:
            out["quote_recorded"] = quotes.record(
                db,
                complex_id=out["complex_id"],
                dong=out.get("dong"),
                exclusive_area=out["exclusive_area"],
                floor=out.get("floor"),
                floor_band=out.get("floor_band"),
                asking_price=out["asking_price"],
            )
        except Exception:  # 호가 기록 실패가 파싱 결과를 날려선 안 된다
            db.rollback()
    return out


# 전용률(전용/공급)의 현실적인 범위. 판상형 신축이 0.80 근처, 타워형 구축이 0.65 근처다.
# 이 밖이면 공급으로 해석해도 말이 안 되므로 후보에서 뺀다.
_RATIO_MIN, _RATIO_MAX = 0.60, 0.90
_RATIO_TYPICAL = 0.75


def _resolve_area(
    out: dict, area: float, keys: list[int], counts: dict[int, int], explicit: bool = False
) -> None:
    """붙여넣은 면적을 그 단지에 **실제로 거래된 전용 평형**에 맞춘다.

    광고의 '34평'·'112㎡' 는 거의 항상 **공급면적**이다. 그대로 전용으로 넣으면
    112㎡ 전용을 가진 단지가 아닌 한 "그런 평형 없음" 으로 비워지고, 사용자는
    평 환산이 안 된 것처럼 본다. 실제로는 34평(=112.4㎡ 공급)의 전용이 85㎡ 다.

    그래서 두 해석을 **데이터에 물어본다**.

    1. 숫자가 이 단지의 전용 평형과 바로 맞으면 → 전용으로 적힌 것.
    2. 아니면 전용률 0.60~0.90 안에 드는 평형을 찾는다. 여럿이면 **거래가 많은 쪽**을
       고른다. '34평' 이 가리키는 것은 그 단지의 주력 평형이기 때문이다.
    3. 둘 다 아니면 비우고 직접 고르게 한다 — 찍는 것보다 낫다.

    `explicit` 은 텍스트에 '전용' 이라고 적혀 있었다는 뜻이다. 그때는 2번을 건너뛴다.
    """
    near = min(keys, key=lambda k: abs(k - area))
    if abs(near - area) <= 2.0:
        if pricing.area_type_key(area) != near:
            out["warnings"].append(
                f"전용 {area:g}㎡ 를 이 단지의 실제 타입 {near}㎡ 로 맞췄습니다."
            )
        out["exclusive_area"] = float(near)
        return

    if not explicit:
        cands = [k for k in keys if _RATIO_MIN <= k / area <= _RATIO_MAX]
        if cands:
            # 거래 건수 우선, 같으면 전용률이 통상값에 가까운 쪽.
            best = max(cands, key=lambda k: (counts.get(k, 0), -abs(k / area - _RATIO_TYPICAL)))
            out["supply_area"] = out.get("supply_area") or area
            out["exclusive_area"] = float(best)
            out["warnings"].append(
                f"{area:g}㎡({pricing.to_pyeong(area):.1f}평)는 공급면적으로 보입니다 — "
                f"이 단지의 전용 {best}㎡({pricing.to_pyeong(best):.1f}평, 전용률 "
                f"{best / area * 100:.0f}%)로 맞췄습니다. 이 서비스의 평당가는 전용 기준입니다."
            )
            return

    out["warnings"].append(
        f"{area:g}㎡ 와 맞는 평형이 이 단지 거래에 없습니다. 목록에서 직접 고르세요."
    )
    out["exclusive_area"] = None
