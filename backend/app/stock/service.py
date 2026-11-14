"""지수 분석 탭의 응답 — 경제지표의 영향(`effects`)과, 지금 구간 예측·그 과거 성적을 같이 낸다.

영향은 `effects.py`, 지표 목록은 `indicators.py` 가 정한다. 아래는 구간 예측 쪽의 설명이다.

예측만 내면 '얼마나 믿을 만한가' 를 화면이 말할 수 없다. 그래서 응답 하나에 (1) 지금 기점의
구간, (2) 같은 후보를 같은 기점들에서 잰 백테스트 점수, (3) 기준선 대비 DM 검정을 같이 싣는다.
판정 문장은 만들지 않는다 — 화면이 숫자로 보여 주고, 읽는 법은 Hint 에 둔다.
"""

from __future__ import annotations

import math

from ..macro import store as macro_store
from . import effects as EF
from . import forecast as F
from . import store
from . import trading as TR
from . import techvalue as TV
from . import valuation as VA
from .indicators import BY_ID as INDICATOR, PAIRS, unit_of
from .indices import INDICES, Index

LABELS = {
    "rw": "무작위 보행",
    "mean": "과거 평균",
    "rf": "금리 + 위험 프리미엄",
    "vol": "금리 + 위험 프리미엄 · 변동성 조정",
}


def _pct(x: float) -> float:
    """로그 수익률 → 단순 수익률(%)."""
    return round((math.exp(x) - 1) * 100, 2)


def _pp(x: float | None) -> float | None:
    return None if x is None or math.isnan(x) else round(x * 100, 3)


def _p(x: float | None) -> float | None:
    return None if x is None or math.isnan(x) else round(x, 4)


def series_of(ix: Index) -> tuple[F.Series, list[tuple[str, float]]]:
    daily = store.daily(ix.market, ix.symbol)
    months, close = F.month_end_closes(daily)
    return F.Series(months, close, macro_store.monthly(ix.rf), F.ewma_vol(daily)), daily


def one(ix: Index) -> dict:
    s, daily = series_of(ix)
    base = {"id": ix.id, "label": ix.label, "currency": ix.currency, "source": ix.source,
            "rf_label": ix.rf_label}
    if len(s.months) < F.MIN_TRAIN + max(F.HORIZONS) + 1:
        return {**base, "available": False, "n_days": len(daily)}
    t = len(s.months) - 1
    horizons = []
    for h in F.HORIZONS:
        bt = F.backtest(s, h)
        models = []
        for m in F.MODELS:
            f = F.forecast(s, t, h, m)
            sc = bt["scores"][m]
            models.append({
                "id": m, "label": LABELS[m], "baseline": m == F.BASELINE,
                "now": None if f is None else {"mid": _pct(f[0]), "lo": _pct(f[1]), "hi": _pct(f[2])},
                "n": sc["n"],
                "rmse": _pp(sc.get("rmse")),
                "coverage": None if not sc["n"] else round(sc["coverage"] * 100, 1),
                "width": _pp(sc.get("width")),
                "interval_score": _pp(sc.get("interval_score")),
                "dm_point_p": _p(sc["dm_point"][1]) if sc["n"] else None,
                "dm_point_t": _p(sc["dm_point"][0]) if sc["n"] else None,
                "dm_interval_p": _p(sc["dm_interval"][1]) if sc["n"] else None,
                "dm_interval_t": _p(sc["dm_interval"][0]) if sc["n"] else None,
            })
        # 그림용 — 기점마다 실제 h개월 수익률과 후보별 구간(단순 %).
        path = {
            "origins": bt["origins"],
            "actual": [_pct(r[4]) for r in bt["rows"][F.BASELINE]],
            "bands": {m: [[_pct(r[2]), _pct(r[3])] for r in bt["rows"][m]] for m in F.MODELS},
        }
        horizons.append({"h": h, "models": models, "backtest": path})
    return {
        **base, "available": True,
        "first_day": daily[0][0], "last_day": daily[-1][0],
        "origin": s.months[t],
        "alpha": F.ALPHA, "min_train": F.MIN_TRAIN,
        "horizons": horizons,
        "effects": effects_of(ix, s.close),
    }


