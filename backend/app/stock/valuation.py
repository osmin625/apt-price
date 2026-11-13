"""장기 투자 탭의 지수 평가 넷 — 버핏 지표·이익 수익률 vs 국채·실러 CAPE·장기 추세 대비 위치를 실제 지수에.

화면은 지수마다 **지금 상태**(값과 그 값이 자기 역사에서 몇 번째쯤인가)와 **과거 성적**(그 위치에 있던 달들의
뒤 5·10년 수익률)을 보여 준다. '사라·팔아라' 는 말하지 않는다(2026-11-12 합의). 설명·결정은
docs/stock/valuation.md '실제 지수에 돌리는 법'.

## 그날 알던 것만 쓴다

과거 성적은 '그달에 이 값을 봤다면' 이 성립할 때만 뜻이 있다. 그래서

- **분기 통계(시가총액·GDP)는 분기 끝에서 3달 뒤부터 쓴다.** 연준 자금순환표는 분기 끝에서 10주쯤, 한국 명목
  GDP 잠정치는 두 달 남짓 뒤에 나온다. 그 전 달에는 한 분기 앞의 값을 쓴다.
- **실러의 이익(E)은 3달 묵혀 쓴다.** 표에는 그 달의 지난 12개월 이익이 있지만, 발표는 분기 끝에서 한두 달
  뒤다(지금도 표 끝 넉 달은 E 가 비어 있다). CAPE 도 이 E 로 직접 계산한다 — 실러의 CAPE 열은 **전 달까지**
  10년 이익을 쓴다(1달 묵힘). 1달 묵혀 계산하면 그 열과 1e-15 까지 같다는 것을 `scripts/verify_valuation.py` 가 본다.
- **장기 추세는 그달까지의 자료로만 맞춘다**(늘어나는 창). 지금까지의 자료로 한 번 맞춘 직선을 과거에 대면
  나중 자료가 추세를 바꾼 만큼 과거의 편차에 미래가 섞인다 — 기법 설명의 '함정' 에 적은 그 함정이다.
- **역사 백분위도 그달까지의 값들 안에서** 잰다. 전체 기간의 순위를 쓰면 '나중에 보니 높았던 달' 이 된다.

## 과거 성적을 읽는 법 — 겹치는 구간과 기저율

달마다 '그 뒤 10년 수익률' 을 재면 이웃한 달끼리 10년 중 9년 11개월이 겹친다. 1,600달이 있어도 서로 다른
10년은 열여섯 남짓이다. 그래서

- 칸마다 **겹치지 않는 구간 수**(그 칸의 달을 h 년 간격으로 솎은 수)를 같이 적고, 셋이 안 되면 판정하지 않는다.
- 범위는 **주가가 평가와 상관없이 움직였다면** 이 칸의 달들이 모든 달 평균보다 얼마나 더(덜) 벌었을지의 95% 다.
  실제 월 수익률을 12달 덩어리로 뽑아 이어 붙인 가짜 주가 경로를 수천 개 만들고, 칸은 그대로 둔 채 그 경로의 뒤 h 년
  수익률로 '칸 평균 − 모든 달 평균' 을 낸다(`null_means` 가 왜 차이인지 적는다). 단기 매매의 '아무 날' 범위와 같은 생각이다(`trading.signal_lens`) — 다만 날이 아니라 경로를 뽑는다.
  덩어리로 뽑는 것은 몇 달 이어지는 추세를 남기려고다.

  처음에는 평가 계열을 시간 축으로 통째로 돌려(circular shift) 짝을 끊었다. 두 계열 각자의 끈적임을 지키는 표준
  방법인데, 재 보니 **관계가 없는 합성 자료에서 18% 가 범위 밖**으로 나갔다(5% 여야 한다). 10년이 여덟 번 남짓
  들어가는 길이에서는 돌려 볼 수 있는 서로 다른 짝이 여덟 가지뿐이라 범위의 끝을 못 잰다. 달마다 섞는 범위는
  68% 였다(겹침을 무시하면 표본이 수십 배로 부푼다). 경로를 뽑는 지금 판의 값은 verify 가 찍는다.
- 그래도 이 범위는 '월 수익률이 12달 넘게는 서로 무관하다' 를 깔고 있다. 주가가 몇 년에 걸쳐 평균으로 돌아오는
  성질이 있다면 그 몫까지 평가의 공으로 셀 수 있다 — 화면 Hint 에 적는다.

수익률은 **물가를 뺀 주가 수익률**(배당 제외, 현지 통화)의 연평균이다. 150년을 견주면 물가가 다른 시대가 섞이고,
KOSPI 는 가격 지수뿐이라 배당을 넣을 수 없다 — 두 지수를 같은 잣대로 둔다.
"""

