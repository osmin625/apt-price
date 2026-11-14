"""기술주 가치 탭 — 재무 가공(`app/stock/fundamentals.py`)과 가치 분해(`frontend/src/stock/techvalue/model.js`)가 정의대로인지.

## 왜

분해의 숫자는 화면이 바로 내고, 재료(지난 12개월 이익)는 EDGAR 의 겹치고 고쳐지는 제출에서 만든다. 둘 다 틀려도
오류 없이 그럴듯한 값이 나온다. 그래서

1. **지난 12개월** — 누적으로만 보고된 분기·빠진 4분기를 차로 메우고, 고쳐 실린 값은 늦은(또는 처음) 제출을 고르고,
   한 분기가 빠지면 내지 않는다(합성 제출).
2. **걸리는 것까지** — 세 분기를 1년으로 부르는 판, 같은 기간의 이른 제출을 고르는 판은 1 의 비교에 걸린다.
3. **베타** — 시장의 1.5배로 움직이게 만든 합성 종목에서 1.5 근처가 나온다.
4. **분해** — 파이썬으로 따로 쓴 식과 model.js 가 같은 값을 낸다(node 가 없으면 건너뜀). 역산한 이익·시점을
   시나리오에 넣으면 설명 안 된 몫이 0 이 된다.
5. **실제 자료** — stock.db 가 있으면: 지난 12개월 합이 회사가 낸 연간 값(10-K)과 모두 같다. 시나리오가 아는
   종목에만 붙어 있고 값이 범위 안이다.
"""

from __future__ import annotations

NEEDS_DB = False  # 1~4 는 합성, 5 는 DB 가 있을 때만

import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import fundamentals as FU  # noqa: E402
from app.stock import techvalue as TV  # noqa: E402
from app.stock.companies import BY_ID  # noqa: E402
from app.stock.scenarios import SCENARIOS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
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
    b = TV.beta(stk, mkt)
    check(b is not None and abs(b["value"] - 1.5) < 0.15 and b["months"] == TV.BETA_MONTHS,
          f"시장의 1.5배로 만든 종목의 베타 {b and b['value']} ({b and b['months']}달)")
    check(TV.beta(stk[:20], mkt) is None, f"{TV.BETA_MIN}달이 안 되면 내지 않는다")


def py_decompose(cap, shares, price, e0, g, r, now, techs):
    R, G = r / 100, g / 100
    base = e0 / (R - G) if e0 > 0 and R > G else 0
    out = []
    for t in techs:
        dt = max(t["year"] + 0.5 - now, 0)
        v = t["profit"] * 1e9 * t["pe"]
        out.append({"pv": t["prob"] * v / (1 + R) ** dt, "dt": dt, "v": v, **t})
    s = sum(t["pv"] for t in out)
    for t in out:
        gap = cap - base - (s - t["pv"])
        t["need"] = gap * (1 + R) ** t["dt"] / (t["prob"] * t["pe"]) / 1e9 if gap > 0 else 0
        t["priceAt"] = (max(e0, 0) * (1 + G) ** t["dt"] + t["profit"] * 1e9) * t["pe"] / shares
    return {"base": base, "sum": s, "residual": cap - base - s, "techs": out}


