"""기술주 가치 탭의 반영 분해(`app/stock/reflect.py`) — 푸는 법·범위·그날 알던 실적이 맞는지.

## 왜

1. **푸는 법** — 절편 자유·기울기 0 이상 최소제곱을 scipy `nnls` 를 가운데로 옮겨 푼다. 부동산의 순수 파이썬
   활성 집합법(`regime.nnls_cd`, 이미 scipy 와 1e-12 로 대조됨)과 같은 답을 내야 한다.
2. **나눈 몫이 다시 합쳐진다** — 평균일 때 + 요인별 몫 + 설명 안 된 몫 = 실제 1년 변화.
3. **범위가 참값을 덮는다** — 끈적이는 요인과 겹치는 1년 창(12달 충격의 합)으로 만든 합성 자료에 참값을 심고, 화면의
   '80% 범위'(24달 덩어리 5~95%)가 참값을 덮는 비율을 잰다. 70~90% 여야 한다 — 처음 쓴 12달 10~90% 는 67% 였다. 크기가 0 인 요인은 범위가 0 을 품어야 한다.
   그리고 **겹침을 무시한 범위(달마다 뽑기)는 덜 덮는다** — 덩어리로 뽑는 이유다.
4. **그날 알던 실적** — 그달 말 뒤에 제출된 값을 흔들어도 그달까지의 매출 상승률·이익률 변화가 그대로다. 그 전에 제출된
   값을 흔들면 달라진다(빈 검사가 아니다).
"""

from __future__ import annotations

NEEDS_DB = False  # 합성 자료로 돈다

import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.realestate.services.regime import nnls_cd  # noqa: E402
from app.stock import reflect as RF  # noqa: E402

fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {what}")
    if not ok:
        fails.append(what)


def ar1(n, phi, seed):
    r = random.Random(seed)
    v, out = 0.0, []
    for _ in range(n):
        v = phi * v + r.gauss(0, 1)
        out.append(v)
    return out


def months(n, start=2000):
    return [f"{start + i // 12}{i % 12 + 1:02d}" for i in range(n)]


def synth(n, b_true, seed, a=8.0):
    """요인 k 개(AR 0.97)와, 그 요인 + 12달 충격의 합(겹치는 1년 창)인 목표."""
    ms = months(n + 12)
    xs = [ar1(n + 12, 0.97, seed * 31 + j) for j in range(len(b_true))]
    r = random.Random(seed * 7 + 1)
    shocks = [r.gauss(0, 4) for _ in range(n + 12)]
    fs = [{"key": f"f{j}", "label": f"f{j}", "group": "거시" if j % 2 else "실적", "sign": 1, "lag": 0, "unit": "%p",
           "x": dict(zip(ms, xs[j]))} for j in range(len(b_true))]
    # 목표는 z 로 바꾼 요인의 선형 결합 — 맞추는 쪽도 z 를 쓰므로 참값이 그대로 b 다.
    zs = []
    for j in range(len(b_true)):
        vals = xs[j][12:]
        zs.append([RF.hist_z(vals, v) for v in vals])
    yoy = {}
    for i in range(n):
        t = i + 12
        yoy[ms[t]] = a + sum(b * zs[j][i] for j, b in enumerate(b_true)) + sum(shocks[t - 11:t + 1])
    for f, j in zip(fs, range(len(b_true))):
        f["x"] = {m: v for m, v in f["x"].items() if m in yoy}
    return yoy, fs


def solver() -> None:
    print("1. 푸는 법 — scipy nnls(가운데로) = 부동산 nnls_cd")
    r = np.random.default_rng(5)
    worst = 0.0
    for _ in range(20):
        n, k = r.integers(80, 200), r.integers(2, 9)
        X = r.normal(size=(n, k))
        y = X @ np.where(r.random(k) < 0.4, 0, r.uniform(0, 5, k)) + r.normal(0, 3, n) + 4
        a1, b1 = RF.fit(X, y)
        a2, b2 = nnls_cd(X.tolist(), y.tolist(), iters=5000)
        worst = max(worst, abs(a1 - a2), float(np.abs(b1 - np.array(b2)).max()))
    check(worst < 1e-6, f"20개 경우의 절편·기울기 (최대 차이 {worst:.1e})")


