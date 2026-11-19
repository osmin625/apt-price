"""종목 비교 — 종목 하나를 고르면 지수 분석·장기 투자 탭이 그 종목의 가격과 견준다(2026-11-20 요청).

화면 맨 위에서 종목을 고르면 탭마다 같은 종목을 본다. 이 모듈은 그 재료를 종목마다 낸다. 규칙과 이유는
docs/stock/picks.md.

## 지수 분석 — 시장 몫을 뺀 수익률

종목 수익률을 그대로 지표에 맞추면 대부분 시장이 움직인 몫이라, 결국 'S&P 500 과 지표' 를 다시 재는 셈이다. 그래서
종목 월 로그 수익률에서 **베타 × SPY 월 로그 수익률**을 뺀 것(초과 수익률)을 이어 붙인 계열을 만들고, 그것을 지수 자리에
넣어 지수 분석과 **같은 계산**(`effects.one`·`joint`)을 돌린다. 범위·발표 시차·판정이 지수 쪽과 같다.

베타는 겹치는 모든 달로 한 번 맞춘다(전체 표본). 영향은 지나간 관계를 재는 서술이라 그때 알던 베타일 까닭이 없고,
달마다 바뀌는 베타를 쓰면 베타가 움직인 몫이 초과 수익률에 섞인다.

## 장기 투자 — 기법마다 달마다 한 값

재무는 **실적 발표 때 알려진 것**이다(`earnings.py`). 달마다 그달 말까지 발표된 마지막 실적으로 기법의 값을 내고, 주가는
그달 수정 종가다 — 그래서 발표와 발표 사이에는 재무가 그대로이고 주가만 움직인다. 주당 값은 그 발표 때의 주식 수로
나누고 그달의 '수정 종가 ÷ 종가' 를 곱해 그림의 수정 주가와 같은 자에 놓는다(분할 전 주식 수에는 분할 전 주가).

가정이 필요한 기법(DCF·역 DCF·안전마진·배당할인)은 가정을 하나로 정해 두고 화면이 그대로 보여 준다 — 할인율은 발표
전달의 10년 국채 + 베타 × 위험 프리미엄 5%, 5년 성장률은 지난 3년 매출 성장률(0~15% 로 자름), 그 뒤 영구 성장 2.5%.
학습용이다(2026-11-20 합의) — 가정을 고르는 것이 기법의 일부라는 것을 보이려는 것이지 적정가를 맞히려는 것이 아니다.
"""

from __future__ import annotations

import math

from ..macro import store as macro_store
from . import earnings as EA
from . import store
from . import valuation as VA
from .companies import COMPANIES  # noqa: F401 — service 가 이 이름으로 종목을 돈다

ERP = 5.0                 # 위험 프리미엄(%) — 관례이지 잰 값이 아니다
TG = 0.025                # 영구 성장률
YEARS = 5                 # DCF 의 높은 성장 구간
G_CLIP = (0.0, 0.15)      # 5년 성장률 — 지난 3년 매출 성장률을 이 안으로 자른다. 디웨이브처럼 매출이 작게 시작하면
                          # 3년에 몇 배가 되어 5년을 그대로 이으면 터무니없는 값이 나온다
SPREAD = 0.05             # 안전마진의 비관·낙관 — 5년 성장률 ±5%p
MIN_GAP = 0.01            # 할인율이 영구 성장률보다 이만큼은 커야 말기 가치를 낸다
GROWTH_YEARS = 3          # 성장률을 재는 간격
NEAR_DAYS = 20            # '3년 전 같은 분기' 로 보는 오차
MIN_YEARS = 5             # 방어적 기준의 '해마다' 를 볼 최소 연수 — 자료가 2009 년부터라 10·20년은 대개 못 채운다
SIZE_1972 = 1e8           # 그레이엄의 규모 기준(1972년 연 매출 1억 달러) — 미국 소비자물가로 그달 값으로 올린다
CAPE_MONTHS = 120
NA = {
    # 종목 하나에는 뜻이 없는 기법 — 화면이 흐리게 두고 까닭을 적는다(`techniques/longStock.js`).
    "buffett-indicator", "moat", "magic-formula", "momentum",
}


def _r(v: float | None, d: int = 4) -> float | None:
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, d)


def _v(o: dict, k: str) -> float | None:
    t = o["ttm"].get(k)
    return t["value"] if t else None


def _ym_days(a: str, b: str) -> int:
    from datetime import date
    da = date(int(a[:4]), int(a[4:6]), int(a[6:8]))
    db = date(int(b[:4]), int(b[4:6]), int(b[6:8]))
    return (db - da).days