from __future__ import annotations

import bisect
import math

import numpy as np

from ..macro import store as macro_store
from ..macro.clients import shiller
from . import store
from .indices import INDICES

HORIZONS = (5, 10)        # 년
BUCKETS = 5               # 역사 백분위 다섯 칸(0–20 … 80–100)
MIN_HIST = 60             # 백분위를 재려면 자기 역사가 5년은 있어야 한다
MIN_FIT = 120             # 추세는 10년 이상 쌓인 뒤부터 맞춘다
LAG_Q = 3                 # 분기 통계는 분기 끝에서 3달 뒤부터 안다
LAG_E = 3                 # 실러 이익은 3달 묵힌다
CAPE_YEARS = 10
MIN_IND = 3               # 겹치지 않는 구간이 이보다 적으면 범위·판정을 내지 않는다
DRAWS = 2000
BLOCK = 12                # 가짜 경로를 만드는 덩어리(달)
SEED = 20261113

# 적재가 받는 것(scripts/ingest_stock.py). 이 모듈이 읽는 계열과 어긋나면 verify_valuation 이 잡는다.
NEEDS: dict[str, tuple[str, ...]] = {
    "ECOS": ("kospi_mcap", "kospi_per", "kr_10y", "kr_gdp", "cpi"),
    "FRED": ("us_mcap", "us_gdp"),
    "SHILLER": tuple(shiller.SERIES),
}

# 기법 id(frontend/src/stock/techniques/long.js) → 이름·단위·높으면 비싼가.
MEASURES: dict[str, dict] = {
    "buffett-indicator": {"label": "시가총액 ÷ GDP", "unit": "%", "high": "expensive"},
    "fed-model": {"label": "이익 수익률 − 10년 국채", "unit": "%p", "high": "cheap"},
    "cape": {"label": "CAPE", "unit": "배", "high": "expensive"},
    "trend-position": {"label": "추세 대비", "unit": "%", "high": "expensive"},
}


# ── 달 셈 ─────────────────────────────────────────────

def mi(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[4:6]) - 1


def ym_of(i: int) -> str:
    return f"{i // 12:04d}{i % 12 + 1:02d}"


def q_end(q: str) -> int:
    """'2026Q2' → 2026-06 의 달 번호."""
    return int(q[:4]) * 12 + int(q[5]) * 3 - 1


def as_index(series: dict[str, float]) -> dict[int, float]:
    return {mi(k): v for k, v in series.items()}


def known_quarterly(q: dict[str, float], lag: int = LAG_Q, until: int | None = None) -> tuple[dict[int, float], dict[int, str]]:
    """분기 값을 '알게 된 달' 부터 다음 분기 값이 알려질 때까지 달마다 편다. 값과 그 값의 분기 이름."""
    out: dict[int, float] = {}
    src: dict[int, str] = {}
    keys = sorted(q, key=q_end)
    for k, nxt in zip(keys, keys[1:] + [None]):
        a = q_end(k) + lag
        b = q_end(nxt) + lag if nxt else (until if until is not None else a) + 1
        for m in range(a, b):
            out[m] = q[k]
            src[m] = k
    return out, src


def latest_at(x: dict[int, float], m: int, lag: int = 0, max_back: int = 12) -> float | None:
    """m − lag 이전에서 가장 최근 값(최대 max_back 달 거슬러)."""
    for j in range(m - lag, m - lag - max_back - 1, -1):
        if j in x:
            return x[j]
    return None


