"""차트 탭(`frontend/src/stock/charts/`) — 목록이 온전하고, 예시 그림의 지표가 그 정의대로 계산되는지.

## 왜

지표 백여 개를 손으로 옮겨 적었다. 식이 틀려도 그림은 그럴듯한 선으로 나온다 — 와일더 평활 대신 단순 평균을 써도,
창 하나가 밀려도 아무것도 멈추지 않는다. 실제로 지그재그·카기는 처음에 '방향 없음' 으로 시작해 극값이 늘 오늘 값이
되는 바람에 한 번도 꺾이지 않는 직선을 그렸다(2026-11-27). 그래서

1. **목록** — id 가 하나씩이고, 단기 매매로 잇는 id(`short`)가 그 탭에 실제로 있고, 묶음이 정한 것 가운데 하나다.
   소스를 읽어서 본다(node 없이도 돈다).
2. **그림** — 그림이 있는 항목마다 선의 길이가 가격과 같고, 값이 절반 넘게 있고, NaN·무한이 없다.
3. **지표 값** — 같은 합성 봉으로 파이썬에 따로 쓴 식(ATR·RSI·CCI·%R·MFI·CMF·슬로우 스토캐스틱·ADX·아룬·
   얼티밋·VR·OBV)과 같은 값을 내나.
4. **걸리는 것까지** — 단순 평균으로 쓴 ATR 은 3 의 비교에 걸린다. 지그재그·카기가 실제로 여러 번 꺾인다.

2~4 는 node 가 있어야 돈다(CI 의 백엔드 칸에는 없어 건너뛰고 그렇다고 찍는다).
"""

from __future__ import annotations

NEEDS_DB = False

import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CH = ROOT / "frontend" / "src" / "stock" / "charts"
GROUPS = {"type", "overlay", "trend", "momentum", "volatility", "volume", "breadth", "flow"}
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {what}")
    if not ok:
        fails.append(what)


def catalog_src() -> None:
    print("1. 목록")
    src = "".join((CH / f).read_text(encoding="utf-8") for f in ("types.js", "trend.js", "volume.js"))
    items = re.findall(r"^    id: '([a-z0-9-]+)', group: '([a-z]+)'", src, re.M)
    ids = [i for i, _ in items]
    check(len(ids) >= 100, f"항목 {len(ids)}개")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    check(not dup, f"id 가 겹치지 않는다 {dup}")
    bad = sorted({g for _, g in items if g not in GROUPS})
    check(not bad, f"묶음이 정한 것 가운데 하나 {bad}")
    short_src = (ROOT / "frontend/src/stock/techniques/short.js").read_text(encoding="utf-8")
    short_ids = set(re.findall(r"^    id: '([a-z0-9-]+)', group:", short_src, re.M))
    links = re.findall(r"short: '([a-z0-9-]+)'", src)
    missing = sorted(set(links) - short_ids)
    check(links and not missing, f"단기 매매로 잇는 {len(links)}곳이 그 탭에 있다 (없는 것 {missing})")


# ── 파이썬 쪽 정의 — calc.js 를 보지 않고 교과서 식대로 ─────────────────

def ema(x, n, alpha=None):
    a = 2 / (n + 1) if alpha is None else alpha
    out, prev, run = [None] * len(x), None, []
    for i, v in enumerate(x):
        if v is None:
            out[i] = prev
            if prev is None:
                run = []
            continue
        if prev is None:
            run.append(v)
            if len(run) == n:
                prev = sum(run) / n
                out[i] = prev
            continue
        prev += a * (v - prev)
        out[i] = prev
    return out


def rma(x, n):
    return ema(x, n, 1 / n)


def sma(x, n):
    return [None if i < n - 1 or any(v is None for v in x[i - n + 1:i + 1]) else sum(x[i - n + 1:i + 1]) / n
            for i in range(len(x))]


def tr(b):
    return [x["h"] - x["l"] if i == 0 else max(x["h"] - x["l"], abs(x["h"] - b[i - 1]["c"]), abs(x["l"] - b[i - 1]["c"]))
            for i, x in enumerate(b)]