def model_check() -> None:
    print("4. 분해 — 파이썬 식 = model.js")
    node = shutil.which("node")
    if not node:
        print("  [--] node 가 없어 건너뜀(CI 백엔드 칸)")
        return
    r = random.Random(11)
    cases = []
    for _ in range(25):
        techs = [{"year": r.randint(2027, 2036), "profit": round(r.uniform(0.5, 60), 2), "prob": round(r.uniform(0.05, 0.9), 2),
                  "pe": r.randint(12, 35)} for _ in range(r.randint(0, 3))]
        cases.append({"cap": r.uniform(5e9, 4e12), "shares": r.uniform(1e8, 1.3e10), "price": r.uniform(5, 500),
                      "e0": r.uniform(-5e8, 2.5e11), "g": round(r.uniform(0, 3), 2), "r": round(r.uniform(6, 20), 2),
                      "now": 2026.87, "techs": techs})
    js = ROOT / "frontend" / "src" / "stock" / "techvalue" / "model.js"
    code = (f"import {{ decompose }} from {json.dumps(js.as_uri())};\n"
            f"const cases = {json.dumps(cases)};\n"
            "console.log(JSON.stringify(cases.map(c => decompose(c))))\n")
    out = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
    if out.returncode:
        check(False, f"node 실행 실패: {out.stderr.strip()[:200]}")
        return
    got = json.loads(out.stdout)
    worst = 0.0
    for c, g in zip(cases, got):
        p = py_decompose(**c)
        pairs = [(p["base"], g["base"]), (p["sum"], g["sum"]), (p["residual"], g["residual"])]
        pairs += [(a["pv"], b["pv"]) for a, b in zip(p["techs"], g["techs"])]
        pairs += [(a["need"], b["need"]) for a, b in zip(p["techs"], g["techs"])]
        pairs += [(a["priceAt"], b["priceAt"]) for a, b in zip(p["techs"], g["techs"])]
        for a, b in pairs:
            worst = max(worst, abs(a - b) / max(1.0, abs(a)))
    check(worst < 1e-9, f"25개 경우의 지금 사업·기술·설명 안 된 몫·역산·실현 때 주가 (최대 상대 차이 {worst:.1e})")

    # 역산을 시나리오에 넣으면 설명 안 된 몫이 0 — 필요 이익과 필요 시점 둘 다
    c = {"cap": 1.5e12, "shares": 3.9e9, "price": 390, "e0": 3e9, "g": 0, "r": 13.5, "now": 2026.87,
         "techs": [{"year": 2029, "profit": 25, "prob": 0.35, "pe": 25}, {"year": 2032, "profit": 40, "prob": 0.2, "pe": 25}]}
    code = (f"import {{ decompose }} from {json.dumps(js.as_uri())};\n"
            f"const c = {json.dumps(c)};\n"
            "const a = decompose(c); const t0 = a.techs[0];\n"
            "const b = decompose({...c, techs: [{...c.techs[0], profit: t0.need}, c.techs[1]]});\n"
            "const big = {...c, techs: [{...c.techs[0], profit: 5000}, c.techs[1]]};\n"
            "const d0 = decompose(big).techs[0];\n"
            "const d = decompose({...big, techs: [{...big.techs[0], year: d0.needYear}, big.techs[1]]});\n"
            "console.log(JSON.stringify({b: b.residual / c.cap, d: d.residual / c.cap, y: d0.needYear}))\n")
    out = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
    j = json.loads(out.stdout)
    check(abs(j["b"]) < 1e-9, "필요 이익을 넣으면 설명 안 된 몫이 0")
    check(j["y"] is not None and abs(j["d"]) < 1e-9, f"필요 시점({j['y'] and round(j['y'], 2)})을 넣으면 설명 안 된 몫이 0")


def real_data() -> None:
    print("5. 실제 자료")
    from app.stock import store

    try:
        syms = store.last_filed()
    except store.StockMissing:
        print("  [--] stock.db 가 없어 건너뜀(CI) — 1~4 는 위에서 돌았다")
        return
    n = bad = 0
    for cid, co in BY_ID.items():
        rows = store.facts(co.symbol)
        if not rows:
            continue
        t = dict(FU.ttm(rows, "net_income"))
        fy = {e: v for (s, e), v in FU.pick(rows, "net_income").items() if s and 350 <= FU._days(s, e) <= 380}
        for e, v in fy.items():
            if e in t:
                n += 1
                bad += abs(t[e] - v) > 1e6
    if not syms:
        print("  [--] 재무가 아직 적재되지 않았다 — python -m scripts.ingest_stock")
    else:
        check(n > 20 and bad == 0, f"지난 12개월 합 = 10-K 연간 순이익 ({n}개 해, 어긋남 {bad})")
    check(set(SCENARIOS) <= set(BY_ID), "시나리오가 아는 종목에만 붙어 있다")
    ok = all(2026 <= s["year"] <= 2050 and 0 < s["prob"] <= 1 and s["profit"] > 0 and 5 <= s["pe"] <= 60 and s.get("source")
             for v in SCENARIOS.values() for s in v)
    check(ok, "시나리오 값이 범위 안이고 출처 문구가 있다")


def main() -> int:
    ttm_checks()
    guard()
    beta_check()
    model_check()
    real_data()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