def _ago(items: list[dict], o: dict, years: int) -> dict | None:
    """o 보다 years 년 앞 분기의 발표(오차 NEAR_DAYS 일) — o 때 이미 알려져 있었다."""
    want = 365.25 * years
    for p in items:
        if abs(_ym_days(p["end"], o["end"]) - want) <= NEAR_DAYS:
            return p
    return None


def _cagr(now: float | None, then: float | None, years: int) -> float | None:
    if not now or not then or now <= 0 or then <= 0:
        return None
    return (now / then) ** (1 / years) - 1


def dcf(fcf: float, g: float, r: float, tg: float = TG, years: int = YEARS) -> float | None:
    """5년 g 로 자라고 그 뒤 tg 로 영원히 — 지금 값의 합. 할인율이 영구 성장률에 너무 가까우면 None."""
    if r - tg < MIN_GAP:
        return None
    pv = 0.0
    f = fcf
    for t in range(1, years + 1):
        f *= 1 + g
        pv += f / (1 + r) ** t
    return pv + f * (1 + tg) / (r - tg) / (1 + r) ** years


def dcf_rows(fcf: float, g: float, r: float, tg: float = TG, years: int = YEARS) -> dict | None:
    """화면의 계산 표 — `dcf` 와 같은 식을 해마다 펼친 것. 합이 `dcf` 와 같다(verify_picks)."""
    if r - tg < MIN_GAP:
        return None
    rows, f, pv = [], fcf, 0.0
    for t in range(1, years + 1):
        f *= 1 + g
        d = 1 / (1 + r) ** t
        rows.append([t, f, d, f * d])
        pv += f * d
    tv = f * (1 + tg) / (r - tg)
    return {"rows": rows, "pv": pv, "tv": tv, "tv_pv": tv * d, "total": pv + tv * d}


def implied_g(fcf: float, r: float, cap: float, lo: float = -0.5, hi: float = 1.0) -> float | None:
    """dcf(fcf, g, r) = 시가총액인 g — 이분법. 범위 밖이면 None."""
    f = lambda g: dcf(fcf, g, r)  # noqa: E731
    a, b = f(lo), f(hi)
    if a is None or b is None or not (a <= cap <= b):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) < cap:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def base(o: dict, items: list[dict]) -> dict:
    """발표 하나의 재료 — 금액은 달러 그대로. 그 발표 때 알던 값뿐이다."""
    bs = o["bs"]
    rev, ni = _v(o, "revenue"), _v(o, "net_income")
    gp = _v(o, "gross_profit")
    if gp is None and rev is not None and _v(o, "cost_of_revenue") is not None:
        gp = rev - _v(o, "cost_of_revenue")
    sh = o["shares"]["value"] if o.get("shares") else None
    beta = o["beta"]["value"] if o.get("beta") else None
    y10 = o.get("y10")
    r = (y10 + beta * ERP) / 100 if y10 is not None and beta is not None else None
    old = _ago(items, o, GROWTH_YEARS)
    g_rev = _cagr(rev, _v(old, "revenue") if old else None, GROWTH_YEARS)
    old_sh = old["shares"]["value"] if old and old.get("shares") else None
    g_eps = _cagr(ni / sh if ni and sh else None,
                  _v(old, "net_income") / old_sh if old and _v(old, "net_income") and old_sh else None, GROWTH_YEARS)
    cfo, capex = _v(o, "cfo"), _v(o, "capex")
    return {
        "date": o["date"], "end": o["end"], "estimated": o["estimated"],
        "revenue": rev, "net_income": ni, "operating_income": _v(o, "operating_income"), "gross_profit": gp,
        "cfo": cfo, "capex": capex, "dep": _v(o, "dep"), "dividends": _v(o, "dividends"),
        "fcf": cfo - capex if cfo is not None and capex is not None else None,
        **{k: bs.get(k) for k in EA.STOCKS},
        "shares": sh, "k": (o["adj"] / o["close"]) if o.get("adj") and o.get("close") else None,
        "y10": y10, "beta": beta, "r": r,
        "g_rev": g_rev, "g": None if g_rev is None else min(max(g_rev, G_CLIP[0]), G_CLIP[1]),
        "g_eps": g_eps,
        "annual": o["annual"],
    }


