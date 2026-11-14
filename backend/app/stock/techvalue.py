"""기술주 가치 탭 — 시가총액을 '지금 사업 + 기대 기술 + 설명 안 된 몫' 으로 나눌 재료를 모은다.

나누는 계산 자체는 화면이 한다(`frontend/src/stock/techvalue/model.js`) — 시나리오를 화면에서 바꿔 보려면
계산이 브라우저에 있어야 하고, 정적 사이트에는 서버가 없다. 여기서는 그 계산이 쓸 **사실**만 낸다:
지금 주가·주식 수·지난 12개월 이익(EDGAR)·베타·10년 국채·월봉 이력, 그리고 시나리오 기본값(`scenarios.py`).
계산 규칙과 이유는 docs/stock/tech-value.md.

## 할인율에 거시가 들어간다

할인율 = 미국 10년 국채(지수 분석과 같은 FRED GS10 월평균, 마지막 실적 발표 전달) + 베타 × 주식 위험 프리미엄. 베타는 종목 월 수익률을
시장 월 수익률에 회귀한 기울기다(최근 60달, 적어도 24달). 시장은 SPY(S&P 500 ETF)의 수정 종가다 — 처음에는 S&P 500 지수 월말
(FRED SP500)을 썼는데 FRED 가 10년치만 줘서(2016-11 부터) 과거 발표 때의 베타를 24~30달로 재야 했다. 그렇게 잰 베타는 같은 때
60달 베타와 평균 0.24~0.45, 크게는 1.31 어긋났다(테슬라 2019-04 발표 때 −0.33). 위험 프리미엄 5% 를 곱하면 할인율이 2~6%p
흔들린다. SPY 는 1999 년부터 있고, 수정 종가라 배당까지 든 수익률이어서 종목 쪽(수정 종가)과 뜻도 같다. 금리가 오르면 먼 해의 이익일수록 지금 값이 크게
줄어든다 — 기대 몫이 큰 종목이 금리에 예민한 까닭이 이 식에 그대로 보인다.

위험 프리미엄의 기본 5% 는 관례이지 잰 값이 아니다. 화면에서 3~7% 로 바꿔 볼 수 있다.
"""

from __future__ import annotations

import math

from . import earnings as EA
from . import fundamentals as FU
from . import reflect as RF
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
MARKET = ("US", "SPY")   # 베타의 시장 — 위 머리말


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


def _release_row(o: dict) -> dict:
    """그림에 찍을 발표 하나 — 숫자만 추린다."""
    if o.get("pending"):
        return {"date": o["date"], "session": o["session"], "pending": True}
    t = {k: (v["value"] if v else None) for k, v in o["ttm"].items()}
    return {"date": o["date"], "session": o["session"], "estimated": o["estimated"], "end": o["end"],
            "form": o["form"], "doc_filed": o["doc_filed"], "quarter": o["quarter"], "yoy": o["yoy"], "ttm": t,
            "shares": o["shares"]["value"] if o["shares"] else None, "close": o["close"], "adj": o["adj"],
            "y10": o["y10"], "beta": o["beta"]["value"] if o["beta"] else None}


def company(co, spx_month: dict[str, float]) -> dict:
    """가치의 재료는 **마지막 실적 발표 때** 것이다(`earnings.py`) — 이익·주식 수·10년 국채·베타. 주가만 오늘이다.

    그래서 발표와 발표 사이에는 가치가 그대로이고 주가만 움직인다. 그 사이의 주가 움직임은 '설명 안 된 몫' 에 들어간다.
    """
    daily = store.daily(co.market, co.symbol)
    monthly = store.monthly(co.market, co.symbol)
    rows = store.facts(co.symbol)
    if not daily or not monthly or not rows:
        return {"id": co.id, "label": co.label, "symbol": co.symbol, "missing": "주가나 재무가 아직 적재되지 않았습니다"}
    items = EA.of_company(co, spx_month)
    basis = EA.latest(items)
    if basis is None or not basis["shares"] or basis["y10"] is None:
        return {"id": co.id, "label": co.label, "symbol": co.symbol, "missing": "실적 발표와 재무를 아직 맞추지 못했습니다"}
    d, close = daily[-1]
    sh = basis["shares"]
    last = monthly[-1][0]
    first = f"{int(last[:4]) - HISTORY_YEARS}{last[4:]}"
    hist = [(m, a) for m, a in monthly if m >= first]
    return {
        "id": co.id, "label": co.label, "symbol": co.symbol, "currency": co.currency,
        "price": {"date": d, "close": close},
        "basis": {"date": basis["date"], "session": basis["session"], "end": basis["end"], "form": basis["form"],
                  "estimated": basis["estimated"], "y10": basis["y10"], "y10_month": EA.prev_month(basis["date"][:6])},
        "shares": sh,
        "cap": close * sh["value"],
        "ttm": basis["ttm"],
        "beta": basis["beta"],
        "history": {"months": [m for m, _ in hist], "close": [round(a, 4) for _, a in hist]},
        "releases": [_release_row(o) for o in items if o["date"][:6] >= first],
        "scenarios": SCENARIOS.get(co.id, []),
        # 과거 1년 주가 변화를 거시·실적·설명 안 된 몫으로 나눈 것(reflect.py) — 시나리오와 달리 잰 값이다.
        "reflect": RF.of_company(co),
    }


def overview() -> dict:
    spx = dict(store.monthly(*MARKET))
    return {
        "rate": {"erp": ERP, "erp_range": list(ERP_RANGE), "tax": TAX},
        "companies": [company(co, spx) for co in COMPANIES],
    }
