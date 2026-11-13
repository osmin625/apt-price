"""주식 지수 일봉(stock.db)과 그 무위험 금리(macro.db)를 받는다.

    python -m scripts.ingest_stock            # 전부 처음부터(덮어쓰기라 두 번 돌려도 같다)

받는 것은 `app/stock/indices.py` 의 지수, 지수 분석이 견주는 지표(`app/stock/indicators.py` —
한국은행 계열 포함), 장기 투자의 지수 평가 재료(`app/stock/valuation.py` 의 `NEEDS` — ECOS·실러),
FRED 계열 전부(`fred.SERIES`). 매일 06:30 동기화(`sync_static.ps1`)가 부른다.

## 받은 값을 그대로 믿지 않는다

받을 때마다 본다. 걸리면 그 지수는 쓰지 않고 [X] 로 끝난다.

- 종가가 양수인가
- **하루 로그 변화가 ±25% 를 넘지 않는가.** KOSPI·S&P 500 의 역대 최대 하루 낙폭이 -12% 안팎
  (1987·2008·2020)이다. 이걸 넘으면 시장이 아니라 자료가 틀렸다 — 단위 바뀜(지수 리베이스),
  다른 계열이 섞임, 소수점 밀림 같은 것
- 마지막 날짜가 오늘에서 너무 멀지 않은가는 검진 신선도가 본다(`checkup.py` 의 `STALE`)
- **실러 자료(비공식)는 공식 출처와 맞춰 본다** — 주가는 FRED SP500 의 달 평균, 10년 금리는 FRED GS10
  (`shiller_problems`). 어긋나면 넣지 않는다
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.macro import store as macro_store  # noqa: E402
from app.macro.clients import ecos, fred, shiller  # noqa: E402
from app.stock import store  # noqa: E402
from app.stock.indicators import INDICATORS  # noqa: E402
from app.stock.indices import INDICES, fetch  # noqa: E402
from app.stock.valuation import NEEDS  # noqa: E402

MAX_DAILY_LOG = 0.25
RETRIES = 3


def with_retry(fn, what: str):
    """일시 오류는 다시 한다 — K-apt 에서 재시도가 없어 시군구 6곳이 통째로 빠진 적이 있다."""
    for k in range(RETRIES):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — 출처마다 오류 종류가 다르다
            if k == RETRIES - 1:
                raise
            print(f"      {what}: {exc} — {2 ** k}초 뒤 다시")
            time.sleep(2 ** k)


def problems(bars: list[tuple[str, float]]) -> list[str]:
    out = []
    if any(c <= 0 for _, c in bars):
        out.append("0 이하 종가가 있다")
    dates = [d for d, _ in bars]
    if dates != sorted(set(dates)):
        out.append("날짜가 겹치거나 순서가 어긋났다")
    for (d0, c0), (d1, c1) in zip(bars, bars[1:]):
        if c0 > 0 and c1 > 0 and abs(math.log(c1 / c0)) > MAX_DAILY_LOG:
            out.append(f"{d0}→{d1} 하루 {math.log(c1 / c0) * 100:+.1f}% — 자료 오류로 본다")
            break
    return out


def shiller_problems(got: dict[str, list[tuple[str, float]]]) -> list[str]:
    """실러 자료를 공식 출처와 맞춰 본다. 마지막 달은 빼고 본다 — 실러가 그 달 첫 거래일 하나로 채운다(표 각주).

    2026-11-13 에 재 보니 주가는 겹치는 119달 중 117달이 1e-6 안이었다. 0.7% 가 난 2016-11 은 FRED 가 그달
    7일부터라 평균한 날이 다르고, 0.2% 인 2024-01 은 실러 쪽 사정이다. 10년 금리는 882달 중 한 달(2019-07,
    0.43%p)만 어긋났다. 그래서 한도는 **주가 1%·금리 0.05%p 를 넘는 달이 전체의 2% 미만**이다 — 열이 밀리거나
    다른 계열이 들어오면 거의 모든 달이 넘는다.
    """
    out = []
    by_month: dict[str, list[float]] = {}
    for d, c in store.daily("US", "SPX"):
        by_month.setdefault(d[:6], []).append(c)
    avg = {k: sum(v) / len(v) for k, v in by_month.items()}
    p = dict(got["shiller_p"])
    common = sorted(set(p) & set(avg))[:-1]
    if len(common) < 24:
        out.append(f"주가를 맞춰 볼 달이 {len(common)}개뿐 — FRED SP500 을 먼저 받으세요")
    else:
        bad = [k for k in common if abs(p[k] / avg[k] - 1) > 0.01]
        if len(bad) > 0.02 * len(common):
            out.append(f"주가가 FRED 달 평균과 1% 넘게 다른 달 {len(bad)}/{len(common)} — 예: {bad[:3]}")
    g = dict(got["shiller_gs10"])
    f = macro_store.monthly("us_10y")
    common = sorted(set(g) & set(f))[:-1]
    if len(common) < 120:
        out.append(f"10년 금리를 맞춰 볼 달이 {len(common)}개뿐 — FRED GS10 을 먼저 받으세요")
    else:
        bad = [k for k in common if abs(g[k] - f[k]) > 0.05]
        if len(bad) > 0.02 * len(common):
            out.append(f"10년 금리가 FRED GS10 과 0.05%p 넘게 다른 달 {len(bad)}/{len(common)} — 예: {bad[:3]}")
    return out


def main() -> int:
    argparse.ArgumentParser(description="주식 지수 적재").parse_args()
    bad = 0

    with store.writer() as db:
        for ix in INDICES:
            t0 = time.perf_counter()
            try:
                bars = sorted(with_retry(lambda ix=ix: fetch(ix), ix.label))
            except Exception as exc:  # noqa: BLE001
                print(f"  [X] {ix.label:<8} {exc}")
                bad += 1
                continue
            why = problems(bars)
            if why:
                print(f"  [X] {ix.label:<8} 쓰지 않음 — {'; '.join(why)}")
                bad += 1
                continue
            n = store.upsert(db, ix.market, ix.symbol, ix.source, bars)
            db.commit()
            print(f"      {ix.label:<8} {n:>5}일  {bars[0][0]}~{bars[-1][0]}  {ix.source}"
                  f"  {time.perf_counter() - t0:.1f}s")

    with macro_store.writer() as mdb:
        # 지수 분석이 견주는 한국은행 계열(app/stock/indicators.py). ingest_macro 도 받지만 그쪽은
        # 손으로 돌린다 — 매일 06:30 동기화가 이것을 부르므로 여기서도 받아 지표를 새로 유지한다.
        # 덮어쓰기라 두 쪽이 받아도 같다.
        ecos_ids = [ind.id for ind in INDICATORS if ind.source == "ECOS"] + list(NEEDS["ECOS"])
        for sid in dict.fromkeys(ecos_ids):
            t0 = time.perf_counter()
            try:
                pts = with_retry(lambda sid=sid: ecos.fetch(sid), sid)
            except Exception as exc:  # noqa: BLE001
                print(f"  [X] {sid:<12} {exc}")
                bad += 1
                continue
            n = macro_store.upsert(mdb, [{"series": sid, "freq": ecos.TABLES[sid][2], "period": p.ym,
                                          "value": p.value, "unit": p.unit, "source": "ECOS"} for p in pts])
            mdb.commit()
            print(f"      {sid:<12} {n:>5}행  {pts[0].ym}~{pts[-1].ym}  ECOS"
                  f"  {time.perf_counter() - t0:.1f}s")

        for name in fred.SERIES:
            t0 = time.perf_counter()
            try:
                pts = with_retry(lambda name=name: fred.fetch_series(name), name)
            except Exception as exc:  # noqa: BLE001
                print(f"  [X] {name:<12} {exc}")
                bad += 1
                continue
            n = macro_store.upsert(mdb, [{"series": name, "freq": fred.SERIES[name][1], "period": p, "value": v,
                                          "unit": u, "source": "FRED"} for p, v, u in pts])
            mdb.commit()
            print(f"      {name:<12} {n:>5}행  {pts[0][0]}~{pts[-1][0]}  FRED"
                  f"  {time.perf_counter() - t0:.1f}s")

        # 실러 자료는 FRED(SP500·GS10)를 받은 뒤에 받는다 — 그 둘과 맞춰 봐야 해서다.
        t0 = time.perf_counter()
        try:
            got = with_retry(shiller.fetch, "실러")
            why = shiller_problems(got)
        except Exception as exc:  # noqa: BLE001
            got, why = None, [str(exc)]
        if why:
            print(f"  [X] 실러 자료   쓰지 않음 — {'; '.join(why)}")
            bad += 1
        else:
            for name, rows in got.items():
                macro_store.upsert(mdb, [{"series": name, "freq": "M", "period": ym, "value": v,
                                          "unit": shiller.SERIES[name][2], "source": "SHILLER"} for ym, v in rows])
            mdb.commit()
            p = got["shiller_p"]
            print(f"      실러 자료   {len(p):>5}달  {p[0][0]}~{p[-1][0]}  shillerdata.com"
                  f"  {time.perf_counter() - t0:.1f}s")

    print("\n이상 없음" if not bad else f"\n[X] 실패 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
