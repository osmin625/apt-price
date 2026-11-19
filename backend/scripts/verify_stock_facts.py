"""종목 재무 가공(`app/stock/fundamentals.py`)과 베타(`app/stock/earnings.py`)가 정의대로인지.

## 왜

종목 비교의 장기 기법(`app/stock/pick.py`)은 지난 12개월 합·대차대조표·베타를 재료로 쓴다. 재료는 EDGAR 의 겹치고
고쳐지는 제출에서 만든다 — 틀려도 오류 없이 그럴듯한 값이 나온다. 그래서

1. **지난 12개월** — 누적으로만 보고된 분기·빠진 4분기를 차로 메우고, 고쳐 실린 값은 늦은(또는 처음) 제출을 고르고,
   한 분기가 빠지면 내지 않는다(합성 제출).
2. **걸리는 것까지** — 세 분기를 1년으로 부르는 판, 같은 기간의 이른 제출을 고르는 판은 1 의 비교에 걸린다.
3. **베타** — 시장의 1.5배로 움직이게 만든 합성 종목에서 1.5 근처가 나온다.
4. **실제 자료** — stock.db 가 있으면: 4분기 이 끝나는 지난 12개월 합(순이익·매출·영업현금흐름)이 회사가 낸 연간
   값(10-K)과 모두 같다. 현금흐름은 10-Q 가 누적(6·9개월)으로만 내서 분기를 전부 차로 만든다 — 차가 틀리면 여기서 걸린다.

(이 파일은 2026-11-20 까지 verify_tech_value.py 였다. 기술주 가치 탭을 없애며 가치 분해 대조를 뺐다.)
"""

from __future__ import annotations

NEEDS_DB = False  # 1~3 은 합성, 4 는 DB 가 있을 때만

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import earnings as EA  # noqa: E402
from app.stock import fundamentals as FU  # noqa: E402
from app.stock.companies import BY_ID  # noqa: E402
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {what}")
    if not ok:
        fails.append(what)


def row(concept, start, end, value, filed, form="10-Q"):
    return {"concept": concept, "start": start, "end": end, "value": float(value), "form": form, "filed": filed}


def synth_facts() -> list[dict]:
    """2024 은 3개월 값이 다 있고, 2025 는 누적만(1분기 3개월·6개월·9개월·1년), 2025 1분기는 나중에 고쳐 실린다."""
    r = []
    q24 = [("20240101", "20240331", 10), ("20240401", "20240630", 11), ("20240701", "20240930", 12)]
    for s, e, v in q24:
        r.append(row("net_income", s, e, v, e[:6] + "28"))
    r.append(row("net_income", "20240101", "20241231", 46, "20250210", "10-K"))  # 4분기 = 46 − 33 = 13
    r.append(row("net_income", "20240101", "20240930", 33, "20241028"))
    r.append(row("net_income", "20250101", "20250331", 14, "20250428"))
    r.append(row("net_income", "20250101", "20250331", 15, "20260428"))  # 1년 뒤 비교 칸에 고쳐 실림
    r.append(row("net_income", "20250101", "20250630", 30, "20250728"))  # 2분기 = 30 − 15(또는 14)
    r.append(row("net_income", "20250101", "20250930", 47, "20251028"))  # 3분기 = 47 − 30 = 17
    r.append(row("net_income", "20250101", "20251231", 65, "20260210", "10-K"))  # 4분기 = 65 − 47 = 18
    return r


def ttm_checks() -> None:
    print("1. 지난 12개월")
    rows = synth_facts()
    q = FU.quarters(rows, "net_income")
    check(q.get("20241231") == ("20241001", 13.0), "4분기 = 1년 − 9개월")
    check(q.get("20250630") == ("20250401", 15.0), "누적만 있는 2분기 = 6개월 − 1분기(고쳐진 1분기 15 가 아니라 6개월과 같은 날 시작한 1분기 기간의 값으로)")
    t = dict(FU.ttm(rows, "net_income"))
    check(t.get("20241231") == 46.0, "2024 12개월 = 10-K 연간 값")
    check(t.get("20251231") == 65.0, "2025 12개월 = 10-K 연간 값(고쳐진 1분기는 2분기 차에 흡수된다)")
    early = dict(FU.ttm(rows, "net_income", first=True))
    check(early.get("20250331") == 11 + 12 + 13 + 14, "처음 제출 판은 고쳐지기 전 1분기(14)를 쓴다")
    late = dict(FU.ttm(rows, "net_income"))
    check(late.get("20250331") == early.get("20250331") + 1, "지금 아는 판은 고쳐진 1분기(15)를 쓴다")
    asof = dict(FU.ttm(rows, "net_income", as_of="20251231"))
    check("20251231" not in asof and "20250930" in asof, "as_of 뒤에 제출된 연간 값은 쓰지 않는다")
    gap = [r for r in rows if not (r["start"] == "20240701" and r["end"] == "20240930")
           and not (r["start"] == "20240101" and r["end"] == "20240930")]
    t2 = dict(FU.ttm(gap, "net_income"))
    check("20241231" not in t2 and "20250331" not in t2, "한 분기가 빠지면 그 분기를 품은 12개월은 내지 않는다")