def py_refs(b: list[dict]) -> dict[str, list]:
    c = [x["c"] for x in b]
    h = [x["h"] for x in b]
    lo = [x["l"] for x in b]
    v = [x["v"] for x in b]
    n = len(b)
    ref: dict[str, list] = {"atr": rma(tr(b), 14)}
    d = [None] + [c[i] - c[i - 1] for i in range(1, n)]
    up = rma([None if x is None else max(x, 0) for x in d], 14)
    dn = rma([None if x is None else max(-x, 0) for x in d], 14)
    ref["rsi"] = [None if u is None or w is None else (100.0 if w == 0 else 100 - 100 / (1 + u / w)) for u, w in zip(up, dn)]
    tp = [(x["h"] + x["l"] + x["c"]) / 3 for x in b]
    m = sma(tp, 20)
    ref["cci"] = [None if m[i] is None else (tp[i] - m[i]) / (0.015 * sum(abs(tp[k] - m[i]) for k in range(i - 19, i + 1)) / 20)
                  for i in range(n)]
    hh = [None if i < 13 else max(h[i - 13:i + 1]) for i in range(n)]
    ll = [None if i < 13 else min(lo[i - 13:i + 1]) for i in range(n)]
    ref["wr"] = [None if hh[i] is None else (hh[i] - c[i]) / (hh[i] - ll[i]) * -100 for i in range(n)]
    raw = [None if hh[i] is None else (c[i] - ll[i]) / (hh[i] - ll[i]) * 100 for i in range(n)]
    ref["stoch_k"] = sma(raw, 3)
    pos = [None] + [tp[i] * v[i] if tp[i] > tp[i - 1] else 0 for i in range(1, n)]
    neg = [None] + [tp[i] * v[i] if tp[i] < tp[i - 1] else 0 for i in range(1, n)]
    s = lambda x, k, i: None if i < k or any(y is None for y in x[i - k + 1:i + 1]) else sum(x[i - k + 1:i + 1])  # noqa: E731
    ref["mfi"] = [None if s(pos, 14, i) is None else 100 - 100 / (1 + s(pos, 14, i) / s(neg, 14, i)) for i in range(n)]
    clv = [0 if x["h"] == x["l"] else ((x["c"] - x["l"]) - (x["h"] - x["c"])) / (x["h"] - x["l"]) for x in b]
    mv = [a * w for a, w in zip(clv, v)]
    ref["cmf"] = [None if i < 19 else sum(mv[i - 19:i + 1]) / sum(v[i - 19:i + 1]) for i in range(n)]
    pdm = [0] + [max(h[i] - h[i - 1], 0) if h[i] - h[i - 1] > lo[i - 1] - lo[i] else 0 for i in range(1, n)]
    mdm = [0] + [max(lo[i - 1] - lo[i], 0) if lo[i - 1] - lo[i] > h[i] - h[i - 1] else 0 for i in range(1, n)]
    t = rma(tr(b), 14)
    pdi = [None if a is None or z is None else a / z * 100 for a, z in zip(rma(pdm, 14), t)]
    mdi = [None if a is None or z is None else a / z * 100 for a, z in zip(rma(mdm, 14), t)]
    dx = [None if p is None else (0 if p + q == 0 else abs(p - q) / (p + q) * 100) for p, q in zip(pdi, mdi)]
    ref["adx"] = rma(dx, 14)

    def since_best(x, i, best):
        w = x[i - 25:i + 1]
        bv = best(w)
        last = max(k for k, y in enumerate(w) if y == bv)
        return 25 - (len(w) - 1 - last)

    ref["aroon_up"] = [None if i < 25 else since_best(h, i, max) / 25 * 100 for i in range(n)]
    bp = [None] + [c[i] - min(lo[i], c[i - 1]) for i in range(1, n)]
    rr = [None] + [max(h[i], c[i - 1]) - min(lo[i], c[i - 1]) for i in range(1, n)]
    avg = lambda k, i: None if s(bp, k, i) is None else s(bp, k, i) / s(rr, k, i)  # noqa: E731
    ref["uo"] = [None if avg(28, i) is None else (4 * avg(7, i) + 2 * avg(14, i) + avg(28, i)) / 7 * 100 for i in range(n)]
    upv = [None] + [v[i] if c[i] > c[i - 1] else v[i] / 2 if c[i] == c[i - 1] else 0 for i in range(1, n)]
    dnv = [None] + [v[i] if c[i] < c[i - 1] else v[i] / 2 if c[i] == c[i - 1] else 0 for i in range(1, n)]
    ref["vr"] = [None if s(upv, 20, i) is None else s(upv, 20, i) / s(dnv, 20, i) * 100 for i in range(n)]
    o, acc = [], 0.0
    for i in range(n):
        if i:
            acc += v[i] if c[i] > c[i - 1] else -v[i] if c[i] < c[i - 1] else 0
        o.append(acc)
    ref["obv"] = o
    return ref


