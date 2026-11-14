"""기술주 가치 탭 — 시가총액을 '지금 사업 + 기대 기술 + 설명 안 된 몫' 으로 나눌 재료를 모은다.

나누는 계산 자체는 화면이 한다(`frontend/src/stock/techvalue/model.js`) — 시나리오를 화면에서 바꿔 보려면
계산이 브라우저에 있어야 하고, 정적 사이트에는 서버가 없다. 여기서는 그 계산이 쓸 **사실**만 낸다:
지금 주가·주식 수·지난 12개월 이익(EDGAR)·베타·10년 국채·월봉 이력, 그리고 시나리오 기본값(`scenarios.py`).
계산 규칙과 이유는 docs/stock/tech-value.md.

## 할인율에 거시가 들어간다

할인율 = 미국 10년 국채(지수 분석과 같은 FRED GS10 월평균) + 베타 × 주식 위험 프리미엄. 베타는 종목 월 수익률을
S&P 500 월 수익률에 회귀한 기울기다(최근 60달, 적어도 24달). 금리가 오르면 먼 해의 이익일수록 지금 값이 크게
줄어든다 — 기대 몫이 큰 종목이 금리에 예민한 까닭이 이 식에 그대로 보인다.

위험 프리미엄의 기본 5% 는 관례이지 잰 값이 아니다. 화면에서 3~7% 로 바꿔 볼 수 있다.
"""

from __future__ import annotations

import math

from ..macro import store as macro_store
from . import fundamentals as FU
from . import store
from .companies import COMPANIES
from .scenarios import SCENARIOS

BETA_MONTHS = 60
BETA_MIN = 24
ERP = 5.0
# 영업이익을 세후로 바꿀 때의 세율 — 미국 연방 법정 세율. 회사마다 실효 세율은 다르지만, 순이익을 그대로 쓰면
# 영업 밖의 일회성 손익이 '지금 사업' 에 들어간다: 알파벳은 2026-09 까지 12개월 순이익 2,357억 달러가 영업이익
# 1,570억 달러보다 컸다(한 분기 만에 1,602억 → 2,442억 — 그 분기에 보유 지분 증권의 공정가치 이익이 990억 달러,
# EDGAR EquitySecuritiesFvNiGainLoss 로 확인). 그래서 영업이익 세후가 기본이고
# 화면에서 순이익으로 바꿀 수 있다. IBM 처럼 영업이익을 XBRL 로 내지 않는 회사는 순이익을 쓴다.
TAX = 21.0
ERP_RANGE = (3.0, 7.0)
HISTORY_YEARS = 10


def _month_end(daily: list[tuple[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for d, c in daily:
        out[d[:6]] = c
    return out


def beta(stock: list[tuple[str, float]], market: dict[str, float]) -> dict | None:
    """끝난 달의 월 수익률로 맞춘 기울기. 진행 중인 이번 달은 뺀다."""
    s = dict(stock)
    months = sorted(m for m in s if m in market)[:-1]
    pairs = []
    for a, b in zip(months, months[1:]):
        if int(b[:4]) * 12 + int(b[4:]) - int(a[:4]) * 12 - int(a[4:]) == 1:
            pairs.append((b, math.log(s[b] / s[a]), math.log(market[b] / market[a])))
    pairs = pairs[-BETA_MONTHS:]
    if len(pairs) < BETA_MIN:
        return None
    xs = [p[2] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx
    return {"value": round(b, 2), "months": len(pairs), "from": pairs[0][0], "to": pairs[-1][0]}


def company(co, spx_month: dict[str, float]) -> dict:
    daily = store.daily(co.market, co.symbol)
    monthly = store.monthly(co.market, co.symbol)
    rows = store.facts(co.symbol)
    if not daily or not monthly or not rows:
        return {"id": co.id, "label": co.label, "symbol": co.symbol, "missing": "주가나 재무가 아직 적재되지 않았습니다"}
    d, close = daily[-1]
    sh = FU.shares(rows)
    ttm = {}
    for k in ("net_income", "revenue", "operating_income"):
        t = FU.ttm(rows, k)
        ttm[k] = {"value": t[-1][1], "end": t[-1][0]} if t else None
    q = FU.quarters(rows, "net_income")
    last = monthly[-1][0]
    first = f"{int(last[:4]) - HISTORY_YEARS}{last[4:]}"
    hist = [(m, a) for m, a in monthly if m >= first]
    return {
        "id": co.id, "label": co.label, "symbol": co.symbol, "currency": co.currency,
        "price": {"date": d, "close": close},
        "shares": sh,
        "cap": close * sh["value"] if sh else None,
        "ttm": ttm,
        "quarters": [{"end": e, "value": v} for e, (_, v) in list(q.items())[-8:]],
        "beta": beta(monthly, spx_month),
        "history": {"months": [m for m, _ in hist], "close": [round(a, 4) for _, a in hist]},
        "scenarios": SCENARIOS.get(co.id, []),
    }


def overview() -> dict:
    spx = _month_end(store.daily("US", "SPX"))
    y10 = macro_store.monthly("us_10y")
    ym = max(y10)
    return {
        "rate": {"y10": y10[ym], "y10_month": ym, "erp": ERP, "erp_range": list(ERP_RANGE), "tax": TAX},
        "companies": [company(co, spx) for co in COMPANIES],
    }
