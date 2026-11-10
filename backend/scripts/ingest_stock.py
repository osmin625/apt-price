"""주식 지수 일봉(stock.db)과 그 무위험 금리(macro.db)를 받는다.

    python -m scripts.ingest_stock            # 전부 처음부터(덮어쓰기라 두 번 돌려도 같다)

받는 것은 `app/stock/indices.py` 의 지수와, 각 지수의 무위험 금리 중 macro.db 에 아직 없는
계열(FRED `us_tbill3m`). 한국은행 기준금리는 `ingest_macro` 가 받는다.

## 받은 값을 그대로 믿지 않는다

받을 때마다 본다. 걸리면 그 지수는 쓰지 않고 [X] 로 끝난다.

- 종가가 양수인가
- **하루 로그 변화가 ±25% 를 넘지 않는가.** KOSPI·S&P 500 의 역대 최대 하루 낙폭이 -12% 안팎
  (1987·2008·2020)이다. 이걸 넘으면 시장이 아니라 자료가 틀렸다 — 단위 바뀜(지수 리베이스),
  다른 계열이 섞임, 소수점 밀림 같은 것
- 마지막 날짜가 오늘에서 너무 멀지 않은가는 검진 신선도가 본다(`checkup.py` 의 `STALE`)
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.macro import store as macro_store  # noqa: E402
from app.macro.clients import fred  # noqa: E402
from app.stock import store  # noqa: E402
from app.stock.indices import INDICES, fetch  # noqa: E402

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
        for name in fred.SERIES:
            t0 = time.perf_counter()
            try:
                pts = with_retry(lambda name=name: fred.fetch_monthly(name), name)
            except Exception as exc:  # noqa: BLE001
                print(f"  [X] {name:<12} {exc}")
                bad += 1
                continue
            n = macro_store.upsert(mdb, [{"series": name, "freq": "M", "period": p, "value": v,
                                          "unit": u, "source": "FRED"} for p, v, u in pts])
            mdb.commit()
            print(f"      {name:<12} {n:>5}달  {pts[0][0]}~{pts[-1][0]}  FRED"
                  f"  {time.perf_counter() - t0:.1f}s")

    print("\n이상 없음" if not bad else f"\n[X] 실패 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
