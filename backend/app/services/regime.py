"""거시 국면 — 요인들이 지금 어느 쪽으로 미는가, 과거에는 어땠나.

## 화살표 하나로 못 박지 않는다

"공급 부족이니 상승" 같은 말은 쉽지만 **재 보면 그렇게 깔끔하지 않다.** 각 요인과
'그 뒤 12개월 경기 남부 가격 변화' 의 상관을 전부 재 봤다(시차 0~24개월).

    주택 소비심리   0m +0.42 ·  6m -0.03 · 12m -0.34 · 18m -0.51
    거래량 전년비   0m +0.25 ·  6m +0.32 · 12m +0.26 · 18m -0.02
    미분양 전년비   0m -0.31 ·  6m -0.12 · 12m -0.00 · 18m -0.06
    대출금리 전년차  0m -0.27 ·  6m -0.31 · 12m -0.30 · 18m -0.16
    가계대출 전년비  0m +0.29 ·  6m +0.04 · 12m -0.13 · 18m -0.20
    M2 전년비      0m -0.07 ·  6m -0.17 · 12m -0.34 · 18m -0.44
    기준금리 수준    0m -0.09 ·  6m -0.00 · 12m +0.06 · 18m +0.10

**가장 센 것도 0.42 고, 심리는 18개월 뒤에 부호가 뒤집힌다**(과열의 끝). 통화량과
기준금리는 0에 가깝다. 그래서 방향만 큼직하게 띄우면 없는 확신을 파는 셈이 된다.
화면에는 방향과 **세기·시차 프로파일을 같이** 낸다.

## 겹치는 창을 조심한다

12개월 변화율을 매달 계산하면 이웃한 관측이 11개월을 공유한다. n=219 처럼 보여도
독립 표본은 20개 남짓이다. 그래서 **매년 12월만 쓴 겹치지 않는 상관**을 같이 낸다.
둘의 부호가 다르면 그 요인은 방향을 말하지 않는다.

## 지금 값이 아니라 '자기 역사 대비 어디쯤' 을 쓴다

요인마다 단위가 다르고(호, 지수, %, 십억원) 추세도 다르다. 수준을 그대로 비교할
수 없으니 **자기 과거 분포에서의 백분위**로 바꾼다. 미분양 14,509호가 많은 것인지는
경기도 미분양의 지난 25년을 봐야 안다.

## 지역이 섞인다

가격은 경기 남부 17개 구인데 미분양·심리는 경기 전체, 통화·금리는 전국이다.
공급 표가 시도까지만 오기 때문이고(`docs/analysis/supply.md`), 좁힐 방법이 없다.
**섞어 쓰는 것을 화면에 적는다** — 경기 전체를 경기 남부처럼 부르지 않는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clients.molit import DISTRICTS
from ..models import RebStat
from .policy import COVERS_FROM, POLICY

# 방향을 말할 수 있는 최소 세기. 이보다 약하면 '거의 없음' 으로 적고 화살표를
# 띄우지 않는다. 0.15 는 재 본 값들의 분포에서 정했다 — 기준금리(-0.09)와
# M2(-0.07) 가 아래로, 거래량(+0.25)·미분양(-0.31)이 위로 떨어진다.
MIN_R = 0.15

# 백분위를 '높다/낮다' 로 가르는 선. 가운데 40% 는 '보통' 이다.
HI, LO = 0.70, 0.30

# 상관을 잴 때 필요한 최소 관측. 겹치는 창이라 실제 독립 표본은 이보다 훨씬 적다.
MIN_OBS = 60


@dataclass(frozen=True)
class Factor:
    key: str
    group: str
    label: str
    metric: str
    sgg_cd: str
    region: str
    transform: str  # level | yoy | diff12 | roll12_yoy
    unit: str
    up_means: str   # 이 값이 커지면 어떤 뜻인가(화면 설명)


# 지역·변환을 한 곳에 모은다. 화면과 측정이 **같은 정의**를 봐야 한다.
FACTORS: tuple[Factor, ...] = (
    Factor("done", "공급", "준공 물량", "done", "41", "경기", "roll12_yoy", "%",
           "새 아파트가 더 많이 입주했다"),
    Factor("unsold", "공급", "미분양", "unsold", "41", "경기", "yoy", "%",
           "안 팔린 집이 늘었다"),
    Factor("trade", "수요", "거래량", "trade_volume", "", "경기 남부", "roll12_yoy", "%",
           "사려는 사람이 늘었다"),
    Factor("sentiment", "수요", "주택시장 소비심리", "sentiment", "41", "경기", "level", "지수",
           "사겠다는 쪽이 늘었다(100 이 중립)"),
    Factor("jeonse_ratio", "수요", "전세가율", "jeonse_ratio", "", "경기 남부", "level", "%",
           "전세가 매매에 가까워졌다"),
    Factor("m2", "통화량", "M2(광의통화)", "m2", "00", "전국", "yoy", "%",
           "시중에 도는 돈이 빨리 늘었다"),
    Factor("loan_balance", "통화량", "가계대출 잔액", "loan_balance", "00", "전국", "yoy", "%",
           "가계가 빚을 빨리 늘렸다"),
    Factor("base_rate", "금리", "한국은행 기준금리", "base_rate", "00", "전국", "diff12", "%p",
           "1년 전보다 금리가 올랐다"),
    Factor("loan_rate", "금리", "가계대출 금리", "loan_rate", "00", "전국", "diff12", "%p",
           "실제로 무는 금리가 올랐다"),
)

GROUP_ORDER = ("공급", "수요", "통화량", "금리", "정책", "세금")


# ──────────────────────────────────────────────────────────
# 계열 만들기
# ──────────────────────────────────────────────────────────
def _raw(db: Session, metric: str, sgg_cd: str) -> dict[str, float]:
    """월별 원계열. `sgg_cd` 가 비면 우리 17개 구의 평균(또는 합)을 쓴다."""
    q = select(RebStat.ym, RebStat.value).where(RebStat.metric == metric)
    if sgg_cd:
        q = q.where(RebStat.sgg_cd == sgg_cd)
    rows = db.execute(q).all()
    if sgg_cd:
        return {ym: float(v) for ym, v in rows}

    # 17개 구를 합친다. 거래량은 합, 지수·비율은 평균이다 — 거래량을 평균 내면
    # 지역을 넓힐 때 값이 작아져 추세가 꺾인 것처럼 보인다.
    agg: dict[str, list[float]] = {}
    for ym, v in rows:
        agg.setdefault(ym, []).append(float(v))
    if metric == "trade_volume":
        return {ym: sum(vs) for ym, vs in agg.items()}
    return {ym: sum(vs) / len(vs) for ym, vs in agg.items()}


def _roll12(s: dict[str, float]) -> dict[str, float]:
    ks = sorted(s)
    return {ks[i]: sum(s[k] for k in ks[i - 11:i + 1]) for i in range(11, len(ks))}


def _yoy(s: dict[str, float]) -> dict[str, float]:
    ks = sorted(s)
    return {ks[i]: (s[ks[i]] / s[ks[i - 12]] - 1) * 100
            for i in range(12, len(ks)) if s[ks[i - 12]]}


def _diff12(s: dict[str, float]) -> dict[str, float]:
    ks = sorted(s)
    return {ks[i]: s[ks[i]] - s[ks[i - 12]] for i in range(12, len(ks))}


def series_of(db: Session, f: Factor) -> dict[str, float]:
    raw = _raw(db, f.metric, f.sgg_cd)
    if f.transform == "level":
        return raw
    if f.transform == "yoy":
        return _yoy(raw)
    if f.transform == "diff12":
        return _diff12(raw)
    if f.transform == "roll12_yoy":
        return _yoy(_roll12(raw))
    raise ValueError(f"모르는 변환: {f.transform}")


def price_series(db: Session) -> dict[str, float]:
    """경기 남부 17개 구 매매가격지수 평균."""
    return _raw(db, "sale_index", "")


# ──────────────────────────────────────────────────────────
# 재기
# ──────────────────────────────────────────────────────────
def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else 0.0


def _percentile(s: dict[str, float], ym: str) -> float:
    vals = sorted(s.values())
    v = s[ym]
    below = sum(1 for x in vals if x < v)
    return below / max(len(vals) - 1, 1)


def _fwd12(price: dict[str, float], yms: list[str], i: int) -> float | None:
    return None if i + 12 >= len(yms) else (price[yms[i + 12]] / price[yms[i]] - 1) * 100


def fwd12_series(price: dict[str, float]) -> list[dict]:
    """달마다 '그 달부터 12개월 동안 가격이 몇 % 변했나'. 상관을 잴 때 쓰는 그 값이다.

    화면의 '그 뒤 가격과의 관계' 절이 이것을 요인 아래에 같은 시간축으로 그린다.
    예전에는 요인 한 줄만 그리고 관계는 표에만 있어서, 제목이 말하는 '가격' 이 그림
    어디에도 없었다. 프론트가 지수에서 다시 계산하지 않고 **같은 `_fwd12` 를 지난
    값**을 받는다 — 그래야 그림과 표가 다른 계산을 하지 않는다. 마지막 12개월은
    그 뒤 1년이 아직 오지 않아 없다.
    """
    yms = sorted(price)
    out = []
    for i, ym in enumerate(yms):
        f = _fwd12(price, yms, i)
        if f is not None:
            out.append({"ym": ym, "v": round(f, 2)})
    return out


def lag_profile(x: dict[str, float], price: dict[str, float],
                lags: tuple[int, ...] = (0, 6, 12, 18, 24)) -> list[dict]:
    """시차별 상관. **argmax 하나만 고르지 않는다** — 25개 중 가장 센 것을 고르면
    고른 값 자체가 우연을 탄다. 프로파일을 통째로 보여 주고 사람이 판단한다."""
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    out = []
    for h in lags:
        pairs = []
        for ym, v in x.items():
            i = idx.get(ym)
            if i is None or i + h >= len(yms):
                continue
            f = _fwd12(price, yms, i + h)
            if f is not None:
                pairs.append((v, f))
        out.append({
            "lag": h,
            "r": round(_corr([p[0] for p in pairs], [p[1] for p in pairs]), 3)
            if len(pairs) >= MIN_OBS else None,
            "n": len(pairs),
        })
    return out


def nonoverlap(x: dict[str, float], price: dict[str, float]) -> tuple[float | None, int]:
    """매년 12월만 쓴 상관. 겹치는 창의 거품을 걷어 낸다."""
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    pairs = []
    for ym, v in x.items():
        i = idx.get(ym)
        if i is None or not ym.endswith("12"):
            continue
        f = _fwd12(price, yms, i)
        if f is not None:
            pairs.append((v, f))
    if len(pairs) < 8:
        return None, len(pairs)
    return round(_corr([p[0] for p in pairs], [p[1] for p in pairs]), 3), len(pairs)


def _pressure(r: float | None, pct: float, agree: bool) -> dict:
    """방향은 **측정된 부호 × 지금 위치**다.

    상관이 양(+)인 요인이 지금 자기 역사에서 높은 쪽이면 상승 압력으로 읽는다.
    둘 중 하나라도 약하면 방향을 말하지 않는다 — 없는 확신을 파느니 비워 둔다.
    """
    if r is None or abs(r) < MIN_R:
        return {"dir": "none", "strength": "거의 없음",
                "why": f"가격과의 상관이 {'측정 불가' if r is None else f'{r:+.2f}'} 라 "
                       f"방향을 말할 수 없습니다"}
    if LO < pct < HI:
        return {"dir": "none", "strength": "중립",
                "why": "지금 값이 자기 역사의 가운데라 어느 쪽도 아닙니다"}
    high = pct >= HI
    up = (r > 0) == high
    strength = "약함" if abs(r) < 0.30 else "중간"
    if not agree:
        strength = "약함"
    return {
        "dir": "up" if up else "down",
        "strength": strength,
        "why": (f"이 요인은 가격과 {r:+.2f} 로 움직였고, 지금 값이 자기 역사의 "
                f"{'위쪽' if high else '아래쪽'} {round(pct * 100)}% 입니다"
                + ("" if agree else " (겹치지 않는 표본에서는 부호가 달라 약하게 봅니다)")),
    }


# 요인 값이 무엇을 바꾼 것인지 사람이 읽는 이름. 같은 준공이라도 공급 탭은 '호'
# 단위 12개월 누적이고 여기는 그 누적의 전년비라, 말해 주지 않으면 두 그림의
# 숫자가 서로 다른 데이터처럼 보인다.
# 명사로 끝낸다 — 화면이 '위는 ○○ — {이것}입니다' 로 잇는다.
TRANSFORM_LABEL = {
    "level": "그 달의 값",
    "yoy": "1년 전 대비 증감률",
    "diff12": "1년 전과의 차이",
    "roll12_yoy": "12개월 합의 1년 전 대비 증감률",
}


def factor_rows(db: Session) -> list[dict]:
    price = price_series(db)
    out = []
    for f in FACTORS:
        s = series_of(db, f)
        if not s:
            continue
        last = max(s)
        prof = lag_profile(s, price)
        r0 = prof[0]["r"]
        nr, nn = nonoverlap(s, price)
        agree = r0 is not None and nr is not None and (r0 > 0) == (nr > 0)
        pct = _percentile(s, last)
        out.append({
            "key": f.key, "group": f.group, "label": f.label, "region": f.region,
            "unit": f.unit, "transform": f.transform, "up_means": f.up_means,
            "transform_label": TRANSFORM_LABEL[f.transform],
            "latest": {"ym": last, "value": round(s[last], 2)},
            "percentile": round(pct, 3),
            "measured": {"r": r0, "n": prof[0]["n"], "nonoverlap_r": nr,
                         "nonoverlap_n": nn, "agree": agree, "profile": prof},
            "pressure": _pressure(r0, pct, agree),
            "series": [{"ym": k, "v": round(v, 2)} for k, v in sorted(s.items())],
        })
    return out


# ──────────────────────────────────────────────────────────
# 과거 추적 — 그때 각 요인은 어땠고, 집값은 어떻게 됐나
# ──────────────────────────────────────────────────────────
def _state(pct: float) -> str:
    return "높음" if pct >= HI else ("낮음" if pct <= LO else "보통")


def history(db: Session, step: int = 6) -> dict:
    """반년마다 각 요인의 상태와 **그 뒤 12개월 가격 변화**를 함께 적는다.

    인과를 말하지 않는다. "그때 이랬고 그 뒤 이랬다" 만 적는다 — 요인은 서로
    얽혀 있고(금리가 낮으면 대출이 늘고 심리가 산다) 표본은 스무 해뿐이다.
    """
    price = price_series(db)
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    cols = [(f, series_of(db, f)) for f in FACTORS]
    # 각 계열의 백분위는 **그 시점까지가 아니라 전체 기간** 기준이다. 보는 사람이
    # '지금 높음' 과 '그때 높음' 을 같은 자로 견주려면 자가 하나여야 한다.
    rows = []
    for i in range(0, len(yms), step):
        ym = yms[i]
        states = {}
        for f, s in cols:
            if ym in s:
                states[f.key] = {"state": _state(_percentile(s, ym)),
                                 "v": round(s[ym], 2)}
        if not states:
            continue
        rows.append({
            "ym": ym,
            "states": states,
            "fwd12": (round(_fwd12(price, yms, i), 2)
                      if _fwd12(price, yms, i) is not None else None),
        })
    return {"step_months": step, "rows": rows,
            # 표본 길이를 문구에 얼리지 않는다('스무 해') — 해마다 하나씩 는다.
            "note": ("그때의 요인 상태와 그 뒤 12개월 가격 변화를 나란히 둔 것입니다. "
                     "요인이 가격을 움직였다는 뜻이 아닙니다 — 요인들은 서로 얽혀 "
                     f"있고 표본은 {len(yms) // 12}년치뿐입니다.")}


def similar_months(db: Session, top: int = 12) -> dict:
    """지금과 요인 상태가 비슷했던 과거 달을 찾아 **그 뒤 무슨 일이 있었나** 본다.

    거리는 백분위 차의 제곱합이다. 요인 수가 적고 단위가 제각각이라 백분위로
    맞춘 뒤 비교한다. 비슷한 달이 적으면 적다고 말한다.
    """
    price = price_series(db)
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    cols = [(f, series_of(db, f)) for f in FACTORS]
    common = sorted(set.intersection(*[set(s) for _, s in cols]) & set(price))
    if len(common) < 24:
        return {"available": False,
                "note": "요인이 모두 갖춰진 달이 24개월이 안 돼 비교할 수 없습니다."}

    pcts = {ym: {f.key: _percentile(s, ym) for f, s in cols} for ym in common}
    now = common[-1]
    scored = []
    for ym in common[:-13]:  # 뒤 12개월 결과가 있어야 쓸모가 있다
        d = math.sqrt(sum((pcts[ym][k] - pcts[now][k]) ** 2 for k in pcts[now]))
        f12 = _fwd12(price, yms, idx[ym])
        if f12 is not None:
            scored.append({"ym": ym, "distance": round(d, 3), "fwd12": round(f12, 2)})
    scored.sort(key=lambda r: r["distance"])
    picked = scored[:top]
    vals = sorted(r["fwd12"] for r in picked)
    mid = (vals[len(vals) // 2] if len(vals) % 2
           else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2) if vals else None
    return {
        "available": True,
        "now": now,
        "months": picked,
        "fwd12": {"median": round(mid, 2) if mid is not None else None,
                  "min": vals[0] if vals else None, "max": vals[-1] if vals else None,
                  "up": sum(1 for v in vals if v > 0), "n": len(vals)},
        "note": ("요인 상태가 지금과 가장 가까웠던 달들입니다. 그 뒤 12개월에 "
                 "무슨 일이 있었는지만 보여 줍니다 — 표본이 작고 서로 이웃한 달이 "
                 "섞여 있어 예측이 아닙니다."),
    }


# ──────────────────────────────────────────────────────────
# 정책·세금 — 재는 것이 아니라 적어 두는 것
# ──────────────────────────────────────────────────────────
def policy_rows(db: Session) -> list[dict]:
    """연표에 **그 뒤 12개월 가격 변화**를 붙인다.

    대책이 가격을 그렇게 만들었다는 뜻이 아니다. 오히려 거꾸로다 — 오르니까
    규제가 나왔다. 그래도 "규제가 나온 뒤 실제로 무슨 일이 있었나" 는 사람들이
    가장 궁금해하는 것이고, 숫자를 안 적으면 각자 기억으로 채운다.
    """
    price = price_series(db)
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    out = []
    for p in POLICY:
        ym = p["date"][:4] + p["date"][5:7]
        i = idx.get(ym)
        out.append({
            **p,
            "fwd12": (round(_fwd12(price, yms, i), 2)
                      if i is not None and _fwd12(price, yms, i) is not None else None),
        })
    return sorted(out, key=lambda r: r["date"], reverse=True)


def policy_summary(rows: list[dict]) -> list[dict]:
    """종류별로 **그 뒤 12개월에 실제로 무슨 일이 있었나.**

    재 보면 상식과 반대다 — 규제강화 뒤가 더 올랐고 완화 뒤가 떨어졌다
    (12·16 +15.3%, 6·17 +17.4%, 7·10 +19.0% / 2022-11 -9.2%, 1·3 -2.7%).
    **정책이 거꾸로 작동해서가 아니라 오르니까 규제가 나왔기 때문이다.** 이걸
    적지 않으면 보는 사람이 "규제하면 오른다" 로 읽는다. 그래서 숫자와 함께
    왜 그렇게 보이는지를 같이 낸다.
    """
    out = []
    for kind in ("규제강화", "규제완화", "공급확대", "세제강화", "세제완화"):
        vals = sorted(r["fwd12"] for r in rows
                      if r["kind"] == kind and r["fwd12"] is not None)
        if not vals:
            continue
        mid = (vals[len(vals) // 2] if len(vals) % 2
               else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2)
        out.append({"kind": kind, "n": len(vals), "median": round(mid, 2),
                    "min": vals[0], "max": vals[-1]})
    return out


def group_rows(factors: list[dict], policy: list[dict]) -> list[dict]:
    """그룹 한 줄로 접는다 — '한 눈에' 가 이 탭의 목적이다.

    방향은 **세기로 가중한 합**이다. 한 그룹 안에서 요인들이 엇갈리면(금리는
    기준금리와 대출금리가 같이 가지만 공급은 준공과 미분양이 엇갈릴 수 있다)
    합이 0 쪽으로 가고 '엇갈림' 으로 적는다.

    정책·세금은 **방향을 내지 않는다.** 사건 수가 열몇 개뿐이고 내생적이다 —
    오르니까 규제가 나온다. 최근 조치와 측정된 사후 변화만 보여 준다.
    """
    out = []
    for g in GROUP_ORDER:
        mine = [f for f in factors if f["group"] == g]
        if mine:
            score = sum((1 if f["pressure"]["dir"] == "up" else
                         -1 if f["pressure"]["dir"] == "down" else 0)
                        * abs(f["measured"]["r"] or 0) for f in mine)
            named = [f for f in mine if f["pressure"]["dir"] != "none"]
            if not named:
                dirn, label = "none", "방향 없음"
            elif abs(score) < 0.05:
                dirn, label = "none", "엇갈림"
            else:
                dirn = "up" if score > 0 else "down"
                label = "상승 쪽" if score > 0 else "하락 쪽"
            out.append({
                "group": g, "kind": "measured", "dir": dirn, "label": label,
                "score": round(score, 3),
                "members": [{"label": f["label"], "dir": f["pressure"]["dir"],
                             "strength": f["pressure"]["strength"],
                             "r": f["measured"]["r"],
                             "percentile": f["percentile"]} for f in mine],
            })
            continue

        # 정책·세금
        want = ("세제강화", "세제완화") if g == "세금" else ("규제강화", "규제완화", "공급확대")
        mine_p = [p for p in policy if p["kind"] in want]
        latest = mine_p[0] if mine_p else None
        out.append({
            "group": g, "kind": "policy", "dir": "none", "label": "방향을 내지 않음",
            "latest": latest,
            "aftermath": [a for a in policy_summary(policy) if a["kind"] in want],
            "why": ("사건이 적고 내생적입니다 — 오르니까 규제가 나옵니다. "
                    "방향 대신 최근 조치와 그 뒤 실제 변화를 적습니다."),
        })
    return out


def overview(db: Session) -> dict:
    factors = factor_rows(db)
    policy = policy_rows(db)
    price = price_series(db)
    yms = sorted(price)
    last = yms[-1]
    yoy = ((price[last] / price[yms[-13]] - 1) * 100) if len(yms) > 13 else None
    # 가장 센 상관을 **그 자리에서** 잰다. 문구에 '0.42' 를 적어 두었더니 화면의
    # 다른 곳은 0.45 라고 하고 있었다 — 데이터가 바뀌면 문구가 먼저 틀린다.
    rs = [abs(f["measured"]["r"]) for f in factors if f["measured"]["r"] is not None]
    max_r = round(max(rs), 2) if rs else None
    return {
        "max_abs_r": max_r,
        "price": {
            "region": f"경기 남부 {len(DISTRICTS)}개 시군구",
            "ym": last,
            "index": round(price[last], 2),
            "yoy": round(yoy, 2) if yoy is not None else None,
            "series": [{"ym": k, "v": round(v, 2)} for k, v in sorted(price.items())],
            "fwd12": fwd12_series(price),
        },
        "groups": list(GROUP_ORDER),
        "factors": factors,
        "groups_detail": group_rows(factors, policy),
        "policy": policy,
        "policy_covers_from": COVERS_FROM,
        "policy_aftermath": policy_summary(policy),
        "history": history(db),
        "similar": similar_months(db),
        "note": ("요인마다 가격과의 상관을 재서 방향을 정합니다. "
                 + (f"가장 센 것도 {max_r:.2f} 라 " if max_r is not None else "")
                 + "어느 요인도 혼자서는 가격을 설명하지 못합니다. "
                 "가격은 경기 남부 구들의 평균이지만 미분양·심리는 경기 전체, "
                 "통화량·금리는 전국 값입니다."),
    }
