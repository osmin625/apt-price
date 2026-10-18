"""거시 합산 모델의 대안을 **같은 백테스트로** 견준다 — 바꾸기 전에 이것으로 잰다.

사용법:
    python -m scripts.cv_macro                 # 변형 다섯과 조합 하나, 요인 목록 둘
    python -m scripts.cv_macro --lags          # 시차 공급을 시차마다 — 고른 시차가 우연인지

## 왜 필요한가

합산 모델(2026-10-18 까지 거시 분석 맨 위 카드, 지금은 화면에서 뺐다)은 요인마다 (상관 부호 × z)를 같은 무게로 평균해 점수
하나를 만들고 직선 하나를 맞춘다. 표본이 작아서다 — 12개월 창이 이웃 달과 11개월을
공유해 독립된 관측은 해마다 하나 남짓이다. 그래서 "더 나은 합치는 법" 은 짐작이 아니라
표본 밖 오차로 정해야 하고, 그 차이가 우연과 구분되는지도 같이 봐야 한다.

## 무엇을 재나

운영 코드와 **같은 백테스트**다. 매달 그때 결과가 알려진 달만(그 달 + 12개월 ≤ 예측
시점)으로 상관 부호·평균·표준편차·기울기를 처음부터 다시 맞추고 그 달을 예측한다.
학습 60개월 미만은 건너뛴다. 먼저 V0 이 기록된 숫자(docs/analysis/macro-model.md)를 내는지
찍는다 — 틀이 틀리면 나머지 비교가 다 틀린다. 운영 코드에서 모델을 걷은 뒤로는 이 파일이
그 방식의 유일한 구현이다.

    V0  지금 방식 — 요인마다 같은 무게
    V1  그룹 먼저 — 공급·수요·통화량·금리 안에서 평균한 뒤 그룹끼리 같은 무게(이중 계산 걷기)
    V2  밸류에이션 항 — 가격지수가 지난 60개월 로그 평균보다 몇 % 위인가를 요인으로 더함
    V3  시차 공급 — 공급(또는 준공 물량)의 24개월 전 값을 요인으로 더함
    V4  |r| 가중 — 부호 대신 학습 표본 상관의 크기로 무게
    V1+V2

요인 목록은 둘이다 — 지금 화면과 같은 '공급' 판, 예전 '준공 물량' 판. 공급은 적정
공급(2013년~)에 묶여 계열이 늦게 시작해 학습 기간까지 바뀐다.

## 읽는 법

변형마다 자기 창이 다르므로(시차를 두면 시작이 늦어진다) **모든 변형이 예측을 낸 같은
달**로 견준다. RMSE 가 낮을수록 낫다. 'DM' 은 Diebold–Mariano 검정이다 — 두 예측의 제곱오차
차이가 0 인가를, 겹치는 창의 자기상관을 Newey–West(바틀렛, 11개월)로 감안해 본다. t 가
음수면 앞쪽이 낫다. 독립 관측이 해마다 하나 남짓이라 **p 는 거칠다** — 0.05 근처를 경계로
쓰지 말고, 시차·시기를 바꿔도 같은 쪽으로 나오는지를 같이 본다(`--lags`).

결과와 판단은 docs/analysis/macro-model.md 에 조건(날짜·DB)과 함께 적는다.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import regime as R  # noqa: E402

# 운영 모델의 '준공 물량' 정의(2026-10-18 에 '공급' 으로 바뀌기 전). 비교용으로만 둔다.
DONE = R.Factor("done", "공급", "준공 물량", "done", "41", "경기", "roll12_log", "",
                "새 아파트가 더 많이 입주했다")
# '공급판' 의 공급 — 12개월 준공 ÷ 적정(2026-10-18). 화면은 2026-10-19 에 '누적 공급' 으로
# 바뀌었지만 기록(macro-model.md)은 이 정의로 쟀으므로 여기서 고정한다. `R.FACTORS` 를 그대로
# 쓰면 화면이 바뀔 때마다 재현 숫자가 조용히 달라진다.
SUPPLY12 = R.Factor("supply", "공급", "공급", "done", "41", "경기", "vs_adequate", "%",
                    "적정 공급보다 더 지었다(100 이 적정)")
VALUATION_WINDOW = 60
LEAD_MONTHS = 24
NW_LAG = 11  # 12개월 창이 겹쳐 오차가 11개월까지 자기상관을 가진다
# 합산 모델의 두 상수. 모델이 regime 에 있던 때의 값 그대로다(2026-10-18 에 걷었다).
MIN_R = 0.15           # |상관| 이 이보다 작은 요인은 뺀다
MODEL_MIN_TRAIN = 60   # 학습 표본이 이보다 적은 시점은 예측하지 않는다(5년)


@dataclass(frozen=True)
class Col:
    key: str
    group: str
    series: dict


def shift(s: dict, months: int) -> dict:
    """s'(t) = s(t − months). 그 달에 이미 알려진 과거 값만 쓴다."""
    out = {}
    for ym, v in s.items():
        k = int(ym[:4]) * 12 + int(ym[4:]) - 1 + months
        out[f"{k // 12}{k % 12 + 1:02d}"] = v
    return out


