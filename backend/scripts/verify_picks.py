"""종목 비교(`app/stock/pick.py`) — 고른 종목에 돌린 장기 기법·시장 몫을 뺀 수익률이 정의대로인지.

## 왜

기법 값은 전부 그럴듯한 숫자로 나온다. 미래의 재무를 섞어도, 시장 몫을 덜 빼도, 화면과 백엔드의 기법 목록이 어긋나도
오류는 없다 — 카드 한 줄이 '지금 값 없음' 으로 조용히 비거나, 있어서는 안 될 값이 보일 뿐이다. 그래서

1. **DCF** — 해마다 펼친 표(`dcf_rows`)의 합이 `dcf` 와 같고, 역 DCF 로 찾은 성장률을 다시 넣으면 시가총액이 나온다.
   할인율이 영구 성장률에 붙으면 값을 내지 않는다.
2. **기준 판정** — F-점수·방어적 기준이 모두 좋아진 가상 회사에서 전부 통과, 재료가 없으면 '모름'(통과도 미달도 아님).
3. **시장 몫** — 시장의 1.5배로 움직이게 만든 종목에서 베타 1.5 근처, 뺀 뒤의 수익률은 시장과 상관이 거의 없다.
   빼지 않은 판은 상관이 크다(걸리는 것까지).
4. **화면과 짝** — 백엔드가 계열을 내는 기법 = 화면(`techniques/longStock.js`)이 그리는 기법, 해당 없음 목록이 같다,
   장기 기법 저장소의 모든 기법이 둘 중 하나에 든다.
5. **실제 자료** — stock.db 가 있으면: 어느 시점 뒤에 실린 재무를 흔들어도 그 시점 전 달의 기법 값이 하나도 안 바뀐다
   (미래를 안 본다). 그 전에 실린 재무를 흔들면 바뀐다(걸리는 것까지).
"""

from __future__ import annotations

NEEDS_DB = False  # 1~4 는 합성·소스, 5 는 DB 가 있을 때만

import math
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import pick as PK  # noqa: E402
from app.stock import store  # noqa: E402
from app.stock.companies import COMPANIES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {what}")
    if not ok:
        fails.append(what)


def dcf_checks() -> None:
    print("1. DCF")
    r = random.Random(7)
    worst = worst_inv = 0.0
    for _ in range(300):
        fcf = r.uniform(1e8, 1e11)
        g = r.uniform(-0.05, 0.3)
        rate = r.uniform(0.05, 0.2)
        rows = PK.dcf_rows(fcf, g, rate)
        v = PK.dcf(fcf, g, rate)
        if rows is None or v is None:
            continue
        worst = max(worst, abs(rows["total"] - v) / v)
        gi = PK.implied_g(fcf, rate, v)
        worst_inv = max(worst_inv, abs(gi - g) if gi is not None else 1)
    check(worst < 1e-12, f"표의 합 = dcf (상대 오차 최대 {worst:.1e})")
    check(worst_inv < 1e-6, f"역 DCF 로 찾은 성장률을 넣으면 그 시가총액 (성장률 오차 최대 {worst_inv:.1e})")
    check(PK.dcf(1e9, 0.05, PK.TG + PK.MIN_GAP / 2) is None, "할인율이 영구 성장률에 붙으면 값을 내지 않는다")
    check(PK.implied_g(1e9, 0.1, 1e15) is None, "어떤 성장률로도 못 맞추는 시가총액이면 None")


def judge_checks() -> None:
    print("2. 기준 판정")
    p = {"net_income": 80, "assets": 1000, "cfo": 90, "lt_debt": 300, "assets_current": 500, "liabilities_current": 300,
         "shares": 100, "gross_profit": 300, "revenue": 1000}
    b = {**p, "net_income": 120, "cfo": 150, "lt_debt": 250, "assets_current": 600, "shares": 98, "gross_profit": 400,
         "revenue": 1200, "assets": 1050}
    fs = PK.fscore(b, p)
    check(fs == [True] * 9, f"모두 좋아진 회사는 아홉 다 통과 — {fs}")
    fs0 = PK.fscore({**b, "lt_debt": None, "gross_profit": None}, None)
    check(fs0[4] is None and fs0[7] is None and fs0[2] is None and fs0[0] is True,
          "재료가 없거나 1년 전이 없으면 그 기준은 '모름' — 미달로 세지 않는다")
    years = [(f"{y}1231", 10.0 * (y - 2000)) for y in range(2003, 2026)]
    base = {"revenue": 5e10, "assets_current": 300, "liabilities_current": 100, "lt_debt": 150, "equity": 1000,
            "annual": {"net_income": years, "dividends": years}}
    dv = PK.defensive(base, cap=1500, size_now=1e9)
    check(dv == [True] * 7, f"일곱 기준을 다 지나게 만든 회사 — {dv}")
    short = {**base, "annual": {"net_income": years[-3:], "dividends": []}}
    dv2 = PK.defensive(short, cap=1500, size_now=1e9)
    check(dv2[3] is None and dv2[4] is None and dv2[5] is None,
          f"자료가 {PK.MIN_YEARS}년이 안 되면 '해마다' 기준은 모름 — {dv2[3:6]}")