def fscore(b: dict, p: dict | None) -> list[bool | None]:
    """피오트로스키 아홉 — 1년 전 같은 분기 발표(p)와 견준다. 재료가 없으면 None."""
    def ratio(x, y):
        return x / y if x is not None and y else None

    def up(a, b_, better=1):
        return None if a is None or b_ is None else (a - b_) * better > 0

    roa = ratio(b["net_income"], b["assets"])
    if p is None:
        p = {}
    roa0 = ratio(p.get("net_income"), p.get("assets"))
    return [
        None if roa is None else roa > 0,
        None if b["cfo"] is None else b["cfo"] > 0,
        up(roa, roa0),
        None if b["cfo"] is None or b["net_income"] is None else b["cfo"] > b["net_income"],
        up(ratio(b["lt_debt"], b["assets"]), ratio(p.get("lt_debt"), p.get("assets")), -1),
        up(ratio(b["assets_current"], b["liabilities_current"]), ratio(p.get("assets_current"), p.get("liabilities_current"))),
        None if b["shares"] is None or p.get("shares") is None else b["shares"] <= p["shares"],
        up(ratio(b["gross_profit"], b["revenue"]), ratio(p.get("gross_profit"), p.get("revenue"))),
        up(ratio(b["revenue"], b["assets"]), ratio(p.get("revenue"), p.get("assets"))),
    ]


def _yearly_all(vals: list[tuple[str, float]], test, years: int) -> bool | None:
    """최근 years 년(자료가 있는 해)이 모두 test 를 지나나. MIN_YEARS 해가 안 되면 None."""
    got = vals[-years:]
    if len(got) < MIN_YEARS:
        return None
    return all(test(v) for _, v in got)


def defensive(b: dict, cap: float | None, size_now: float | None) -> list[bool | None]:
    """그레이엄 방어적 투자자의 일곱 — 자료가 모자라면 None(통과도 미달도 아님)."""
    ni_y = b["annual"].get("net_income") or []
    div_y = b["annual"].get("dividends") or []
    ca, cl, ltd = b["assets_current"], b["liabilities_current"], b["lt_debt"]
    # 이익 성장 — 처음 3년 평균과 마지막 3년 평균, 10년 떨어져 있어야 한다.
    grow = None
    if len(ni_y) >= 13:
        a = sum(v for _, v in ni_y[-13:-10]) / 3
        z = sum(v for _, v in ni_y[-3:]) / 3
        grow = a > 0 and z >= a * 4 / 3
    pe3 = None
    if cap and len(ni_y) >= 3:
        avg = sum(v for _, v in ni_y[-3:]) / 3
        pe3 = cap / avg if avg > 0 else None
    pb = cap / b["equity"] if cap and b["equity"] and b["equity"] > 0 else None
    return [
        None if b["revenue"] is None or size_now is None else b["revenue"] >= size_now,
        None if ca is None or not cl else ca / cl >= 2,
        None if ltd is None or ca is None or cl is None else ltd <= ca - cl,
        _yearly_all(ni_y, lambda v: v > 0, 10),
        _yearly_all(div_y, lambda v: v > 0, 20),
        grow,
        None if pe3 is None or pb is None else (pe3 <= 15 and pb <= 1.5) or pe3 * pb <= 22.5,
    ]


