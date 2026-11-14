"""기술주 가치 탭의 반영 분해 — 종목 1년 주가 변화를 '모든 요인이 평균일 때 + 요인별 %p + 설명 안 된 몫' 으로.

부동산 거시 분석의 반영 분해(`realestate/services/regime.reflect`, docs/analysis/macro-model.md)와 같은 생각이다 —
**방향은 이론으로 정하고 크기만 데이터로** 잰다. 설명 안 된 몫이 '거시·실적으로는 설명되지 않는 움직임' 이고,
기대가 큰 종목에서는 그 몫이 기대의 움직임에 가깝다. 예측이 아니다 — 같은 달에 같이 움직인 크기다.

    yoy(t) = a + Σ b_j · s_j · z_j(t − 발표 시차_j),    b_j ≥ 0     (부호 제약 최소제곱)

## 요인

- **거시** — 지수 분석의 S&P 500 짝(`indicators.PAIRS['spx']`) 그대로. 움직임의 정의(`effects.movement` — 1년 차·
  1년 상승률·수준), 발표 시차, 상식의 방향(`expect`)을 거기서 읽는다. 지수 분석과 다른 방향을 따로 두지 않는다.
- **실적** — 지난 12개월 매출의 1년 상승률(%)과 이익률의 1년 변화(%p). 이익률은 영업이익 ÷ 매출이고, 영업이익을 따로
  내지 않는 회사(IBM)는 순이익 ÷ 매출이다. 둘 다 오르면 주가에 좋다(+). 순이익 상승률을 쓰지 않는 것은 적자 회사
  (디웨이브·예전 테슬라)에서 상승률이 정의되지 않아서다.

## 시차 — 부동산과 다르다

부동산은 금리가 수요로 전달되는 데 6개월을 뒀다. 주가는 알려지는 날 움직이므로 **발표 시차만** 둔다(물가·M2·실업률은
다음 달에야 나와 1달). 실적은 **그달 말까지 제출된 값만**, 같은 기간이 여러 번 실렸으면 **처음 제출된 값**을 쓴다
(`fundamentals.ttm(as_of=…, first=True)`) — 나중에 고쳐진 숫자로 과거를 설명하면 그때 몰랐던 것을 안 셈이다.

## 범위 — 참값을 80% 덮게

블록 부트스트랩(겹치는 1년 창의 자기상관을 덩어리째 지킨다)의 **5~95%** 다. 처음에는 부동산처럼 12달 덩어리의 10~90%
를 썼는데, 합성 자료에 참값을 심어 재 보니 **67% 만 덮었다**(80% 여야 한다). 덩어리 길이·분위를 바꿔 잰 덮는 비율
(2026-11-14, 180달·요인 다섯·참값 셋):

    덩어리 12달 10~90% 67%   5~95% 77%
    덩어리 24달 10~90% 69%   5~95% 79%
    덩어리 36달 10~90% 66%   5~95% 77%

부트스트랩이 표본 하나의 흔들림만 보고, 끈적이는 요인이 몇 년씩 한쪽에 머무는 몫을 다 잡지 못해서다. 그래서 24달
덩어리의 5~95% 를 '80% 범위' 로 쓴다 — 이름이 아니라 잰 덮는 비율로 정한다. 달마다 뽑으면 같은 5~95% 로도 44% 만 덮는다.
시기를 반으로 나눠 맞춘 크기도 낸다 — 부동산에서 얽힌 요인끼리 몫을 주고받아 시기마다 크기가 크게 흔들렸다.
"""

from __future__ import annotations

import math
import random
from datetime import date

import numpy as np
from scipy.optimize import nnls

from ..macro import store as macro_store
from . import fundamentals as FU
from . import store
from .effects import _shift, movement
from .indicators import BY_ID as INDICATOR
from .indicators import PAIRS

BOOT = 400
BLOCK = 24
Q = (0.05, 0.95)   # '80% 범위' — 위 표대로 잰 덮는 비율로 정했다
SEED = 20261114
MIN_MONTHS = 60     # 요인이 모두 갖춰진 달 — 부동산과 같은 5년