def fill(x: dict[int, float], until: int, upto: int = 2) -> dict[int, float]:
    """물가처럼 한두 달 늦게 나오는 계열을 마지막 값으로 최대 `upto` 달 잇는다 — 지수의 마지막 달과 맞추려고."""
    if not x:
        return x
    out = dict(x)
    last = max(x)
    for m in range(last + 1, min(until, last + upto) + 1):
        out[m] = x[last]
    return out


# ── 평가 계열 ─────────────────────────────────────────

def trend_dev(lp: dict[int, float], min_fit: int = MIN_FIT) -> tuple[dict[int, float], tuple[float, float, int] | None]:
    """로그 가격에 그달까지의 자료로만 맞춘 직선에서의 거리(%). 마지막 맞춤(기울기·절편·기준 달)도 돌린다.

    누적합으로 푼다 — 달마다 처음부터 다시 맞추면 1,800달 × 1,800달이다.
    """
    keys = sorted(lp)
    out: dict[int, float] = {}
    sx = sy = sxx = sxy = 0.0
    last = None
    if not keys:
        return out, None
    x0 = keys[0]
    for k, m in enumerate(keys, start=1):
        x = m - x0
        y = lp[m]
        sx += x
        sy += y
        sxx += x * x
        sxy += x * y
        if k < min_fit:
            continue
        den = k * sxx - sx * sx
        b = (k * sxy - sx * sy) / den
        a = (sy - b * sx) / k
        out[m] = (math.exp(y - (a + b * x)) - 1) * 100
        last = (b, a, x0)
    return out, last


def cape_of(price_real: dict[int, float], e_real: dict[int, float], lag: int, years: int = CAPE_YEARS) -> dict[int, float]:
    """실질 주가 ÷ (m − lag 까지 10년 실질 이익 평균). 이익이 120달 다 있어야 낸다."""
    n = years * 12
    out: dict[int, float] = {}
    for m, p in price_real.items():
        end = m - lag
        if end not in e_real:
            # 표 끝처럼 E 가 비면 가장 최근 E 로 끝을 당긴다(최대 6달) — '그때 알던 가장 최근 이익'
            end = next((j for j in range(end, end - 7, -1) if j in e_real), None)
            if end is None:
                continue
        win = [e_real.get(j) for j in range(end - n + 1, end + 1)]
        if any(v is None for v in win):
            continue
        avg = sum(win) / n
        if avg > 0:
            out[m] = p / avg
    return out


def us_inputs() -> dict:
    P = as_index(macro_store.monthly("shiller_p"))
    E = as_index(macro_store.monthly("shiller_e"))
    CPI = as_index(macro_store.monthly("shiller_cpi"))
    GS10 = as_index(macro_store.monthly("shiller_gs10"))
    return {"P": P, "E": E, "CPI": CPI, "GS10": GS10,
            "mcap": macro_store.quarterly("us_mcap"), "gdp": macro_store.quarterly("us_gdp")}


def kr_inputs() -> dict:
    ix = next(i for i in INDICES if i.id == "kospi")
    close: dict[int, float] = {}
    for d, c in store.daily(ix.market, ix.symbol):
        close[mi(d[:6])] = c  # 날짜 순이라 마지막 거래일이 남는다
    return {"close": close, "cpi": as_index(macro_store.monthly("cpi")),
            "mcap": as_index(macro_store.monthly("kospi_mcap")), "per": as_index(macro_store.monthly("kospi_per")),
            "y10": as_index(macro_store.monthly("kr_10y")), "gdp": macro_store.quarterly("kr_gdp")}


