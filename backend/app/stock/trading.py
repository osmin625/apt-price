"""단기 매매 탭의 실제 지수 계산 — 종가로 잴 수 있는 기법 12개를 S&P 500·KOSPI 에 그대로 돌린다.

기법의 글·합성 예시는 `frontend/src/stock/techniques/short.js` 에 있다. 여기는 같은 규칙을 실제 종가에
적용해 (1) 지금 상태, (2) 과거 성적, (3) 실제 사례를 만든다(docs/stock/trading.md '실제 지수에 돌리는 법').

## 신호가 난 다음 날 종가에 체결한다

규칙은 '그날 종가에 산다' 로 적혀 있지만, 그날 종가를 보고 나서야 신호를 알 수 있다. 같은 종가에 체결하면
그 하루치만큼 미래를 본 셈이라 신호 다음 거래일 종가에 사고판다(`FILL`). 편도 비용은 `COST` 다 — 지수
ETF 의 수수료·호가 차이를 어림한 값이고, 사서 들고 있기도 살 때 한 번 낸다.

## 기저율은 아무 날이나 고른 것

신호 뒤 h 거래일 수익률을 '아무 날이나 샀을 때' 와 견준다. 신호가 n 번이면 아무 날 n 개를 뽑아 평균을 내는 것을
`DRAWS` 번 되풀이해 95% 범위를 만든다. 신호 평균이 이 범위 밖이어야 '아무 날보다 낫다(못하다)' 다. 오르는 장에서는
아무 날이나 사도 벌기 때문에, 신호 뒤 평균이 플러스라는 것만으로는 아무것도 말하지 못한다.

같은 쪽 신호가 h 일 안에 또 나면 하나로 센다 — 몰려 난 신호가 한 구간을 여러 번 세면 범위가 실제보다 좁아 보인다.

## 패턴은 정해 둔 규칙으로만 찾는다

사람 눈으로 고르면 지나고 나서 어디서나 보인다. 그래서 꼭대기·바닥을 지그재그(`PIVOT` 만큼 되돌아야 확정)로
정하고, Lo·Mamaysky·Wang(2000, 'Foundations of Technical Analysis')의 정의를 따라 연속한 꼭짓점의 높이 관계로
패턴을 정한다. 꼭짓점은 되돌림이 확인된 날에야 알 수 있으므로 패턴도 그날부터만 쓴다 — 미래를 보지 않는다
(`scripts/verify_short_rules.py` 가 잘라 낸 계열로 다시 돌려 같은 신호가 나는지 본다).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

COST = 0.001        # 편도 0.1%
FILL = 1            # 신호 다음 거래일 종가에 체결
HORIZONS = (20, 60) # 신호 뒤 보는 거래일 — 한 달·석 달 남짓
DRAWS = 2000
MIN_N = 5           # 이보다 적으면 범위를 내지 않는다 — 신호 두세 번의 평균은 우연과 구별되지 않는다
PIVOT = 0.03        # 지그재그 — 3% 되돌아야 꼭대기·바닥이 확정된다
TOL = 0.03          # 'X 와 Y 가 비슷한 높이' 의 허용
# 둘은 패턴이 몇 번 잡히나만 보고 골랐다(성적은 보지 않았다 — 성적으로 고르면 과거에 맞춘 규칙이 된다).
# 2026-11-12 잰 값: 5%·1.5%(LMW 2000 의 허용)면 S&P 500 10년에 박스 0·컵 0·깃발 0, 3%·3% 면 박스 2·깃발 1 · KOSPI 박스 39.
# 그래도 S&P 500 의 컵앤핸들은 0 이다 — 그럴 때는 합성 예시가 남는다(docs/stock/trading.md '예시와 실제').
POLE = 2 * PIVOT    # 깃대 — 30거래일 안에 이만큼 넘게 오른다
SEED = 20261112


# ── 지표 — frontend/src/stock/techniques/synth.js 와 같은 정의 ─────────────────

def sma(x: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x: list[float | None], n: int) -> list[float | None]:
    k = 2 / (n + 1)
    out: list[float | None] = [None] * len(x)
    e = None
    for i, v in enumerate(x):
        if v is None:
            continue
        e = v if e is None else v * k + e * (1 - k)
        out[i] = e
    return out


def stdev(x: list[float], n: int) -> list[float | None]:
    """모표준편차(n 으로 나눈다) — 볼린저가 쓴 정의."""
    m = sma(x, n)
    out: list[float | None] = [None] * len(x)
    for i, mi in enumerate(m):
        if mi is not None:
            out[i] = math.sqrt(sum((x[j] - mi) ** 2 for j in range(i - n + 1, i + 1)) / n)
    return out


def rsi(x: list[float], n: int = 14) -> list[float | None]:
    """와일더 평활(1/n). 처음 n 일은 단순 평균으로 시작한다."""
    out: list[float | None] = [None] * len(x)
    up = dn = 0.0
    for i in range(1, len(x)):
        d = x[i] - x[i - 1]
        u, w = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            up += u / n
            dn += w / n
        else:
            up = (up * (n - 1) + u) / n
            dn = (dn * (n - 1) + w) / n
        if i >= n:
            out[i] = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    return out


def macd(x: list[float], fast: int = 12, slow: int = 26, sig: int = 9):
    f, s = ema(x, fast), ema(x, slow)
    line = [f[i] - s[i] if i >= slow - 1 else None for i in range(len(x))]
    signal = ema(line, sig)
    hist = [None if a is None or b is None else a - b for a, b in zip(line, signal)]
    return line, signal, hist


def channel(x: list[float], n: int) -> tuple[list[float | None], list[float | None]]:
    """지난 n 일(오늘 제외)의 최고·최저 — 돌파는 어제까지의 고점을 오늘 넘는 것이다."""
    hi: list[float | None] = [None] * len(x)
    lo: list[float | None] = [None] * len(x)
    for i in range(n, len(x)):
        w = x[i - n:i]
        hi[i], lo[i] = max(w), min(w)
    return hi, lo


def crossed_up(a, b, i: int) -> bool:
    """i-1 에 b 이하였다가 i 에 b 를 넘었나. b 는 수 하나 또는 계열."""
    bp = b if isinstance(b, (int, float)) else b[i - 1]
    bi = b if isinstance(b, (int, float)) else b[i]
    if None in (a[i - 1], a[i], bp, bi):
        return False
    return a[i - 1] <= bp and a[i] > bi


def crossed_down(a, b, i: int) -> bool:
    bp = b if isinstance(b, (int, float)) else b[i - 1]
    bi = b if isinstance(b, (int, float)) else b[i]
    if None in (a[i - 1], a[i], bp, bi):
        return False
    return a[i - 1] >= bp and a[i] < bi


def trade(n: int, enter, exit_) -> list[tuple[int, int]]:
    """규칙대로 들어가고 나온 신호 날 [(i, +1|-1)] — 들고 있지 않을 때만 진입, 들고 있을 때만 청산(short.js `trade`)."""
    marks = []
    pos = False
    for i in range(1, n):
        if not pos and enter(i):
            marks.append((i, 1))
            pos = True
        elif pos and exit_(i):
            marks.append((i, -1))
            pos = False
    return marks


# ── 꼭대기·바닥 ─────────────────────────────────────────────

@dataclass(frozen=True)
class Pivot:
    i: int        # 꼭짓점의 날
    v: float
    top: bool
    seen: int     # 확정된 날 — 그 날 종가가 꼭짓점에서 PIVOT 만큼 되돌았다


def zigzag(close: list[float], th: float | None = None) -> list[Pivot]:
    """되돌림 th 로 확정하는 꼭대기·바닥. 꼭대기와 바닥이 번갈아 나온다. t 까지의 종가만으로 t 의 확정이 정해진다."""
    th = PIVOT if th is None else th
    out: list[Pivot] = []
    if not close:
        return out
    hi = lo = 0
    trend = 0  # +1 오르는 중(꼭대기를 찾는다) · −1 내리는 중 · 0 아직 모름
    for t in range(1, len(close)):
        c = close[t]
        if trend == 0:
            if c > close[hi]:
                hi = t
            if c < close[lo]:
                lo = t
            if c <= close[hi] * (1 - th):
                out.append(Pivot(hi, close[hi], True, t))
                trend, lo = -1, t
            elif c >= close[lo] * (1 + th):
                out.append(Pivot(lo, close[lo], False, t))
                trend, hi = 1, t
        elif trend > 0:
            if c > close[hi]:
                hi = t
            elif c <= close[hi] * (1 - th):
                out.append(Pivot(hi, close[hi], True, t))
                trend, lo = -1, t
        else:
            if c < close[lo]:
                lo = t
            elif c >= close[lo] * (1 + th):
                out.append(Pivot(lo, close[lo], False, t))
                trend, hi = 1, t
    return out


def _near(a: float, b: float, tol: float | None = None) -> bool:
    return abs(a - b) <= (TOL if tol is None else tol) * (a + b) / 2


def _at(p: Pivot, q: Pivot, t: int) -> float:
    """p·q 를 잇는 선의 t 날 값."""
    return p.v + (q.v - p.v) * (t - p.i) / (q.i - p.i)


@dataclass
class Shape:
    """패턴 하나 — 꼭짓점이 다 확정된 날(`seen`)부터 다음 꼭짓점이 확정되기 전까지 돌파를 기다린다."""
    kind: str
    pivots: list[Pivot]
    dir: int                                       # 돌파하면 낼 신호 쪽(+1 오름 · −1 내림). 0 이면 양쪽
    up: object = None                              # t → 위로 넘으면 +1 인 선(없으면 None)
    down: object = None                            # t → 아래로 깨면 −1 인 선
    names: tuple[str, ...] = ()
    lines: list[tuple[int, int]] = field(default_factory=list)   # 꼭짓점 번호 쌍 — 그림의 선
    until: int | None = None                       # 이 날까지만 기다린다(깃발·손잡이의 길이 제한)


def _hs(p: list[Pivot]) -> Shape | None:
    """헤드앤숄더(꼭대기 셋, 가운데가 가장 높다) · 역헤드앤숄더(바닥 셋, 가운데가 가장 낮다)."""
    if len(p) < 5:
        return None
    e1, e2, e3, e4, e5 = p[-5:]
    if e5.top and e3.v > e1.v and e3.v > e5.v and _near(e1.v, e5.v) and _near(e2.v, e4.v):
        return Shape("헤드앤숄더", p[-5:], -1, down=lambda t: _at(e2, e4, t),
                     names=("왼쪽 어깨", "", "머리", "", "오른쪽 어깨"), lines=[(1, 3)])
    if not e5.top and e3.v < e1.v and e3.v < e5.v and _near(e1.v, e5.v) and _near(e2.v, e4.v):
        return Shape("역헤드앤숄더", p[-5:], 1, up=lambda t: _at(e2, e4, t),
                     names=("왼쪽 어깨", "", "머리", "", "오른쪽 어깨"), lines=[(1, 3)])
    return None


def _double(p: list[Pivot]) -> Shape | None:
    """이중 바닥·천장 — 같은 높이의 바닥(꼭대기) 둘이 한 달 넘게 떨어져 있다. 가운데 꼭짓점을 넘으면 신호."""
    if len(p) < 3:
        return None
    e1, e2, e3 = p[-3:]
    if not _near(e1.v, e3.v) or e3.i - e1.i < 20:
        return None
    if not e3.top:
        return Shape("이중 바닥", p[-3:], 1, up=lambda t: e2.v, names=("첫 바닥", "", "둘째 바닥"))
    return Shape("이중 천장", p[-3:], -1, down=lambda t: e2.v, names=("첫 천장", "", "둘째 천장"))


def _triangle(p: list[Pivot]) -> Shape | None:
    """대칭 삼각 — 꼭대기는 낮아지고 바닥은 높아진다(꼭짓점 다섯). 어느 쪽으로든 선을 벗어나면 그쪽 신호."""
    if len(p) < 5:
        return None
    q = p[-5:]
    tops = [x for x in q if x.top]
    bots = [x for x in q if not x.top]
    if not (all(a.v > b.v for a, b in zip(tops, tops[1:])) and all(a.v < b.v for a, b in zip(bots, bots[1:]))):
        return None
    t1, t2 = tops[-2:]
    b1, b2 = bots[-2:]
    k = lambda x: q.index(x)  # noqa: E731
    return Shape("삼각 수렴", q, 0, up=lambda t: _at(t1, t2, t), down=lambda t: _at(b1, b2, t),
                 lines=[(k(t1), k(t2)), (k(b1), k(b2))])


def _rectangle(p: list[Pivot]) -> Shape | None:
    """박스(지지·저항) — 꼭대기끼리, 바닥끼리 같은 높이(꼭짓점 다섯). 박스를 벗어나는 쪽이 신호."""
    if len(p) < 5:
        return None
    q = p[-5:]
    tops = [x.v for x in q if x.top]
    bots = [x.v for x in q if not x.top]
    if not (_near(max(tops), min(tops)) and _near(max(bots), min(bots))):
        return None
    hi, lo = max(tops), min(bots)
    return Shape("박스", q, 0, up=lambda t: hi, down=lambda t: lo)


def _flag(p: list[Pivot]) -> Shape | None:
    """깃발 — 짧은 큰 상승(깃대, 30거래일 안에 POLE 넘게) 뒤 깃대의 절반 안쪽 되돌림. 깃대 끝을 넘으면 신호.
    쉬는 구간이 깃대보다 길어지면 패턴이 아니다(short.js 규칙 셋째)."""
    if len(p) < 3:
        return None
    e1, e2, e3 = p[-3:]
    if e3.top or e2.v / e1.v - 1 < POLE or e2.i - e1.i > 30:
        return None
    if e2.v - e3.v > (e2.v - e1.v) / 2:
        return None
    return Shape("깃발", p[-3:], 1, up=lambda t: e2.v, names=("깃대 시작", "깃대 끝", ""),
                 until=e2.i + (e2.i - e1.i))


def _cup(p: list[Pivot]) -> Shape | None:
    """컵앤핸들(오닐) — 12~33% 깊이의 컵이 7주(35거래일) 넘게, 오른쪽 가장자리가 왼쪽과 5% 안,
    손잡이 바닥은 컵의 위쪽 절반. 손잡이 고점(오른쪽 가장자리)을 넘으면 신호. 손잡이는 컵 길이의 절반 안."""
    if len(p) < 4:
        return None
    e1, e2, e3, e4 = p[-4:]
    if not e1.top or e4.top:
        return None
    depth = 1 - e2.v / e1.v
    if not (0.12 <= depth <= 0.33 and e3.i - e1.i >= 35 and _near(e1.v, e3.v, 0.05)):
        return None
    if e4.v <= e2.v + (e3.v - e2.v) / 2:
        return None
    return Shape("컵앤핸들", p[-4:], 1, up=lambda t: e3.v, names=("왼쪽 가장자리", "컵 바닥", "오른쪽 가장자리", "손잡이"),
                 until=e3.i + (e3.i - e1.i) // 2)


def scan(close: list[float], finder) -> tuple[list[dict], dict | None]:
    """꼭짓점이 확정될 때마다 패턴을 보고, 다음 꼭짓점이 확정되기 전까지 돌파를 기다린다.

    돌려주는 것: 신호 [{i, dir, shape}] 와, 마지막 날에 아직 기다리는 패턴(형성 중) 하나.
    """
    piv = zigzag(close)
    events: list[dict] = []
    pending = None
    k = 0
    for t in range(len(close)):
        while k < len(piv) and piv[k].seen <= t:
            k += 1
            pending = finder(piv[:k])
        if pending is None:
            continue
        if pending.until is not None and t > pending.until:
            pending = None
            continue
        c = close[t]
        d = 0
        if pending.up is not None and c > pending.up(t):
            d = 1
        elif pending.down is not None and c < pending.down(t):
            d = -1
        if d:
            events.append({"i": t, "dir": d, "shape": pending})
            pending = None
    return events, pending


# ── 기법 ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rule:
    id: str          # short.js 의 id 와 같다
    label: str       # 화면에 '무엇을 돌렸나' 로 나가는 한 줄
    run: object      # close → Result
    kind: str        # 'hold'(진입·청산이 있는 규칙) · 'pattern'(일회성 신호)


@dataclass
class Result:
    marks: list[tuple[int, int]]                     # 신호 날과 방향
    start: int                                       # 규칙이 처음 계산되는 날(앞부분은 지표가 비어 있다)
    overlays: list[dict] = field(default_factory=list)
    panel: dict | None = None
    band: dict | None = None
    now: dict | None = None                          # 지금 지표 값 {label, value, unit}
    shapes: list[dict] = field(default_factory=list) # 패턴 신호(marks 와 같은 순서)
    pending: Shape | None = None


def _ma_cross(c):
    m50, m200 = sma(c, 50), sma(c, 200)
    marks = trade(len(c), lambda i: crossed_up(m50, m200, i), lambda i: crossed_down(m50, m200, i))
    return Result(marks, 200, overlays=[{"label": "50일 평균", "values": m50, "color": "var(--series-1)"},
                                        {"label": "200일 평균", "values": m200, "color": "var(--series-2)"}],
                  now={"label": "50일선이 200일선보다", "value": (m50[-1] / m200[-1] - 1) * 100, "unit": "%"})


def _macd(c):
    line, sig, hist = macd(c)
    marks = trade(len(c), lambda i: crossed_up(line, sig, i), lambda i: crossed_down(line, sig, i))
    return Result(marks, 35, panel={"label": "MACD", "series": [
        {"label": "히스토그램", "values": hist, "bar": True},
        {"label": "MACD 선", "values": line, "color": "var(--series-1)"},
        {"label": "신호선", "values": sig, "color": "var(--series-2)", "dash": True}]},
        now={"label": "MACD − 신호선", "value": hist[-1] / c[-1] * 100, "unit": "% (종가 대비)"})


def _donchian(c):
    hi20, _ = channel(c, 20)
    _, lo10 = channel(c, 10)
    marks = trade(len(c), lambda i: hi20[i] is not None and c[i] > hi20[i],
                  lambda i: lo10[i] is not None and c[i] < lo10[i])
    return Result(marks, 20, band={"hi": hi20, "lo": lo10, "label": "20일 최고 · 10일 최저"},
                  now={"label": "20일 최고가까지", "value": (hi20[-1] / c[-1] - 1) * 100, "unit": "%"})


def _rsi(c):
    r = rsi(c, 14)
    marks = trade(len(c), lambda i: crossed_up(r, 30, i), lambda i: crossed_down(r, 70, i))
    return Result(marks, 15, panel={"label": "RSI(14)", "series": [{"label": "RSI", "values": r, "color": "var(--series-1)"}],
                                    "levels": [30, 70], "range": [0, 100]},
                  now={"label": "RSI(14)", "value": r[-1], "unit": ""})


def _bollinger(c):
    m, s = sma(c, 20), stdev(c, 20)
    up = [None if a is None else a + 2 * b for a, b in zip(m, s)]
    lo = [None if a is None else a - 2 * b for a, b in zip(m, s)]
    marks = trade(len(c), lambda i: lo[i] is not None and c[i] < lo[i], lambda i: m[i] is not None and c[i] > m[i])
    pb = (c[-1] - lo[-1]) / (up[-1] - lo[-1]) * 100 if up[-1] != lo[-1] else 50.0
    return Result(marks, 20, overlays=[{"label": "20일 평균", "values": m, "color": "var(--series-1)"}],
                  band={"hi": up, "lo": lo, "label": "±2 표준편차"},
                  now={"label": "띠 안의 위치(아래 0 · 위 100)", "value": pb, "unit": ""})


def _ma_gap(c):
    m = sma(c, 20)
    gap = [None if a is None else x / a * 100 for x, a in zip(c, m)]
    marks = trade(len(c), lambda i: crossed_up(gap, 95, i), lambda i: crossed_down(gap, 105, i))
    return Result(marks, 20, panel={"label": "20일 이격도", "series": [{"label": "이격도", "values": gap, "color": "var(--series-1)"}],
                                    "levels": [95, 100, 105]},
                  now={"label": "20일 이격도", "value": gap[-1], "unit": ""})


def _pattern(finder):
    def run(c):
        ev, pend = scan(c, finder)
        return Result([(e["i"], e["dir"]) for e in ev], 0, shapes=ev, pending=pend)
    return run


def _sr(c):
    """지지·저항은 박스를 벗어나는 날만 잰다 — 박스 안에서 사고파는 판은 선을 사람이 고르는 몫이 커서 규칙으로 못 박지 않았다."""
    return _pattern(_rectangle)(c)


RULES: tuple[Rule, ...] = (
    Rule("ma-cross", "50일·200일 단순평균 교차", _ma_cross, "hold"),
    Rule("macd", "12·26·9 MACD 선과 신호선 교차", _macd, "hold"),
    Rule("donchian", "20일 최고가 돌파 진입 · 10일 최저가 이탈 청산", _donchian, "hold"),
    Rule("rsi", "RSI(14) 30 위로 올라오면 진입 · 70 아래로 내려오면 청산", _rsi, "hold"),
    Rule("bollinger", "20일 ±2 표준편차 — 아래 띠 밑에서 진입 · 평균 위에서 청산", _bollinger, "hold"),
    Rule("ma-gap", "20일 이격도 95 위로 올라오면 진입 · 105 아래로 내려오면 청산", _ma_gap, "hold"),
    Rule("head-shoulders", f"꼭짓점 다섯 — 가운데가 가장 높고(낮고) 양 어깨·두 골짜기가 {TOL:.0%} 안 · 목선 돌파", _pattern(_hs), "pattern"),
    Rule("double-bottom", f"같은 높이({TOL:.0%} 안) 바닥·천장 둘이 20거래일 넘게 떨어짐 · 가운데 꼭짓점 돌파", _pattern(_double), "pattern"),
    Rule("triangle", "꼭대기는 낮아지고 바닥은 높아지는 꼭짓점 다섯 · 어느 쪽 선이든 벗어나는 쪽", _pattern(_triangle), "pattern"),
    Rule("flag", f"30거래일 안 {POLE:.0%} 넘는 깃대 · 절반 안쪽 되돌림 · 깃대 끝 돌파(깃대 길이 안)", _pattern(_flag), "pattern"),
    Rule("cup-handle", "12~33% 깊이·35거래일 넘는 컵 · 위쪽 절반의 손잡이 · 가장자리 돌파", _pattern(_cup), "pattern"),
    Rule("support-resistance", f"꼭대기끼리·바닥끼리 {TOL:.0%} 안인 꼭짓점 다섯(박스) · 박스를 벗어나는 쪽", _sr, "pattern"),
)
BY_ID = {r.id: r for r in RULES}


# ── 성적 ────────────────────────────────────────────────────

def _days(a: str, b: str) -> int:
    d = lambda s: date(int(s[:4]), int(s[4:6]), int(s[6:]))  # noqa: E731
    return (d(b) - d(a)).days


def strategy(close: list[float], dates: list[str], marks, start: int, cost: float = COST) -> dict:
    """들고 있는 동안만 지수 수익을 받는다(쉬는 동안 0). 신호 다음 날 종가에 체결, 체결마다 편도 비용."""
    n = len(close)
    eq = bh = 1.0
    peak_eq = peak_bh = 1.0
    mdd_eq = mdd_bh = 0.0
    fills = {i + FILL: d for i, d in marks if i + FILL < n}
    pos = False
    held = 0
    trades: list[dict] = []
    entry = None
    s = start + FILL
    bh *= 1 - cost
    for t in range(s, n):
        if t > s:
            r = close[t] / close[t - 1]
            bh *= r
            if pos:
                eq *= r
                held += 1
        d = fills.get(t)
        if d == 1 and not pos:
            eq *= 1 - cost
            pos, entry = True, t
        elif d == -1 and pos:
            eq *= 1 - cost
            pos = False
            trades.append({"in": entry, "out": t, "ret": close[t] / close[entry] * (1 - cost) ** 2 - 1})
        peak_eq, peak_bh = max(peak_eq, eq), max(peak_bh, bh)
        mdd_eq, mdd_bh = min(mdd_eq, eq / peak_eq - 1), min(mdd_bh, bh / peak_bh - 1)
    yrs = _days(dates[s], dates[-1]) / 365.25
    cagr = lambda x: (x ** (1 / yrs) - 1) * 100 if yrs > 0 else None  # noqa: E731
    span = n - 1 - s
    return {
        "from": dates[s], "to": dates[-1],
        "cagr": cagr(eq), "bh_cagr": cagr(bh), "total": (eq - 1) * 100, "bh_total": (bh - 1) * 100,
        "mdd": mdd_eq * 100, "bh_mdd": mdd_bh * 100,
        "exposure": held / span * 100 if span else None,
        "trades": len(trades),
        "win": sum(t["ret"] > 0 for t in trades) / len(trades) * 100 if trades else None,
        "avg_trade": sum(t["ret"] for t in trades) / len(trades) * 100 if trades else None,
        "avg_hold": sum(t["out"] - t["in"] for t in trades) / len(trades) if trades else None,
        "open": pos,
    }


def forward(close: list[float], i: int, h: int, cost: float = COST) -> float | None:
    """i 날 신호 → 다음 날 종가에 사서 h 거래일 뒤 종가에 판 수익률(왕복 비용 뺌)."""
    a, b = i + FILL, i + FILL + h
    if b >= len(close):
        return None
    return close[b] / close[a] * (1 - cost) ** 2 - 1


def thin(marks, h: int, d: int) -> list[int]:
    """d 쪽 신호 중 앞서 센 같은 쪽 신호에서 h 거래일 안에 난 것을 뺀다."""
    out: list[int] = []
    for i, dd in marks:
        if dd == d and (not out or i - out[-1] >= h):
            out.append(i)
    return out


def signal_lens(close: list[float], marks, start: int, h: int, d: int, rng: np.random.Generator) -> dict:
    """d 쪽 신호 뒤 h 거래일 수익률을 아무 날이나 고른 것과 견준다."""
    base = np.array([r for i in range(start, len(close)) if (r := forward(close, i, h)) is not None])
    ev = [r for i in thin(marks, h, d) if i >= start and (r := forward(close, i, h)) is not None]
    n = len(ev)
    out = {"n": n, "base_mean": float(base.mean() * 100), "base_hit": float((base > 0).mean() * 100)}
    if not n:
        return out
    mean = float(np.mean(ev))
    out |= {"mean": mean * 100, "hit": sum(r > 0 for r in ev) / n * 100}
    if n >= MIN_N:
        draws = base[rng.integers(0, len(base), size=(DRAWS, n))].mean(axis=1)
        lo, hi = np.percentile(draws, [2.5, 97.5])
        out |= {"lo": float(lo * 100), "hi": float(hi * 100),
                "verdict": "above" if mean > hi else "below" if mean < lo else "inside"}
    return out


# ── 응답 ────────────────────────────────────────────────────

BEFORE, AFTER = 120, 60  # 실제 사례 그림 — 신호 앞 120 · 뒤 60 거래일(패턴은 첫 꼭짓점 조금 앞부터)


def _r(v, k=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, k)


def _cut(vs, a: int, b: int, k: int = 2):
    return [_r(v, k) for v in vs[a:b]]


def example(rule: Rule, res: Result, close: list[float], dates: list[str]) -> dict | None:
    """실제 사례 하나 — 뒤 60 거래일이 다 지난 가장 최근 신호. 고르지 않고 규칙으로 정한다(가장 그럴듯한 것을 고르면 성적이 좋아 보인다)."""
    if not res.marks:
        return None
    n = len(close)
    done = [k for k, (i, _) in enumerate(res.marks) if i + FILL + AFTER < n]
    k = done[-1] if done else len(res.marks) - 1
    i, d = res.marks[k]
    first = i - BEFORE
    sh = res.shapes[k]["shape"] if res.shapes else None
    if sh:
        # 패턴은 그 모양이 그림의 주인공이다 — 앞 120일을 다 깔면 몇 주짜리 모양이 점처럼 작아진다.
        p0 = sh.pivots[0].i
        first = p0 - max(20, (i - p0) // 2)
    a, b = max(0, first), min(n, i + AFTER + 1)
    spec: dict = {
        "close": _cut(close, a, b), "first": dates[a], "last": dates[b - 1],
        "at": dates[i], "dir": d, "after": _r(forward(close, i, AFTER) * 100, 1) if forward(close, i, AFTER) is not None else None,
        "marks": [{"i": j - a, "dir": dd} for j, dd in res.marks if a <= j < b],
    }
    if res.overlays:
        spec["overlays"] = [{**o, "values": _cut(o["values"], a, b)} for o in res.overlays]
    if res.band:
        spec["band"] = {"label": res.band["label"], "hi": _cut(res.band["hi"], a, b), "lo": _cut(res.band["lo"], a, b)}
    if res.panel:
        spec["panel"] = {**res.panel, "series": [{**s, "values": _cut(s["values"], a, b, 3)} for s in res.panel["series"]]}
    if sh:
        spec["kind"] = sh.kind
        spec["points"] = [{"i": p.i - a, "label": nm, "below": not p.top}
                          for p, nm in zip(sh.pivots, sh.names or [""] * len(sh.pivots))]
        lines = []
        for x, y in sh.lines:
            p, q = sh.pivots[x], sh.pivots[y]
            lines.append({"i0": p.i - a, "v0": _r(p.v), "i1": i - a, "v1": _r(_at(p, q, i))})
        for f, lab in ((sh.up, "돌파선"), (sh.down, "이탈선")):
            if f is not None and not sh.lines:
                lines.append({"i0": sh.pivots[0].i - a, "v0": _r(f(sh.pivots[0].i)), "i1": i - a, "v1": _r(f(i)), "label": lab})
        spec["lines"] = lines
    return spec


def now_of(rule: Rule, res: Result, close: list[float], dates: list[str]) -> dict:
    n = len(close)
    last = res.marks[-1] if res.marks else None
    out: dict = {"day": dates[-1], "close": _r(close[-1])}
    if last:
        i, d = last
        out["last"] = {"date": dates[i], "dir": d, "ago": n - 1 - i,
                       **({"kind": res.shapes[-1]["shape"].kind} if res.shapes else {})}
    if rule.kind == "hold":
        holding = bool(last and last[1] == 1)
        out["holding"] = holding
        # 신호가 마지막 날이면 체결은 아직이다 — 다음 거래일에 들어간다.
        out["fill_pending"] = bool(last and last[0] + FILL >= n)
    if res.now:
        out["value"] = {**res.now, "value": _r(res.now["value"])}
    if res.pending:
        p = res.pending
        t = n - 1
        out["forming"] = {"kind": p.kind, "since": dates[p.pivots[-1].seen],
                          "up": _r(p.up(t)) if p.up else None, "down": _r(p.down(t)) if p.down else None}
    return out


def evaluate(rule: Rule, close: list[float], dates: list[str], seed: int = SEED) -> dict:
    res = rule.run(close)
    rng = np.random.default_rng(seed)
    lens = {f"{'up' if d > 0 else 'down'}{h}": signal_lens(close, res.marks, res.start, h, d, rng)
            for d in (1, -1) for h in HORIZONS}
    return {
        "now": now_of(rule, res, close, dates),
        "signals": lens,
        "count": {"up": sum(d > 0 for _, d in res.marks), "down": sum(d < 0 for _, d in res.marks)},
        "strategy": strategy(close, dates, res.marks, res.start) if rule.kind == "hold" else None,
        "example": example(rule, res, close, dates),
    }


def _clean(x):
    """응답의 실수를 줄인다 — 화면은 소수 둘째 자리까지만 쓴다."""
    if isinstance(x, float):
        return _r(x)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def overview(series: list[tuple[object, list[tuple[str, float]]]]) -> dict:
    """series: [(Index, 일봉)] — 미국이 먼저(indices.INDICES 순서)."""
    out = {"cost": COST * 100, "fill": FILL, "horizons": list(HORIZONS), "draws": DRAWS, "min_n": MIN_N,
           "pivot": PIVOT * 100, "tol": TOL * 100, "after": AFTER,
           "indices": [], "rules": {r.id: {"label": r.label, "kind": r.kind, "by": {}} for r in RULES}}
    for ix, daily in series:
        if len(daily) < 300:
            continue
        dates = [d for d, _ in daily]
        close = [c for _, c in daily]
        out["indices"].append({"id": ix.id, "label": ix.label, "first": dates[0], "last": dates[-1], "n": len(close)})
        for r in RULES:
            out["rules"][r.id]["by"][ix.id] = evaluate(r, close, dates)
    return _clean(out)
