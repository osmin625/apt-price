"""종목의 재무는 실적 발표 때 알려진 것으로 본다(`app/stock/earnings.py`) — 발표일 짝짓기·발표 때 알던 값·시장 계열이 정의대로인지.

## 왜

발표일을 잘못 짝지으면 오류 없이 하루~몇 주 이른(미래를 본) 기법 값이 나온다(종목 비교, `app/stock/pick.py`). 분할 전 주식 수에 분할 뒤 주가를 곱해도
그림만 이상할 뿐 아무것도 멈추지 않는다. 그래서

1. **짝짓기** — 분기 끝 뒤·제출일 이하의 **마지막** 2.02 를 고른다(테슬라처럼 인도 대수 8-K 가 먼저 있어도). 맞는
   8-K 가 없으면 제출일 그대로(`estimated`). 고쳐 낸 제출(10-K/A)은 당기지 않는다.
2. **발표 때 알던 값** — 발표 i 의 내용은 그 뒤에 실린 제출을 흔들어도 그대로다. 발표 i 자신의 제출을 흔들면 달라진다
   (걸리는 것까지). 발표가 그달이고 10-K 가 다음 달이면 그 분기의 12개월 합이 **발표한 날**부터 알려진다.
3. **시장 계열 대조** — SPY 를 받을 때의 대조(`ingest_stock.market_problems`)가 멀쩡한 자료는 통과시키고, 한 달 밀린 자료와
   너무 짧은 자료는 막는다.
4. **실제 자료** — stock.db 가 있으면: 종목마다 발표가 있고, 발표일을 못 찾은 분기가 드물고, 발표 사이 시가총액 변화가
   수정 종가 변화와 맞는다(분할 전후 주식 수·주가 단위가 섞이면 20배씩 튄다), 발표 때 베타가 60달로 잰 것이다.
"""

from __future__ import annotations

NEEDS_DB = False  # 1~3 은 합성, 4 는 DB 가 있을 때만

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import earnings as EA  # noqa: E402
from app.stock import fundamentals as FU  # noqa: E402
from app.stock.companies import COMPANIES  # noqa: E402
from scripts.ingest_stock import market_problems  # noqa: E402
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {what}")
    if not ok:
        fails.append(what)


def row(concept, start, end, value, filed, form="10-Q"):
    return {"concept": concept, "start": start, "end": end, "value": float(value), "form": form, "filed": filed}


def rel(d, t="20:01:00"):
    return {"date": d, "accepted": f"{d[:4]}-{d[4:6]}-{d[6:]}T{t}.000Z", "accession": d, "items": "2.02,9.01"}


def synth() -> tuple[list[dict], list[dict]]:
    """두 해 여덟 분기. 분기마다 매출·순이익 3개월 값, 연말은 10-K 의 1년 값(4분기는 차로). 발표는 제출 며칠 전.

    2025 3분기는 분기 끝 이틀 뒤에 인도 대수 같은 2.02 가 먼저 있다. 2024 2분기는 발표 8-K 가 없다.
    2025 1분기 10-Q 는 몇 달 뒤 고쳐 실린다(10-Q/A) — 그 앞에 2025 2분기 발표가 있다.
    """
    rows, rels = [], []
    qs = [("0101", "0331", "0428", "0425"), ("0401", "0630", "0728", "0725"), ("0701", "0930", "1028", "1024")]
    for y in (2024, 2025):
        for k, (s, e, f, r) in enumerate(qs):
            for c, v in (("revenue", 100 + 10 * k + (y - 2024) * 40), ("net_income", 10 + k + (y - 2024) * 4)):
                rows.append(row(c, f"{y}{s}", f"{y}{e}", v, f"{y}{f}"))
            rows.append(row("shares_out", "", f"{y}{e}", 1e9, f"{y}{f}"))
            if k:  # 10-Q 는 연초부터 누적도 싣는다 — 4분기는 1년 − 9달로만 나온다
                for c, v0 in (("revenue", 100), ("net_income", 10)):
                    tot = sum(v0 + (10 if c == "revenue" else 1) * j + (y - 2024) * (40 if c == "revenue" else 4) for j in range(k + 1))
                    rows.append(row(c, f"{y}0101", f"{y}{e}", tot, f"{y}{f}"))
            if not (y == 2024 and k == 1):
                rels.append(rel(f"{y}{r}"))
        for c, v in (("revenue", 4 * 100 + 60 + (y - 2024) * 160), ("net_income", 46 + (y - 2024) * 16)):
            rows.append(row(c, f"{y}0101", f"{y}1231", v, f"{y + 1}0203", "10-K"))
        rows.append(row("shares_out", "", f"{y}1231", 1e9, f"{y + 1}0203", "10-K"))
        rels.append(rel(f"{y + 1}0130"))
    rels.append(rel("20251002", "13:04:00"))                      # 인도 대수 — 실적이 아니다
    rows.append(row("revenue", "20250101", "20250331", 999, "20250801", "10-Q/A"))
    return rows, rels


