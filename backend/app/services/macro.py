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


# ---------------------------------------------------------------- 인사이트
#
# 값만 17줄 그려 놓으면 읽는 일이 통째로 사람 몫이 된다. 그래서 **세 장의 그림**으로
# 질문을 바꿔 준다. 문장을 자동 생성하지 않는 이유는, 해석 문장이 근거 숫자와
# 떨어지면 이 저장소가 가장 경계하는 '추정을 사실처럼 보여 주는 것' 이 되기 때문이다.
# 그림에서는 점의 위치가 곧 근거다.
#
# 만들지 않은 것: **선행·후행 분석.** 각 시군구 월변화율과 17곳 중앙값의 교차상관을
# ±6개월 래그에서 재 봤더니 17곳 중 14곳이 래그 0이었다(상관 0.59~0.86). 경기 남부는
# 거의 동시에 움직여서 선행지표로 쓸 지역이 없다. 재 보고 아니면 버린다.

MIN_MONTHS = 24  # 사이클 판단에 최소한 필요한 길이. 화성 분구는 여기서 빠진다.


def _pct(a: float, b: float) -> float | None:
    return (b / a - 1) * 100 if a else None


def _series_map(db: Session, metric: str) -> dict[str, list[tuple[str, float]]]:
    rows = db.execute(
        select(RebStat.sgg_cd, RebStat.ym, RebStat.value, RebStat.unit)
        .where(RebStat.metric == metric)
        .order_by(RebStat.ym)
    ).all()
    out: dict[str, list[tuple[str, float]]] = {}
    for sgg, ym, v, unit in rows:
        out.setdefault(sgg, []).append((ym, convert(v, metric, unit)))
    return out


def cycle_phase(db: Session) -> dict:
    """국면 4분면 — 가로 전고점 대비(%), 세로 최근 3개월(%).

    같은 경기 남부인데 국면이 크게 갈린다. 어떤 구는 지금이 전고점이고 어떤 시는
    전고점 대비 -18%에서 거의 못 올라왔다. 한 축으로는 안 보이고 두 축을 겹쳐야
    '신고가 / 회복 중 / 정체 / 꺾임' 이 갈린다.
    """
    idx = _series_map(db, "sale_index")
    items = []
    for sgg, name in DISTRICTS.items():
        s = idx.get(sgg) or []
        if len(s) < MIN_MONTHS:
            continue
        vals = [v for _, v in s]
        yms = [y for y, _ in s]
        pi = max(range(len(vals)), key=lambda i: vals[i])
        after = vals[pi:]
        ti = pi + min(range(len(after)), key=lambda i: after[i])
        cur = vals[-1]
        m3 = _pct(vals[-4], cur) if len(vals) > 4 else None
        prev3 = _pct(vals[-7], vals[-4]) if len(vals) > 7 else None
        items.append({
            "sgg_cd": sgg,
            "name": name,
            "from_peak": round(_pct(vals[pi], cur) or 0, 2),
            "peak_ym": yms[pi],
            "from_trough": round(_pct(vals[ti], cur) or 0, 2),
            "trough_ym": yms[ti],
            "m3": round(m3, 2) if m3 is not None else None,
            "m12": round(_pct(vals[-13], cur), 2) if len(vals) > 13 else None,
            "accel": round(m3 - prev3, 2) if (m3 is not None and prev3 is not None) else None,
            "latest_ym": yms[-1],
        })
    return {
        "items": items,
        "x_label": "전고점 대비 (%)",
        "y_label": "최근 3개월 (%)",
        "note": "가로 0 은 지금이 전고점이라는 뜻입니다. 세로 0 위는 최근 3개월 상승, "
                "아래는 하락입니다. 월간 매매가격지수 기준이며, 공표 기간이 24개월이 "
                "안 되는 화성시 분구는 사이클을 판단할 수 없어 뺐습니다.",
        "excluded": [
            DISTRICTS[s] for s in DISTRICTS
            if len(idx.get(s) or []) < MIN_MONTHS
        ],
    }


