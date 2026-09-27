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
    # 시공사 합동 단지는 이름이 1:N 이라 못 고른다. 동 번호로 좁혀 본다.
    _resolve_by_dong(out, req.text, db, cxs)

    if req.complex_id:
        picked = db.get(Complex, req.complex_id)
        if not picked:
            raise HTTPException(404, "단지를 찾을 수 없습니다")
        out["complex_id"] = picked.id
        out["complex_name"] = picked.name
        # 이름이 안 맞는다는 경고는 사용자가 직접 고른 순간 의미가 없다.
        out["warnings"] = [w for w in out["warnings"] if w.get("field") != "complex"]

    cid = out.get("complex_id")
    if cid:
        points = analysis.load_points(db, months=120, complex_id=cid)
        keys, reps = _area_types(points)
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
            out["warnings"].append({"field": "dong", "text":
                f"{out['dong']}동 기준 역까지 도보 {dong_walk:.1f}분입니다"
                f"(단지 중심점 {center:.1f}분). 이 동 좌표로 계산합니다."})
        elif out.get("dong") and dong_walk is None:
            out["warnings"].append({"field": "dong", "text":
                f"{out['dong']}동의 좌표가 없어 역거리는 단지 중심점 기준으로 계산합니다."})

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
                out["warnings"].append({"field": "floor", "text":
                    f"'{want}' 표기를 {out['floor']}층으로 봤습니다"
                    f"(총 {mf}층 기준 — 모델은 층 구간만 쓰므로 결과는 같습니다)."})

        area = out.get("exclusive_area")
        if area and keys:
            counts: dict[int, int] = {}
            for pt in points:
                k = pricing.area_type_key(pt.exclusive_area)
                counts[k] = counts.get(k, 0) + 1
            _resolve_area(out, area, keys, counts,
                          explicit=out.get("area_is_explicit"), reps=reps)
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
                # 단건도 확인일자가 붙어 있으면 읽는다 — 일괄 붙여넣기와 같은 기준.
                confirmed_on=listing_parse.parse_confirmed_on(req.text),
            )
        except Exception:  # 호가 기록 실패가 파싱 결과를 날려선 안 된다
            db.rollback()
    return out


# 전용률(전용/공급)의 현실적인 범위. 판상형 신축이 0.80 근처, 타워형 구축이 0.65 근처다.
# 이 밖이면 공급으로 해석해도 말이 안 되므로 후보에서 뺀다.
_RATIO_MIN, _RATIO_MAX = 0.60, 0.90
_RATIO_TYPICAL = 0.75


def _resolve_by_dong(out: dict, text: str, db: Session, complexes: list) -> None:
    """단지명을 못 찾았을 때 **동 번호**로 좁힌다.

    시공사 합동 단지는 네이버가 '신성,신안,쌍용,진흥' 으로 묶어 쓰고 국토부는
    '신나무실신성'·'신나무실신안'·'신나무실쌍용'·'신나무실진흥' 으로 쪼개 기록한다.
    이름으로는 1:N 이라 고를 수 없다.

    그런데 **동 번호는 겹치지 않는다.** 실거래에 찍힌 동을 세어 보면 이렇다.

        신나무실신안  531~534    신나무실신성  521~524
        신나무실쌍용  541~544    신나무실진흥  551~554

    그래서 543동은 쌍용, 534동은 신안으로 유일하게 정해진다. 이름 조각과 동 번호가
    **둘 다** 맞을 때만 고르므로, '쌍용' 이 흔한 이름이어도 엉뚱한 단지가 걸리지 않는다.
    둘 이상 남으면 고르지 않고 후보로만 둔다 — 찍는 것보다 낫다.
    """
    from sqlalchemy import select

    from ..models import Trade
    from ..services import listing_parse

    dong = (out.get("dong") or "").strip()
    if out.get("complex_id") or not dong:
        return
    frags = listing_parse.name_fragments(text)
    if len(frags) < 2:
        return  # 조각이 하나뿐이면 이름이 쪼개진 경우가 아니다

    pool = [c for c in complexes if any(f in c.name for f in frags)]
    if not pool:
        return

    ids = [c.id for c in pool]
    rows = db.execute(
        select(Trade.complex_id)
        .where(Trade.complex_id.in_(ids))
        .where(Trade.apt_dong.in_([dong, dong + "동"]))
        .distinct()
    ).scalars().all()
    if len(rows) != 1:
        return

    cx = next(c for c in pool if c.id == rows[0])
    out["complex_id"] = cx.id
    out["complex_name"] = cx.name
    out["warnings"] = [w for w in out.get("warnings", [])
                       if w.get("field") != "complex"]
    out["warnings"].append({"field": "complex", "text":
        f"'{', '.join(frags)}' 는 시공사가 함께 지은 단지라 실거래에는 나뉘어 있습니다. "
        f"{dong}동 거래가 있는 '{cx.name}' 으로 맞췄습니다."})