JS = """
const K = await import(%(calc)s)
const S = await import(%(sample)s)
const C = await import(%(catalog)s)
const b = S.BARS, c = b.map((x) => x.c)
const vals = {
  atr: K.atr(b), rsi: K.rsi(c), cci: K.cci(b), wr: K.williamsR(b), stoch_k: K.stochastic(b, 14, 3, 3).k,
  mfi: K.mfi(b), cmf: K.cmf(b), adx: K.dmi(b).adx, aroon_up: K.aroon(b).up, uo: K.ultimate(b), vr: K.vr(b), obv: K.obv(b),
}
const plots = []
for (const x of C.ITEMS) {
  if (!x.plot) continue
  const s = x.plot()
  const n = (s.bars || s.close).length
  const arrs = [...(s.overlays || []).map((o) => o.values), ...(s.panel?.series || []).map((o) => o.values)]
  if (s.band) arrs.push(s.band.hi, s.band.lo)
  for (const a of arrs) plots.push([x.id, n, a.length, a.filter((v) => v != null && Number.isFinite(v)).length,
                                    a.filter((v) => v != null && !Number.isFinite(v)).length])
}
const cut = S.cut(c)
const z = K.zigzag(cut, 5)
let turns = 0
for (let i = 2; i < z.length; i++) if (Math.sign(z[i] - z[i - 1]) * Math.sign(z[i - 1] - z[i - 2]) < 0) turns++
console.log(JSON.stringify({ bars: b, vals, plots, turns, kagi: K.kagi(cut, 2).length }))
"""


def node_checks() -> None:
    node = shutil.which("node")
    if not node:
        print("2~4. node 가 없어 건너뜀(CI 백엔드 칸) — 1 은 위에서 돌았다")
        return
    code = JS % {k: json.dumps((CH / f"{k}.js").as_uri()) for k in ("calc", "sample", "catalog")}
    out = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=120, encoding="utf-8")
    if out.returncode:
        check(False, f"node 실행 실패: {out.stderr.strip()[:300]}")
        return
    d = json.loads(out.stdout)

    print("2. 그림")
    # 선형회귀 채널은 일부러 마지막 60일에만 긋는다
    short = [p for p in d["plots"] if p[0] != "reg-channel" and (p[2] != p[1] or p[3] < p[1] * 0.5)]
    nan = [p for p in d["plots"] if p[4]]
    check(len(d["plots"]) > 100 and not short, f"선 {len(d['plots'])}개의 길이가 가격과 같고 값이 절반 넘게 있다 (어긋남 {short[:3]})")
    check(not nan, f"NaN·무한이 없다 {nan[:3]}")

    print("3. 지표 값 — 파이썬으로 따로 쓴 식과")
    ref = py_refs(d["bars"])
    for k, js in d["vals"].items():
        py = ref[k]
        same_null = all((a is None) == (b is None) for a, b in zip(js, py))
        diff = max((abs(a - b) for a, b in zip(js, py) if a is not None and b is not None), default=math.inf)
        scale = max(abs(b) for b in py if b is not None)
        check(same_null and diff <= 1e-9 * max(1, scale), f"{k:8s} 값이 비는 자리가 같고 차이 {diff:.1e}")

    print("4. 걸리는 것까지")
    atr_sma = sma(tr(d["bars"]), 14)
    gap = max(abs(a - b) for a, b in zip(d["vals"]["atr"], atr_sma) if a is not None and b is not None)
    check(gap > 1e-3, f"단순 평균으로 쓴 ATR 은 3 의 비교에 걸린다(차이 {gap:.3f}) — 비교가 빈 검사가 아니다")
    check(d["turns"] >= 3, f"지그재그(5%)가 {d['turns']}번 꺾인다 — 직선이 아니다")
    check(d["kagi"] >= 6, f"카기(2%)가 {d['kagi']}점 — 한 번도 안 꺾이는 판이 아니다")


def main() -> int:
    catalog_src()
    node_checks()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