def market_checks() -> None:
    print("3. 시장 몫")
    r = random.Random(11)
    mkt, stk = [], []
    pm = ps = 100.0
    for i in range(150):
        m = f"{2010 + i // 12}{i % 12 + 1:02d}"
        x = r.gauss(0.008, 0.045)
        pm *= math.exp(x)
        ps *= math.exp(1.5 * x + r.gauss(0, 0.03))
        mkt.append((m, pm))
        stk.append((m, ps))
    orig = store.monthly
    store.monthly = lambda market, symbol: mkt if symbol == "SPY" else stk
    try:
        lvl, beta = PK.excess(COMPANIES[0])
    finally:
        store.monthly = orig
    check(beta is not None and abs(beta["value"] - 1.5) < 0.1, f"시장의 1.5배로 만든 종목의 베타 {beta and beta['value']}")
    ms = sorted(lvl)
    e = [math.log(lvl[b] / lvl[a]) for a, b in zip(ms, ms[1:])]
    xm = dict(mkt)
    x = [math.log(xm[b] / xm[a]) for a, b in zip(ms, ms[1:])]
    s = [math.log(dict(stk)[b] / dict(stk)[a]) for a, b in zip(ms, ms[1:])]

    def corr(a, b):
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        return sum((u - ma) * (v - mb) for u, v in zip(a, b)) / math.sqrt(
            sum((u - ma) ** 2 for u in a) * sum((v - mb) ** 2 for v in b))

    check(abs(corr(e, x)) < 0.05, f"뺀 뒤의 수익률과 시장의 상관 {corr(e, x):.3f}")
    check(corr(s, x) > 0.8, f"빼지 않은 종목 수익률은 시장과 상관이 크다 {corr(s, x):.2f} — 위 검사가 빈 검사가 아니다")


def _keys(block: str) -> set[str]:
    return set(re.findall(r"^  '?([a-z][a-z-]*)'?:", block, re.M))


def pair_checks() -> None:
    print("4. 화면과 짝")
    js = (ROOT / "frontend/src/stock/techniques/longStock.js").read_text(encoding="utf-8")
    py = (ROOT / "backend/app/stock/pick.py").read_text(encoding="utf-8")
    cat = (ROOT / "frontend/src/stock/techniques/long.js").read_text(encoding="utf-8")

    def block(name: str) -> str:
        a = js.index(f"const {name} = {{") if f"const {name} = {{" in js else js.index(f"export const {name} = {{")
        return js[a:js.index("\n}\n", a)]

    drawn = _keys(block("LINES")) | _keys(block("PANELS"))
    na = _keys(block("NA_WHY"))
    made = set(re.findall(r'put\("([a-z-]+)"', py))
    check(made == drawn, f"백엔드가 내는 기법 = 화면이 그리는 기법 (백엔드만 {sorted(made - drawn)}, 화면만 {sorted(drawn - made)})")
    check(na == PK.NA, f"해당 없음 목록이 같다 (화면 {sorted(na)}, 백엔드 {sorted(PK.NA)})")
    ids = set(re.findall(r"^    id: '([a-z-]+)', group:", cat, re.M))
    check(len(ids) > 15 and ids == drawn | na, f"장기 기법 {len(ids)}개가 모두 그리거나 해당 없음 (빠짐 {sorted(ids - drawn - na)})")


def real_data() -> None:
    print("5. 실제 자료 — 미래를 안 본다")
    try:
        store.last_filed()
    except store.StockMissing:
        print("  [--] stock.db 가 없어 건너뜀(CI) — 1~4 는 위에서 돌았다")
        return
    orig = store.facts
    for co in COMPANIES:
        rows = orig(co.symbol)
        if not rows:
            continue
        full = PK.series(co)
        if "missing" in full:
            check(False, f"{co.label} 계열을 못 냈다 — {full['missing']}")
            continue
        months = full["months"]
        cut = months[len(months) * 2 // 3]           # 3분의 2 지점의 달 — 그 달 1일 전에 실린 것만 '그때 알던 것'
        day = cut + "01"
        r = random.Random(5)
        try:
            store.facts = lambda s, rows=rows: [{**x, "value": x["value"] * r.uniform(0.3, 3)} if x["filed"] >= day else x
                                                for x in rows]
            later = PK.series(co)
            # 줄마다 다르게 흔든다 — 전부 두 배로 하면 주식 수도 두 배라 배수·비율이 그대로여서 아무것도 안 바뀐다
            store.facts = lambda s, rows=rows: [{**x, "value": x["value"] * r.uniform(0.3, 3)} if x["filed"] < day else x
                                                for x in rows]
            earlier = PK.series(co)
        finally:
            store.facts = orig
        # 발표일은 제출일보다 이르다 — 제출을 흔든 줄이 '알려진 날' 로는 cut 전일 수 있어, 비교는 cut 석 달 전까지만.
        upto = months.index(cut) - 3
        diff = changed = 0
        for tid, d in full["series"].items():
            for k, arr in d.items():
                a = arr[:upto]
                b = later["series"].get(tid, {}).get(k, [None] * len(arr))[:upto]
                c = earlier["series"].get(tid, {}).get(k, [None] * len(arr))[:upto]
                diff += sum(1 for u, v in zip(a, b) if u != v)
                changed += sum(1 for u, v in zip(a, c) if u != v)
        check(diff == 0, f"{co.label} {cut} 뒤에 실린 재무를 흔들어도 그 전 달 값이 같다 (다른 칸 {diff})")
        check(changed > 0, f"{co.label} 그 전에 실린 재무를 흔들면 바뀐다 ({changed}칸) — 위 검사가 빈 검사가 아니다")


def main() -> int:
    dcf_checks()
    judge_checks()
    market_checks()
    pair_checks()
    real_data()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