def matching() -> None:
    print("1. 발표일 짝짓기")
    rows, rels = synth()
    items = EA.releases(rows, rels)
    by_end = {o["end"]: o for o in items if not o.get("pending")}
    check(by_end["20250930"]["date"] == "20251024", f"인도 대수 8-K 가 먼저 있어도 마지막 2.02(10-24) — {by_end['20250930']['date']}")
    check(by_end["20240630"]["estimated"] and by_end["20240630"]["date"] == "20240728",
          "발표 8-K 가 없으면 제출일 그대로, estimated")
    check(by_end["20241231"]["date"] == "20250130" and by_end["20241231"]["form"] == "10-K", "연간 보고서도 발표일로(1-30)")
    kr = EA.known_rows(rows, rels)
    amended = [r for r in kr if r["form"] == "10-Q/A"]
    check(amended and all(r["filed"] == r["doc_filed"] == "20250801" for r in amended),
          "고쳐 낸 제출은 그 앞의 다음 분기 발표(07-25)로 당기지 않는다")
    check(len(items) == len(by_end), "모든 분기에 내용이 있으면 '내용 대기' 가 없다")
    rels2 = rels + [rel("20260424")]
    items2 = EA.releases(rows, rels2)
    check(items2[-1].get("pending") and items2[-1]["date"] == "20260424", "10-Q 가 아직이면 마지막 발표는 내용 대기")
    q = by_end["20241231"]["quarter"]
    check(q["revenue"] == 4 * 100 + 60 - (100 + 110 + 120) and q["net_income"] == 46 - 33, f"4분기 = 1년 − 9달 ({q})")
    y = by_end["20251231"]["yoy"]["revenue"]
    check(y is not None and abs(y - ((620 - 450) / 130 - 1) * 100) < 0.1, f"1년 전 같은 분기 대비 {y}%")
    check(EA._session("2026-10-28T20:01:33.000Z") == "장 뒤" and EA._session("2026-11-10T12:01:56.000Z") == "장 전",
          "접수 시각으로 장 전·장 뒤")


def lookahead() -> None:
    print("2. 발표 때 알던 값만")
    rows, rels = synth()
    base = {o["end"]: o for o in EA.releases(rows, rels) if not o.get("pending")}
    target = base["20250630"]
    # 그 뒤에 실린 제출(3분기 10-Q 이후)을 모두 흔든다
    r = random.Random(3)
    later = [{**x, "value": x["value"] * r.uniform(0.3, 3)} if x["filed"] > target["doc_filed"] else x for x in rows]
    got = {o["end"]: o for o in EA.releases(later, rels) if not o.get("pending")}["20250630"]
    check(got["quarter"] == target["quarter"] and got["ttm"] == target["ttm"], "뒤에 실린 제출을 흔들어도 그 발표의 내용이 같다")
    own = [{**x, "value": x["value"] * 2} if x["filed"] == target["doc_filed"] else x for x in rows]
    got = {o["end"]: o for o in EA.releases(own, rels) if not o.get("pending")}["20250630"]
    check(got["quarter"] != target["quarter"], "그 발표 자신의 제출을 흔들면 달라진다(걸리는 것까지)")

    # 2025 4분기는 2026-01-30 발표, 10-K 는 2026-02-03 — 그 분기의 12개월 합은 1월 말에 알려져 있어야 한다
    kr = EA.known_rows(rows, rels)
    t_rel = dict(FU.ttm(kr, "revenue", as_of="20260131", first=True))
    t_doc = dict(FU.ttm(rows, "revenue", as_of="20260131", first=True))
    t_pre = dict(FU.ttm(kr, "revenue", as_of="20260129", first=True))
    check("20251231" in t_rel and "20251231" not in t_pre, "발표한 날(2026-01-30)부터 그 분기의 12개월 합이 알려진다")
    check("20251231" not in t_doc, "제출일 기준이면 그때(2026-01-31)는 아직 모른다 — 당긴 효과가 실제로 있다")