def series(co) -> dict:
    """달마다 기법의 값 — 그림과 표가 쓰는 계열."""
    bars = store.monthly_bars(co.market, co.symbol)
    rows = store.facts(co.symbol)
    if not bars or not rows:
        return {"missing": "주가나 재무가 아직 적재되지 않았습니다"}
    spy = dict(store.monthly(*EA.MARKET))
    items = [o for o in EA.of_company(co, spy) if not o.get("pending")]
    bases = [base(o, items) for o in items]
    by_end = {b["end"]: b for b in bases}
    prev = {b["end"]: next((by_end[p["end"]] for p in [_ago(items, o, 1)] if p), None) for o, b in zip(items, bases)}
    if not bases:
        return {"missing": "실적 발표와 재무를 아직 맞추지 못했습니다"}

    cpi = VA.as_index(macro_store.monthly("us_cpi"))
    last_i = VA.mi(bars[-1][0])
    cpi = VA.fill(cpi, last_i)
    y10 = macro_store.monthly("us_10y")
    c72 = [v for m, v in cpi.items() if VA.ym_of(m).startswith("1972")]
    c72 = sum(c72) / len(c72) if c72 else None

    # 장기 추세 — 상장 때부터의 실질 수정 주가 전부로 맞춘다(지수 쪽 `trend_dev` 와 같은 함수).
    lp = {VA.mi(m): math.log(a / cpi[VA.mi(m)]) for m, _, a in bars if VA.mi(m) in cpi and a > 0}
    dev, _ = VA.trend_dev(lp)

    first = next((b["date"][:6] for b in bases if b["k"]), None)
    months, price = [], []
    out: dict[str, dict[str, list]] = {}

    def put(tid: str, key: str, v):
        out.setdefault(tid, {}).setdefault(key, [None] * len(months))
        out[tid][key][-1] = v

    ni_real: dict[int, float] = {}
    j = -1
    for m, close, adj in bars:
        if first is None or m < first:
            continue
        while j + 1 < len(bases) and bases[j + 1]["date"][:6] <= m:
            j += 1
        # 그달까지 발표된 것 가운데 주가 자(k)가 있는 마지막 — 상장 전 발표(디웨이브의 SPAC 시절)는 건너뛴다
        b = next((bases[i] for i in range(j, -1, -1) if bases[i]["k"] and bases[i]["shares"]), None)
        months.append(m)
        price.append(round(adj, 4))
        for d in out.values():
            for arr in d.values():
                arr.append(None)
        if b is None:
            continue
        i = VA.mi(m)
        sh, k = b["shares"], b["k"]
        cap = adj / k * sh
        ps = lambda tot: None if tot is None or tot <= 0 else _r(tot / sh * k)  # noqa: E731 — 주당·수정 주가 자
        eps = b["net_income"] / sh if b["net_income"] is not None else None
        bps = b["equity"] / sh if b["equity"] is not None else None
        ni, eq = b["net_income"], b["equity"]

        # 가치형 — 주가와 같은 자의 선
        if eps and bps and eps > 0 and bps > 0:
            put("graham-number", "value", _r(math.sqrt(22.5 * eps * bps) * k))
        if b["assets_current"] is not None and b["liabilities"] is not None:
            ncav = b["assets_current"] - b["liabilities"]
            put("net-net", "value", ps(ncav))
            put("net-net", "buy", ps(ncav * 2 / 3))
        if b["fcf"] and b["fcf"] > 0 and b["r"] is not None and b["g"] is not None:
            v = dcf(b["fcf"], b["g"], b["r"])
            put("dcf", "value", ps(v))
            lo = dcf(b["fcf"], b["g"] - SPREAD, b["r"])
            hi = dcf(b["fcf"], b["g"] + SPREAD, b["r"])
            put("margin-of-safety", "low", ps(lo))
            put("margin-of-safety", "value", ps(v))
            put("margin-of-safety", "high", ps(hi))
            if v:
                put("margin-of-safety", "margin", _r((1 - cap / v) * 100, 1))
            g_imp = implied_g(b["fcf"], b["r"], cap)
            put("reverse-dcf", "implied", None if g_imp is None else _r(g_imp * 100, 1))
        if b["g_rev"] is not None:
            put("reverse-dcf", "past", _r(b["g_rev"] * 100, 1))
        if b["dividends"] and b["dividends"] > 0 and b["r"] is not None and b["r"] - TG >= MIN_GAP:
            put("ddm", "value", ps(b["dividends"] * (1 + TG) / (b["r"] - TG)))

        # 비율형 — 주가 아래 칸
        if ni is not None and eq and eq > 0:
            put("roe", "roe", _r(ni / eq * 100, 1))
        if ni is not None and b["dep"] is not None and b["capex"] is not None:
            put("owner-earnings", "oe", _r((ni + b["dep"] - b["capex"]) / cap * 100, 2))
        if ni is not None:
            put("owner-earnings", "ey", _r(ni / cap * 100, 2))
            put("fed-model", "ey", _r(ni / cap * 100, 2))
        bond = y10.get(EA.prev_month(m))
        put("fed-model", "bond", _r(bond, 2))
        if ni is not None and bond is not None:
            put("fed-model", "gap", _r(ni / cap * 100 - bond, 2))
        if ni and ni > 0:
            put("low-pe-pb", "pe", _r(cap / ni, 1))
        if eq and eq > 0:
            put("low-pe-pb", "pb", _r(cap / eq, 2))
        if ni and ni > 0 and b["g_eps"] and b["g_eps"] > 0:
            put("peg", "peg", _r(cap / ni / (b["g_eps"] * 100), 2))
        fs = fscore(b, prev.get(b["end"]))
        if any(x is not None for x in fs):
            put("f-score", "score", sum(1 for x in fs if x))
        size = SIZE_1972 * cpi[i] / c72 if c72 and i in cpi else None
        dv = defensive(b, cap, size)
        put("defensive", "score", sum(1 for x in dv if x))
        put("defensive", "known", sum(1 for x in dv if x is not None))
        if ni is not None and i in cpi:
            ni_real[i] = ni / cpi[i]
            win = [ni_real.get(t) for t in range(i - CAPE_MONTHS + 1, i + 1)]
            if all(v is not None for v in win) and sum(win) > 0:
                put("cape", "cape", _r((cap / cpi[i]) / (sum(win) / CAPE_MONTHS), 1))
        if i in dev:
            put("trend-position", "dev", _r(dev[i], 1))

    return {"months": months, "price": price, "bases": bases, "prev": prev, "series": out, "size72": c72, "cpi": cpi}


