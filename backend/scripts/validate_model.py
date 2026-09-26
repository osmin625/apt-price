"""합성 데이터에서 회귀가 참값을 되찾아오는지 검증한다.

사용법:
    python -m scripts.validate_model
    python -m scripts.validate_model --coverage 40

읽기 전용이며, 실패하면 종료 코드 1로 끝난다.

## 세 단계 검증

1. **스칼라 복원** — 각 계수가 추정 대상의 3 표준오차 안에 들어오는가(연기 감지기).
2. **잔차 복원** — 추정한 단지별 잔차가 시드가 뽑은 참 u_c 와 얼마나 맞는가.
   축소(shrinkage)를 건 값은 **일부러** 기울기가 1보다 작아야 한다. 둘 다
   출력해서 축소가 실제로 작동하는지 눈으로 확인한다.
3. **커버리지** — RNG seed 만 바꿔 수십 번 재생성·재적합해 95% 신뢰구간이
   추정 대상을 포함하는 비율을 센다. 95% 근처여야 한다.

   3번이 핵심이다. 샌드위치 추정량이 틀렸을 때 1번은 통과할 수 있지만
   커버리지는 통과하지 못한다. 실제로 그랬다: 개발 중 스칼라는 6/6 통과인데
   커버리지가 72.5%로 나왔고, 원인은 추정량이 아니라 **판정 목표값**이었다.

## 무엇을 참값으로 볼 것인가 — 여기서 한 번 틀렸다

시드의 참 도보 곡선은 18분에서 꺾인다. 회귀의 선형 W 계수는 단일 기울기라
-0.0140 을 그대로 맞힐 수 없다. 처음에는 '관측 분포에서의 기울기 평균'을
목표로 삼았는데 그것도 틀렸다 — 회귀계수는 기울기의 단순 평균이 아니라
**분산 가중 사영**이고, 게다가 강남분·연식·구 FE 로 부분화된 뒤의 사영이다.

그래서 estimand_walk() 가 노이즈를 거의 0으로 둔 같은 데이터에 같은 설계를
적합해 목표값을 구한다. 설계·가중치·꺾임·부분화가 전부 자동으로 반영된다.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import hedonic  # noqa: E402
from scripts import seed_demo  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"

# 파라미터 6개에 각각 |t|<2 를 적용하면 모든 것이 정상이어도
# 1 - 0.95^6 ≈ 26% 확률로 최소 하나가 실패한다. 다중검정 보정 없이 2.0을 쓰면
# 테스트가 제 설계 때문에 깜빡이게 된다. 개별 검정은 3.0(≈99.7%)으로 느슨하게 두고,
# 추정량이 제대로 보정됐는지는 --coverage 가 판정한다. 스칼라는 연기 감지기,
# 커버리지가 진짜 시험이다.
T_THRESHOLD = 3.0


def load_truth() -> dict:
    if not seed_demo.TRUTH_PATH.exists():
        print(f"참값 파일이 없습니다: {seed_demo.TRUTH_PATH}")
        print("먼저 `python -m scripts.seed_demo --recreate-schema` 를 실행하세요.")
        sys.exit(1)
    return json.loads(seed_demo.TRUTH_PATH.read_text(encoding="utf-8"))


def estimand_walk(specs, months: int, truth: dict, meta: dict) -> float:
    """선형 W 계수가 실제로 겨냥하는 값(추정 대상, estimand).

    참 곡선은 18분에서 꺾이는데 회귀는 단일 기울기를 적합한다. 이때 계수는
    기울기들의 **단순 평균이 아니라** 분산 가중 사영이고, 게다가 강남분·연식·
    구 FE 로 부분화(partial out)된 뒤의 사영이다. 기울기 평균을 목표로 삼으면
    추정량이 멀쩡해도 커버리지가 72%로 떨어진다(실제로 그렇게 나왔다).

    해석식으로 유도하는 대신, **노이즈를 거의 0으로 둔 같은 데이터에 같은 설계를
    적합해** 그 계수를 목표로 삼는다. 설계·가중치·꺾임·부분화가 전부 반영된다.
    """
    quiet = {**truth, "sigma_trade": 1e-4, "sigma_complex": 0.0}
    trades, _ = seed_demo.generate(
        random.Random(0), list(specs), months, date.today(), quiet
    )
    rows = [{**meta[t["complex_id"]], **t} for t in trades if t["complex_id"] in meta]
    return hedonic.fit(rows, spec="M2", ref_year=truth["ref_year"])["linear_walk"]["coef"]


def targets(truth: dict, walk_estimand: float) -> list[tuple[str, str, float]]:
    """(표시명, 추정값 키, 참값). 키는 아래 extract() 가 해석한다."""
    return [
        ("도보 준탄력도", "walk", walk_estimand),
        ("강남 준탄력도", "gangnam", truth["gangnam_semi_elast"]),
        ("log(전용면적)", "log_area", truth["log_area_elast"]),
        ("월 상승률(%)", "month_pct", truth["monthly_drift"] * 100),
        ("고층 프리미엄", "floor_고층", truth["floor_factors"]["고층"]),
        ("1층 디스카운트", "floor_1층", truth["floor_factors"]["1층"]),
    ]


def extract(fit: dict, key: str) -> tuple[float, float] | None:
    """적합 결과에서 (추정값, 표준오차)를 꺼낸다."""
    if key == "walk":
        lw = fit["linear_walk"]
        return lw["coef"], lw["se"]
    if key == "gangnam":
        t = next((t for t in fit["terms"] if t["name"] == "gangnam_min"), None)
        return (t["coef"], t["se"]) if t else None
    if key == "log_area":
        la = fit["stage1"]["log_area"]
        return (la["coef"], la["se"]) if la else None
    if key == "month_pct":
        v = fit["stage1"]["month_trend_pct"]
        # 월 추세는 월별 더미의 기울기라 단일 SE가 없다. 보수적으로 0.05%p 를 쓴다.
        return (v, 0.05) if v is not None else None
    if key.startswith("floor_"):
        band = key.split("_", 1)[1]
        t = next((f for f in fit["stage1"]["floor_terms"] if f["band"] == band), None)
        return (t["coef"], t["se"]) if t and t["se"] > 0 else None
    return None


def scalar_check(fit: dict, truth: dict, walk_estimand: float) -> tuple[int, int]:
    print("\n파라미터 복원 검증")
    print(f"  {'파라미터':<20} {'참값':>10} {'추정값':>10} {'SE':>9} {'t(차이)':>8}  판정")
    passed = total = 0
    for label, key, true_v in targets(truth, walk_estimand):
        got = extract(fit, key)
        if got is None:
            print(f"  {label:<20} {true_v:>10.5f} {'—':>10} {'—':>9} {'—':>8}  건너뜀")
            continue
        est, se = got
        total += 1
        t = (est - true_v) / se if se > 0 else float("inf")
        ok = abs(t) < T_THRESHOLD
        passed += ok
        print(f"  {label:<20} {true_v:>10.5f} {est:>10.5f} {se:>9.5f} "
              f"{t:>+8.2f}  {PASS if ok else FAIL}")
    return passed, total


def residual_check(fit: dict, truth: dict) -> bool:
    """추정 잔차 r̂_c 가 시드의 참 u_c 를 되찾는가."""
    import numpy as np

    u = truth["u_c"]
    pairs = [
        (u[str(r["complex_id"])], r["residual"], r["residual_shrunk_pct"])
        for r in fit["residuals"]
        if str(r["complex_id"]) in u
    ]
    if len(pairs) < 5:
        print("\n단지 고유효과 복원: 표본 부족")
        return False

    true_u = np.array([p[0] for p in pairs])
    raw = np.array([p[1] for p in pairs])
    shrunk = np.log1p(np.array([p[2] for p in pairs]) / 100.0)

    corr = float(np.corrcoef(true_u, raw)[0, 1])
    slope_raw = float(np.polyfit(true_u, raw, 1)[0])
    slope_shrunk = float(np.polyfit(true_u, shrunk, 1)[0])

    ok = corr > 0.85
    print(f"\n단지 고유효과 복원 (n={len(pairs)})")
    print(f"  corr(r̂_c, u_c) = {corr:.3f}   {PASS if ok else FAIL} (기준 > 0.85)")
    print(f"  기울기 원본   = {slope_raw:.3f}  (1에 가까워야 함)")
    print(f"  기울기 축소   = {slope_shrunk:.3f}  (1보다 작아야 정상 — 축소가 걸린 증거)")
    if slope_shrunk >= slope_raw:
        print("  ! 축소값 기울기가 원본보다 크거나 같습니다. 축소가 안 걸렸을 수 있습니다.")
    return ok


def coverage_check(reps: int, months: int, base_seed: int, truth: dict) -> bool:
    """RNG seed 만 바꿔 재생성·재적합 — 95% CI 가 추정 대상을 포함하는 비율.

    지리(단지·역·도보거리)는 고정하고 가격만 다시 뽑는다. 따라서 추정 대상도 고정이다.
    """
    import numpy as np

    print(f"\n커버리지 검증 ({reps}회 재생성)")
    with SessionLocal() as db:
        rows = hedonic.load_rows(db, months=months)
        if not rows:
            print("  DB에 거래가 없습니다.")
            return False
        meta = {r["complex_id"]: r for r in rows}
        with SessionLocal() as db2:
            specs = seed_demo.load_specs(db2, random.Random(0))

    true_walk = estimand_walk(specs, months, truth, meta)

    hits = fails = 0
    widths = []
    for i in range(reps):
        rng = random.Random(base_seed + 1000 + i)
        trades, _ = seed_demo.generate(rng, specs, months, date.today(), truth)
        rows = []
        for t in trades:
            base = meta.get(t["complex_id"])
            if base is None:
                continue
            rows.append({**base, **t, "build_year": t["build_year"]})
        try:
            fit = hedonic.fit(rows, spec="M2", ref_year=truth["ref_year"])
        except Exception as exc:
            print(f"  [{i}] 적합 실패: {exc}")
            fails += 1
            continue
        lw = fit["linear_walk"]
        lo, hi = lw["coef"] - 1.96 * lw["se"], lw["coef"] + 1.96 * lw["se"]
        widths.append(hi - lo)
        hits += lo <= true_walk <= hi
        if (i + 1) % 10 == 0:
            print(f"  ...{i + 1}/{reps}  누적 포함 {hits}")

    done = reps - fails
    rate = hits / done if done else 0.0
    ok = 0.88 <= rate <= 1.0
    print(f"  추정 대상(estimand) = {true_walk:+.5f}")
    print(f"  95% CI 포함: {hits}/{done} = {rate:.1%}   {PASS if ok else FAIL} (기준 88~100%)")
    if widths:
        print(f"  CI 평균 폭 = {float(np.mean(widths)):.5f}")
    if rate < 0.88:
        print("  ! 커버리지 미달 — 표준오차가 과소추정되고 있을 수 있습니다(샌드위치/가중치 점검).")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--spec", default="M2")
    parser.add_argument("--coverage", type=int, default=0, help="재생성 횟수(0이면 생략)")
    args = parser.parse_args()

    if not hedonic.available():
        print("모델 의존성이 없습니다. pip install -r requirements.txt")
        return 1

    truth = load_truth()

    with SessionLocal() as db:
        rows = hedonic.load_rows(db, months=args.months)
    if not rows:
        print("거래가 없습니다. `python -m scripts.seed_demo --recreate-schema` 먼저 실행하세요.")
        return 1

    fit = hedonic.fit(rows, spec=args.spec, ref_year=truth["ref_year"])

    meta = {r["complex_id"]: r for r in rows}
    with SessionLocal() as db:
        specs = seed_demo.load_specs(db, random.Random(0))
    walk_estimand = estimand_walk(specs, args.months, truth, meta)

    print(f"시드 {truth['seed']} · 단지 {fit['n_complexes']}곳 · 거래 {fit['n_obs']}건 "
          f"· 스펙 {fit['spec']}")
    print(f"Stage2 R²={fit['r2']}  τ={fit['tau']} ({fit['tau_pct']}%)   "
          f"Stage1 within-R²={fit['stage1']['within_r2']}")

    passed, total = scalar_check(fit, truth, walk_estimand)
    resid_ok = residual_check(fit, truth)

    cov_ok = True
    if args.coverage:
        cov_ok = coverage_check(args.coverage, args.months, truth["seed"], truth)

    all_ok = passed == total and resid_ok and cov_ok
    print(f"\n{'=' * 52}")
    print(f"스칼라 {passed}/{total} · 잔차 {'OK' if resid_ok else 'FAIL'}"
          + (f" · 커버리지 {'OK' if cov_ok else 'FAIL'}" if args.coverage else ""))
    print("전체 판정:", PASS if all_ok else FAIL)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