def valuation(price: dict, win: int = VALUATION_WINDOW) -> dict:
    """가격지수가 지난 `win` 개월 로그 평균보다 몇 % 위인가. 그 달까지의 값만 쓴다."""
    ks = sorted(price)
    lp = [math.log(price[k]) for k in ks]
    return {ks[i]: (lp[i] - sum(lp[i - win + 1:i + 1]) / win) * 100
            for i in range(win - 1, len(ks))}


def backtest(cols: list[Col], price: dict, agg: str) -> dict:
    """합산 모델의 백테스트. `agg` 만 갈아 끼운다(equal | group | absr)."""
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    common = sorted(set.intersection(*[set(c.series) for c in cols]) & set(price))
    rows = [{"ym": ym, "x": [c.series[ym] for c in cols], "y": R._fwd12(price, yms, idx[ym])}
            for ym in common]
    lab = [r for r in rows if r["y"] is not None]
    hist = [sorted(c.series.items()) for c in cols]
    groups = [c.group for c in cols]

    def ref_at(ym):
        mus, sds = [], []
        for h in hist:
            vs = [v for k, v in h if k <= ym]
            mu = sum(vs) / len(vs)
            mus.append(mu)
            sds.append(math.sqrt(sum((v - mu) ** 2 for v in vs) / len(vs)) or 1.0)
        return mus, sds

    def fit(train, ref):
        p = len(train[0]["x"])
        ys = [r["y"] for r in train]
        mu, sd = ref
        rs = [R._corr([r["x"][j] for r in train], ys) for j in range(p)]
        use = [j for j in range(p) if abs(rs[j]) >= MIN_R]

        def score(x):
            if not use:
                return 0.0
            c = {j: (1 if rs[j] > 0 else -1) * (x[j] - mu[j]) / sd[j] for j in use}
            if agg == "equal":
                return sum(c.values()) / len(use)
            if agg == "absr":
                w = sum(abs(rs[j]) for j in use)
                return sum(abs(rs[j]) * c[j] for j in use) / w
            if agg == "group":
                g: dict[str, list[float]] = {}
                for j in use:
                    g.setdefault(groups[j], []).append(c[j])
                return sum(sum(v) / len(v) for v in g.values()) / len(g)
            raise ValueError(agg)

        sc = [score(r["x"]) for r in train]
        n = len(train)
        ms, my = sum(sc) / n, sum(ys) / n
        var = sum((v - ms) ** 2 for v in sc)
        b = sum((v - ms) * (y - my) for v, y in zip(sc, ys)) / var if var else 0.0
        return (lambda x: my + b * (score(x) - ms)), [cols[j].key for j in use]

    preds, means = {}, {}
    for t in lab:
        train = [q for q in lab if idx[q["ym"]] + 12 <= idx[t["ym"]]]
        if len(train) < MODEL_MIN_TRAIN:
            continue
        f, _ = fit(train, ref_at(t["ym"]))
        preds[t["ym"]] = (f(t["x"]), t["y"])
        means[t["ym"]] = (sum(q["y"] for q in train) / len(train), t["y"])
    now = rows[-1]
    known = [q for q in lab if idx[q["ym"]] + 12 <= idx[now["ym"]]]
    f, used = fit(known, ref_at(now["ym"]))
    return {"preds": preds, "means": means, "now": now["ym"], "pred_now": f(now["x"]),
            "used_now": used, "start": common[0]}


def rmse(ps: dict, keys: list[str]) -> float:
    return math.sqrt(sum((ps[k][0] - ps[k][1]) ** 2 for k in keys) / len(keys))


def hit(ps: dict, keys: list[str]) -> float:
    return sum(1 for k in keys if (ps[k][0] > 0) == (ps[k][1] > 0)) / len(keys) * 100


def dm(pa: dict, pb: dict, keys: list[str], lag: int = NW_LAG) -> tuple[float, float]:
    """Diebold–Mariano(제곱오차). (t, 양측 p). t 가 음수면 A 가 낫다."""
    d = [(pa[k][0] - pa[k][1]) ** 2 - (pb[k][0] - pb[k][1]) ** 2 for k in keys]
    n = len(d)
    m = sum(d) / n

    def g(h):
        return sum((d[i] - m) * (d[i - h] - m) for i in range(h, n)) / n

    v = g(0) + 2 * sum((1 - h / (lag + 1)) * g(h) for h in range(1, lag + 1))
    if v <= 0:
        return float("nan"), float("nan")
    t = m / math.sqrt(v / n)
    return t, math.erfc(abs(t) / math.sqrt(2))


