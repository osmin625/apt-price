"""매크로 — 한국부동산원 공표 통계를 경기 남부 17개 시군구로 묶어 본다.

## 이 화면이 답하는 질문

"우리 대상 지역이 **서로 어떻게 다르게 움직이는가**". 단지 하나가 아니라 시군구
전체의 흐름이고, 우리 모델이 아니라 **공표 통계**다. 그래서 모델이 맞는지 보는
바깥 기준이 된다.

KB부동산 데이터허브에도 같은 통계가 있지만 차트에 5개까지만 그려지고 지역 선택이
저장되지 않아 열 때마다 17번을 다시 골라야 했다. 여기서는 17개가 기본이다.

## 단위를 한 곳에서만 환산한다

한국부동산원은 금액을 **천원**으로 준다. 이 프로젝트는 전부 **만원**을 쓴다.
적재할 때 바꾸지 않고 받은 값과 단위를 그대로 저장한 뒤(`RebStat.unit`) 여기서
한 번 환산한다. 적재에서 바꾸면 공표값과 저장값이 달라져 나중에 대조할 수 없고,
화면마다 바꾸면 한 곳에서 빠뜨린다 — 실제로 천원을 만원으로 읽어 평당 2.2억이라는
값을 만들 뻔했다. 그런 오류는 '비싼 동네' 로만 보여서 조용히 지나간다.

`avg_unit_price` 는 ㎡당이라 **평당으로도** 환산해 준다. 그래야 우리 평당가와
같은 축에서 비교된다(1평 = 3.305785㎡).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clients.molit import DISTRICTS
from ..models import RebStat

PYEONG_M2 = 3.305785

# 화면에 보이는 지표. 순서가 곧 선택 순서다.
METRICS: list[dict] = [
    {
        "key": "sale_index",
        "label": "매매가격지수",
        "unit": "지수",
        "note": "2026년 1월 = 100. 그 지역 아파트값이 기준시점 대비 몇인지입니다. "
                "지역 간 '수준'이 아니라 '변화'를 비교하는 값입니다.",
        "decimals": 2,
    },
    {
        "key": "jeonse_index",
        "label": "전세가격지수",
        "unit": "지수",
        "note": "2026년 1월 = 100. 매매지수와 벌어지는 폭이 전세가율로 나타납니다.",
        "decimals": 2,
    },
    {
        "key": "jeonse_ratio",
        "label": "전세가율",
        "unit": "%",
        "note": "평균 매매가격 대비 평균 전세가격. 갭이 좁을수록 높습니다.",
        "decimals": 1,
    },
    {
        "key": "avg_unit_price",
        "label": "평당 매매가격",
        "unit": "만원/평",
        "note": "한국부동산원이 공표하는 ㎡당 평균가격을 평당으로 환산한 값입니다. "
                "우리 모델의 보정 평당가와 같은 축에서 비교할 수 있지만, 이쪽은 "
                "면적·층·시점을 보정하지 않은 단순 평균입니다.",
        "decimals": 0,
    },
    {
        "key": "avg_sale_price",
        "label": "평균 매매가격",
        "unit": "만원",
        "note": "아파트 한 채 평균. 지역마다 주력 평형이 달라 평당가와 순서가 다를 수 있습니다.",
        "decimals": 0,
    },
    {
        "key": "med_sale_price",
        "label": "중위 매매가격",
        "unit": "만원",
        "note": "평균은 고가 단지에 끌립니다. 중위값과 벌어지면 그 지역 안의 편차가 큽니다.",
        "decimals": 0,
    },
]

_BY_KEY = {m["key"]: m for m in METRICS}


def convert(value: float, metric: str, unit: str) -> float:
    """공표 단위 → 화면 단위. **환산은 여기에만 있다.**"""
    if metric == "avg_unit_price":
        # 천원/㎡ → 만원/평
        return value / 10.0 * PYEONG_M2
    if unit == "천원":
        return value / 10.0
    return value


def available(db: Session) -> bool:
    return db.execute(select(func.count()).select_from(RebStat)).scalar_one() > 0


def series(db: Session, metric: str, *, since: str | None = None) -> dict:
    """한 지표의 시군구별 월 시계열.

    화성시 분구는 2026년 2월부터만 있다. **없는 달을 만들어 채우지 않는다** —
    0 으로 메우면 '그 달에 값이 0' 이라는 거짓이 되고, 앞 값으로 끌면 있지도 않은
    관측을 그린 것이 된다. 짧은 시계열은 짧게 그리고, 화면이 그 사실을 적는다.
    """
    meta = _BY_KEY.get(metric)
    if not meta:
        raise ValueError(f"모르는 지표: {metric}")

    stmt = select(
        RebStat.sgg_cd, RebStat.ym, RebStat.value, RebStat.unit
    ).where(RebStat.metric == metric)
    if since:
        stmt = stmt.where(RebStat.ym >= since)
    rows = db.execute(stmt.order_by(RebStat.ym)).all()

    by_sgg: dict[str, list[dict]] = {}
    months: set[str] = set()
    for sgg, ym, value, unit in rows:
        by_sgg.setdefault(sgg, []).append(
            {"ym": ym, "value": round(convert(value, metric, unit), 4)}
        )
        months.add(ym)

    items = []
    for sgg, name in DISTRICTS.items():
        pts = by_sgg.get(sgg, [])
        if not pts:
            continue
        last = pts[-1]
        first = pts[0]
        change = None
        if first["value"]:
            change = (last["value"] / first["value"] - 1) * 100
        items.append({
            "sgg_cd": sgg,
            "name": name,
            "points": pts,
            "latest": last["value"],
            "latest_ym": last["ym"],
            "first_ym": first["ym"],
            "change_pct": round(change, 2) if change is not None else None,
            # 다른 지역보다 늦게 시작한 지역(화성 분구)을 화면이 구분할 수 있게 한다.
            "partial": first["ym"] != min(months) if months else False,
        })

    # 최신값 내림차순. 지수는 수준 비교가 의미 없으므로 변화율로 세운다.
    key = "change_pct" if metric.endswith("_index") else "latest"
    items.sort(key=lambda x: (x[key] is None, -(x[key] or 0)))

    return {
        "metric": metric,
        "label": meta["label"],
        "unit": meta["unit"],
        "note": meta["note"],
        "decimals": meta["decimals"],
        "months": sorted(months),
        "items": items,
        "n_districts": len(items),
    }


def latest_table(db: Session) -> dict:
    """모든 지표의 최신값을 시군구 한 줄로. 한눈에 보는 표."""
    sub = (
        select(RebStat.metric, func.max(RebStat.ym).label("ym"))
        .group_by(RebStat.metric)
        .subquery()
    )
    rows = db.execute(
        select(RebStat.sgg_cd, RebStat.metric, RebStat.ym, RebStat.value, RebStat.unit)
        .join(sub, (RebStat.metric == sub.c.metric) & (RebStat.ym == sub.c.ym))
    ).all()

    cells: dict[str, dict[str, float]] = {}
    ym_of: dict[str, str] = {}
    for sgg, metric, ym, value, unit in rows:
        cells.setdefault(sgg, {})[metric] = round(convert(value, metric, unit), 4)
        ym_of[metric] = ym

    items = [
        {"sgg_cd": sgg, "name": name, **cells.get(sgg, {})}
        for sgg, name in DISTRICTS.items()
        if sgg in cells
    ]
    items.sort(key=lambda x: -(x.get("avg_unit_price") or 0))

    return {
        "metrics": METRICS,
        "latest_ym": ym_of,
        "items": items,
    }