def identity() -> None:
    print("2. 나눈 몫이 다시 합쳐진다")
    yoy, fs = synth(160, [3, 0, 5, 0], 1)
    d = RF.decompose(yoy, fs, boot=50)
    total = d["base"] + sum(f["contrib"] for f in d["factors"]) + d["residual"]
    check(abs(total - d["actual"]) < 0.05, f"평균 {d['base']} + 요인 몫 + 설명 안 된 몫 {d['residual']} = 실제 {d['actual']}")
    s = d["series"]
    check(abs(s["base"] + s["macro"][-1] + s["fund"][-1] - d["fitted"]) < 0.15, "그림의 거시 + 실적 + 평균 = 맞춘 값")
    short = {m: v for k, (m, v) in enumerate(sorted(yoy.items())) if k < RF.MIN_MONTHS - 1}
    check(not RF.decompose(short, fs, boot=10)["available"], f"{RF.MIN_MONTHS}달이 안 되면 나누지 않는다")


def coverage() -> None:
    print("3. 범위가 참값을 덮는다(합성, 참값 심음)")
    b_true = [4.0, 0.0, 6.0, 0.0, 2.5]
    hit = tot = zero_in = zero_tot = 0
    naive_hit = 0
    for s in range(60):
        yoy, fs = synth(180, b_true, 100 + s)
        d = RF.decompose(yoy, fs, boot=200, seed=s)
        for f, bt in zip(d["factors"], b_true):
            if bt > 0:
                tot += 1
                hit += f["b_lo"] <= bt <= f["b_hi"]
            else:
                zero_tot += 1
                zero_in += f["b_lo"] <= 1e-9
        # 겹침을 무시한 범위 — 달마다 뽑는다
        keys = [f for f in fs if f["x"]]
        common = sorted(set(yoy).intersection(*[set(f["x"]) for f in keys]))
        X = np.array([[RF.hist_z([f["x"][m] for m in common], f["x"][t]) for f in keys] for t in common])
        y = np.array([yoy[m] for m in common])
        rng = np.random.default_rng(s)
        B = np.array([RF.fit(X[i], y[i])[1] for i in (rng.integers(0, len(y), len(y)) for _ in range(200))])
        for j, bt in enumerate(b_true):
            if bt > 0:
                naive_hit += np.percentile(B[:, j], RF.Q[0] * 100) <= bt <= np.percentile(B[:, j], RF.Q[1] * 100)
    cov = hit / tot
    naive = naive_hit / tot
    check(0.70 <= cov <= 0.90, f"크기가 있는 요인의 '80% 범위' 가 참값을 덮은 비율 {cov:.0%} (70~90% 여야)")
    check(zero_in / zero_tot >= 0.8, f"크기가 0 인 요인의 범위가 0 을 품은 비율 {zero_in / zero_tot:.0%}")
    check(naive < cov - 0.1, f"달마다 뽑는 범위는 {naive:.0%} 만 덮는다 — 덩어리로 뽑는 이유")


def lookahead() -> None:
    print("4. 그날 알던 실적")
    rows = []
    for k in range(16):
        y, q = 2020 + k // 4, k % 4
        s = f"{y}{q * 3 + 1:02d}01"
        e = {0: f"{y}0331", 1: f"{y}0630", 2: f"{y}0930", 3: f"{y}1231"}[q]
        fm = q * 3 + 5
        filed = f"{y + fm // 13}{(fm - 1) % 12 + 1:02d}10"
        rows.append({"concept": "revenue", "start": s, "end": e, "value": 100 + 5 * k, "form": "10-Q", "filed": filed})
        rows.append({"concept": "operating_income", "start": s, "end": e, "value": 10 + k, "form": "10-Q", "filed": filed})
    ms = [f"{2021 + i // 12}{i % 12 + 1:02d}" for i in range(48)]
    base = RF.fundamentals_known(rows, ms)
    t = "202306"
    cut = RF._month_end(t)
    later = [dict(r, value=r["value"] * 1.5) if r["filed"] > cut else r for r in rows]
    # 같은 기간이 그 뒤에 고쳐 실려도(나중 제출) 그달까지의 값은 처음 제출을 쓴다
    later += [dict(r, value=r["value"] * 2, filed="20250101") for r in rows if r["filed"] <= cut]
    other = RF.fundamentals_known(later, ms)
    same = all(base[k].get(m) == other[k].get(m) for k in ("revenue_growth", "margin_change") for m in ms if m <= t)
    check(same and len([m for m in base["revenue_growth"] if m <= t]) > 3,
          "그달 말 뒤의 제출·고쳐 실림을 흔들어도 그달까지 값이 같다")
    early = [dict(r, value=r["value"] * 1.5) if r["filed"] <= cut and r["end"] >= "20221001" else r for r in rows]
    diff = RF.fundamentals_known(early, ms)
    check(base["revenue_growth"].get(t) != diff["revenue_growth"].get(t), "그 전에 제출된 값을 흔들면 달라진다(빈 검사가 아니다)")


def main() -> int:
    solver()
    identity()
    coverage()
    lookahead()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