def us_measures(d: dict) -> tuple[dict[int, float], dict[str, dict]]:
    """(실질 주가, {기법 id: {values, src, extra}})."""
    P, E, CPI, GS10 = d["P"], d["E"], d["CPI"], d["GS10"]
    real = {m: P[m] / CPI[m] for m in P if m in CPI}
    last = max(real)
    out: dict[str, dict] = {}

    ratio = {q: d["mcap"][q] / 1000 / d["gdp"][q] * 100 for q in d["mcap"] if q in d["gdp"]}
    vals, src = known_quarterly(ratio, until=last)
    out["buffett-indicator"] = {"values": {m: v for m, v in vals.items() if m <= last}, "src": src,
                                "source": "연준 자금순환표 비금융 법인 주식(시가) ÷ 명목 GDP — FRED NCBEILQ027S·GDP"}

    ey, bond, gap = {}, {}, {}
    for m in P:
        if m not in GS10:
            continue
        e = latest_at(E, m, LAG_E, max_back=6)
        if e is None:
            continue
        ey[m] = e / P[m] * 100
        bond[m] = GS10[m]
        gap[m] = ey[m] - bond[m]
    out["fed-model"] = {"values": gap, "extra": {"ey": ey, "bond": bond},
                        "source": "S&P 500 지난 12개월 이익 ÷ 주가(실러 자료, 이익은 3달 묵힘) − 미국 10년 국채"}

    e_real = {m: E[m] / CPI[m] for m in E if m in CPI}
    out["cape"] = {"values": cape_of(real, e_real, LAG_E),
                   "source": "S&P 500 실질 주가 ÷ 10년 실질 이익 평균(실러 자료로 계산, 이익은 3달 묵힘)"}

    dev, fit = trend_dev({m: math.log(v) for m, v in real.items()})
    out["trend-position"] = {"values": dev, "fit": fit, "price": real,
                             "source": "S&P 500 실질 주가(실러 자료)의 로그에 그달까지 맞춘 직선"}
    return real, out


def kr_measures(d: dict) -> tuple[dict[int, float], dict[str, dict]]:
    close = d["close"]
    last = max(close)
    cpi = fill(d["cpi"], last)
    real = {m: close[m] / cpi[m] for m in close if m in cpi}
    out: dict[str, dict] = {}

    gdp, src = known_quarterly(d["gdp"], until=last)
    # 시가총액은 천원, GDP 는 분기 십억원 — 천원 ÷ 1e6 = 십억원, 분기 × 4 = 1년.
    out["buffett-indicator"] = {
        "values": {m: d["mcap"][m] / 1e6 / (gdp[m] * 4) * 100 for m in d["mcap"] if m in gdp},
        "src": src, "source": "KOSPI 시가총액 ÷ 명목 GDP(계절조정 분기 × 4) — 한국은행 ECOS"}

    ey, bond, gap = {}, {}, {}
    for m, per in d["per"].items():
        if m in d["y10"] and per > 0:
            ey[m] = 100 / per
            bond[m] = d["y10"][m]
            gap[m] = ey[m] - bond[m]
    out["fed-model"] = {"values": gap, "extra": {"ey": ey, "bond": bond},
                        "source": "KOSPI 1 ÷ PER − 국고채 10년 — 한국은행 ECOS"}

    # KOSPI 주당 이익은 따로 공표되지 않아 종가 ÷ PER 로 되돌려 얻는다. PER 이 2004-01 부터라 CAPE 는 10년 뒤부터.
    e_real = {m: close[m] / per / cpi[m] for m, per in d["per"].items() if m in close and m in cpi and per > 0}
    out["cape"] = {"values": cape_of(real, e_real, 0),
                   "source": "KOSPI 실질 종가 ÷ 10년 실질 주당 이익 평균(종가 ÷ PER 로 얻음) — ECOS"}

    dev, fit = trend_dev({m: math.log(v) for m, v in real.items()})
    out["trend-position"] = {"values": dev, "fit": fit, "price": real,
                             "source": "KOSPI 실질 월말 종가의 로그에 그달까지 맞춘 직선"}
    return real, out


# ── 지금 상태·과거 성적 ───────────────────────────────

