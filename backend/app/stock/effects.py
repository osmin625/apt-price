"""경제지표가 움직일 때 지수는 어땠나 — 방향(+/−)과 크기, 그리고 그것이 우연이 아닌가.

화면 '지수 분석' 의 맨 위 막대다. 지표·짝·변화 정의는 `indicators.py`, 경위와 한계는
docs/stock/effects.md.

## 무엇을 재나

달 t 마다 x = 지표의 1년 움직임(t-12 → t, `indicators.py` 의 `kind`), y = 지수 로그 수익률.

- `same` — 같은 1년: y = t-12 → t
- `after3`·`after12` — 그 뒤: y = t+p → t+p+h. p 는 발표 시차(`pub_lag`). 물가처럼 다음 달에야
  알려지는 값을 그 달 말부터 재면, 아직 몰랐던 값으로 미래를 맞힌 셈이 된다

y = a + b·x 를 최소제곱으로 푼다. 막대는 **평소 폭만큼 움직였을 때**(b × x 의 표준편차)의 지수
수익률이다. 지표마다 단위가 달라(%p·%) 1단위당 값으로는 막대 길이를 견줄 수 없다 — 환율 1% 는 흔하고
금리 1%p 는 드물다. 1단위당 값(b)은 따로 싣는다.

## 범위가 거짓으로 좁아지지 않게 — 등분산 Hansen–Hodrick + t 임계값

달마다 1년 창을 재면 이웃한 달의 x·y 가 11개월씩 겹친다. 그대로 최소제곱 표준오차를 쓰면 표본이 실제보다
12배쯤 많은 것처럼 계산되어 범위가 좁아지고, **아무 관계도 없는 지표가 '뚜렷함' 으로 뜬다.**

처음에는 Newey–West(시차 11, 정규 임계값)로 했다. 합성 자료에 참값을 심어 재 보니(2026-11-10,
`scripts/verify_index_effects.py` 와 같은 생성기, 시드 300) **그래도 좁았다** — 참값이 0 인데 '뚜렷함'
이 300개월에서 17%, 120개월(S&P 500 의 10년)에서 21% 떴다. 겹친 1년 창이라 서로 독립인 관측은
KOSPI 25개 남짓·S&P 500 10개 남짓뿐이고, 표본이 이만큼 작으면 이분산 견고(HAC) 추정이 분산을 낮게
잡는다. 대역폭을 키우고 fixed-b 임계값을 써도 10%·15% 였다. 견준 것 중 가장 정직했던 것이

- 분산: 가중치 없는 Hansen–Hodrick 을 **등분산 가정으로**(오차의 자기공분산 × x 의 자기공분산, 시차 11)
- 임계값: 정규가 아니라 t, 자유도 = 개월 수 ÷ 12 − 계수 수 − 1(독립인 해의 수)

로 300개월 6%·120개월 8% 였다(덮는 비율 94%·92%). 지수 수익률은 변동성이 몰려다녀 등분산이 아니지만,
이 표본 크기에서는 그 어긋남보다 작은 표본의 치우침이 훨씬 컸다. 그래도 5% 보다 조금 넓게 헛짚으므로
화면 ⓘ 에 '지표가 여럿이라 우연히 뚜렷해 보이는 것이 섞일 수 있다' 고 적는다.

연관이지 원인이 아니다. 금리가 오른 해에 주가가 내렸다고 금리가 주가를 내렸다고 할 수 없다 — 경기가
둘을 같이 움직였을 수 있다. 화면 ⓘ 가 그렇게 적는다.
"""

from __future__ import annotations

import math

LAG = 11             # 1년 창이 겹치는 개월 수 — 분산을 잴 때 이만큼의 자기공분산을 더한다
OVERLAP = 12         # 독립인 관측 하나가 몇 개월인가 — t 임계값의 자유도를 정한다
HORIZONS = {"same": 12, "after3": 3, "after12": 12}
MIN_N = 36           # 이보다 짧으면 재지 않는다(3년)


def _shift(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[4:]) - 1 + k
    return f"{y + m // 12:04d}{m % 12 + 1:02d}"


def movement(kind: str, s: dict[str, float]) -> dict[str, float]:
    """지표 계열 → 달마다의 1년 움직임(화면 단위: %p 또는 %)."""
    out = {}
    for t, v in s.items():
        if kind == "level":
            out[t] = v
            continue
        p = s.get(_shift(t, -12))
        if p is None:
            continue
        if kind == "diff":
            out[t] = v - p
        elif kind == "growth":
            if p > 0:
                out[t] = (v / p - 1) * 100
        else:
            raise ValueError(kind)
    return out


def pairs(x: dict[str, float], close: dict[str, float], horizon: str, pub_lag: int) -> list[tuple[str, float, float]]:
    """(t, x_t, y_t). y 는 로그 수익률. 양 끝 종가가 다 있는 달만."""
    h = HORIZONS[horizon]
    out = []
    for t in sorted(x):
        if horizon == "same":
            a, b = _shift(t, -12), t
        else:
            a = _shift(t, pub_lag)
            b = _shift(a, h)
        if a in close and b in close:
            out.append((t, x[t], math.log(close[b] / close[a])))
    return out