def factor_sets(db) -> dict[str, dict[str, Col]]:
    fs = [SUPPLY12 if f.key == "supply" else f for f in R.FACTORS]
    base = {f.key: Col(f.key, f.group, R.series_of(db, f)) for f in fs}
    done = {"done": Col("done", "공급", R.series_of(db, DONE)),
            **{k: v for k, v in base.items() if k != "supply"}}
    return {"공급판": base, "준공판": done}


def run_variants(price: dict, sets: dict) -> None:
    val = Col("val60", "가격", valuation(price))
    for name, cols in sets.items():
        sup = "supply" if "supply" in cols else "done"
        lead = Col(f"{sup}_lag{LEAD_MONTHS}", "공급", shift(cols[sup].series, LEAD_MONTHS))
        cl = list(cols.values())
        variants = {
            "V0 지금 방식": (cl, "equal"),
            "V1 그룹 먼저": (cl, "group"),
            "V2 밸류에이션 항": (cl + [val], "equal"),
            f"V3 시차 공급({LEAD_MONTHS}m)": (cl + [lead], "equal"),
            "V4 |r| 가중": (cl, "absr"),
            "V1+V2": (cl + [val], "group"),
        }
        out = {k: backtest(c, price, a) for k, (c, a) in variants.items()}
        v0 = out["V0 지금 방식"]
        own = sorted(v0["preds"])
        print(f"\n[재현 확인] {name} V0 자기 창 {len(own)}개월({own[0]}~) RMSE {rmse(v0['preds'], own):.2f}"
              f" · 과거 평균 {rmse(v0['means'], own):.2f} · 지금 예상 {v0['pred_now']:+.2f}"
              f"  ← macro-model.md 의 기록과 같아야 한다")
        keys = sorted(set.intersection(*[set(o["preds"]) for o in out.values()]))
        print(f"== {name} — 같은 달 {len(keys)}개({keys[0]}~{keys[-1]})")
        print(f"  {'변형':<18}{'시작':>8}{'RMSE':>7}{'평균':>7}{'적중%':>6}{'지금':>8}"
              f"   vs V0 (t, p)    vs 과거 평균 (t, p)")
        for k, o in out.items():
            ps = o["preds"]
            t0, p0 = dm(ps, v0["preds"], keys) if o is not v0 else (float("nan"), float("nan"))
            tm, pm = dm(ps, o["means"], keys)
            print(f"  {k:<18}{o['start']:>8}{rmse(ps, keys):>7.2f}{rmse(o['means'], keys):>7.2f}"
                  f"{hit(ps, keys):>6.0f}{o['pred_now']:>+8.2f}   ({t0:+.2f}, {p0:.2f})"
                  f"    ({tm:+.2f}, {pm:.2f})")
    a, b = (backtest(list(c.values()), price, "equal")["preds"] for c in sets.values())
    keys = sorted(set(a) & set(b))
    t, p = dm(b, a, keys)
    names = list(sets)
    print(f"\n== V0 끼리 — {names[1]} vs {names[0]}, 같은 달 {len(keys)}개: "
          f"RMSE {rmse(b, keys):.2f} vs {rmse(a, keys):.2f} · DM t {t:+.2f} p {p:.2f}")


def run_lags(price: dict, cols: dict) -> None:
    """시차 공급(준공 물량)을 시차마다. 한 시차에서만 들으면 고른 값이 우연을 탄 것이다."""
    cl = list(cols.values())
    runs = {"V0": backtest(cl, price, "equal")}
    for lag in (6, 12, 18, 24, 30, 36):
        runs[f"+준공 {lag}m"] = backtest(
            cl + [Col(f"done_lag{lag}", "공급", shift(cols["done"].series, lag))], price, "equal")
    keys = sorted(set.intersection(*[set(o["preds"]) for o in runs.values()]))
    print(f"\n== 시차 공급(준공판) — 같은 달 {len(keys)}개({keys[0]}~{keys[-1]})")
    for k, o in runs.items():
        t, p = dm(o["preds"], runs["V0"]["preds"], keys) if k != "V0" else (float("nan"), float("nan"))
        print(f"  {k:<12} RMSE {rmse(o['preds'], keys):5.2f} · 과거 평균 {rmse(o['means'], keys):5.2f}"
              f" · 지금 {o['pred_now']:+.2f} · vs V0 t {t:+.2f} p {p:.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="거시 합산 모델 대안 백테스트")
    ap.add_argument("--lags", action="store_true", help="시차 공급을 시차마다 견준다")
    args = ap.parse_args()
    with SessionLocal() as db:
        price = R.price_series(db)
        sets = factor_sets(db)
    if args.lags:
        run_lags(price, sets["준공판"])
    else:
        run_variants(price, sets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
