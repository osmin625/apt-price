"""단기 매매 기법을 실제 지수에 돌린 계산(`app/stock/trading.py`)이 미래를 보지 않고, 비용·기저율을 제대로 세는지.

## 왜

신호의 과거 성적은 '그날까지 알던 것만으로 냈다면' 이 성립할 때만 뜻이 있다. 패턴 탐지는 특히 위험하다 — 꼭대기는
지나고 나서야 꼭대기이고, 그걸 그날 안 것처럼 쓰면 패턴이 기막히게 들어맞는다. 그래서 다섯 가지를 본다.

1. **미래를 안 본다** — 합성 종가를 t 날에서 잘라 다시 돌린 신호가, 전체로 돌린 신호 중 t 날까지의 것과 같다.
   꼭짓점(지그재그)도 같은 식으로 본다. 패턴마다 신호가 한 번 이상 나는지도 본다 — 안 나면 이 검사는 빈 검사다.
2. **걸리는 것까지** — 다음 날 종가를 엿보는 규칙을 일부러 만들어 1 의 비교에 넣으면 걸려야 한다.
3. **비용** — 비용을 넣은 누적 수익과 뺀 누적 수익의 비가 정확히 (1 − 비용)^체결 횟수 다. 신호 다음 날에 체결한다.
4. **기저율 범위** — 아무 날이나 고른 '가짜 신호' 는 범위 밖으로 나가는 일이 5% 안팎이어야 하고(너무 잦으면 범위가
   좁다), 수익이 가장 좋았던 날만 고른 신호는 범위 밖(위)으로 나가야 한다.
5. **지표가 정의대로다** — 손으로 쓴 정의(산술 평균·와일더 평활·어제까지의 채널)와 대조한다.
6. **지표가 화면 쪽과 같다** — 합성 예시의 지표(`frontend/src/stock/techniques/synth.js`)와 같은 입력에서 같은 값을
   내나. node 가 없으면 이 칸만 건너뛰고 그렇다고 찍는다(CI 의 백엔드 칸). 5 는 늘 돈다.

DB 없이 돈다.
"""

from __future__ import annotations

NEEDS_DB = False  # 합성 종가로 돈다

import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import trading as T  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {what}")
    if not ok:
        fails.append(what)


