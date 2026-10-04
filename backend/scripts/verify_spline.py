"""벡터화한 스플라인 기저가 `pricing.rcs_basis` 와 **같은 값**인지 검사한다.

사용법:
    python -m scripts.verify_spline

## 왜 따로 검사하는가

제한 3차 스플라인 기저는 시드 생성기와 회귀 모델이 **같은 함수**를 써야 한다.
한쪽만 바뀌면 측정오차가 생겨, 추정량에 아무 문제가 없어도 참값 복원 검증이
실패한다. 속도 때문에 행 단위 루프를 numpy 로 바꿨으니(적합에서 2.2초),
두 구현이 같은 값을 내는지는 눈이 아니라 검사가 답해야 한다.

매듭 개수와 분포 모양을 바꿔 가며, 매듭 위/아래/사이의 값을 모두 넣어 본다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import pricing  # noqa: E402
from app.services.hedonic import _spline_cols  # noqa: E402

TOL = 1e-12


def check(label: str, values: np.ndarray, knots: list[float]) -> tuple[bool, float]:
    cols: dict = {}
    names = _spline_cols(cols, "x", values, knots)
    fast = np.column_stack([np.asarray(cols[n], dtype=float) for n in names])
    slow = np.array([pricing.rcs_basis(float(v), knots) for v in values])
    if fast.shape != slow.shape:
        print(f"  {label:<34} 모양 불일치 {fast.shape} vs {slow.shape}")
        return False, float("inf")
    gap = float(np.max(np.abs(fast - slow)))
    ok = gap <= TOL
    print(f"  {label:<34} 열 {fast.shape[1]}개 최대오차 {gap:.3e} {'OK' if ok else '실패'}")
    return ok, gap


def main() -> int:
    rng = np.random.RandomState(0)
    worst = 0.0
    ok = True

    for n in (3, 4, 5, 6, 7):
        knots = list(np.linspace(5.0, 60.0, n))
        # 매듭 바깥(선형 꼬리)·매듭 위·매듭 사이를 모두 넣는다.
        vals = np.concatenate([
            np.array(knots, dtype=float),
            np.array([-20.0, 0.0, 100.0, 1e3]),
            rng.uniform(-5, 80, 500),
        ])
        good, gap = check(f"균등 매듭 {n}개", vals, knots)
        ok &= good
        worst = max(worst, gap)

    # 실제 분포를 닮은 매듭(한쪽에 몰림) + 상한에 뭉친 값
    knots = [2.5, 8.0, 14.0, 20.0, 27.0, 30.0]
    vals = np.concatenate([rng.uniform(1, 30, 800), np.full(400, 30.0)])
    good, gap = check("치우친 매듭 6개 · 상한 뭉침", vals, knots)
    ok &= good
    worst = max(worst, gap)

    # log 공간(면적)처럼 음수를 포함하는 경우
    knots = [-0.8, -0.2, 0.0, 0.3, 0.9]
    vals = rng.uniform(-1.5, 1.5, 600)
    good, gap = check("log 공간 매듭 5개(음수 포함)", vals, knots)
    ok &= good
    worst = max(worst, gap)

    print(f"\n{'통과' if ok else '실패'} — 최대오차 {worst:.3e} (허용 {TOL:.0e})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
