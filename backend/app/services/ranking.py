"""매물 여러 건을 한꺼번에 평가하고 줄 세운다.

일괄 붙여넣기(`/api/model/parse-bulk`)와 누적 순위(`/api/quotes/ranking`)가 같은
계산을 쓴다. 두 곳에 같은 로직을 두면 한쪽만 고쳐져 값이 달라진다.

## 성능

한 건씩 `estimate_fair_price` 를 부르면 매물마다 **구 전체 거래를 다시 읽고**
시점지수·층계수를 새로 만든다. 46건에 12초가 들었다. (구, 기간) 단위 표본은
요청 안에서 공유한다 — 5.3초로 줄었다.

## 중복

한 물건을 중개사 여러 곳이 올리므로 목록에는 같은 매물이 반복된다. 합치지 않으면
순위 상위가 같은 값 여러 줄로 채워져 아무것도 알 수 없다. `Quote` 테이블은 이미
같은 키로 중복을 막지만, 일괄 붙여넣기의 **그 자리 결과**에도 같은 규칙을 적용한다.
"""

from __future__ import annotations

from .. import pricing
from . import analysis
from . import model_view as mv


def verdict_of(pct: float) -> str:
    if pct <= -10:
        return "저평가"
    if pct <= -3:
        return "다소 저렴"
    if pct < 3:
        return "적정"
    if pct < 10:
        return "다소 비쌈"
    return "고평가"


def evaluate_many(db, rows: list[dict], months: int, basis: str = "market") -> dict:
    """`rows` 를 평가해 순위를 매긴다.

    rows 의 각 항목: complex_id, dong, exclusive_area, floor, asking_price
    그 밖의 키(seen_count, first_seen 등)는 결과에 그대로 실어 보낸다.
    """
    ctx: dict = {}
    fit = mv.peek_fit(db)
    dong_effects = (fit or {}).get("dong_effects")

    items, skipped = [], []
    for r in rows:
        cid = r.get("complex_id")
        area = r.get("exclusive_area")
        ask = r.get("asking_price")
        if not (cid and area and ask):
            skipped.append({"text": r.get("complex_name") or str(cid), "reason": "정보 부족"})
            continue

        fair = analysis.estimate_fair_price(
            db, complex_id=cid, exclusive_area=area, floor=r.get("floor"),
            months=months, dong=r.get("dong"), dong_effects=dong_effects, ctx=ctx,
        )
        if not fair or not fair.get("fair_price"):
            skipped.append({
                "text": (fair or {}).get("complex", {}).get("name") or str(cid),
                "reason": "비교 실거래 없음",
            })
            continue

        gap_pct = (ask - fair["fair_price"]) / fair["fair_price"] * 100
        item = {
            **{k: v for k, v in r.items() if k not in ("complex_id",)},
            "complex_id": cid,
            "complex_name": fair["complex"]["name"],
            "exclusive_area": area,
            "pyeong": round(pricing.to_pyeong(area), 1),
            "floor_band": fair.get("floor_band"),
            "fair_price": fair["fair_price"],
            "gap_pct": round(gap_pct, 1),
            "verdict": verdict_of(gap_pct),
            "sample_count": fair.get("sample_count"),
            "confidence": fair.get("confidence"),
        }

        # 요인 기준. 면적 곡선은 전 단지 공통이라 특정 평형에서 어긋나므로,
        # 같은 평형 실거래로 교정한 값을 쓴다(단건 진단과 같은 방식).
        m = mv.model_price(db, fit, {
            "complex_id": cid, "exclusive_area": area,
            "floor": r.get("floor"), "dong": r.get("dong"),
        }) if fit else None
        if m and m.get("market_ppp") and fair.get("fair_ppp"):
            k = float(fair["fair_ppp"]) / float(m["market_ppp"])
            if 0.5 <= k <= 2.0:
                fp = round(m["factor_price"] * k)
                item["factor_price"] = fp
                item["gap_factor_pct"] = round((ask - fp) / fp * 100, 1)
                # 요인 분해도 같이 보낸다. 표에서 행에 호버하면 "왜 이 값인지" 를
                # 바로 볼 수 있어야 한다 — 순위만 보고는 납득할 수 없다.
                item["factor_parts"] = {
                    "complex": m.get("complex_parts"),
                    "unit": m.get("unit_parts"),
                    "premium_pct": m.get("complex_premium_pct"),
                }

        items.append(item)

    key = "gap_factor_pct" if basis == "factor" else "gap_pct"
    ranked = [i for i in items if i.get(key) is not None]
    rest = [i for i in items if i.get(key) is None]
    ranked.sort(key=lambda i: i[key])
    for n, i in enumerate(ranked, 1):
        i["rank"] = n
    for i in rest:
        i["rank"] = None

    return {
        "count": len(items),
        "basis": basis,
        "basis_label": "요인 기준" if basis == "factor" else "실거래 기준",
        "items": ranked + rest,
        "skipped": skipped,
    }


def merge_duplicates(items: list[dict]) -> tuple[list[dict], int]:
    """같은 (단지·동·평형·층·호가)를 한 줄로 합치고 몇 건이었는지 센다.

    층을 '저/중/고' 로만 밝힌 매물은 같은 구간이 같은 대표층이 되므로 서로 다른
    물건이 합쳐질 수 있다. 가격까지 같아야 합치므로 실무상 문제는 적지만 완전하지는
    않다 — 그래서 합친 건수를 화면에 드러낸다.
    """
    merged: dict[tuple, dict] = {}
    for i in items:
        k = (i.get("complex_id"), i.get("dong"), round(i.get("exclusive_area") or 0),
             i.get("floor"), i.get("asking_price"))
        if k in merged:
            merged[k]["listing_count"] = merged[k].get("listing_count", 1) + 1
        else:
            i.setdefault("listing_count", 1)
            merged[k] = i
    out = list(merged.values())
    return out, sum(i.get("listing_count", 1) - 1 for i in out)
