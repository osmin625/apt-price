"""지수 분석의 영향 막대가 참값을 되찾는지 — 합성 자료에 정해 둔 영향을 심고 다시 잰다.

## 왜

막대가 '뚜렷함(초록·빨강)' 이라고 말하려면 95% 범위가 정말 95% 범위여야 한다. 달마다 1년 창을 재면
이웃 달이 11개월씩 겹쳐, 보통 표준오차로는 범위가 거짓으로 좁아지고 관계없는 지표도 뚜렷하게
뜬다(`app/stock/effects.py` 머리말). 눈으로는 안 보이는 실패라 참값을 아는 자료로 잰다 — 부동산 모델의
'참값을 심어 생성(seed_demo)' 과 같은 생각이다.

## 무엇을

1. **덮는 비율.** 지표 월 변화가 AR(1)로 움직이고, 지수 월 수익률 = β × 지표 월 변화 + 잡음. 그러면
   1년 수익률의 1년 변화 기울기가 β 다. 300개월(KOSPI 쯤)·120개월(S&P 500 의 10년) 각각, 시드 여럿에서
   95% 범위가 β 를 덮는 비율이 90% 이상인가
2. **헛짚음.** β=0 이면 '뚜렷함' 이 10% 이하인가. 처음 쓴 Newey–West 는 17%·21% 였다(effects.py 머리말)
3. **걸리는가.** 겹침을 무시하면(시차 0) 1 이 무너져야 한다 — 검사 안에서 직접 바꿔 본다
4. **발표 시차.** 시차 1 지표의 '그 뒤' 수익률이 t+1 에서 시작하는가(값으로 확인)
5. **받는 곳.** `indicators.py` 의 지표가 모두 제 출처의 표(`ecos.TABLES`·`fred.SERIES`)에 있고 짝이 아는
   지표만 가리키는가. 빠지면 그 막대는 오류 없이 '표본이 짧아 재지 않음' 으로 뜬다

DB 없이 돈다(numpy·scipy 는 requirements 에 있다).
"""

from __future__ import annotations

NEEDS_DB = False  # 합성 자료로 돈다

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import effects as E  # noqa: E402

SEEDS = 200


def synth(beta: float, seed: int, months: int) -> tuple[dict[str, float], dict[str, float]]:
    """(지표 수준 — 금리 같은 %, 월말 종가)."""
    rng = random.Random(seed)
    level, px, d = 3.0, 1000.0, 0.0
    ind, close = {}, {}
    ym = "199001"
    for _ in range(months):
        d = 0.6 * d + rng.gauss(0, 0.15)          # 지표 월 변화(%p) — 이어지는 경향
        level += d
        px *= math.exp(beta * d + rng.gauss(0.005, 0.05))
        ind[ym], close[ym] = level, px
        ym = E._shift(ym, 1)
    return ind, close


def coverage(beta: float, months: int, lag: int | None = None) -> tuple[float, float]:
    """(95% 범위가 β 를 덮는 비율, '뚜렷함' 비율). lag 를 주면 그 시차로 잰다(깨 보기용)."""
    cover = sig = 0
    for s in range(SEEDS):
        ind, close = synth(beta, s, months)
        ps = E.pairs(E.movement("diff", ind), close, "same", 0)
        (b,), (se,), c = E.ols_hh([[p[1]] for p in ps], [p[2] for p in ps],
                                  lag=E.LAG if lag is None else lag)
        lo, hi = b - c * se, b + c * se
        cover += lo <= beta <= hi
        sig += lo > 0 or hi < 0
    return cover / SEEDS, sig / SEEDS


def main() -> int:
    bad = 0

    def check(ok: bool, what: str) -> None:
        nonlocal bad
        print(f"  {'OK  ' if ok else 'FAIL'} {what}")
        bad += not ok

    for months in (300, 120):
        cov, _ = coverage(-0.08, months)
        check(cov >= 0.90, f"{months}개월 β=−0.08 — 95% 범위가 참값을 덮는 비율 {cov:.0%} (90% 이상)")
        _, fp = coverage(0.0, months)
        check(fp <= 0.10, f"{months}개월 β=0 — '뚜렷함' 으로 뜨는 비율 {fp:.0%} (10% 이하)")

    # 걸리는가: 겹침을 무시하면 무너져야 한다. 안 무너지면 1 은 아무것도 못 보는 검사다.
    naive, _ = coverage(-0.08, 300, lag=0)
    check(naive < 0.7, f"겹침을 무시하면(시차 0) 덮는 비율이 무너지는가 — {naive:.0%} (70% 아래여야 검사가 본다)")

    # 발표 시차: 종가를 달마다 다르게 두고 시작 달을 값으로 확인한다.
    close = {E._shift("200001", k): 100.0 * (1.01 ** k) * (1 + (k % 7) / 100) for k in range(40)}
    x = {"200006": 1.0}
    p0 = E.pairs(x, close, "after3", 0)[0][2]
    p1 = E.pairs(x, close, "after3", 1)[0][2]
    want1 = math.log(close[E._shift("200007", 3)] / close["200007"])
    check(abs(p1 - want1) < 1e-12 and abs(p0 - p1) > 1e-6,
          "발표 시차 1 — '그 뒤 3개월' 이 다음 달(200007)에서 시작한다")

    from app.macro.clients import ecos, fred
    from app.stock.indicators import BY_ID, INDICATORS, PAIRS

    table = {"ECOS": ecos.TABLES, "FRED": fred.SERIES}
    lost = [i.id for i in INDICATORS if i.id not in table[i.source]]
    check(not lost, f"지표가 모두 제 출처의 표에 있다{' — 빠짐: ' + ', '.join(lost) if lost else ''}")
    stray = [i for ids in PAIRS.values() for i in ids if i not in BY_ID]
    check(not stray, f"짝이 아는 지표만 가리킨다{' — 모름: ' + ', '.join(stray) if stray else ''}")

    # 상식의 방향은 카드의 기준이다 — 빠지거나 ±1 이 아니면 '상식대로·반대' 가 조용히 틀린다.
    odd = [i.id for i in INDICATORS if i.expect not in (1, -1) or not i.why.strip()]
    check(not odd, f"지표마다 상식의 방향(±1)과 이유가 있다{' — 빠짐: ' + ', '.join(odd) if odd else ''}")
    # 미국이 먼저다(2026-11-12 요청) — 지수도, 지수마다의 지표도(FRED 가 ECOS 앞).
    from app.stock.indices import INDICES
    order_ok = INDICES[0].market == "US" and all(
        (us := [BY_ID[i].source == "FRED" for i in ids]) == sorted(us, reverse=True) for ids in PAIRS.values())
    check(order_ok, "미국 지수·지표가 앞에 있다")
    from app.stock.service import _agree
    got = [_agree({"verdict": v}, e) for v, e in (("pos", 1), ("neg", 1), ("neg", -1), ("none", -1))]
    check(got == ["yes", "no", "yes", "unclear"] and _agree(None, 1) is None,
          "상식과 맞는지 — 뚜렷할 때만 맞다·반대, 범위가 0 을 넘으면 뚜렷하지 않음")

    print("\n이상 없음" if not bad else f"\n[X] 실패 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