def guard() -> None:
    print("2. 걸리는 것까지")
    rows = synth_facts()
    gap = [r for r in rows if not (r["start"] == "20240701" and r["end"] == "20240930")
           and not (r["start"] == "20240101" and r["end"] == "20240930")]
    q = FU.quarters(gap, "net_income")
    ends = list(q)
    sloppy = {ends[k]: sum(q[e][1] for e in ends[k - 3:k + 1]) for k in range(3, len(ends))}  # 이어졌는지 안 봄
    leaked = set(sloppy) - set(dict(FU.ttm(gap, "net_income")))
    check(bool(leaked), f"이어졌는지 안 보는 판은 빠진 분기를 품은 12개월을 낸다({sorted(leaked)}) — 1 의 검사가 이것을 막는다")
    check(dict(FU.ttm(rows, "net_income", first=True)).get("20250331") != dict(FU.ttm(rows, "net_income")).get("20250331"),
          "이른 제출·늦은 제출 판이 실제로 다른 값을 낸다(같으면 1 의 고쳐진 값 검사가 빈 검사다)")


def beta_check() -> None:
    print("3. 베타")
    r = random.Random(3)
    mkt, stk = {}, []
    pm = ps = 100.0
    for i in range(80):
        m = f"{2020 + i // 12}{i % 12 + 1:02d}"
        x = r.gauss(0.008, 0.045)
        pm *= math.exp(x)
        ps *= math.exp(1.5 * x + r.gauss(0, 0.02))
        mkt[m] = pm
        stk.append((m, ps))
    b = EA.beta(stk, mkt)
    check(b is not None and abs(b["value"] - 1.5) < 0.15 and b["months"] == EA.BETA_MONTHS,
          f"시장의 1.5배로 만든 종목의 베타 {b and b['value']} ({b and b['months']}달)")
    check(EA.beta(stk[:20], mkt) is None, f"{EA.BETA_MIN}달이 안 되면 내지 않는다")


# 처음 실린 판으로도 맞을 수 없는 해 — 회사가 해 도중에 기준을 바꿨다. 까닭 없이 더하지 말 것.
EXCEPT = {
    # IBM 은 2014 3분기 10-Q 에서 반도체 사업을 중단 사업으로 돌려 9개월 누적을 고친 기준으로 냈다. 1·2분기의 처음 값은
    # 옛 기준(합 468억)이고 9개월은 새 기준이라, 네 분기 합이 10-K(927.9억)보다 5.7억 달러 크다.
    ("IBM", "revenue"): ("20141231",),
}


def real_data() -> None:
    print("4. 실제 자료")
    from app.stock import store

    try:
        syms = store.last_filed()
    except store.StockMissing:
        print("  [--] stock.db 가 없어 건너뜀(CI) — 1~3 은 위에서 돌았다")
        return
    if not syms:
        print("  [--] 재무가 아직 적재되지 않았다 — python -m scripts.ingest_stock")
        return
    # 처음 실린 값끼리 견준다(`first=True`) — 종목 비교가 쓰는 판이다. 지금 아는 값(가장 늦은 제출)은 회사가 뒤에
    # 과거를 고쳐 실을 때 어긋날 수 있다: IBM 은 2014 10-K 에서 2013 매출을 사업 매각으로 고쳐 싣고(997억 → 984억)
    # 9개월 누적·3분기도 고쳤지만 1·2분기는 옛 값 그대로 실어, 네 분기 합이 고친 연간 값과 6.9억 달러 어긋난다.
    for concept, least in (("net_income", 20), ("revenue", 20), ("cfo", 15)):
        n = bad = 0
        for cid, co in BY_ID.items():
            skip = EXCEPT.get((co.symbol, concept), ())
            rows = store.facts(co.symbol)
            t = dict(FU.ttm(rows, concept, first=True))
            fy = {e: v for (s, e), v in FU.pick(rows, concept, first=True).items() if s and 350 <= FU._days(s, e) <= 380}
            for e, v in fy.items():
                if e in t and e not in skip:
                    n += 1
                    bad += abs(t[e] - v) > 1e6
        check(n > least and bad == 0, f"지난 12개월 합 = 10-K 연간 값 — {concept} ({n}개 해, 어긋남 {bad})")


def main() -> int:
    ttm_checks()
    guard()
    beta_check()
    real_data()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