def _resolve_area(
    out: dict, area: float, keys: list[int], counts: dict[int, int],
    explicit: bool = False, reps: dict[int, float] | None = None,
) -> None:
    """붙여넣은 면적을 그 단지에 **실제로 거래된 전용 평형**에 맞춘다.

    ## 세 가지를 순서대로 시도한다

    1. **정수 평 구간.** 네이버는 전용 평을 버림해서 쓴다 — 실제 49.58㎡ 는
       14.998평이지만 화면에는 '전용14' 로 나온다. 그러니 그 표기는 점이 아니라
       `[14, 15)평 = [46.3, 49.6)㎡` 구간이다. 하한을 점추정으로 쓰면 실제값과
       3.3㎡ 벌어져 멀쩡한 매물이 버려진다.
    2. **근접 매칭.** 구간 정보가 없으면 ±2㎡ 안에서 가장 가까운 타입.
    3. **공급면적 재해석.** 광고의 `34평`·`112㎡` 는 대개 공급이다. 전용률
       0.60~0.90 안에 드는 타입을 찾고, 여럿이면 거래가 많은 쪽을 고른다.

    비교 대상은 **반올림한 타입 키가 아니라 실제 대표 면적**이다. 키 `50` 은
    49.58㎡ 를 반올림한 값이라, 키로 비교하면 구간 판정이 어긋난다.

    3번은 예전에 `explicit`(전용이라고 적힘) 이면 건너뛰었는데, 그러면 1·2 가
    모두 실패했을 때 통째로 버려진다. 마지막 수단으로는 써야 한다.
    """
    reps = reps or {k: float(k) for k in keys}

    def rep(k: int) -> float:
        return reps.get(k, float(k))

    # 1) 정수 평 구간
    py = out.get("area_pyeong")
    if py:
        lo, hi = py * pricing.PYEONG_M2, (py + 1) * pricing.PYEONG_M2
        band = [k for k in keys if lo <= rep(k) <= hi]
        if band:
            best = max(band, key=lambda k: counts.get(k, 0))
            if abs(rep(best) - area) > 0.05:
                out["warnings"].append({"field": "area", "text":
                    f"'전용 {py}평' 은 네이버가 버림해 쓴 값이라 "
                    f"{lo:.1f}~{hi:.1f}㎡ 를 뜻합니다. 이 단지의 실제 타입 "
                    f"{rep(best):.2f}㎡({pricing.to_pyeong(rep(best)):.2f}평)로 맞췄습니다."})
            out["exclusive_area"] = float(best)
            return

    # 2) 근접 매칭
    near = min(keys, key=lambda k: abs(rep(k) - area))
    if abs(rep(near) - area) <= 2.0:
        if pricing.area_type_key(area) != near:
            out["warnings"].append({"field": "area", "text":
                f"전용 {area:g}㎡ 를 이 단지의 실제 타입 {near}㎡ 로 맞췄습니다."})
        out["exclusive_area"] = float(near)
        return

    # 3) 공급면적 재해석 — 마지막 수단
    cands = [k for k in keys if _RATIO_MIN <= rep(k) / area <= _RATIO_MAX]
    if cands:
        best = max(cands, key=lambda k: (counts.get(k, 0), -abs(rep(k) / area - _RATIO_TYPICAL)))
        out["supply_area"] = out.get("supply_area") or area
        out["exclusive_area"] = float(best)
        out["warnings"].append({"field": "area", "text":
            f"{area:g}㎡({pricing.to_pyeong(area):.1f}평)는 공급면적으로 보입니다 — "
            f"이 단지의 전용 {best}㎡({pricing.to_pyeong(best):.1f}평, 전용률 "
            f"{rep(best) / area * 100:.0f}%)로 맞췄습니다. 이 서비스의 평당가는 전용 기준입니다."})
        return

    # 여기까지 왔다는 것은 이 단지의 거래에 맞는 평형이 없다는 뜻이다.
    # 그런데 그것이 **면적을 잘못 읽었다는 뜻은 아니다.**
    #
    # 매물에 `전용75.97` 이라고 적혀 있으면 그 값은 확실하다. 맞는 평형이 없는 것은
    # 그 평형이 아직 거래되지 않았기 때문이다(수원성중흥S-클래스는 실거래가 1건뿐이고
    # 그마저 84.66㎡였다). 그런데도 면적을 지워 버리면 화면에는 "전용면적 또는 가격을
    # 읽지 못했습니다" 라고 뜬다 — 멀쩡히 읽은 값을 못 읽었다고 말하는 셈이고,
    # 사용자는 붙여넣기가 깨진 줄 알게 된다.
    #
    # 그래서 **명시된 값은 살린다.** 비교할 거래가 없다는 사실은 평가 단계가
    # '비교 실거래 없음' 으로 따로 알려 준다. 반대로 평 표기처럼 값 자체가 추정인
    # 경우에는 지운다 — 그때는 정말 잘못 읽었을 수 있다.
    if explicit:
        out["warnings"].append({"field": "area", "text":
            f"전용 {area:g}㎡ 는 이 단지에서 아직 거래된 적이 없는 평형입니다. "
            f"적힌 값을 그대로 씁니다 — 비교할 실거래가 없어 적정가는 못 낼 수 있습니다."})
        return

    out["warnings"].append({"field": "area", "text":
        f"{area:g}㎡ 와 맞는 평형이 이 단지 거래에 없습니다. 목록에서 직접 고르세요."})
    out["exclusive_area"] = None