def _agree(r: dict | None, expect: int) -> str | None:
    """잰 값이 상식의 방향(`indicators.expect`)과 맞나 — 'yes' · 'no' · 'unclear'(범위가 0 을 넘음).

    판정은 95% 범위로 백엔드가 정한 `verdict` 를 그대로 쓴다. 막대가 상식 쪽이어도 범위가 0 을 넘으면
    'unclear' 다 — 회색 막대를 '상식대로' 라고 부르면 뚜렷하지 않은 것을 확인한 것처럼 읽힌다.
    """
    if not r:
        return None
    if r["verdict"] == "none":
        return "unclear"
    return "yes" if (r["verdict"] == "pos") == (expect > 0) else "no"


def effects_of(ix: Index, close: dict[str, float]) -> dict:
    """{시점: {rows: [지표별 영향], joint: 함께 넣은 값}} — 화면의 단추 셋이 이것을 고른다."""
    ids = PAIRS[ix.id]
    xs = {i: EF.movement(INDICATOR[i].kind, macro_store.monthly(i)) for i in ids}
    out = {}
    for hz in EF.HORIZONS:
        rows = []
        for i in ids:
            ind = INDICATOR[i]
            r = EF.one(xs[i], close, hz, ind.pub_lag, ind.kind)
            rows.append({"id": i, "label": ind.label, "group": ind.group, "kind": ind.kind,
                         "unit": unit_of(ind), "pub_lag": ind.pub_lag, "source": ind.source,
                         "expect": ind.expect, "why": ind.why,
                         **(r or {"n": 0}), "agree": _agree(r, ind.expect),
                         # 뚜렷하지 않아도 막대가 어느 쪽으로 기울었나 — 화면이 '상식 쪽으로 기움' 으로 적는다.
                         "lean": None if not r else (r["bar"] > 0) == (ind.expect > 0)})
        out[hz] = {"rows": rows,
                   "joint": EF.joint(xs, close, hz, {i: INDICATOR[i].pub_lag for i in ids})}
    return out


def overview() -> dict:
    return {"indices": [one(ix) for ix in INDICES]}


_short: dict[tuple, dict] = {}


def short_term() -> dict:
    """단기 매매 탭 — 종가로 재는 기법을 지수마다 돌린 지금 상태·과거 성적·실제 사례(`trading.py`).

    한 번 계산에 몇 초 걸려 지수의 마지막 날로 기억해 둔다 — 새 종가가 적재되면 키가 바뀐다.
    """
    key = tuple(sorted(store.last_dates().items()))
    got = _short.get(key)
    if got is None:
        # 지역 변수로 들고 돌려준다 — 두 요청이 겹치면 다른 쪽의 clear() 가 방금 넣은 것을 지울 수 있다.
        got = TR.overview([(ix, store.daily(ix.market, ix.symbol)) for ix in INDICES])
        _short.clear()
        _short[key] = got
    return got


_long: dict[tuple, dict] = {}


def long_term() -> dict:
    """장기 투자 탭 — 지수 평가 넷의 지금 상태·과거 성적(`valuation.py`).

    가짜 주가 경로를 수천 개 뽑아 몇 초 걸린다. 지수의 마지막 날과 평가 재료의 마지막 시점으로 기억해 둔다 —
    새 값이 적재되면 키가 바뀐다.
    """
    names = [n for src in VA.NEEDS.values() for n in src]
    key = (tuple(sorted(store.last_dates().items())),
           tuple(sorted(macro_store.last_period(names).items())),
           tuple(sorted(macro_store.last_period(names, "Q").items())))
    got = _long.get(key)
    if got is None:
        got = VA.overview()
        _long.clear()
        _long[key] = got
    return got


def tech_value() -> dict:
    """기술주 가치 탭 — 종목마다 지금 주가·주식 수·지난 12개월 이익·베타·시나리오(`techvalue.py`). 계산이 가벼워
    캐시하지 않는다(종목 넷의 재무 줄을 읽는 데 1초 안쪽)."""
    return TV.overview()

