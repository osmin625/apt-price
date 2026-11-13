"""장기 투자의 지수 평가 넷(`app/stock/valuation.py`)이 미래를 보지 않고, 범위를 제대로 재는지.

## 왜

'CAPE 가 높았던 달 뒤 10년은 수익이 낮았다' 는 그달에 그 값을 알 수 있었을 때만 뜻이 있다. 이 계산에는 미래가
새어 들어올 구멍이 셋 있다 — 늦게 발표되는 통계(분기 GDP·이익), 전체 기간으로 맞춘 추세, 전체 기간의 순위.
그리고 겹치는 10년 구간은 표본을 실제보다 수십 배 많아 보이게 한다. 그래서 다섯 가지를 본다.

1. **미래를 안 본다** — 합성 입력에서 t 달 뒤의 값을 전부 흔들어도 t 달까지의 평가·백분위가 그대로다. 발표
   시차 안(분기 끝 3달, 이익 3달)의 값을 흔들어도 그대로다.
2. **걸리는 것까지** — 전체 기간으로 맞춘 추세, 묵히지 않은 이익은 1 의 비교에 걸려야 한다.
3. **범위가 맞다** — 관계가 없는 합성 자료(끈적이는 평가 계열 + 따로 노는 주가)에서 칸이 범위 밖으로 나가는 일이
   5% 안팎이고, 관계를 심으면 잡는다. 그리고 **겹침을 무시한 범위(달마다 섞기)와 처음 쓴 범위(평가 계열 통째로
   돌리기)는 너무 자주 걸린다** — 경로를 뽑는 이유가 이것이다.
4. **계산이 정의대로다** — 추세는 그달까지의 최소제곱 직선(np.polyfit)과, 백분위는 직접 센 것과 같다.
5. **실제 자료** — macro.db 가 있으면: 1달 묵혀 계산한 CAPE 가 실러의 CAPE 열과 맞고(실러는 전 달까지 10년), 버핏 지표의 단위 환산이
   그럴듯한 범위(30~400%)다. 없으면(CI) 이 칸만 건너뛰고 그렇다고 찍는다.
"""

from __future__ import annotations

NEEDS_DB = False  # 1~4 는 합성 입력, 5 는 DB 가 있을 때만

import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import valuation as V  # noqa: E402

fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {what}")
    if not ok:
        fails.append(what)


def ar1(n: int, phi: float, sd: float, seed: int, mean: float = 0.0) -> list[float]:
    r = random.Random(seed)
    v, out = mean, []
    for _ in range(n):
        v = mean + phi * (v - mean) + r.gauss(0, sd)
        out.append(v)
    return out


def walk(n: int, seed: int, mu: float = 0.003, sd: float = 0.04, start: float = 100.0) -> list[float]:
    r = random.Random(seed)
    p, out = start, []
    for _ in range(n):
        p *= math.exp(r.gauss(mu, sd))
        out.append(p)
    return out


M0 = V.mi("190001")


def us_synth(n: int = 720, seed: int = 1) -> dict:
    P = walk(n, seed)
    E = [p * 0.06 * math.exp(x) for p, x in zip(P, ar1(n, 0.97, 0.05, seed + 1))]
    CPI = walk(n, seed + 2, 0.002, 0.004)
    G = [4 + x for x in ar1(n, 0.99, 0.15, seed + 3)]
    d = {"P": {M0 + i: P[i] for i in range(n)}, "E": {M0 + i: E[i] for i in range(n - 4)},
         "CPI": {M0 + i: CPI[i] for i in range(n)}, "GS10": {M0 + i: G[i] for i in range(n)}}
    mcap, gdp = {}, {}
    for i in range(2, n, 3):
        q = f"{(M0 + i) // 12}Q{(M0 + i) % 12 // 3 + 1}"
        gdp[q] = 1000 * math.exp(0.012 * i / 3)
        mcap[q] = P[i] * 4000 * math.exp(ar1(1, 0, 0.05, i)[0])
    d["mcap"], d["gdp"] = mcap, gdp
    return d


