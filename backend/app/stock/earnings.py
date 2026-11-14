"""실적 발표 — 기술주 가치는 실적 발표 때에만 다시 잰다(2026-11-15 요청).

시장이 한 분기의 실적을 아는 날은 10-Q·10-K 를 낸 날(companyfacts 의 `filed`)이 아니라 그보다 며칠 이른 실적
보도자료(8-K 항목 2.02)의 날이다(`clients/edgar.py` '실적 발표일'). 그래서 재무 줄마다 **알려진 날**을 그 발표일로
당긴다(`known_rows`). 가치 분해·반영 분해·발표 목록이 모두 이 날짜를 쓴다.

## 어느 8-K 가 그 분기의 발표인가

한 제출(10-Q·10-K)의 분기 끝 뒤, 제출일 이하의 항목 2.02 8-K 가운데 **마지막** 것이다. 첫 것이 아니다 — 테슬라는 분기가
끝나면 이틀 뒤 인도 대수를 같은 항목으로 내고(2026-10-02), 실적은 3주 뒤에 낸다(2026-10-21). 그 사이에 맞는 8-K 가 없으면
제출일을 그대로 쓰고 `estimated` 로 적는다. 고쳐 낸 제출(10-K/A 등)은 당기지 않는다 — 그 앞의 다음 분기 발표가 잡혀
고친 숫자를 그때 안 것처럼 된다.

## 발표 때 알던 값만

발표 하나의 내용(분기 매출·영업이익·순이익, 지난 12개월 합, 주식 수)은 그 발표일까지 알려진 값 가운데 **처음 실린
값**이다(`fundamentals` 의 `as_of`·`first`). 그 발표 때의 할인율 재료도 그때 알던 것이다 — 10년 국채는 발표 전달의
월평균(그달 평균은 그달이 끝나야 나온다), 베타는 발표 전달까지의 월봉이다.

보도자료의 숫자는 XBRL 이 아니어서 못 읽는다. 그래서 발표는 됐는데 10-Q 가 아직이면 날짜만 있고 내용은 비어 있다
(`pending`).
"""

from __future__ import annotations

from datetime import date

from ..macro import store as macro_store
from . import fundamentals as FU
from . import store

DOC_FORMS = ("10-Q", "10-K")
DURATION = ("revenue", "operating_income", "net_income")
YOY_DAYS = (355, 375)    # 1년 전 같은 분기로 보는 간격 — 회계 주차(52·53주)까지 덮는다


