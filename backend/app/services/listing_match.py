"""붙여넣은 매물 목록을 **우리 단지·평형에 맞춰** 줄 세우고 남긴다.

`listing_parse` 가 텍스트에서 글자를 읽는다면, 여기서는 읽은 값을 DB 에 대조해
'어느 단지의 어느 평형인가' 를 정한다. 단지명이 여럿에 걸리면 동 번호로 좁히고,
네이버가 버림해 쓴 평이나 광고의 공급면적은 실제로 거래된 전용 평형에 맞춘다.
그 다음 `ranking` 으로 평가하고 `quotes.record` 로 쌓는다.

예전에는 이 흐름이 통째로 `routers/model.py` 안에 있었다. 라우터가 260줄짜리 해석
규칙을 품고 있어서, '면적 맞추는 규칙' 을 고치려는 사람이 HTTP 엔드포인트 파일을
열어야 했다. 라우터는 요청을 받아 여기로 넘기고 오류를 HTTP 코드로 바꾸기만 한다.
"""

from __future__ import annotations

from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import pricing
from ..models import Complex, ComplexDong, Trade
from . import analysis, listing_parse, quotes, ranking


class NoListings(Exception):
    """매물을 하나도 못 찾았다. 라우터가 422 로 바꾼다."""


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
    dong = (out.get("dong") or "").strip()
    if out.get("complex_id") or not dong:
        return
    frags = listing_parse.name_fragments(text)
    if len(frags) >= 2:
        # 이름이 쪼개진 경우 — 조각으로 후보를 만든다.
        pool = [c for c in complexes if any(f in c.name for f in frags)]
    else:
        # 조각이 하나뿐일 때. 예전에는 여기서 그만뒀다 — '쌍용' 같은 흔한 이름을
        # DB 전체에서 찾으면 엉뚱한 단지가 걸리기 때문이다.
        #
        # 그런데 **이미 추려 둔 후보 안에서만** 찾으면 그 위험이 없다. '현대 104동'
        # 의 후보는 이름이 정확히 '현대' 인 곳들뿐이고, 그중 104동 거래가 있는 곳이
        # 하나면 그게 답이다. 재 봤다 — 실제 붙여넣기 82건에서 41건이 이렇게 유일하게
        # 정해졌다(성원 -> 수원 권선 세류동 성원, 신나무실5단지주공 ->
        # 신나무실휴먼시아5단지). 24건은 동으로도 여럿이라 그대로 두고, 9건은 그 동의
        # 거래가 없어 그대로 둔다.
        ids = {c.get("id") for c in (out.get("candidates") or [])}
        pool = [c for c in complexes if c.id in ids]
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
    # 추정이라는 것을 밝힌다. 이름만으로는 못 고른 것을 동 번호로 좁힌 것이고,
    # 그 동의 거래가 우연히 한 단지에만 있었을 수도 있다.
    if len(frags) >= 2:
        why = (f"'{', '.join(frags)}' 는 시공사가 함께 지은 단지라 실거래에는 "
               f"나뉘어 있습니다. ")
    else:
        why = (f"이름이 같은 단지가 {len(pool)}곳이라 이름만으로는 못 고릅니다. ")
    out["warnings"].append({"field": "complex", "text":
        why + f"{dong}동 거래가 있는 곳이 '{cx.name}'"
        + (f"({cx.umd_nm})" if getattr(cx, "umd_nm", None) else "")
        + " 하나뿐이라 그것으로 맞췄습니다."})


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


def _candidate_info(db: Session, cands: list[dict]) -> list[dict]:
    """후보에 **고를 수 있을 만큼**의 정보를 붙인다.

    시군구만으로는 못 고른다 — '현대' 는 수원 장안구에만 세 곳이다(천천동·파장동·
    정자동). 법정동·지번·준공년도·세대수와 **등록된 동 번호**를 같이 준다. 특히 동
    번호가 결정적이다: 붙여넣은 매물이 101~104동이면 그 동이 있는 곳이 답이다.

    거래 건수도 붙인다. 0건인 단지를 고르면 적정가를 못 내므로, 고르기 전에 보여
    주는 쪽이 낫다 — 골랐는데 "비교 실거래 없음" 이 뜨면 왜인지 알 수 없다.
    """
    ids = [c["id"] for c in cands]
    if not ids:
        return []

    dongs: dict[int, list[str]] = {}
    for d in db.execute(
        select(ComplexDong).where(ComplexDong.complex_id.in_(ids))
    ).scalars().all():
        dongs.setdefault(d.complex_id, []).append(str(d.dong))

    trades = dict(
        db.execute(
            select(Trade.complex_id, func.count())
            .where(Trade.complex_id.in_(ids))
            .group_by(Trade.complex_id)
        ).all()
    )

    out = []
    for c in cands:
        cx = db.get(Complex, c["id"])
        if not cx:
            continue
        out.append({
            **c,
            "sgg_name": cx.sgg_name,
            "umd_nm": cx.umd_nm,
            "jibun": cx.jibun,
            "build_year": cx.build_year,
            "household_count": cx.household_count,
            "trade_count": trades.get(cx.id, 0),
            "dongs": sorted(dongs.get(cx.id, []))[:8],
        })
    # 거래가 많은 쪽을 위로. 그쪽이 맞을 확률이 높고, 적정가도 낼 수 있다.
    out.sort(key=lambda c: -c["trade_count"])
    return out