def _fill_floor(out: dict) -> None:
    """'고층' 같은 표기를 그 구간의 대표 층으로 바꾼다(단건 파싱과 같은 규칙)."""
    if out.get("floor") is not None or not out.get("floor_band") or not out.get("max_floor"):
        return
    mf = int(out["max_floor"])
    want = out["floor_band"]
    hits = [f for f in range(1, mf + 1) if pricing.floor_band(f, mf) == want]
    if hits:
        out["floor"] = hits[len(hits) // 2]


def _area_types(points) -> tuple[list[int], dict[int, float]]:
    """(타입 키 목록, 타입별 **실제 대표 면적**).

    키는 반올림값이라 `50` 이 실제로는 49.58㎡ 일 수 있다. 평 구간 판정처럼
    소수점이 결과를 가르는 곳에서는 실제 값을 써야 한다.
    """
    from statistics import median

    grouped: dict[int, list[float]] = {}
    for p in points:
        grouped.setdefault(pricing.area_type_key(p.exclusive_area), []).append(p.exclusive_area)
    return sorted(grouped), {k: float(median(v)) for k, v in grouped.items()}


class BulkRequest(BaseModel):
    text: str = Field(max_length=200_000)
    months: int = Field(default=24, ge=6, le=120)
    basis: str = Field(default="market", pattern="^(market|factor)$")


@router.post("/parse-bulk")
def parse_bulk(req: BulkRequest, db: Session = Depends(get_db)):
    """목록을 통째로 붙여넣어 **여러 매물을 한 번에** 읽고 줄 세운다.

    네이버 부동산은 공개 API 가 없고 자동 수집은 이용약관 문제가 있어 이 프로젝트가
    처음부터 제외했다. 하지만 사용자가 **보고 있는 목록을 복사해 붙여넣는 것**은
    자동 수집이 아니다. 필터를 건 목록 화면을 그대로 복사하면 스크리닝이 된다.

    읽은 매물은 `Quote` 로 남는다. 그래서 `/api/quotes/ranking` 에서 지금까지 본
    모든 매물의 순위를 언제든 다시 볼 수 있다.
    """
    from sqlalchemy import select

    from ..models import Complex
    from ..services import analysis, listing_parse, quotes, ranking

    blocks = listing_parse.split_listings(req.text)
    if not blocks:
        raise HTTPException(422, "매물을 찾지 못했습니다. 목록 화면의 텍스트를 붙여넣어 주세요.")

    cxs = db.execute(select(Complex)).scalars().all()
    meta_cache: dict[int, dict] = {}

    def complex_meta(cid: int) -> dict:
        if cid not in meta_cache:
            pts = analysis.load_points(db, months=120, complex_id=cid)
            keys, reps = _area_types(pts)
            counts: dict[int, int] = {}
            for p in pts:
                k = pricing.area_type_key(p.exclusive_area)
                counts[k] = counts.get(k, 0) + 1
            cx = db.get(Complex, cid)
            meta_cache[cid] = {
                "keys": keys,
                "reps": reps,
                "counts": counts,
                "max_floor": cx.max_floor if cx else None,
            }
        return meta_cache[cid]

    rows, skipped = [], []
    for block in blocks:
        raw = block["text"]
        p = listing_parse.parse_listing(raw, cxs).as_dict()
        _resolve_by_dong(p, raw, db, cxs)
        cid = p.get("complex_id")
        if not cid:
            skipped.append({"text": raw.splitlines()[0][:40], "reason": "단지를 찾지 못했습니다"})
            continue

        meta = complex_meta(cid)
        p["max_floor"] = p.get("total_floor") or meta["max_floor"]
        _fill_floor(p)
        if p.get("exclusive_area") and meta["keys"]:
            _resolve_area(p, p["exclusive_area"], meta["keys"], meta["counts"],
                          explicit=p.get("area_is_explicit"), reps=meta["reps"])
        if not p.get("exclusive_area") or not p.get("asking_price"):
            skipped.append({
                "text": raw.splitlines()[0][:40],
                "reason": "전용면적 또는 가격을 읽지 못했습니다",
            })
            continue

        rows.append({
            "complex_id": cid,
            "complex_name": p.get("complex_name"),
            "dong": p.get("dong"),
            "exclusive_area": p["exclusive_area"],
            "floor": p.get("floor"),
            "asking_price": p["asking_price"],
            "price_is_range": p.get("price_is_range", False),
            "confirmed_on": block["confirmed_on"],
        })

    out = ranking.evaluate_many(db, rows, months=req.months, basis=req.basis)
    merged, away = ranking.merge_duplicates(out["items"])
    # 합친 뒤에는 순위를 다시 매겨야 번호가 연속된다.
    key = "gap_factor_pct" if req.basis == "factor" else "gap_pct"
    ok = [i for i in merged if i.get(key) is not None]
    rest = [i for i in merged if i.get(key) is None]
    ok.sort(key=lambda i: i[key])
    for n, i in enumerate(ok, 1):
        i["rank"] = n
    for i in rest:
        i["rank"] = None

    # DB 에 남긴다 — 같은 호가는 중복으로 쌓이지 않고, 값이 바뀌면 새 기록이 된다.
    saved = 0
    for i in ok + rest:
        try:
            if quotes.record(
                db, complex_id=i["complex_id"], dong=i.get("dong"),
                exclusive_area=i["exclusive_area"], floor=i.get("floor"),
                floor_band=i.get("floor_band"), asking_price=i["asking_price"],
                confirmed_on=i.get("confirmed_on"),
            ) == "created":
                saved += 1
        except Exception:
            db.rollback()

    return {
        "count": len(merged),
        "found": len(blocks),
        "merged_away": away,
        "new_saved": saved,
        "basis": req.basis,
        "items": ok + rest,
        "skipped": skipped + out["skipped"],
    }