def rally_character(db: Session) -> dict:
    """상승의 성격 — 가로 12개월 매매 변화(%), 세로 전세가율 12개월 변화(%p).

    '얼마나 올랐나' 보다 한 단계 깊은 질문에 답한다: **그 상승을 전세가 받쳐 줬는가.**
    매매가 전세보다 빨리 오르면 전세가율이 떨어진다. 둘을 겹치면 많이 오른 곳일수록
    전세가 못 따라왔다는 것이 보인다(재 보니 실제로 그랬다 — 수지 +19.5%/-4.6%p,
    오산 +1.4%/+1.1%p).

    주의: 이것은 **관측된 관계**이지 인과가 아니다. 전세가율은 매매가가 오르기만 해도
    떨어지므로, 같은 현상을 두 각도에서 본 것에 가깝다. 그래도 '오르는데 전세도 같이
    붙는 곳' 과 '매매만 가는 곳' 이 갈리는 것은 사실이고, 그 구분이 이 그림의 값이다.
    """
    idx = _series_map(db, "sale_index")
    jr = _series_map(db, "jeonse_ratio")
    items = []
    for sgg, name in DISTRICTS.items():
        si, ji = idx.get(sgg) or [], jr.get(sgg) or []
        if len(si) < 13 or len(ji) < 13:
            continue
        sale12 = _pct(si[-13][1], si[-1][1])
        items.append({
            "sgg_cd": sgg,
            "name": name,
            "sale_12m": round(sale12, 2) if sale12 is not None else None,
            "ratio_now": round(ji[-1][1], 1),
            "ratio_12m": round(ji[-1][1] - ji[-13][1], 2),
        })
    return {
        "items": items,
        "x_label": "12개월 매매 변화 (%)",
        "y_label": "전세가율 12개월 변화 (%p)",
        "note": "오른쪽 아래일수록 '매매만 간 상승'(전세가 못 따라옴), 오른쪽 위는 "
                "전세가 함께 붙은 상승입니다. 전세가율은 매매가가 오르기만 해도 "
                "떨어지므로 인과가 아니라 같은 현상의 두 측면으로 읽어야 합니다.",
        "excluded": [],
    }


def model_gap(db: Session, fit: dict | None) -> dict:
    """모델과의 어긋남 — 부동산원 평당가 순위 vs 분해 모델 구 계수 순위.

    두 값은 서로 다른 데이터와 방법에서 나온다. 부동산원은 공표 평균(면적·층·시점
    보정 없음)이고, 우리 계수는 그것들을 통제한 뒤 남은 구 효과다. 그래서 **순위가
    맞는 것이 기본**이고(실제로 거의 맞는다), 크게 벌어지는 지역이 눈여겨볼 곳이다.

    벌어지는 이유는 둘 중 하나다. 그 지역의 평형·연식 구성이 특이해 단순 평균이
    끌려갔거나, 우리 모델이 그 지역에서 뭔가를 놓쳤거나. 어느 쪽인지는 이 그림이
    말해 주지 않는다 — **어디를 들여다볼지만 알려 준다.**
    """
    up = _series_map(db, "avg_unit_price")
    reb_now = {s: v[-1][1] for s, v in up.items() if v}

    coefs: dict[str, dict] = {}
    for t in (fit or {}).get("terms", []) or []:
        name = str(t.get("name") or "")
        if name.startswith("sgg_"):
            coefs[name[4:]] = t

    common = [s for s in DISTRICTS if s in reb_now and s in coefs]
    # 기준 구(더미에서 빠진 구)는 계수가 없다. 0 으로 두면 다른 구와 같은 축에 선다.
    base = [s for s in DISTRICTS if s in reb_now and s not in coefs]
    rows = [
        {"sgg_cd": s, "name": DISTRICTS[s], "reb": reb_now[s],
         "coef_pct": round((pow(2.718281828, coefs[s]["coef"]) - 1) * 100, 2),
         "p": coefs[s].get("p")}
        for s in common
    ] + [
        {"sgg_cd": s, "name": DISTRICTS[s], "reb": reb_now[s],
         "coef_pct": 0.0, "p": None, "is_base": True}
        for s in base
    ]
    if not rows:
        return {"items": [], "note": "모델 계수를 읽지 못했습니다.", "spearman": None}

    by_reb = sorted(rows, key=lambda r: -r["reb"])
    by_coef = sorted(rows, key=lambda r: -r["coef_pct"])
    rank_reb = {r["sgg_cd"]: i + 1 for i, r in enumerate(by_reb)}
    rank_coef = {r["sgg_cd"]: i + 1 for i, r in enumerate(by_coef)}
    for r in rows:
        r["rank_reb"] = rank_reb[r["sgg_cd"]]
        r["rank_coef"] = rank_coef[r["sgg_cd"]]
        r["rank_gap"] = r["rank_coef"] - r["rank_reb"]

    n = len(rows)
    d2 = sum((r["rank_gap"]) ** 2 for r in rows)
    spearman = 1 - (6 * d2) / (n * (n * n - 1)) if n > 2 else None

    rows.sort(key=lambda r: r["rank_reb"])
    return {
        "items": rows,
        "spearman": round(spearman, 3) if spearman is not None else None,
        "x_label": "부동산원 평당가 순위",
        "y_label": "모델 구 계수 순위",
        "note": "대각선 위에 있으면 모델이 공표 평균보다 그 지역을 낮게 보고, 아래면 "
                "높게 봅니다. 기본은 맞는 것이고, 크게 벌어진 지역이 들여다볼 곳입니다 — "
                "평형·연식 구성이 특이하거나, 모델이 뭔가를 놓쳤거나입니다.",
    }