def _area_types(points) -> tuple[list[int], dict[int, float]]:
    """(타입 키 목록, 타입별 **실제 대표 면적**).

    키는 반올림값이라 `50` 이 실제로는 49.58㎡ 일 수 있다. 평 구간 판정처럼
    소수점이 결과를 가르는 곳에서는 실제 값을 써야 한다.
    """
    grouped: dict[int, list[float]] = {}
    for p in points:
        grouped.setdefault(pricing.area_type_key(p.exclusive_area), []).append(p.exclusive_area)
    return sorted(grouped), {k: float(median(v)) for k, v in grouped.items()}


def parse_bulk(db: Session, text: str, name_map: dict[str, int],
               months: int, basis: str) -> dict:
    """목록을 통째로 붙여넣어 **여러 매물을 한 번에** 읽고 줄 세운다.

    네이버 부동산은 공개 API 가 없고 자동 수집은 이용약관 문제가 있어 이 프로젝트가
    처음부터 제외했다. 하지만 사용자가 **보고 있는 목록을 복사해 붙여넣는 것**은
    자동 수집이 아니다. 필터를 건 목록 화면을 그대로 복사하면 스크리닝이 된다.

    읽은 매물은 `Quote` 로 남는다. 그래서 `/api/quotes/ranking` 에서 지금까지 본
    모든 매물의 순위를 언제든 다시 볼 수 있다.
    """
    blocks = listing_parse.split_listings(text)
    if not blocks:
        raise NoListings("매물을 찾지 못했습니다. 목록 화면의 텍스트를 붙여넣어 주세요.")

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
        # 사용자가 고른 것이 있으면 그것이 **이름 매칭보다 우선**이다. 같은 이름이
        # 여럿이라 못 고른 것을 사람이 가린 것이므로, 파서가 다시 뒤집으면 안 된다.
        head_name = listing_parse.head_name_text(raw)
        picked = name_map.get(head_name)
        if picked:
            cx = db.get(Complex, picked)
            if cx:
                p["complex_id"] = cx.id
                p["complex_name"] = cx.name

        cid = p.get("complex_id")
        if not cid:
            skipped.append({
                "text": raw.splitlines()[0][:40],
                "reason": "단지를 찾지 못했습니다",
                # 고를 수 있게 후보를 같이 보낸다. 이름 단위로 묶어 한 번만 고르면
                # 그 이름의 매물이 전부 풀린다.
                "name": head_name,
                "candidates": _candidate_info(db, p.get("candidates") or []),
            })
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
            "memo": block["memo"],
            "aspect": listing_parse.parse_aspect(raw),
        })

    out = ranking.evaluate_many(db, rows, months=months, basis=basis)
    merged, away = ranking.merge_duplicates(out["items"])
    # 합친 뒤에는 순위를 다시 매겨야 번호가 연속된다.
    key = "gap_factor_pct" if basis == "factor" else "gap_pct"
    ok = [i for i in merged if i.get(key) is not None]
    rest = [i for i in merged if i.get(key) is None]
    ok.sort(key=lambda i: i[key])
    for n, i in enumerate(ok, 1):
        i["rank"] = n
    for i in rest:
        i["rank"] = None

    # DB 에 남긴다 — 같은 호가는 중복으로 쌓이지 않고, 값이 바뀌면 새 기록이 된다.
    #
    # 줄마다 **이번에 처음 들어온 것인지**를 같이 돌려준다.
    #
    # 북마클릿은 누를 때마다 '지금까지 담은 전부' 를 클립보드에 넣는다(여러 단지를
    # 돌고 마지막에 한 번만 붙여넣게 하려는 것이다). 그래서 두 번째 붙여넣기부터는
    # 결과에 **이미 본 매물이 섞인다** — 새로 뭐가 들어왔는지 눈으로 골라야 했다.
    #
    # `record()` 가 이미 'created' / 'seen' 을 가린다. 그 값을 버리지 않고 줄에 붙이면
    # 화면에서 새 것만 추릴 수 있다. 실패한 줄은 None 으로 둔다 — 저장이 안 된 것을
    # '새 것' 이라고 말하면 거짓이고, '있던 것' 이라고 말해도 거짓이다.
    saved = 0
    for i in ok + rest:
        try:
            got = quotes.record(
                db, complex_id=i["complex_id"], dong=i.get("dong"),
                exclusive_area=i["exclusive_area"], floor=i.get("floor"),
                floor_band=i.get("floor_band"), asking_price=i["asking_price"],
                confirmed_on=i.get("confirmed_on"), memo=i.get("memo"),
                aspect=i.get("aspect"),
            )
            i["is_new"] = got == "created"
            if got == "created":
                saved += 1
        except Exception:
            db.rollback()
            i["is_new"] = None

    return {
        "count": len(merged),
        "found": len(blocks),
        "merged_away": away,
        "new_saved": saved,
        "basis": basis,
        "items": ok + rest,
        "skipped": skipped + out["skipped"],
    }