def ols_hh(X, y, lag: int = LAG):
    """(계수, 표준오차, 95% 임계값). X 는 상수항 없이 넘긴다 — 평균을 빼서 상수항을 흡수한다.

    분산 = (X'X)⁻¹ [Σ_{|j|≤lag} γ_u(j) · Σ_t x_t x_{t−j}'] (X'X)⁻¹ — 등분산 Hansen–Hodrick.
    왜 이것인가는 모듈 머리말. 대각이 0 아래로 나오면(드물다) 0 으로 자른다.
    """
    import numpy as np
    from scipy import stats

    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, k = X.shape
    Xc = X - X.mean(axis=0)
    yc = y - y.mean()
    xtx_inv = np.linalg.inv(Xc.T @ Xc)
    beta = xtx_inv @ Xc.T @ yc
    u = yc - Xc @ beta
    S = (u @ u / n) * (Xc.T @ Xc)
    for j in range(1, lag + 1):
        gu = u[j:] @ u[:-j] / n
        G = Xc[j:].T @ Xc[:-j]
        S = S + gu * (G + G.T)
    var = np.clip(np.diag(xtx_inv @ S @ xtx_inv), 0, None)
    df = max(n / OVERLAP - k - 1, 2)
    return beta, np.sqrt(var), float(stats.t.ppf(0.975, df))


def _pct(v: float) -> float:
    """로그 수익률 → 단순 수익률(%)."""
    return round((math.exp(v) - 1) * 100, 2)


def _sd(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _verdict(lo: float, hi: float) -> str:
    return "pos" if lo > 0 else "neg" if hi < 0 else "none"


def one(x: dict[str, float], close: dict[str, float], horizon: str, pub_lag: int, kind: str) -> dict | None:
    """지표 하나 × 시점 하나의 영향."""
    ps = pairs(x, close, horizon, pub_lag)
    if len(ps) < MIN_N:
        return None
    xs = [p[1] for p in ps]
    ys = [p[2] for p in ps]
    (b,), (se,), c = ols_hh([[v] for v in xs], ys)
    b, se = float(b), float(se)
    sd = _sd(xs)
    lo, hi = (b - c * se) * sd, (b + c * se) * sd

    half = len(ps) // 2
    halves = []
    for part in (ps[:half], ps[half:]):
        (bh,), _, _ = ols_hh([[p[1]] for p in part], [p[2] for p in part])
        halves.append({"from": part[0][0], "to": part[-1][0], "bar": _pct(float(bh) * sd)})

    # 오른 시기 vs 내린 시기. 나누는 선은 지표의 꼴마다 다르다.
    #   diff   — 0: 1년 새 올랐나 내렸나(금리·실업률)
    #   level  — 0: 금리차가 양수인가 역전인가
    #   growth — 중앙값: 물가·M2 는 1년 상승률이 거의 늘 양수라 0 으로 나누면 한쪽에 몇 달만 남는다
    #            (재 보니 한국 물가 306달 대 3달). '평소보다 빨리 오른 해 vs 느리게 오른 해' 로 나눈다.
    # diff 는 변화가 0 인 달(기준금리가 1년 내내 그대로)을 양쪽 다 뺀다 — '오른 시기' 에 넣으면 거짓이다.
    cut = sorted(xs)[len(xs) // 2] if kind == "growth" else 0.0
    up = [p[2] for p in ps if (p[1] > cut if kind == "diff" else p[1] >= cut)]
    down = [p[2] for p in ps if p[1] < cut]

    def mean(v):
        return _pct(sum(v) / len(v)) if v else None

    return {
        "n": len(ps), "from": ps[0][0], "to": ps[-1][0],
        "sd": round(sd, 3),
        "slope": round(b * 100, 3),        # 1단위당 지수 로그 수익률(%p) — 작을 때는 % 와 거의 같다
        "bar": _pct(b * sd), "lo": _pct(lo), "hi": _pct(hi),
        "verdict": _verdict(lo, hi),
        "halves": halves,
        "flip": (halves[0]["bar"] > 0) != (halves[1]["bar"] > 0),
        "cut": round(cut, 3),
        "up": {"mean": mean(up), "n": len(up)}, "down": {"mean": mean(down), "n": len(down)},
        "points": [[p[0], round(p[1], 3), _pct(p[2])] for p in ps],
    }


def joint(xs: dict[str, dict[str, float]], close: dict[str, float], horizon: str,
          lags: dict[str, int]) -> dict | None:
    """지표를 모두 한 회귀에 넣었을 때 — 다른 지표를 통제한 뒤의 값. 공통 표본만 쓴다.

    발표 시차가 지표마다 달라 '그 뒤' 의 시작 달이 갈린다. 가장 늦게 알려지는 지표에 맞춰(시차의 최댓값)
    모두 같은 y 를 쓴다 — 그래야 한 회귀가 된다.
    """
    lag = max(lags.values())
    ids = list(xs)
    common = sorted(set.intersection(*[set(v) for v in xs.values()]))
    rows = []
    for t in common:
        ps = pairs({t: 0.0}, close, horizon, lag)
        if ps:
            rows.append((t, [xs[i][t] for i in ids], ps[0][2]))
    # 독립인 해가 계수 수보다 넉넉해야 한다 — S&P 500 의 10년에 지표 여섯을 넣으면 자유도가 바닥난다.
    if len(rows) / OVERLAP < len(ids) + 4:
        return None
    b, se, c = ols_hh([r[1] for r in rows], [r[2] for r in rows])
    out = {}
    for k, i in enumerate(ids):
        sd = _sd([r[1][k] for r in rows])
        lo, hi = (b[k] - c * se[k]) * sd, (b[k] + c * se[k]) * sd
        out[i] = {"bar": _pct(float(b[k]) * sd), "lo": _pct(float(lo)), "hi": _pct(float(hi)),
                  "verdict": _verdict(float(lo), float(hi))}
    return {"n": len(rows), "from": rows[0][0], "to": rows[-1][0], "by": out}