def market() -> None:
    print("3. 시장 계열(SPY) 대조")
    r = random.Random(5)
    months = []
    y, m = 2014, 1
    while len(months) < 150:
        months.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    lv = [100.0]
    for _ in months[1:]:
        lv.append(lv[-1] * (1 + r.gauss(0.007, 0.04)))
    spx = [(f"{mm}28", v) for mm, v in zip(months, lv)]
    spy = [(mm, v / 10, v / 10 * (1 + 0.0016 * k)) for k, (mm, v) in enumerate(zip(months, lv))]  # 배당 달 0.16%
    check(market_problems(spy, spx) == [], "배당만큼 다른 SPY 는 통과")
    shifted = [(mm, c, a) for (mm, _, _), (_, c, a) in zip(spy[1:], spy)]   # 한 달 밀림
    check(bool(market_problems(shifted, spx)), "한 달 밀린 SPY 는 막는다")
    check(bool(market_problems(spy[:100], spx)), "120달이 안 되면 막는다")


def real_data() -> None:
    print("4. 실제 자료")
    from app.stock import store

    try:
        spy = dict(store.monthly(*EA.MARKET))
    except store.StockMissing:
        print("  [--] stock.db 가 없어 건너뜀(CI) — 1~4 는 위에서 돌았다")
        return
    if not spy:
        check(False, f"시장 {EA.MARKET[1]} 월봉이 없다 — python -m scripts.ingest_stock")
        return
    for co in COMPANIES:
        items = [o for o in EA.of_company(co, spy) if not o.get("pending")]
        if not items:
            check(False, f"{co.label} 발표가 없다 — python -m scripts.ingest_stock")
            continue
        est = sum(o["estimated"] for o in items)
        check(est <= max(1, len(items) // 10), f"{co.label} 발표일을 못 찾은 분기 {est}/{len(items)}")
        ok = [o for o in items if o["shares"] and o["close"]]
        ratios = [(b["close"] * b["shares"]["value"] / (a["close"] * a["shares"]["value"])) / (b["adj"] / a["adj"])
                  for a, b in zip(ok, ok[1:])]
        lo, hi = min(ratios), max(ratios)
        # 주식 수가 한 분기에 크게 느는 회사(디웨이브 유상증자 1.28배)까지 덮고, 분할 단위가 섞인 것(2배 이상)은 걸린다
        check(0.75 <= lo and hi <= 1.5, f"{co.label} 발표 사이 시가총액 ÷ 수정 종가 변화 {lo:.2f}~{hi:.2f}")
        # 시장·종목 월봉이 둘 다 60달 넘게 쌓인 뒤의 발표는 베타를 60달로 잰다 — 짧은 창의 베타는 크게 흔들린다(earnings.py 머리말)
        first = max(min(spy), min(m for m, _ in store.monthly(co.market, co.symbol)))
        enough = f"{int(first[:4]) + 5}{first[4:]}"
        short = [o["date"] for o in items if o["date"][:6] > enough and (not o["beta"] or o["beta"]["months"] < EA.BETA_MONTHS)]
        check(not short, f"{co.label} 월봉이 5년 넘게 쌓인 뒤 발표의 베타가 {EA.BETA_MONTHS}달 — 모자란 발표 {short[:3]}")


def main() -> int:
    matching()
    lookahead()
    market()
    real_data()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
