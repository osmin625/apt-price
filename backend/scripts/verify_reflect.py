"""반영 분해의 부호 제약 최소제곱(`regime.nnls_cd`, 순수 파이썬)이 scipy 의 `nnls` 와 **같은 답**인지.

사용법:
    python -m scripts.verify_reflect

## 왜 있나

거시 분석의 반영 분해는 numpy 없이 돌아야 한다 — numpy/statsmodels 는 hedonic 만 쓰고 나머지
탭은 미설치 환경에서도 떠야 한다(CLAUDE.md). 그래서 좌표 하강으로 직접 풀었다. 빠르게(또는
다르게) 만든 것은 같은 답을 내는지 대조한다 — 이 저장소의 규칙이다.

대조는 둘이다.
1. **실데이터** — 화면이 쓰는 그 X·y(이론 방향·시차를 곱한 z, 매매지수 1년 변화).
2. **일부러 얽힌 문제** — 서로 거의 같은 열(금리 둘처럼), 이론과 반대인 열, 0 인 열을 섞어
   무작위로 200개. 경계(b=0)에 걸리는 경우가 많아야 제약 처리를 제대로 본다.

허용 오차는 계수·절편 1e-6. 그리고 **걸려야 할 때 걸리는지** — 한 바퀴만 돌고 멈춘 풀이를 넣으면
어긋나야 한다(자체 시험).
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
from scipy.optimize import nnls  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.services import regime  # noqa: E402

TOL = 1e-6


def reference(X, y):
    Xa, ya = np.asarray(X, float), np.asarray(y, float)
    xm, ym = Xa.mean(0), ya.mean()
    b, _ = nnls(Xa - xm, ya - ym)
    return float(ym - xm @ b), [float(v) for v in b]


def gap(solve, X, y) -> float:
    a1, b1 = solve(X, y)
    a2, b2 = reference(X, y)
    return max([abs(a1 - a2)] + [abs(p - q) for p, q in zip(b1, b2)])


def problems(k: int = 200):
    rng = random.Random(7)
    for _ in range(k):
        n, p = rng.randint(40, 160), rng.randint(3, 10)
        X = [[rng.gauss(0, 1) for _ in range(p)] for _ in range(n)]
        for r in X:  # 거의 같은 열 하나(금리 둘처럼)
            r[1] = r[0] + rng.gauss(0, 0.05)
        beta = [rng.choice([0.0, rng.uniform(0, 3), -rng.uniform(0, 3)]) for _ in range(p)]
        y = [sum(b * x for b, x in zip(beta, r)) + rng.gauss(0, 1) for r in X]
        yield X, y


def main() -> int:
    bad = 0
    with SessionLocal() as db:
        _, common, X, y, _ = regime._reflect_frame(db)
    g = gap(regime.nnls_cd, X, y)
    print(f"  실데이터 {common[0]}~{common[-1]} ({len(common)}개월, 요인 {len(X[0])}) — 최대 차이 {g:.2e}")
    bad += g > TOL
    worst = max(gap(regime.nnls_cd, Xr, yr) for Xr, yr in problems())
    print(f"  일부러 얽힌 문제 200개 — 최대 차이 {worst:.2e}")
    bad += worst > TOL
    # 자체 시험 — 한 바퀴만 돌고 멈춘 풀이는 어긋나야 한다.
    caught = gap(lambda X_, y_: regime.nnls_cd(X_, y_, iters=1), X, y) > TOL
    print(f"  자체 시험(한 바퀴 풀이를 잡나) — {'잡음' if caught else '못 잡음'}")
    bad += not caught
    print(f"\n{'통과' if not bad else '실패'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