def synth(seed: int, n: int = 8000, vol: float = 0.015) -> list[float]:
    """변동성 국면이 번갈아 오는 무작위 보행 — 국면이 있어야 박스·삼각처럼 좁아지는 모양이 생긴다."""
    r = random.Random(seed)
    px, out = 1000.0, []
    for i in range(n):
        v = vol * (0.5 if (i // 400) % 2 else 1.2)
        px *= math.exp(r.gauss(0.0002, v))
        out.append(px)
    return out


def marks_upto(rule, c, t):
    return [m for m in rule.run(c).marks if m[0] <= t]


def lookahead() -> None:
    print("1. 미래를 안 본다")
    series = [synth(s) for s in (1, 2, 3)]
    for rule in T.RULES:
        total = 0
        ok = True
        for c in series:
            full = rule.run(c).marks
            total += len(full)
            for t in (700, 2333, 4100, 6000, 7400):
                if [m for m in full if m[0] <= t] != rule.run(c[:t + 1]).marks:
                    ok = False
        check(ok, f"{rule.id}: 잘라 낸 계열의 신호가 같다")
        check(total > 0, f"{rule.id}: 합성 계열에서 신호가 난다({total}번)")
    c = series[0]
    full = T.zigzag(c)
    check(all([p for p in full if p.seen <= t] == T.zigzag(c[:t + 1]) for t in (500, 3000, 7000)),
          "꼭짓점: 잘라 낸 계열의 확정 꼭짓점이 같다")
    check(all(p.seen > p.i for p in full), "꼭짓점: 확정된 날이 꼭짓점 뒤다")


def guard() -> None:
    print("2. 걸리는 것까지 — 다음 날을 엿보는 규칙")

    def peek(c):
        marks = T.trade(len(c), lambda i: i + 1 < len(c) and c[i + 1] > c[i] * 1.01,
                        lambda i: i + 1 < len(c) and c[i + 1] < c[i] * 0.99)
        return T.Result(marks, 0)

    bad = T.Rule("peek", "엿보기", peek, "hold")
    c = synth(1)
    caught = any([m for m in bad.run(c).marks if m[0] <= t] != bad.run(c[:t + 1]).marks for t in (700, 2333, 4100))
    check(caught, "엿보는 규칙이 1 의 비교에 걸린다")


def cost() -> None:
    print("3. 비용과 체결")
    c = synth(4, 3000)
    dates = [f"{2000 + i // 250:04d}{1 + (i % 250) // 21 % 12:02d}{1 + i % 21:02d}" for i in range(len(c))]
    for rule in T.RULES:
        if rule.kind != "hold":
            continue
        res = rule.run(c)
        a = T.strategy(c, dates, res.marks, res.start, cost=T.COST)
        b = T.strategy(c, dates, res.marks, res.start, cost=0.0)
        fills = sum(1 for i, _ in res.marks if i >= res.start and i + T.FILL < len(c))
        want = (1 - T.COST) ** fills
        got = (1 + a["total"] / 100) / (1 + b["total"] / 100)
        check(abs(got / want - 1) < 1e-9, f"{rule.id}: 비용 비 = (1−c)^{fills}")
    i = 100
    want = c[i + 1 + 20] / c[i + 1] * (1 - T.COST) ** 2 - 1
    check(abs(T.forward(c, i, 20) - want) < 1e-12, "신호 다음 날 종가에 사서 h 일 뒤 판다")
    check(T.forward(c, len(c) - 5, 20) is None, "뒤가 모자라면 세지 않는다")


def base_rate() -> None:
    print("4. 기저율 범위")
    c = synth(5, 6000)
    rng = np.random.default_rng(1)
    r = random.Random(9)
    out = 0
    tries = 300
    for _ in range(tries):
        days = sorted(r.sample(range(200, 5900), 30))
        marks = [(d, 1) for d in days]
        lens = T.signal_lens(c, marks, 0, 20, 1, rng)
        out += lens["verdict"] != "inside"
    rate = out / tries
    check(0.01 <= rate <= 0.10, f"아무 날 신호가 범위 밖으로 나간 비율 {rate:.1%} (5% 안팎이어야)")
    fw = sorted(((T.forward(c, i, 20), i) for i in range(len(c)) if T.forward(c, i, 20) is not None), reverse=True)
    best = T.thin(sorted((i, 1) for _, i in fw[:400]), 20, 1)
    lens = T.signal_lens(c, [(i, 1) for i in best], 0, 20, 1, rng)
    check(lens.get("verdict") == "above", f"좋은 날만 고른 신호는 범위 위로 나간다({lens.get('verdict')})")
    check(T.thin([(0, 1), (5, 1), (25, 1), (30, -1)], 20, 1) == [0, 25], "같은 쪽 신호는 h 일 안이면 하나로 센다")


def hand() -> None:
    print("5. 지표 — 손으로 쓴 정의")
    c = synth(6, 400)
    s = T.sma(c, 20)
    check(all(abs(s[i] - sum(c[i - 19:i + 1]) / 20) < 1e-9 for i in range(19, 400)), "sma = 20일 산술 평균")
    hi, lo = T.channel(c, 20)
    check(hi[50] == max(c[30:50]) and lo[50] == min(c[30:50]), "채널은 어제까지 20일(오늘 제외)")
    # 와일더 RSI — 처음 14일 단순 평균, 그 뒤 (13·이전 + 오늘)/14
    d = np.diff(c)
    up, dn = np.maximum(d, 0), np.maximum(-d, 0)
    au, ad = up[:14].mean(), dn[:14].mean()
    want = [100 - 100 / (1 + au / ad)]
    for k in range(14, len(d)):
        au, ad = (au * 13 + up[k]) / 14, (ad * 13 + dn[k]) / 14
        want.append(100 - 100 / (1 + au / ad))
    got = T.rsi(c, 14)[14:]
    check(max(abs(a - b) for a, b in zip(got, want)) < 1e-9, "RSI = 와일더 평활")


def same_as_screen() -> None:
    print("6. 지표 — 화면 쪽(synth.js)과 같은 값")
    node = shutil.which("node")
    if not node:
        print("  [--] node 가 없어 건너뜀 — 손으로 쓴 정의와의 대조는 위에서 돌았다")
        return
    c = [round(x, 4) for x in synth(7, 600)]
    js = ROOT / "frontend" / "src" / "stock" / "techniques" / "synth.js"
    code = (f"import {{ sma, ema, stdev, rsi, macd, channel }} from {json.dumps(js.as_uri())};\n"
            f"const c = {json.dumps(c)};\n"
            "const m = macd(c);\n"
            "console.log(JSON.stringify({sma: sma(c, 50), ema: ema(c, 26), stdev: stdev(c, 20), rsi: rsi(c, 14),\n"
            "  line: m.line, signal: m.signal, hi: channel(c, 20).map(x => x.hi), lo: channel(c, 10).map(x => x.lo)}))\n")
    out = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
    if out.returncode:
        check(False, f"node 실행 실패: {out.stderr.strip()[:200]}")
        return
    j = json.loads(out.stdout)
    line, signal, _ = T.macd(c)
    py = {"sma": T.sma(c, 50), "ema": T.ema(c, 26), "stdev": T.stdev(c, 20), "rsi": T.rsi(c, 14),
          "line": line, "signal": signal, "hi": T.channel(c, 20)[0], "lo": T.channel(c, 10)[1]}
    for k, v in py.items():
        ok = len(v) == len(j[k]) and all((a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-8)
                                         for a, b in zip(v, j[k]))
        check(ok, f"{k}: 파이썬 = synth.js")


def main() -> int:
    lookahead()
    guard()
    cost()
    base_rate()
    hand()
    same_as_screen()
    print(f"\n{'FAIL ' + str(len(fails)) if fails else '모두 통과'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
