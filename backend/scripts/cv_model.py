"""Stage 2 를 교차검증한다 — **요인을 넣을지 말지를 같은 자로 잰다.**

사용법:
    python -m scripts.cv_model                       # 스펙 사다리 전체
    python -m scripts.cv_model --spec M3 --folds 10
    python -m scripts.cv_model --drop top_floor      # 그 요인을 빼면 얼마나 나빠지나
    python -m scripts.cv_model --ablate              # 요인을 하나씩 빼 본다

## 왜 필요한가

요인을 더할 때마다 "넣을까 말까" 를 손으로 재 왔다. 최고층·브랜드는 adj R² 로,
주변 입지는 5겹 교차검증으로 쟀는데 **기준이 달라서 두 결정을 나란히 비교할 수가
없었다.** 그리고 요인이 쌓일수록 표본 안 적합도는 올라가기만 한다 — M3 Stage 2 는
이미 열이 200개가 넘는데 단지는 1,800곳대다.

표본 안 R² 로는 과적합을 못 본다. 표본 밖 오차만이 "이 요인이 **새로운 정보**를
주는가" 에 답한다.

## 왜 Stage 2 만 교차검증하나

Stage 1 은 단지 고정효과라 **입지·브랜드·최고층 같은 단지 수준 변수를 쓰지 않는다.**
그래서 α̂_c 를 전체 표본으로 한 번 구해 두고 단지를 겹으로 나눠도 정보가 새지 않는다.
Stage 1 까지 겹마다 다시 돌리면 비용만 수십 배가 되고 답은 같다.

## 가중치는 겹 사이에 고정한다

적합과 같은 가중치 ω_c = 1/(se²_c + τ²) 를 쓰되, **τ² 는 전체 적합의 값을 모든
비교에 공통으로** 쓴다. 겹마다 다시 추정하면 변수 집합이 아니라 가중치가 달라져서
비교가 흐려진다.

## 읽는 법

가중 RMSE 가 **낮을수록** 좋다. 기준 대비 개선이 음수면 과적합이다 — 표본 안에서는
좋아졌는데 밖에서는 나빠진 것. 평균만 보지 말고 **겹별 수치**를 같이 봐야 한다.
한 겹이 끌어올린 것인지 고르게 나아진 것인지가 거기서 갈린다.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import hedonic  # noqa: E402

SEED = 20261005

# 하나씩 빼 볼 수 있는 요인. Stage 2 설계행렬에서 그 변수의 열만 들어낸다.
ABLATABLE = (
    "walk_min", "gangnam_min", "age", "log_households", "top_floor",
    "elem_dist", "mid_dist", "academy", "adult",
)


def _design(hed, alpha, spec, knots, drop: tuple[str, ...] = ()):
    """설계행렬에서 `drop` 에 든 요인의 열을 뺀다."""
    import statsmodels.api as sm

    X, spline_terms = hed._stage2_design(alpha, spec, knots)
    if drop:
        cols = []
        for var in drop:
            cols += [c for c in spline_terms.get(var, []) if c in X.columns]
            cols += [c for c in X.columns if c == f"{var}_missing"]
        if cols:
            X = X.drop(columns=cols)
    return sm.add_constant(X.astype(float), has_constant="add")


def run(months: int, spec_key: str, folds: int, drop: tuple[str, ...],
        ablate: bool, ladder: bool) -> int:
    import numpy as np
    import statsmodels.api as sm

    with SessionLocal() as db:
        rows = hedonic.load_rows(db, months=months)

    specs = list(hedonic.SPECS) if ladder else [spec_key]
    print(f"거래 {len(rows):,}건 · {folds}겹 · 시드 {SEED}\n")

    for key in specs:
        spec = hedonic.SPECS[key]
        fit = hedonic.fit(rows, spec=key)
        alpha = fit["alpha"]
        tau2 = float(fit["tau"]) ** 2

        # 매듭은 전체로 한 번 만든다. 겹마다 다시 만들면 겹 사이 비교가 흐려진다.
        nk = hedonic.knots_for(len(alpha))
        knots = {}
        for var in ABLATABLE:
            if var in alpha.columns and alpha[var].notna().any():
                k = hedonic._knots(alpha[var].dropna().astype(float).to_numpy(), nk)
                if k:
                    knots[var] = k

        y = alpha["alpha"].astype(float).to_numpy()
        se = alpha["se_alpha"].astype(float).to_numpy()
        w = 1.0 / (se**2 + tau2)
        rng = np.random.default_rng(SEED)
        fold = rng.permutation(len(alpha)) % folds

        def cv(drop_: tuple[str, ...]) -> tuple[float, list[float], int]:
            X = _design(hedonic, alpha, spec, knots, drop_).to_numpy()
            errs = []
            for f in range(folds):
                tr, te = fold != f, fold == f
                res = sm.WLS(y[tr], X[tr], weights=w[tr]).fit()
                e = y[te] - X[te] @ res.params
                errs.append(float(np.sqrt(np.average(e**2, weights=w[te]))))
            return float(np.mean(errs)), errs, X.shape[1]

        base, base_errs, ncol = cv(drop)
        label = key + (f" (−{'·'.join(drop)})" if drop else "")
        print(f"[{label}] 단지 {len(alpha):,}곳 · 열 {ncol}")
        print(f"  가중 RMSE {base:.5f}   겹별 " + " ".join(f"{e:.4f}" for e in base_errs))
        print(f"  (참고) 표본 안 adj R² {fit['adj_r2']:.4f} · τ {fit['tau']:.5f}")

        if ablate:
            print(f"\n  요인을 하나씩 빼면 — 손실이 크면 그 요인이 일하고 있다는 뜻")
            print(f"  {'뺀 요인':<16}{'RMSE':>10}{'손실':>9}{'나빠진 겹':>10}")
            out = []
            for var in ABLATABLE:
                if var not in knots and var not in (alpha.columns if hasattr(alpha, "columns") else []):
                    continue
                m, errs, _ = cv(tuple(set(drop) | {var}))
                worse = sum(1 for a, b in zip(errs, base_errs) if a > b)
                out.append((m - base, var, m, worse))
            for d, var, m, worse in sorted(out, reverse=True):
                print(f"  {var:<16}{m:>10.5f}{d:>+9.5f}{worse:>7}/{folds}")
            print("\n  손실이 0 이하면 그 요인은 **빼는 편이 낫다** — 표본 밖에서")
            print("  도움이 안 되면서 열만 늘리고 있다.")
        print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 2 교차검증")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--spec", default="M3")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--drop", action="append", default=[],
                    help="이 요인을 뺀 채로 잰다 (반복 가능)")
    ap.add_argument("--ablate", action="store_true", help="요인을 하나씩 빼 본다")
    ap.add_argument("--ladder", action="store_true", help="스펙 사다리 전체")
    args = ap.parse_args()

    if not hedonic.available():
        print("모델 의존성이 없습니다. pip install -r requirements.txt")
        return 1

    warnings.filterwarnings("ignore")
    return run(args.months, args.spec, args.folds, tuple(args.drop),
               args.ablate, args.ladder)


if __name__ == "__main__":
    sys.exit(main())
