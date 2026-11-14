"""EDGAR 재무 줄(`store.facts`)에서 분기 값·지난 12개월(TTM) 합·주식 수를 낸다.

## 분기 값이 그대로 오지 않는다

10-Q 는 그 분기(3개월)와 연초부터 누적(6·9개월)을 같이 싣고, 10-K 는 1년치만 싣는다 — **4분기 값은
어디에도 따로 없다.** 그래서 같은 날 시작하는 긴 기간과 짧은 기간의 차로 빈 분기를 만든다(1년 − 9개월 = 4분기,
6개월 − 1분기 = 2분기). 예전 제출에는 3개월 값 없이 누적만 있는 경우도 있어 같은 규칙으로 메운다.

지난 12개월은 **이어진 네 분기**의 합이다. 분기 사이가 7일 넘게 비면(한 분기가 빠졌으면) 내지 않는다 —
세 분기 합을 1년으로 부르면 이익이 25% 작게 나온다.

## 그날 알던 값 · 지금 아는 값

같은 기간이 여러 번 실리고 고쳐지기도 한다. `as_of` 를 주면 그날까지 제출된 것만, `first=True` 면 그 가운데
가장 이른 제출(그때 처음 알려진 값)을 쓴다. 기본은 지금 아는 값(가장 늦은 제출)이다. 지금 화면은 기본을 쓰고,
과거 시점의 계산은 그날 알던 값을 쓴다 — 고쳐진 숫자로 과거를 재면 그때 몰랐던 것을 안 셈이다.
"""

from __future__ import annotations

from datetime import date, timedelta

Q_DAYS = (80, 100)       # 한 분기로 보는 기간 길이(일) — 회계 주차(52·53주)까지 덮는다
GAP_DAYS = 7             # 이어진 분기로 보는 틈


def _d(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _s(d: date) -> str:
    return d.strftime("%Y%m%d")


def _days(start: str, end: str) -> int:
    return (_d(end) - _d(start)).days + 1


def pick(rows: list[dict], concept: str, as_of: str | None = None, first: bool = False) -> dict[tuple[str, str], float]:
    """(시작, 끝) → 값. 같은 기간이 여럿이면 가장 늦은(first 면 가장 이른) 제출."""
    best: dict[tuple[str, str], tuple[str, float]] = {}
    for r in rows:
        if r["concept"] != concept or (as_of and r["filed"] > as_of):
            continue
        k = (r["start"], r["end"])
        cur = best.get(k)
        if cur is None or (r["filed"] < cur[0] if first else r["filed"] > cur[0]):
            best[k] = (r["filed"], r["value"])
    return {k: v for k, (_, v) in best.items()}


def quarters(rows: list[dict], concept: str, as_of: str | None = None, first: bool = False) -> dict[str, tuple[str, float]]:
    """분기 끝 → (분기 시작, 값). 3개월 값이 없으면 같은 날 시작하는 긴 기간의 차로 만든다."""
    vals = {k: v for k, v in pick(rows, concept, as_of, first).items() if k[0]}
    q: dict[str, tuple[str, float]] = {}
    for (s, e), v in vals.items():
        if Q_DAYS[0] <= _days(s, e) <= Q_DAYS[1]:
            q[e] = (s, v)
    # 같은 날 시작하는 (긴, 짧은) 짝 — 긴 것의 끝까지 남은 한 분기
    by_start: dict[str, list[tuple[str, float]]] = {}
    for (s, e), v in vals.items():
        by_start.setdefault(s, []).append((e, v))
    for s, ends in by_start.items():
        ends.sort()
        for (e1, v1), (e2, v2) in zip(ends, ends[1:]):
            gs = _s(_d(e1) + timedelta(days=1))
            if e2 not in q and Q_DAYS[0] <= _days(gs, e2) <= Q_DAYS[1]:
                q[e2] = (gs, v2 - v1)
    return dict(sorted(q.items()))


def ttm(rows: list[dict], concept: str, as_of: str | None = None, first: bool = False) -> list[tuple[str, float]]:
    """(분기 끝, 지난 12개월 합) — 이어진 네 분기가 있을 때만."""
    q = quarters(rows, concept, as_of, first)
    ends = list(q)
    out = []
    for k in range(3, len(ends)):
        win = ends[k - 3:k + 1]
        ok = all(abs((_d(q[b][0]) - _d(a)).days - 1) <= GAP_DAYS for a, b in zip(win, win[1:]))
        if ok:
            out.append((ends[k], sum(q[e][1] for e in win)))
    return out


def shares(rows: list[dict], as_of: str | None = None) -> dict | None:
    """주식 수 — 대차대조표 발행 주식 수가 희석 가중평균보다 오래되지 않았으면 그것, 아니면 희석 가중평균.

    둘은 뜻이 조금 다르다. 테슬라는 2026-09-30 에 발행 39.5억 주, 희석 가중평균 35.4억 주였다 — 아직 가득
    차지 않은 성과 보상 주식이 발행 주식에는 들고 희석 주식에는 안 든다. 시가총액의 관례는 발행 주식 수다.
    """
    out_ = {e: v for (s, e), v in pick(rows, "shares_out", as_of).items() if not s}
    dil = {e: v for (s, e), v in pick(rows, "shares_diluted", as_of).items()
           if s and Q_DAYS[0] <= _days(s, e) <= Q_DAYS[1]}
    a = max(out_) if out_ else None
    b = max(dil) if dil else None
    if a and (not b or a >= b):
        return {"value": out_[a], "end": a, "kind": "발행 주식 수"}
    if b:
        return {"value": dil[b], "end": b, "kind": "희석 가중평균 주식 수"}
    return None