def now_of(s: dict) -> dict:
    """마지막 달의 재료 — 화면의 계산 표가 이것으로 실제 숫자를 채운다."""
    m = s["months"][-1]
    b = next((x for x in reversed(s["bases"]) if x["date"][:6] <= m and x["k"] and x["shares"]), None)
    if b is None:
        return {}
    cap = s["price"][-1] / b["k"] * b["shares"]
    i = VA.mi(m)
    size = SIZE_1972 * s["cpi"][i] / s["size72"] if s["size72"] and i in s["cpi"] else None
    p = s["prev"].get(b["end"])
    keep = ("date", "end", "estimated", "revenue", "net_income", "operating_income", "gross_profit", "cfo", "capex",
            "dep", "dividends", "fcf", *EA.STOCKS, "shares", "k", "y10", "beta", "r", "g_rev", "g", "g_eps")
    return {
        "month": m, "price": s["price"][-1], "cap": cap,
        **{k: b[k] for k in keep},
        "annual_ni": b["annual"].get("net_income", [])[-13:],
        "annual_div": b["annual"].get("dividends", [])[-20:],
        "size": size,
        "fscore": fscore(b, p), "prev": None if p is None else {k: p[k] for k in keep},
        "defensive": defensive(b, cap, size),
        "dcf": dcf_rows(b["fcf"], b["g"], b["r"]) if b["fcf"] and b["fcf"] > 0 and b["g"] is not None and b["r"] else None,
        "dcf_low": dcf(b["fcf"], b["g"] - SPREAD, b["r"]) if b["fcf"] and b["fcf"] > 0 and b["g"] is not None and b["r"] else None,
        "dcf_high": dcf(b["fcf"], b["g"] + SPREAD, b["r"]) if b["fcf"] and b["fcf"] > 0 and b["g"] is not None and b["r"] else None,
        "implied_g": implied_g(b["fcf"], b["r"], cap) if b["fcf"] and b["fcf"] > 0 and b["r"] else None,
        "erp": ERP, "tg": TG, "years": YEARS, "g_clip": list(G_CLIP), "spread": SPREAD, "growth_years": GROWTH_YEARS,
        "min_years": MIN_YEARS,
    }


def excess(co) -> tuple[dict[str, float], dict | None]:
    """종목 수정 종가에서 시장(SPY) 몫을 뺀 계열 — {YYYYMM: 수준}. 베타는 겹치는 모든 달로 한 번 맞춘다."""
    a = dict(store.monthly(co.market, co.symbol))
    m_ = dict(store.monthly(*EA.MARKET))
    months = sorted(k for k in a if k in m_)
    pairs = []
    for p, q in zip(months, months[1:]):
        if VA.mi(q) - VA.mi(p) == 1:
            pairs.append((q, math.log(a[q] / a[p]), math.log(m_[q] / m_[p]), p))
    if len(pairs) < EA.BETA_MIN:
        return {}, None
    xs = [x for _, _, x, _ in pairs]
    ys = [y for _, y, _, _ in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    # 첫 짝의 앞 달이 기준(1.0)이다. 달이 빠진 곳(상장 전후)은 이어 붙이지 않고 거기서 끊긴 채 다음 짝부터 잇는다 —
    # 빠진 달의 수익률을 0 으로 치면 그 사이 움직임이 사라진다. 네 종목은 월봉이 끊긴 데가 없다.
    lvl = 0.0
    out = {pairs[0][3]: 1.0}
    for q, y, x, _ in pairs:
        lvl += y - b * x
        out[q] = math.exp(lvl)
    return out, {"value": round(b, 2), "months": len(pairs), "from": pairs[0][0], "to": pairs[-1][0]}


def company(co) -> dict:
    head = {"id": co.id, "label": co.label, "symbol": co.symbol, "currency": co.currency}
    s = series(co)
    if "missing" in s:
        return {**head, "missing": s["missing"]}
    return {
        **head,
        "months": s["months"], "price": s["price"],
        "releases": [{"date": b["date"], "end": b["end"], "estimated": b["estimated"]} for b in s["bases"]
                     if b["date"][:6] >= s["months"][0]],
        "techniques": s["series"],
        "now": now_of(s),
        "na": sorted(NA),
    }

