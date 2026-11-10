"""지수 구간 예측이 미래를 보지 않는지 — 기점 뒤의 값을 바꿔도 그 기점의 예측이 그대로인가.

## 왜

백테스트 점수는 '그때 알던 것만으로 냈다면' 이 성립할 때만 뜻이 있다. 미래가 한 방울만
새도 점수는 좋아지고 화면은 그 점수를 믿으라고 말한다 — 조용히 틀리는 가장 흔한 길이다.
`app/stock/forecast.py` 에서 샐 자리는 셋이다.

- 학습에 쓰는 과거 h개월 수익률 — 끝이 기점을 넘는 것을 넣으면 h-1 개월을 보고 맞힌다
- 변동성(EWMA) — 기점 달 뒤의 일별 값을 쓰면 안 된다
- 무위험 금리 — 기점 뒤 달 값을 당겨 오면 안 된다(`_rf_h` 는 앞 달로만 물러난다)

## 어떻게

합성 일별 종가(무작위 보행, 시드 고정)와 월 금리로 재료를 만든다. 기점 t 를 여럿 골라, **t 달
뒤의 일별 종가와 금리만** 마구 바꾼 재료로 다시 만든 예측이 원래와 비트까지 같은지 본다.
일별 단계에서 바꾸므로 월말 종가·변동성을 만드는 길까지 같이 시험된다.

걸리지 말아야 할 때 안 걸리는지도 본다 — **t 달 안**의 값을 바꾸면 예측이 달라져야 한다.
안 달라지면 이 검사는 아무것도 못 보는 검사다.

DB 없이 돈다.
"""

from __future__ import annotations

NEEDS_DB = False  # 합성 재료로 돈다

import datetime as dt
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import forecast as F  # noqa: E402


def synth(seed: int = 7, years: int = 9) -> tuple[list[tuple[str, float]], dict[str, float]]:
    rng = random.Random(seed)
    day = dt.date(2010, 1, 4)
    px = 1000.0
    daily = []
    while day < dt.date(2010 + years, 1, 1):
        if day.weekday() < 5:
            vol = 0.01 if (day.year % 3) else 0.025  # 변동성 국면이 있어야 vol 모델이 일을 한다
            px *= math.exp(rng.gauss(0.0003, vol))
            daily.append((day.strftime("%Y%m%d"), px))
        day += dt.timedelta(days=1)
    rf = {}
    for y in range(2010, 2010 + years):
        for m in range(1, 13):
            if (y, m) != (2013, 6):  # 빈 달 하나 — 앞 달로 물러나는 길도 탄다
                rf[f"{y:04d}{m:02d}"] = 1.0 + 0.3 * math.sin(y + m / 6)
    return daily, rf


def build(daily, rf) -> F.Series:
    months, close = F.month_end_closes(daily)
    return F.Series(months, close, rf, F.ewma_vol(daily))


def perturb(daily, rf, cut: str, seed: int):
    """cut('YYYYMM') 보다 **뒤** 달의 값만 바꾼다."""
    rng = random.Random(seed)
    d2 = [(d, c * math.exp(rng.gauss(0, 0.2))) if d[:6] > cut else (d, c) for d, c in daily]
    r2 = {k: (v + rng.uniform(-3, 3) if k > cut else v) for k, v in rf.items()}
    return d2, r2


def main() -> int:
    daily, rf = synth()
    base = build(daily, rf)
    n = len(base.months)
    picks = sorted({F.MIN_TRAIN + 5, n // 2, n - 8, n - 2})
    bad = checked = 0
    for t in picks:
        cut = base.months[t]
        moved = build(*perturb(daily, rf, cut, seed=t))
        for h in F.HORIZONS:
            for m in F.MODELS:
                try:
                    a = F.forecast(base, t, h, m)
                    b = F.forecast(moved, t, h, m)
                except IndexError as exc:
                    # 학습 범위를 기점 너머로 넓히면 끝 쪽 기점에서 '없는 달' 을 읽다 여기로 온다.
                    bad += 1
                    print(f"  FAIL 기점 {cut} h={h} {m}: 기점 뒤 달을 읽으려 했다 ({exc})")
                    continue
                if a is None:
                    continue
                checked += 1
                if a != b:
                    bad += 1
                    print(f"  FAIL 기점 {cut} h={h} {m}: {a} → {b}")
    print(f"  기점 {len(picks)}개 · 예측 {checked}개 — 뒤를 바꿔도 같은가: {'OK' if not bad else 'FAIL'}")

    # 걸려야 할 때 걸리는지: 기점 달 '안' 의 값을 바꾸면 달라져야 한다.
    t = n // 2
    cut = base.months[t - 1]  # t 달부터 바뀐다
    moved = build(*perturb(daily, rf, cut, seed=99))
    same = [m for h in F.HORIZONS for m in F.MODELS
            if F.forecast(base, t, h, m) == F.forecast(moved, t, h, m)]
    sees = not same
    print(f"  기점 달 안을 바꾸면 달라지는가: {'OK' if sees else 'FAIL — 이 검사는 아무것도 못 본다'}"
          + (f" (그대로인 것: {same})" if same else ""))

    ok = not bad and checked > 0 and sees
    print("\n이상 없음" if ok else "\n[X] 미래를 본다 — 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