def kr_synth(n: int = 360, seed: int = 11) -> dict:
    C = walk(n, seed, 0.004, 0.06, 1000)
    per = [12 * math.exp(x) for x in ar1(n, 0.95, 0.08, seed + 1)]
    m0 = V.mi("199501")
    d = {"close": {m0 + i: C[i] for i in range(n)},
         "cpi": {m0 + i: v for i, v in enumerate(walk(n - 1, seed + 2, 0.002, 0.003))},
         "mcap": {m0 + i: C[i] * 1e9 for i in range(n)}, "per": {m0 + i: per[i] for i in range(n)},
         "y10": {m0 + i: 4 + x for i, x in enumerate(ar1(n, 0.99, 0.1, seed + 3))}}
    gdp = {}
    for i in range(2, n, 3):
        gdp[f"{(m0 + i) // 12}Q{(m0 + i) % 12 // 3 + 1}"] = 300000 * math.exp(0.012 * i / 3)
    d["gdp"] = gdp
    return d


def shake(d: dict, after: int, seed: int, keys=None, qafter: int | None = None) -> dict:
    """t 달 뒤의 값을 모두 흔든 사본. 분기는 '그 분기가 알려지는 달' 이 아니라 분기 끝이 t 뒤인 것만."""
    r = random.Random(seed)
    out = {}
    for k, x in d.items():
        if keys is not None and k not in keys:
            out[k] = x
            continue
        if x and isinstance(next(iter(x)), str):
            lim = after if qafter is None else qafter
            out[k] = {q: (v * (1 + r.uniform(-0.3, 0.3)) if V.q_end(q) > lim else v) for q, v in x.items()}
        else:
            out[k] = {m: (v * (1 + r.uniform(-0.3, 0.3)) if m > after else v) for m, v in x.items()}
    return out


def same_upto(a: dict, b: dict, t: int) -> bool:
    ks = [m for m in a if m <= t]
    return all(m in b and abs(a[m] - b[m]) < 1e-9 * max(1, abs(a[m])) for m in ks) and \
        len(ks) == len([m for m in b if m <= t])