def _d(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _all_filings(rows: list[dict]) -> list[dict]:
    """10-Q·10-K 제출마다 (제출일, 양식, 분기 끝) — 분기 끝은 그 제출의 기간 값 가운데 가장 늦은 끝. 제출일순."""
    ends: dict[tuple[str, str], str] = {}
    for r in rows:
        if r["form"] in DOC_FORMS and r["start"] and r["concept"] in DURATION:
            k = (r["filed"], r["form"])
            ends[k] = max(ends.get(k, ""), r["end"])
    return [{"filed": f, "form": fm, "end": e} for (f, fm), e in sorted(ends.items())]


def filings(rows: list[dict]) -> list[dict]:
    """분기 끝마다 첫 제출만 — 같은 분기를 다시 낸 제출(고쳐 낸 10-Q 등)은 발표가 아니다."""
    seen: set[str] = set()
    out = []
    for f in _all_filings(rows):
        if f["end"] not in seen:
            seen.add(f["end"])
            out.append(f)
    return out


def release_of(end: str, filed: str, rel_dates: list[str]) -> str | None:
    """분기 끝 뒤, 제출일 이하의 마지막 2.02 8-K 날짜."""
    got = [d for d in rel_dates if end < d <= filed]
    return got[-1] if got else None


def known_rows(rows: list[dict], rels: list[dict]) -> list[dict]:
    """재무 줄의 `filed` 를 시장이 안 날(그 제출의 실적 발표일)로 당긴 사본. 원래 제출일은 `doc_filed`."""
    dates = sorted(r["date"] for r in rels)
    end_of = {(f["filed"], f["form"]): f["end"] for f in _all_filings(rows)}
    moved: dict[tuple[str, str], str] = {}
    out = []
    for r in rows:
        k = (r["filed"], r["form"])
        if k not in moved:
            e = end_of.get(k)
            moved[k] = (release_of(e, r["filed"], dates) if e else None) or r["filed"]
        out.append({**r, "filed": moved[k], "doc_filed": r["filed"]})
    return out


def _yoy(q: dict[str, tuple[str, float]], end: str) -> float | None:
    v = q.get(end)
    if not v:
        return None
    for e, (_, w) in q.items():
        if YOY_DAYS[0] <= (_d(end) - _d(e)).days <= YOY_DAYS[1] and w > 0:
            return round((v[1] / w - 1) * 100, 1)
    return None


def prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    return f"{y - 1}12" if m == 1 else f"{y}{m - 1:02d}"


def releases(rows: list[dict], rels: list[dict], monthly: list[tuple[str, float, float]] | None = None,
             spx: dict[str, float] | None = None, y10: dict[str, float] | None = None) -> list[dict]:
    """분기마다 발표 하나 — 날짜·장 전/뒤·분기 내용·그때의 주가·할인율 재료. 날짜순.

    monthly 는 (YYYYMM, 종가, 수정 종가). 주가·베타·금리를 빼고 내용만 보려면 넘기지 않는다(검증 스크립트).
    """
    from .techvalue import beta  # 순환 import — techvalue 가 이 모듈을 쓴다

    kr = known_rows(rows, rels)
    by_date = {r["date"]: r for r in rels}
    dates = sorted(by_date)
    bars = {m: (c, a) for m, c, a in (monthly or [])}
    adj = [(m, a) for m, _, a in (monthly or [])]
    out = []
    for f in filings(rows):
        rd = release_of(f["end"], f["filed"], dates)
        known = rd or f["filed"]
        item = {"date": known, "estimated": rd is None, "doc_filed": f["filed"], "form": f["form"], "end": f["end"],
                "session": _session(by_date[rd]["accepted"]) if rd else None}
        q = {k: FU.quarters(kr, k, as_of=known, first=True) for k in DURATION}
        item["quarter"] = {k: (q[k][f["end"]][1] if f["end"] in q[k] else None) for k in DURATION}
        item["yoy"] = {k: _yoy(q[k], f["end"]) for k in ("revenue", "operating_income")}
        ttm = {}
        for k in DURATION:
            t = dict(FU.ttm(kr, k, as_of=known, first=True))
            ttm[k] = {"value": t[f["end"]], "end": f["end"]} if f["end"] in t else None
        item["ttm"] = ttm
        item["shares"] = FU.shares(kr, as_of=known)
        if monthly is not None:
            m = known[:6]
            item["month"] = m
            item["close"], item["adj"] = bars.get(m, (None, None))
            item["y10"] = (y10 or {}).get(prev_month(m))
            item["beta"] = beta([(k, a) for k, a in adj if k <= m], spx or {})
        out.append(item)
    # 발표는 됐는데 10-Q 가 아직인 것 — 마지막으로 맞춘 발표 뒤의 2.02 가운데 마지막 것 하나
    last = max((o["date"] for o in out if not o["estimated"]), default="")
    after = [d for d in dates if d > last]
    if out and after:
        out.append({"date": after[-1], "pending": True, "session": _session(by_date[after[-1]]["accepted"]),
                    "month": after[-1][:6]})
    return out


def _session(accepted: str) -> str:
    """접수 시각(UTC)으로 장 전·장 중·장 뒤. 동부 시각은 여름 UTC−4, 겨울 UTC−5 — 둘 다 덮게 넓게 가른다."""
    h = int(accepted[11:13]) + int(accepted[14:16]) / 60
    if h < 13.5:        # 09:30 EDT = 13:30 UTC
        return "장 전"
    if h >= 20:         # 16:00 EDT = 20:00 UTC (겨울엔 21:00 — 20~21 사이 겨울 접수는 장 중이지만 드물다)
        return "장 뒤"
    return "장 중"


def latest(items: list[dict]) -> dict | None:
    """내용이 있는 마지막 발표 — 가치 분해의 기준."""
    got = [o for o in items if not o.get("pending") and o["ttm"].get("net_income")]
    return got[-1] if got else None


def of_company(co, spx: dict[str, float]) -> list[dict]:
    return releases(store.facts(co.symbol), store.releases(co.symbol),
                    store.monthly_bars(co.market, co.symbol), spx, macro_store.monthly("us_10y"))