def expanding_pct(values: dict[int, float], min_hist: int = MIN_HIST) -> dict[int, float]:
    """그달까지의 값들 안에서 몇 번째쯤인가(0–100). 같은 값은 반으로 센다."""
    seen: list[float] = []
    out: dict[int, float] = {}
    for m in sorted(values):
        v = values[m]
        bisect.insort(seen, v)
        if len(seen) < min_hist:
            continue
        lo = bisect.bisect_left(seen, v)
        hi = bisect.bisect_right(seen, v)
        out[m] = (lo + (hi - lo) / 2) / len(seen) * 100
    return out


def forward(real: dict[int, float], m: int, years: int) -> float | None:
    """m 달 실질 주가에서 years 년 뒤까지의 연평균 수익률(%)."""
    j = m + 12 * years
    if m not in real or j not in real:
        return None
    return ((real[j] / real[m]) ** (1 / years) - 1) * 100


def thin(ms: list[int], gap: int) -> int:
    """gap 달 간격으로 솎았을 때 남는 수 — 겹치지 않는 구간."""
    n, last = 0, None
    for m in sorted(ms):
        if last is None or m - last >= gap:
            n += 1
            last = m
    return n


def bucket_of(p: float) -> int:
    return min(int(p // (100 / BUCKETS)), BUCKETS - 1)


def null_means(B: np.ndarray, o: np.ndarray, lr: np.ndarray, years: int, rng: np.random.Generator,
               draws: int, block: int = BLOCK) -> np.ndarray:
    """칸(B)은 그대로, 주가는 실제 월 로그 수익률(lr)을 block 달 덩어리로 뽑아 이은 가짜 경로 — 칸 평균이 그 경로의
    모든 달 평균보다 얼마나 높은가 [draws × 칸].

    칸 평균 자체가 아니라 **모든 달 평균과의 차이**를 뽑는다. 칸의 달들은 표본 전체와 같은 충격을 나눠 가져서, 실제
    경로에서 칸 평균은 그 경로의 전체 평균 가까이 붙는다. 칸 평균만 뽑아 실제 전체 평균 둘레의 범위로 쓰면 그
    공유분만큼 범위가 넓어진다 — 재 보니 관계가 없을 때 0.7% 만 걸렸고(5% 여야), 심어 둔 관계를 20번 중 7번만 잡았다.
    """
    T = len(lr)
    nb = -(-T // block)
    out = np.empty((draws, BUCKETS))
    step = 250
    for a in range(0, draws, step):
        k = min(step, draws - a)
        starts = rng.integers(0, T, size=(k, nb))
        idx = ((starts[:, :, None] + np.arange(block)) % T).reshape(k, -1)[:, :T]
        c = np.concatenate([np.zeros((k, 1)), np.cumsum(lr[idx], axis=1)], axis=1)
        R = (np.exp((c[:, o + 12 * years] - c[:, o]) / years) - 1) * 100
        all_mean = R.mean(axis=1)
        for b in range(BUCKETS):
            sel = B == b
            out[a:a + k, b] = R[:, sel].mean(axis=1) - all_mean if sel.any() else np.nan
    return out


def perf(pct: dict[int, float], real: dict[int, float], years: int, rng: np.random.Generator,
         draws: int = DRAWS) -> dict:
    """역사 백분위 칸마다 그 뒤 years 년 연평균 실질 수익률과, 주가가 평가와 무관했을 때의 범위."""
    months = sorted(real)
    if months and months[-1] - months[0] + 1 != len(months):
        raise ValueError("실질 주가에 빈 달이 있다 — 경로를 뽑으려면 달이 이어져야 한다")
    origins = [m for m in sorted(pct) if forward(real, m, years) is not None]
    gap = 12 * years
    if not origins:
        return {"n": 0, "rows": [], "base": None}
    R = np.array([forward(real, m, years) for m in origins])
    B = np.array([bucket_of(pct[m]) for m in origins])
    o = np.array([m - months[0] for m in origins])
    lr = np.diff(np.log([real[m] for m in months]))
    sims = null_means(B, o, lr, years, rng, draws)
    base = float(R.mean())
    rows = []
    for b in range(BUCKETS):
        sel = B == b
        ms = [m for m, ok in zip(origins, sel) if ok]
        row: dict = {"lo": b * 100 // BUCKETS, "hi": (b + 1) * 100 // BUCKETS, "n": int(sel.sum()),
                     "n_ind": thin(ms, gap), "mean": float(R[sel].mean()) if sel.any() else None,
                     "lo95": None, "hi95": None, "verdict": None}
        if row["n"] and row["n_ind"] >= MIN_IND:
            # 범위는 '모든 달 평균 + 가짜 경로에서의 차이 95%' — 화면은 수익률 단위로 읽는다.
            lo, hi = np.percentile(sims[:, b], [2.5, 97.5])
            row["lo95"], row["hi95"] = base + float(lo), base + float(hi)
            row["verdict"] = ("above" if row["mean"] > row["hi95"] else
                              "below" if row["mean"] < row["lo95"] else "inside")
        rows.append(row)
    return {"n": len(origins), "n_ind": thin(origins, gap), "base": base,
            "first": ym_of(origins[0]), "last": ym_of(origins[-1]), "rows": rows}


def _r(v, d=2):
    return None if v is None or not math.isfinite(v) else round(float(v), d)


def describe(mid: str, m: dict, real: dict[int, float], rng: np.random.Generator) -> dict:
    vals = m["values"]
    if not vals:
        return {"missing": "계산할 자료가 없습니다"}
    keys = sorted(vals)
    pct = expanding_pct(vals)
    last = keys[-1]
    arr = np.array([vals[k] for k in keys])
    now = {"month": ym_of(last), "value": _r(vals[last]), "pct": _r(pct.get(last), 0),
           "period": m.get("src", {}).get(last, ym_of(last)),
           "mean": _r(arr.mean()), "sd": _r(arr.std()), "since": ym_of(keys[0])}
    if mid == "fed-model":
        now["ey"] = _r(m["extra"]["ey"][last])
        now["bond"] = _r(m["extra"]["bond"][last])
    series: dict = {"dates": [ym_of(k) for k in keys], "values": [_r(vals[k]) for k in keys]}
    if mid == "fed-model":
        series["ey"] = [_r(m["extra"]["ey"][k]) for k in keys]
        series["bond"] = [_r(m["extra"]["bond"][k]) for k in keys]
    if mid == "trend-position":
        # 그림의 가격 선은 맞춘 첫 달부터가 아니라 가격이 있는 처음부터 — 추세선은 지금까지의 자료로 맞춘 것.
        pk = sorted(m["price"])
        b, a, x0 = m["fit"]
        scale = m["price"][pk[-1]]
        series["price_dates"] = [ym_of(k) for k in pk]
        series["price"] = [_r(m["price"][k] / scale * 100, 3) for k in pk]
        series["trend"] = [_r(math.exp(a + b * (k - x0)) / scale * 100, 3) for k in pk]
        now["growth"] = _r((math.exp(12 * b) - 1) * 100, 1)
    return {"source": m["source"], "now": now, "series": series,
            "perf": {str(h): _clean(perf(pct, real, h, rng)) for h in HORIZONS}}


def _clean(x):
    if isinstance(x, float):
        return _r(x)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def overview() -> dict:
    """장기 투자 탭 응답 — 기법 id × 지수."""
    rng = np.random.default_rng(SEED)
    built = {"spx": us_measures(us_inputs()), "kospi": kr_measures(kr_inputs())}
    out: dict = {"horizons": list(HORIZONS), "buckets": BUCKETS, "draws": DRAWS, "min_ind": MIN_IND,
                 "min_hist": MIN_HIST, "lag_q": LAG_Q, "lag_e": LAG_E,
                 "indices": [{"id": ix.id, "label": ix.label} for ix in INDICES], "measures": {}}
    for mid, meta in MEASURES.items():
        out["measures"][mid] = {**meta, "by": {}}
        for ix in INDICES:
            real, ms = built[ix.id]
            out["measures"][mid]["by"][ix.id] = describe(mid, ms[mid], real, rng)
    return out