def lookahead() -> None:
    print("1. 미래를 안 본다")
    for name, synth, build in (("미국", us_synth, V.us_measures), ("한국", kr_synth, V.kr_measures)):
        d = synth()
        _, base = build(d)
        months = sorted(next(iter(base.values()))["values"])
        for mid in V.MEASURES:
            vals = base[mid]["values"]
            check(len(vals) > 100, f"{name} {mid}: 합성 입력에서 값이 난다({len(vals)}달)")
            ok = True
            okp = True
            for k, t in enumerate(sorted(vals)[len(vals) // 4::len(vals) // 5][:4]):
                _, other = build(shake(d, t, 100 + k))
                ok &= same_upto(vals, other[mid]["values"], t)
                pa, pb = V.expanding_pct(vals), V.expanding_pct(other[mid]["values"])
                okp &= same_upto(pa, pb, t)
            check(ok, f"{name} {mid}: t 뒤를 흔들어도 t 까지 값이 같다")
            check(okp, f"{name} {mid}: t 뒤를 흔들어도 t 까지 역사 백분위가 같다")
        del months
    # 발표 시차 안 — 분기 끝이 t − 3 뒤인 분기와 t − 3 뒤의 이익은 t 에 아직 모른다.
    d = us_synth()
    _, base = V.us_measures(d)
    t = V.mi("193006")
    _, other = V.us_measures(shake(d, t - V.LAG_E, 7, keys={"E"}))
    check(all(abs(base[m]["values"][t] - other[m]["values"][t]) < 1e-9 for m in ("fed-model", "cape")),
          f"이익을 t-{V.LAG_E} 뒤만 흔들면 t 의 이익 수익률·CAPE 가 같다")
    _, other = V.us_measures(shake(d, t, 8, keys={"mcap", "gdp"}, qafter=t - V.LAG_Q))
    check(abs(base["buffett-indicator"]["values"][t] - other["buffett-indicator"]["values"][t]) < 1e-9,
          f"분기 끝이 t-{V.LAG_Q} 뒤인 분기만 흔들면 t 의 버핏 지표가 같다")
    _, other = V.us_measures(shake(d, t, 9, keys={"mcap", "gdp"}, qafter=t - V.LAG_Q - 3))
    check(abs(base["buffett-indicator"]["values"][t] - other["buffett-indicator"]["values"][t]) > 1e-6,
          "한 분기 더 앞을 흔들면 달라진다(시차를 너무 길게 잡지 않았다)")


def guard() -> None:
    print("2. 걸리는 것까지")
    d = us_synth()
    real, _ = V.us_measures(d)

    def leaky_trend(dd):
        r, _ = V.us_measures(dd)
        lp = {m: math.log(v) for m, v in r.items()}
        ks = sorted(lp)
        b, a = np.polyfit(ks, [lp[k] for k in ks], 1)
        return {m: (math.exp(lp[m] - (a + b * m)) - 1) * 100 for m in ks}

    def leaky_cape(dd):
        r, _ = V.us_measures(dd)
        e_real = {m: dd["E"][m] / dd["CPI"][m] for m in dd["E"]}
        return V.cape_of(r, e_real, 0)

    base = leaky_trend(d)
    t = sorted(base)[len(base) // 2]
    check(not same_upto(base, leaky_trend(shake(d, t, 3)), t), "전체 기간으로 맞춘 추세는 1 의 비교에 걸린다")
    base = leaky_cape(d)
    other = leaky_cape(shake(d, t - V.LAG_E, 4, keys={"E"}))
    check(abs(base[t] - other[t]) > 1e-9, "묵히지 않은 이익의 CAPE 는 발표 시차 안을 흔들면 걸린다")


def calibration() -> None:
    print("3. 범위")
    rng = np.random.default_rng(1)
    out = tot = 0
    naive_out = naive_tot = rot_out = 0
    for s in range(60):
        n = 1200
        m0 = V.mi("190001")
        x = ar1(n, 0.985, 0.2, 500 + s)
        vals = {m0 + i: v for i, v in enumerate(x)}
        real = {m0 + i: v for i, v in enumerate(walk(n, 900 + s, 0.003, 0.04))}
        pct = V.expanding_pct(vals)
        p = V.perf(pct, real, 10, rng, draws=400)
        for r in p["rows"]:
            if r["verdict"]:
                tot += 1
                out += r["verdict"] != "inside"
        # 겹침을 무시한 범위(달마다 섞기)와 처음 쓴 범위(평가 계열 통째로 돌리기) — 얼마나 자주 걸리나
        origins = [m for m in sorted(pct) if V.forward(real, m, 10) is not None]
        R = np.array([V.forward(real, m, 10) for m in origins])
        B = np.array([V.bucket_of(pct[m]) for m in origins])
        N = len(origins)
        perm = np.array([[R[rng.permutation(B) == b].mean() for b in range(V.BUCKETS)] for _ in range(200)])
        rot = []
        for k in rng.integers(120, N - 120, size=200):
            Bs = np.roll(B, k)
            rot.append([R[Bs == b].mean() if (Bs == b).any() else np.nan for b in range(V.BUCKETS)])
        rot = np.array(rot)
        for b in range(V.BUCKETS):
            if (B == b).sum() and V.thin([m for m, x in zip(origins, B) if x == b], 120) >= V.MIN_IND:
                naive_tot += 1
                mean = R[B == b].mean()
                lo, hi = np.percentile(perm[:, b], [2.5, 97.5])
                naive_out += not lo <= mean <= hi
                col = rot[:, b][np.isfinite(rot[:, b])]
                lo, hi = np.percentile(col, [2.5, 97.5])
                rot_out += not lo <= mean <= hi

    rate = out / max(tot, 1)
    naive = naive_out / max(naive_tot, 1)
    check(tot > 100, f"판정이 난 칸이 충분하다({tot}칸)")
    check(0.0 <= rate <= 0.12, f"관계가 없을 때 범위 밖 {rate:.1%} (5% 안팎이어야)")
    rot = rot_out / max(naive_tot, 1)
    check(naive > 3 * max(rate, 0.05), f"달마다 섞는 범위는 {naive:.1%} 로 너무 자주 걸린다 — 겹침을 무시하면 표본이 부푼다")
    check(rot > max(2 * rate, 0.10), f"평가 계열을 통째로 돌리는 범위는 {rot:.1%} — 짝이 몇 가지뿐이라 끝을 못 잰다")

    # 관계를 심는다 — 평가가 높을수록 그 뒤 수익이 낮다.
    hits = 0
    for s in range(20):
        n = 1600
        m0 = V.mi("190001")
        x = ar1(n, 0.985, 0.2, 700 + s)
        r = random.Random(800 + s)
        p, real = 100.0, {}
        for i in range(n):
            p *= math.exp(0.003 - 0.004 * x[i] + r.gauss(0, 0.03))
            real[m0 + i] = p
        pct = V.expanding_pct({m0 + i: v for i, v in enumerate(x)})
        top = V.perf(pct, real, 10, rng, draws=400)["rows"][-1]
        hits += top["verdict"] == "below"
    check(hits >= 10, f"심어 둔 관계를 잡는다 — 맨 위 칸이 '낮음' 인 경우 {hits}/20")


def definitions() -> None:
    print("4. 정의")
    m0 = V.mi("190001")
    lp = {m0 + i: v for i, v in enumerate(np.cumsum(ar1(400, 0.5, 0.03, 3)) + 4)}
    dev, _ = V.trend_dev(lp)
    ok = True
    for t in (m0 + 150, m0 + 260, m0 + 399):
        ks = [k for k in sorted(lp) if k <= t]
        b, a = np.polyfit([k - m0 for k in ks], [lp[k] for k in ks], 1)
        want = (math.exp(lp[t] - (a + b * (t - m0))) - 1) * 100
        ok &= abs(dev[t] - want) < 1e-6
    check(ok, "추세 = 그달까지의 최소제곱 직선(np.polyfit)")
    vals = {m0 + i: v for i, v in enumerate(ar1(300, 0.9, 1, 4))}
    pct = V.expanding_pct(vals)
    t = m0 + 200
    hist = [vals[k] for k in vals if k <= t]
    want = (sum(v < vals[t] for v in hist) + 0.5 * sum(v == vals[t] for v in hist)) / len(hist) * 100
    check(abs(pct[t] - want) < 1e-9, "백분위 = 그달까지 값 가운데 아래인 비율")
    q, _ = V.known_quarterly({"2000Q1": 1.0, "2000Q2": 2.0}, until=V.mi("200012"))
    check(V.mi("200005") not in q and q.get(V.mi("200006")) == 1.0 and q.get(V.mi("200008")) == 1.0
          and q.get(V.mi("200009")) == 2.0 and q.get(V.mi("200012")) == 2.0,
          f"분기 값은 분기 끝 {V.LAG_Q}달 뒤부터, 다음 분기가 알려질 때까지")
    check(V.thin([0, 10, 60, 119, 120, 250], 120) == 3, "겹치지 않는 구간 수")


def real_data() -> None:
    print("5. 실제 자료")
    from app.macro import store as macro_store

    try:
        d = V.us_inputs()
    except macro_store.MacroMissing:
        print("  [--] macro.db 가 없어 건너뜀(CI) — 1~4 는 위에서 돌았다")
        return
    if not d["P"]:
        print("  [--] 실러 자료가 아직 적재되지 않았다 — python -m scripts.ingest_stock")
        return
    real = {m: d["P"][m] / d["CPI"][m] for m in d["P"] if m in d["CPI"]}
    e_real = {m: d["E"][m] / d["CPI"][m] for m in d["E"] if m in d["CPI"]}
    mine = V.cape_of(real, e_real, 1)
    theirs = V.as_index(macro_store.monthly("shiller_cape"))
    common = [m for m in mine if m in theirs and m + V.LAG_E <= max(d["E"])]
    worst = max(abs(mine[m] / theirs[m] - 1) for m in common)
    check(len(common) > 1500 and worst < 1e-9,
          f"1달 묵힌 CAPE = 실러의 CAPE 열 ({len(common)}달, 최대 상대 차이 {worst:.1e})")
    _, us = V.us_measures(d)
    _, kr = V.kr_measures(V.kr_inputs())
    for name, ms in (("미국", us), ("한국", kr)):
        b = ms["buffett-indicator"]["values"]
        lo, hi = min(b.values()), max(b.values())
        check(30 <= lo and hi <= 400, f"{name} 버핏 지표 {lo:.0f}~{hi:.0f}% — 단위 환산이 그럴듯하다")
        ey = ms["fed-model"]["extra"]["ey"]
        # 2009 년 미국은 지난 12개월 이익이 꺼져 0.7% 까지 내려갔다 — 이익이 0 근처면 정상적으로 작다.
        check(all(0.3 <= v <= 25 for v in ey.values()), f"{name} 이익 수익률 {min(ey.values()):.1f}~{max(ey.values()):.1f}%")


def main() -> int:
    lookahead()
    guard()
    calibration()
    definitions()
    real_data()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
