"""고정효과 흡수(within transformation) 검증.

## 무엇을 검증하나

Stage 1 은 단지 더미 497개를 설계행렬에 직접 넣는다(28,451 × 528). 이걸 그룹 평균
차감으로 바꾸면 열이 31개로 줄어 39배 빨라지는데, **결과가 같아야** 의미가 있다.

Frisch-Waugh-Lovell 정리가 보장하는 것은 **기울기 계수**가 같다는 것뿐이다.
이 프로젝트는 거기서 멈추지 않고 단지 수준 α̂_c 와 그 표준오차까지 쓰므로,
그 둘을 따로 확인해야 한다. se(α̂_c) 는 Stage 2 가중치·τ²·EB 수축에 모두 들어가서
틀리면 최종 계수까지 조용히 흔든다.

## 검사 항목

1. **기울기 계수** — 면적·층·월·동거리. FWL 이 보장하므로 1e-10 수준에서 같아야 한다.
2. **α̂_c** — 단지 수준. 흡수 방식에서는 잔차의 그룹 평균으로 복원한다.
3. **se(α̂_c)** — 더미 표준오차 대신 공식으로 계산하므로 **정확히 같을 수 없다**.
   상대오차와 상관계수를 보고 Stage 2 결과가 흔들리지 않는지로 판정한다.
4. **Stage 2 계수** — 최종적으로 화면에 나가는 값. 여기가 같으면 실용적으로 안전하다.
5. **속도**.

## 실행

    python -m scripts.verify_absorb            # 24개월
    python -m scripts.verify_absorb --months 36
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import statsmodels.api as sm

from app.db import SessionLocal
from app.services import hedonic
from app.services.hedonic import FLOOR_REF, _knots, _spline_cols


class DummyPathFailed(RuntimeError):
    """더미 회귀가 **수치적으로** 실패했다 — 모델이 틀린 것이 아니다."""


def build_parts(df):
    """Stage 1 설계행렬을 '더미'와 '나머지'로 나눠 만든다."""
    cx = pd.get_dummies(df["complex_id"].astype(str), prefix="cx", dtype=float)

    acols: dict[str, list[float]] = {}
    area_terms = _spline_cols(
        acols, "log_area", df["log_area"], _knots(df["log_area"].astype(float).to_numpy())
    )
    parts = [pd.DataFrame(acols, index=df.index)]

    dw = df["dong_walk_min"]
    dev = (dw - dw.groupby(df["complex_id"]).transform("mean")).fillna(0.0)
    parts.append(pd.DataFrame({"dong_walk_dev": dev.astype(float)}, index=df.index))

    # 직거래 더미. `_fit_stage1` 과 **같은 조건**으로 넣어야 한다 — 설계가 다르면
    # 이 검증이 '같은 모델의 두 계산법' 비교가 아니게 된다.
    if "is_direct" in df.columns and float(df["is_direct"].sum()) > 0:
        parts.append(pd.DataFrame(
            {"deal_direct": df["is_direct"].astype(float)}, index=df.index
        ))

    fb = pd.get_dummies(df["floor_band"], prefix="fb", dtype=float).drop(
        columns=[f"fb_{FLOOR_REF}", "fb_정보없음"], errors="ignore"
    )
    parts.append(fb)

    mo = pd.get_dummies(df["deal_ym"], prefix="ym", dtype=float).drop(
        columns=[f"ym_{df['deal_ym'].max()}"], errors="ignore"
    )
    parts.append(mo)

    Z = pd.concat(parts, axis=1)
    return cx, Z, area_terms


def fit_dummy(df, cx, Z):
    """현재 방식 — 더미를 행렬에 직접 넣는다."""
    X = pd.concat([cx, Z], axis=1)
    y = df["log_ppp"].astype(float)
    try:
        res = sm.OLS(y, X).fit(cov_type="HC1")
    except Exception as exc:  # noqa: BLE001
        # LAPACK 이 SVD 초기화에 실패하면 (`init_gesdd failed init`) 뒤따르는
        # 비교가 전부 FAIL 로 찍힌다. 그건 모델이 틀렸다는 뜻이 아니다.
        raise DummyPathFailed(
            f"더미 회귀가 수치적으로 실패했습니다 ({type(exc).__name__}: {exc}). "
            f"설계행렬이 {X.shape[0]:,}×{X.shape[1]:,} 입니다 — "
            f"--max-complexes 를 줄여 다시 돌리세요."
        ) from exc
    cids = [int(c[3:]) for c in cx.columns]
    alpha = pd.Series([float(res.params[c]) for c in cx.columns], index=cids)
    se = pd.Series([float(res.bse[c]) for c in cx.columns], index=cids)
    beta = res.params[Z.columns]
    return res, alpha.sort_index(), se.sort_index(), beta


def fit_absorbed(df, Z):
    """흡수 방식 — 그룹 평균을 뺀 뒤 적합하고 α̂ 를 복원한다.

    α̂_c = mean_c(y - Zβ̂) 이고, 분산은 두 항으로 잡는다.

        Var(α̂_c) = (Σ_{i∈c} e_i²)·dfc / n_c²  +  z̄_c' V(β̂) z̄_c

    앞은 그룹 평균의 강건 분산(HC0 형태 + HC1 자유도 보정), 뒤는 β̂ 불확실성이 옮겨온
    몫이다. 뒤 항은 전체 se 의 절반(중앙 52%)이라 버릴 수 없고, 앞 항에 그룹별 잔차
    대신 공통 σ² 를 쓰면 정답과의 상관이 1.00 에서 0.72 로 떨어진다. 후보 다섯 개를
    재서 고른 형태다.
    """
    gid = df["complex_id"].to_numpy()
    y = df["log_ppp"].astype(float)

    ybar = y.groupby(gid).transform("mean")
    zbar = Z.groupby(gid).transform("mean")
    res = sm.OLS(y - ybar, Z - zbar).fit(cov_type="HC1")
    beta = res.params

    # α̂_c = mean_c(y - Zβ)
    resid_lvl = y - Z.to_numpy() @ beta.to_numpy()
    alpha = resid_lvl.groupby(gid).mean().sort_index()
    e = (resid_lvl - alpha.reindex(gid).to_numpy()).to_numpy()

    # 주의: bincount 의 인덱스는 factorize 의 **등장 순서** 코드이고 alpha 는 정렬돼
    # 있다. 되짚어 맞추지 않으면 단지별 값이 통째로 뒤섞인다(이 검증 중 실제로 겪었다).
    codes, uniq = pd.factorize(gid)
    remap = pd.Series(np.arange(len(uniq)), index=uniq).reindex(alpha.index).to_numpy()
    n_c = np.bincount(codes).astype(float)[remap]
    sum_e2 = np.bincount(codes, weights=e**2)[remap]

    n, k, g = len(df), Z.shape[1], len(uniq)
    dfc = n / max(n - k - g, 1)
    zbar_c = Z.groupby(gid).mean().sort_index().to_numpy()
    V = res.cov_params().to_numpy()
    quad = np.maximum(np.einsum("ij,jk,ik->i", zbar_c, V, zbar_c), 0.0)
    se = pd.Series(np.sqrt(sum_e2 * dfc / n_c**2 + quad), index=alpha.index)
    return res, alpha, se, beta


def stage2_from(alpha_tbl, spec_key="M2"):
    knots = {}
    # 연속 요인이 늘면 여기에도 넣어야 한다. `hedonic.fit` 의 매듭 루프와 **같은**
    # 목록이어야 하는데, 한 번 어긋나서 top_floor 가 빠졌고 Stage 2 가 KeyError 로
    # 죽었다. 4·5번 검사가 통째로 돌지 않았는데 `| tail` 이 종료 코드를 가려
    # '통과' 처럼 보였다.
    for var in ("walk_min", "gangnam_min", "age", "log_households", "top_floor",
                "elem_dist", "mid_dist", "academy", "adult"):
        if var in alpha_tbl.columns and alpha_tbl[var].notna().any():
            knots[var] = _knots(alpha_tbl[var].dropna().astype(float).to_numpy())
    return hedonic._fit_stage2(alpha_tbl, hedonic.SPECS[spec_key], knots)


def rel(a, b):
    denom = np.maximum(np.abs(a), 1e-12)
    return float(np.max(np.abs(a - b) / denom))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--spec", default="M2")
    ap.add_argument(
        "--max-complexes", type=int, default=900,
        help="더미 설계행렬이 메모리에 들어가도록 단지 수를 제한한다 (0 = 전부)",
    )
    args = ap.parse_args()

    with SessionLocal() as db:
        rows = hedonic.load_rows(db, months=args.months)
    df = hedonic._build_frame(rows, date.today().year)

    # 단지를 줄인다. 흡수 항등식은 **어떤 부분표본에서도** 성립하므로 전수가 아니어도
    # 검증이 된다. 반면 비용은 단지 수에 비례해 폭발한다 — 더미 설계행렬이
    # 11.7만 × 2,055 면 float64 로 1.9GB 이고, SVD 가 그 사본을 여러 개 만든다.
    #
    # 전수로 돌렸을 때 실제로 `init_gesdd failed init`(LAPACK SVD 초기화 실패)이
    # 났고, 그 결과가 [FAIL] 네 줄로 찍혔다. **메모리 부족이 정확성 실패처럼
    # 보였다.** 그래서 기본값을 줄이고, 실패하면 실패 이유를 말하게 했다.
    if args.max_complexes:
        keep = sorted(df["complex_id"].unique())[: args.max_complexes]
        df = df[df["complex_id"].isin(set(keep))].reset_index(drop=True)
    cx, Z, _ = build_parts(df)
    print(f"거래 {len(df):,} · 단지 {cx.shape[1]} · 설계행렬 "
          f"{len(df):,}×{cx.shape[1] + Z.shape[1]} → 흡수 후 {len(df):,}×{Z.shape[1]}\n")

    t0 = time.perf_counter(); r_d, a_d, s_d, b_d = fit_dummy(df, cx, Z); t_d = time.perf_counter() - t0
    t0 = time.perf_counter(); r_a, a_a, s_a, b_a = fit_absorbed(df, Z); t_a = time.perf_counter() - t0

    ok = True

    # 1) 기울기 계수 — FWL 이 보장
    d_beta = float(np.max(np.abs(b_d.to_numpy() - b_a.reindex(b_d.index).to_numpy())))
    p1 = d_beta < 1e-8
    ok &= p1
    print(f"[{'PASS' if p1 else 'FAIL'}] 1. 기울기 계수 {Z.shape[1]}개 최대 절대차 {d_beta:.2e} (<1e-8)")

    # 2) α̂_c
    d_alpha = float(np.max(np.abs(a_d.to_numpy() - a_a.to_numpy())))
    p2 = d_alpha < 1e-8
    ok &= p2
    print(f"[{'PASS' if p2 else 'FAIL'}] 2. α̂_c {len(a_d)}개 최대 절대차 {d_alpha:.2e} (<1e-8)")

    # 3) se(α̂_c) — 공식이 다르므로 근사 일치만 요구
    r_se = rel(s_d.to_numpy(), s_a.to_numpy())
    corr = float(np.corrcoef(s_d.to_numpy(), s_a.to_numpy())[0, 1])
    med = float(np.median(s_a.to_numpy() / s_d.to_numpy()))
    p3 = corr > 0.99 and 0.9 < med < 1.1
    ok &= p3
    print(f"[{'PASS' if p3 else 'FAIL'}] 3. se(α̂_c) 상관 {corr:.4f} (>0.99) · "
          f"비율 중앙 {med:.4f} (0.9~1.1) · 최대 상대차 {r_se:.1%}")

    # 4) Stage 2 계수 — 실제로 화면에 나가는 값
    base = df.groupby("complex_id").agg(
        complex_name=("complex_name", "first"), sgg_cd=("sgg_cd", "first"),
        sgg_name=("sgg_name", "first"), umd_nm=("umd_nm", "first"),
        line=("line", "first"), trade_count=("log_ppp", "size"),
        walk_min=("walk_min", "first"), dong_walk_mean=("dong_walk_min", "mean"),
        gangnam_min=("gangnam_min", "first"), age=("age", "first"),
        log_households=("log_households", "first"), lat=("lat", "first"),
        lng=("lng", "first"), ppp_median=("log_ppp", "median"),
        top_floor=("top_floor", "first"), brand=("brand", "first"),
        elem_dist=("elem_dist", "first"), mid_dist=("mid_dist", "first"),
        academy=("academy", "first"), adult=("adult", "first"),
    ).reset_index()
    base["ppp_median"] = np.exp(base["ppp_median"])

    t_d2 = base.assign(alpha=a_d.to_numpy(), se_alpha=s_d.to_numpy())
    t_a2 = base.assign(alpha=a_a.to_numpy(), se_alpha=s_a.to_numpy())
    m_d = stage2_from(t_d2, args.spec)
    m_a = stage2_from(t_a2, args.spec)
    cd = {t["name"]: t["coef"] for t in m_d["terms"]}
    ca = {t["name"]: t["coef"] for t in m_a["terms"]}
    shared = [k for k in cd if k in ca]
    worst, wname = 0.0, ""
    for k in shared:
        d = abs(cd[k] - ca[k]) / max(abs(cd[k]), 1e-6)
        if d > worst:
            worst, wname = d, k
    p4 = worst < 0.02
    ok &= p4
    print(f"[{'PASS' if p4 else 'FAIL'}] 4. Stage 2 계수 {len(shared)}개 최대 상대차 "
          f"{worst:.2%} (<2%, 최악 '{wname}')")

    lw_d = m_d["linear_walk"]["coef"]; lw_a = m_a["linear_walk"]["coef"]
    print(f"        도보 선형계수 {lw_d:.6f} vs {lw_a:.6f} "
          f"({(np.exp(lw_d)-1)*100:+.3f}%/분 vs {(np.exp(lw_a)-1)*100:+.3f}%/분)")

    # 5) 속도
    print(f"\n[속도] 더미 {t_d:.2f}s → 흡수 {t_a:.2f}s  ({t_d/max(t_a,1e-9):.1f}배)")

    print("\n" + ("전부 통과 — 흡수 방식으로 교체해도 안전합니다."
                  if ok else "실패 항목이 있습니다. 교체하면 안 됩니다."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
