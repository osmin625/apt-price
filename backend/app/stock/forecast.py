"""지수의 월·분기 수익률 구간 예측 — **평가 장치가 먼저**고 모델은 그 위에 얹는다.

## 무엇을 하나

월말 종가로 h개월(1·3) 로그 수익률의 80% 구간을 낸다. 후보는 넷이고, 같은 시간순 표본 밖
백테스트(walk-forward)로 견준다. **기준선은 무작위 보행**(중심 0)이다 — 지수 수익률을 맞힌다는
주장은 대부분 이것을 못 이긴다. 못 이기면 화면이 그렇게 말한다(값으로, 판정 문장 없이).

| id | 중심 | 폭 |
|---|---|---|
| rw | 0 | 과거 h개월 수익률의 분위(평균을 뺀 모양) |
| mean | 과거 h개월 수익률 평균 | rw 와 같은 모양 |
| rf | 지금 무위험 금리 + 과거 초과수익 평균 | 과거 초과수익의 분위 |
| vol | rf 와 같다 | 과거 초과수익을 그때 변동성으로 나눈 분위 × 지금 변동성 |

## 미래를 보지 않는다

기점 t 의 예측은 **t 월말까지 알려진 것만** 쓴다. 과거 h개월 수익률은 끝이 t 이하인 것만
(기점이 t-h 이하) — 끝이 t 를 넘는 수익률을 학습에 넣으면 겹친 h-1 개월만큼 답을 보고 맞힌다.
`verify_lookahead` 가 t 뒤의 값을 바꿔도 t 의 예측이 그대로인지 본다.

순수 파이썬이다 — 표본이 수백 개라 numpy 가 필요 없고, CI 에서도 같은 코드가 돈다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ALPHA = 0.2          # 80% 구간
HORIZONS = (1, 3)    # 개월
MIN_TRAIN = 36       # 기점마다 과거 h개월 수익률이 이만큼은 있어야 예측한다(3년)
EWMA_LAMBDA = 0.94   # RiskMetrics 일별 값
TRADING_DAYS = 21    # 한 달 거래일 — 일별 변동성을 h개월로 늘릴 때만 쓴다
MODELS = ("rw", "mean", "rf", "vol")
BASELINE = "rw"


@dataclass(frozen=True)
class Series:
    """한 지수의 재료. 전부 월('YYYYMM') 열쇠다."""
    months: list[str]            # 완결된 달만, 오름차순
    close: dict[str, float]      # 월말 종가
    rf: dict[str, float]         # 그 달 무위험 금리(연%) — 없으면 rf·vol 은 그 기점을 건너뛴다
    vol: dict[str, float]        # 그 달 마지막 거래일의 일별 EWMA 표준편차(로그)


def month_end_closes(daily: list[tuple[str, float]]) -> tuple[list[str], dict[str, float]]:
    """일별 (YYYYMMDD, 종가) → 완결된 달의 월말 종가.

    **마지막 관측이 있는 달은 버린다.** 11월 5일까지 받았으면 11월 '월말' 은 아직 없다 —
    그 값을 월말로 쓰면 마지막 수익률 하나가 닷새짜리가 된다. 마지막 관측이 정확히 말일이어도
    거래일 달력을 몰라 구분하지 못하므로 같이 버린다(한 달 늦을 뿐 틀리지 않는다).
    """
    last: dict[str, float] = {}
    for d, v in sorted(daily):
        last[d[:6]] = v
    months = sorted(last)
    if months:
        months = months[:-1]
    return months, {m: last[m] for m in months}


def ewma_vol(daily: list[tuple[str, float]], lam: float = EWMA_LAMBDA, warm: int = 60) -> dict[str, float]:
    """달마다 그 달 마지막 거래일까지의 EWMA 일별 표준편차. 앞 `warm` 일은 시작값을 잡는 데 쓴다."""
    pts = sorted(daily)
    r = [(pts[i][0], math.log(pts[i][1] / pts[i - 1][1])) for i in range(1, len(pts))]
    if len(r) <= warm:
        return {}
    var = sum(x * x for _, x in r[:warm]) / warm
    out: dict[str, float] = {}
    for d, x in r[warm:]:
        var = lam * var + (1 - lam) * x * x
        out[d[:6]] = math.sqrt(var)
    return out


def quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (pos - lo)


def _ret(s: Series, i: int, h: int) -> float:
    return math.log(s.close[s.months[i + h]] / s.close[s.months[i]])


RF_STALE = 3  # 금리가 이 달 수보다 오래됐으면 쓰지 않는다


def _rf_h(s: Series, i: int, h: int) -> float | None:
    """기점 달에 **알려져 있던** 가장 최근 금리(연%) → h개월 로그 수익률.

    한국은행은 기준금리 월 값을 다음 달에 낸다. 그 달 값이 아직 없으면 그 앞 달 값을 쓴다 —
    기준금리는 결정되는 날 알려지므로 '그때 알던 값' 이다. 뒤 달 값을 끌어오지는 않는다.
    """
    ym = s.months[i]
    y, m = int(ym[:4]), int(ym[4:])
    for _ in range(RF_STALE + 1):
        v = s.rf.get(f"{y:04d}{m:02d}")
        if v is not None:
            return math.log1p(v / 100) * h / 12
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return None


def forecast(s: Series, t: int, h: int, model: str) -> tuple[float, float, float] | None:
    """기점 t(월 인덱스)에서 h개월 로그 수익률의 (중심, 하단, 상단). 재료가 모자라면 None."""
    past = range(0, t - h + 1)  # 끝(i+h)이 t 이하인 기점들
    if len(past) < MIN_TRAIN:
        return None
    lo_q, hi_q = ALPHA / 2, 1 - ALPHA / 2
    if model in ("rw", "mean"):
        rs = [_ret(s, i, h) for i in past]
        m = sum(rs) / len(rs)
        dev = [x - m for x in rs]
        c = 0.0 if model == "rw" else m
        return c, c + quantile(dev, lo_q), c + quantile(dev, hi_q)

    rf_now = _rf_h(s, t, h)
    ex = []
    for i in past:
        f = _rf_h(s, i, h)
        if f is not None:
            ex.append((i, _ret(s, i, h) - f))
    if rf_now is None or len(ex) < MIN_TRAIN:
        return None
    m = sum(x for _, x in ex) / len(ex)
    c = rf_now + m
    if model == "rf":
        dev = [x - m for _, x in ex]
        return c, c + quantile(dev, lo_q), c + quantile(dev, hi_q)
    if model == "vol":
        scale = math.sqrt(TRADING_DAYS * h)
        z = [(x - m) / (s.vol[s.months[i]] * scale) for i, x in ex if s.months[i] in s.vol]
        v_now = s.vol.get(s.months[t])
        if v_now is None or len(z) < MIN_TRAIN:
            return None
        w = v_now * scale
        return c, c + quantile(z, lo_q) * w, c + quantile(z, hi_q) * w
    raise ValueError(model)


# ──────────────────────────────────────────────────────────
# 평가
# ──────────────────────────────────────────────────────────
def interval_score(lo: float, hi: float, y: float, alpha: float = ALPHA) -> float:
    """Gneiting–Raftery 구간 점수. 좁을수록 낮고, 벗어나면 벗어난 만큼 2/α 배 벌점. 낮을수록 좋다.

    적중률(포함 비율)만 보면 구간을 넓히기만 해도 80% 를 맞춘다. 폭과 벗어남을 한 숫자에
    같이 넣어야 '넓혀서 맞힌 것' 과 '알아서 맞힌 것' 이 갈린다.
    """
    return (hi - lo) + (2 / alpha) * max(lo - y, 0) + (2 / alpha) * max(y - hi, 0)


def dm(da: list[float], db: list[float], lag: int) -> tuple[float, float]:
    """Diebold–Mariano. 손실 열 둘(같은 기점). (t, 양측 p). t 가 음수면 A 가 낫다.

    분산은 Newey–West(lag). h개월 수익률을 매달 기점으로 재면 창이 h-1 개월 겹쳐 손실이
    그만큼 자기상관을 가진다 — `scripts/cv_macro.py` 와 같은 식이다.
    """
    d = [a - b for a, b in zip(da, db)]
    n = len(d)
    if n < 2:
        return float("nan"), float("nan")
    m = sum(d) / n

    def g(k):
        return sum((d[i] - m) * (d[i - k] - m) for i in range(k, n)) / n

    v = g(0) + 2 * sum((1 - k / (lag + 1)) * g(k) for k in range(1, lag + 1))
    if v <= 0:
        return float("nan"), float("nan")
    t = m / math.sqrt(v / n)
    return t, math.erfc(abs(t) / math.sqrt(2))


def backtest(s: Series, h: int) -> dict:
    """모든 후보를 **같은 기점들**에서 잰다 — 후보마다 기점이 다르면 쉬운 시기만 고른 후보가 이긴다."""
    origins = [t for t in range(len(s.months) - h)
               if all(forecast(s, t, h, m) is not None for m in MODELS)]
    rows = {m: [] for m in MODELS}
    for t in origins:
        y = _ret(s, t, h)
        for m in MODELS:
            c, lo, hi = forecast(s, t, h, m)
            rows[m].append((s.months[t], c, lo, hi, y))
    lag = max(h - 1, 0)
    base = rows[BASELINE]
    out = {}
    for m in MODELS:
        r = rows[m]
        n = len(r)
        if not n:
            out[m] = {"n": 0}
            continue
        se = [(c - y) ** 2 for _, c, _, _, y in r]
        isc = [interval_score(lo, hi, y) for _, _, lo, hi, y in r]
        se_b = [(c - y) ** 2 for _, c, _, _, y in base]
        is_b = [interval_score(lo, hi, y) for _, _, lo, hi, y in base]
        t_se, p_se = dm(se, se_b, lag) if m != BASELINE else (None, None)
        t_is, p_is = dm(isc, is_b, lag) if m != BASELINE else (None, None)
        out[m] = {
            "n": n,
            "rmse": math.sqrt(sum(se) / n),
            "coverage": sum(1 for _, _, lo, hi, y in r if lo <= y <= hi) / n,
            "width": sum(hi - lo for _, _, lo, hi, _ in r) / n,
            "interval_score": sum(isc) / n,
            "dm_point": (t_se, p_se),
            "dm_interval": (t_is, p_is),
        }
    return {"origins": [s.months[t] for t in origins], "rows": rows, "scores": out}