def hist_z(values: list[float], v: float) -> float:
    """자기 역사 평균에서 표준편차 몇 배 — 부동산 `regime.hist_z` 와 같은 자(모집단 표준편차)."""
    n = len(values)
    m = sum(values) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in values) / n)
    return (v - m) / sd if sd > 0 else 0.0


def fit(X: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    """절편은 자유, 기울기는 0 이상. 가운데로 옮겨 nnls 로 푼다 — 절편이 자유면 중심화한 문제와 같다."""
    mx = X.mean(axis=0)
    my = y.mean()
    b, _ = nnls(X - mx, y - my)
    return float(my - mx @ b), b


def r2(a: float, b: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    res = y - a - X @ b
    ss = ((y - y.mean()) ** 2).sum()
    return float(1 - (res ** 2).sum() / ss) if ss else 0.0


def _month_end(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    d = date(y + m // 12, m % 12 + 1, 1).toordinal() - 1
    return date.fromordinal(d).strftime("%Y%m%d")


def fundamentals_known(rows: list[dict], months: list[str]) -> dict[str, dict[str, float]]:
    """달마다 그달 말까지 처음 제출된 값으로 낸 매출 상승률(%)·이익률 변화(%p). 이익률의 이름도 돌린다."""
    has_op = any(r["concept"] == "operating_income" for r in rows)
    num = "operating_income" if has_op else "net_income"
    out: dict[str, dict[str, float]] = {"revenue_growth": {}, "margin_change": {}}
    cache: dict[str, tuple] = {}
    for m in months:
        cut = _month_end(m)
        # 제출이 없는 달은 앞 달과 같은 값이다 — 같은 '마지막 제출일' 이면 다시 계산하지 않는다.
        last = max((r["filed"] for r in rows if r["filed"] <= cut), default=None)
        if last is None:
            continue
        if last not in cache:
            rev = FU.ttm(rows, "revenue", as_of=cut, first=True)
            nm = dict(FU.ttm(rows, num, as_of=cut, first=True))
            g = c = None
            if len(rev) >= 5:
                (e1, v1), (e0, v0) = rev[-1], rev[-5]
                if v0 > 0 and _months(e0, e1) == 12:
                    g = (v1 / v0 - 1) * 100
                    if e1 in nm and e0 in nm and v1 > 0:
                        c = (nm[e1] / v1 - nm[e0] / v0) * 100
            cache[last] = (g, c)
        g, c = cache[last]
        if g is not None:
            out["revenue_growth"][m] = g
        if c is not None:
            out["margin_change"][m] = c
    return out | {"_margin_label": "영업이익률" if has_op else "순이익률"}


def _months(e0: str, e1: str) -> int:
    return (int(e1[:4]) - int(e0[:4])) * 12 + int(e1[4:6]) - int(e0[4:6])


def factors_for(co) -> list[dict]:
    """[{key, label, group, sign, lag, unit, x: {ym: 움직임}}] — 거시 여섯 + 실적 둘."""
    out = []
    for iid in PAIRS["spx"]:
        ind = INDICATOR[iid]
        mv = movement(ind.kind, macro_store.monthly(iid))
        out.append({"key": iid, "label": ind.label, "group": "거시", "sign": ind.expect, "lag": ind.pub_lag,
                    "unit": "%" if ind.kind == "growth" else "%p", "x": {_shift(t, ind.pub_lag): v for t, v in mv.items()}})
    rows = store.facts(co.symbol)
    months = [m for m, _ in store.monthly(co.market, co.symbol)]
    fk = fundamentals_known(rows, months)
    out.append({"key": "revenue_growth", "label": "매출 1년 상승률", "group": "실적", "sign": 1, "lag": 0, "unit": "%",
                "x": fk["revenue_growth"]})
    out.append({"key": "margin_change", "label": f"{fk['_margin_label']} 1년 변화", "group": "실적", "sign": 1, "lag": 0,
                "unit": "%p", "x": fk["margin_change"]})
    return out


def yoy_of(monthly: list[tuple[str, float]]) -> dict[str, float]:
    s = dict(monthly)
    return {m: (v / s[_shift(m, -12)] - 1) * 100 for m, v in s.items() if _shift(m, -12) in s}


def pct(vs, q: float) -> float:
    return float(np.percentile(np.asarray(vs), q * 100))


def decompose(yoy: dict[str, float], fs: list[dict], boot: int = BOOT, seed: int = SEED) -> dict:
    """요인(움직임 x 와 방향 sign)과 목표(1년 변화)로 나눈다. 순수 계산 — 검증 스크립트가 합성 자료로 부른다."""
    keys = [f for f in fs if f["x"]]
    common = sorted(set(yoy).intersection(*[set(f["x"]) for f in keys])) if keys else []
    if len(common) < MIN_MONTHS:
        return {"available": False, "months": len(common),
                "note": f"요인이 모두 갖춰진 달이 {len(common)}달이라 나누지 않습니다({MIN_MONTHS}달부터)."}
    Z = []
    for f in keys:
        vals = [f["x"][m] for m in common]
        Z.append([f["sign"] * hist_z(vals, v) for v in vals])
    X = np.array(Z).T
    y = np.array([yoy[m] for m in common])
    a, b = fit(X, y)
    n = len(common)
    rng = random.Random(seed)
    B = []
    for _ in range(boot):
        idx: list[int] = []
        while len(idx) < n:
            st = rng.randrange(0, n - BLOCK + 1)
            idx.extend(range(st, st + BLOCK))
        idx = idx[:n]
        B.append(fit(X[idx], y[idx])[1])
    B = np.array(B)
    halves = []
    for sl in (slice(0, n // 2), slice(n // 2, None)):
        ah, bh = fit(X[sl], y[sl])
        halves.append({"from": common[sl][0], "to": common[sl][-1], "r2": round(r2(ah, bh, X[sl], y[sl]), 2),
                       "b": {f["key"]: round(float(v), 2) for f, v in zip(keys, bh)}})
    x_now = X[-1]
    rows = []
    for j, f in enumerate(keys):
        lo, hi = pct(B[:, j], Q[0]), pct(B[:, j], Q[1])
        c_lo, c_hi = sorted((lo * x_now[j], hi * x_now[j]))
        rows.append({"key": f["key"], "label": f["label"], "group": f["group"], "sign": f["sign"], "lag": f["lag"],
                     "unit": f["unit"], "x": round(f["x"][common[-1]], 2),
                     "z": round(f["sign"] * x_now[j], 2), "b": round(float(b[j]), 2),
                     "b_lo": round(lo, 2), "b_hi": round(hi, 2),
                     "zero_pct": round(float((B[:, j] < 1e-9).mean() * 100)),
                     "contrib": round(float(b[j] * x_now[j]), 2), "lo": round(c_lo, 2), "hi": round(c_hi, 2)})
    fitted = a + X @ b
    macro = X[:, [j for j, f in enumerate(keys) if f["group"] == "거시"]] @ b[[j for j, f in enumerate(keys) if f["group"] == "거시"]]
    fund = X[:, [j for j, f in enumerate(keys) if f["group"] == "실적"]] @ b[[j for j, f in enumerate(keys) if f["group"] == "실적"]]
    return {
        "available": True, "now": common[-1], "from": common[0], "months": n,
        "base": round(a, 2), "fitted": round(float(fitted[-1]), 2), "actual": round(float(y[-1]), 2),
        "residual": round(float(y[-1] - fitted[-1]), 2), "r2": round(r2(a, b, X, y), 2),
        "factors": rows, "halves": halves, "boot": {"n": boot, "block": BLOCK, "q": list(Q)},
        "series": {"months": common, "actual": [round(float(v), 1) for v in y],
                   "macro": [round(float(v), 1) for v in macro], "fund": [round(float(v), 1) for v in fund],
                   "base": round(a, 2)},
    }


def of_company(co) -> dict:
    monthly = store.monthly(co.market, co.symbol)
    if not monthly:
        return {"available": False, "note": "월봉이 아직 적재되지 않았습니다."}
    return decompose(yoy_of(monthly), factors_for(co))
