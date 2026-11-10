"""공식 출처로 받은 지수 종가를 비공식 출처(야후 파이낸스 차트)와 맞춰 본다.

    python -m scripts.probe_stock_crosscheck

## 왜

KOSPI 는 한국은행 ECOS, S&P 500 은 FRED 에서 받는다. 둘 다 공식이지만 **우리가 고른 계열
코드가 정말 그 지수인가**는 받은 숫자만 봐서는 모른다(ECOS 의 같은 표에 KOSDAQ 이 나란히
있다). 다른 길로 받은 같은 날 종가와 견주면 잘못 고른 계열·단위·날짜 밀림이 드러난다.

비공식 출처는 **대조용**이다(합의: 공식 우선). 그래서 네트워크를 쓰는 `probe_*` 로 두고 검진이
찾는 `verify_*` 로 두지 않는다 — 야후가 막히면 우리 검진이 실패해서는 안 된다.

기준: 겹치는 날 전부에서 상대 차이 0.1% 이내. 지수 종가는 반올림 자리만 다를 뿐 같아야 한다.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock import store  # noqa: E402
from app.stock.indices import INDICES  # noqa: E402

YAHOO = {"kospi": "%5EKS11", "spx": "%5EGSPC"}
TOL = 0.001


def yahoo(sym: str) -> dict[str, float]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))["chart"]["result"][0]
    off = d["meta"].get("gmtoffset", 0)
    closes = d["indicators"]["quote"][0]["close"]
    out = {}
    for ts, c in zip(d["timestamp"], closes):
        if c is None:
            continue
        day = dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).strftime("%Y%m%d")
        out[day] = float(c)
    return out


def main() -> int:
    bad = 0
    for ix in INDICES:
        ours = dict(store.daily(ix.market, ix.symbol))
        try:
            theirs = yahoo(YAHOO[ix.id])
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] {ix.label:<8} 야후를 못 받았습니다 — {exc}")
            continue
        common = sorted(set(ours) & set(theirs))
        if len(common) < 200:
            print(f"  [X] {ix.label:<8} 겹치는 날이 {len(common)}일뿐 — 날짜가 밀렸을 수 있다")
            bad += 1
            continue
        diffs = [(abs(ours[d] / theirs[d] - 1), d) for d in common]
        worst, day = max(diffs)
        over = sum(1 for x, _ in diffs if x > TOL)
        mark = "  " if not over else "[X]"
        print(f"  {mark} {ix.label:<8} 겹친 {len(common)}일 · 최대 차이 {worst * 100:.3f}% ({day}: "
              f"우리 {ours[day]:.2f} · 야후 {theirs[day]:.2f}) · {TOL * 100:.1f}% 넘는 날 {over}일")
        bad += bool(over)
    print("\n이상 없음" if not bad else f"\n[X] 어긋난 지수 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
