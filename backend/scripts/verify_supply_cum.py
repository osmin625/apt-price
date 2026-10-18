"""거시 분석의 '누적 공급'(월별)이 공급 분석의 '누적 차이'(연별)와 **같은 값**인지 대조한다.

사용법:
    python -m scripts.verify_supply_cum

## 왜 있나

같은 과부족 누계를 두 곳이 따로 계산한다 — 공급 분석은 해마다(`supply.balance` 의
`gap_cum_smooth`), 거시 분석은 달마다(`regime._cum_adequate`). 한쪽만 고치면(적정의 기준을
단년으로 바꾸거나 시작 해를 옮기면) 두 탭이 같은 '누적 공급' 을 다르게 말한다. 눈으로 보니
같다는 근거가 아니다 — 12월 값이 그 해 누계와 같아야 한다.

허용 오차는 **쌓은 해 수 × 0.5호 + 0.5호**다. 공급 분석은 반올림 전 적정을 쌓은 뒤 누계만
반올림하고, 거시 쪽은 공급 분석이 내놓는 **반올림된** 해별 적정을 받아 쌓는다. 그래서 해마다
최대 0.5호씩 벌어질 수 있다 — 처음 1호로 두었더니 서울에서 1~2호 차이 다섯 해가 걸렸다(2026-10-19).
그보다 크면 계산이 갈린 것이다.

적정이 공표된 해까지만 본다. 그 뒤 달은 거시 쪽이 마지막 해 적정을 이어 쓰고 공급 분석은
누계를 멈추므로 견줄 짝이 없다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import regime, supply  # noqa: E402

ROUND_STEP = 0.5  # 호 — 해별 적정 반올림 한 번의 최대 오차


def compare(yearly: dict[str, int], monthly: dict[str, float], sgg: str, quiet: bool = False) -> int:
    """어긋난 해의 수. 12월 값이 없거나 허용 오차를 넘으면 센다."""
    bad = 0
    for i, (y, v) in enumerate(sorted(yearly.items())):
        m = monthly.get(f"{y}12")
        tol = ROUND_STEP * (i + 1) + ROUND_STEP
        if m is None or abs(m - v) > tol:
            bad += 1
            if not quiet:
                print(f"[X] {sgg} {y}: 공급 분석 {v:,} · 거시 12월 {m if m is None else round(m):,}")
    return bad


def main() -> int:
    bad = 0
    checked = 0
    with SessionLocal() as db:
        for sgg in ("41", "11"):
            yearly = {r["year"]: r["gap_cum_smooth"] for r in supply.balance(db, sgg)["rows"]
                      if r["gap_cum_smooth"] is not None}
            monthly = regime._cum_adequate(db, sgg)
            if not yearly or not monthly:
                print(f"[X] {sgg}: 비어 있습니다 — 연별 {len(yearly)}해 · 월별 {len(monthly)}달")
                bad += 1
                continue
            checked += len(yearly)
            bad += compare(yearly, monthly, sgg)
            print(f"  {sgg}: {len(yearly)}해 대조 ({min(yearly)}~{max(yearly)}) · 월별 {min(monthly)}~{max(monthly)}")
            # 자체 시험 — **걸려야 할 때 걸리는지.** 첫 해 6월부터 100호를 더하면 모든 해가
            # 어긋나야 한다. 그대로일 때 안 걸리는 것은 바로 위의 대조가 보인다.
            first = min(yearly)
            broken = {k: v + (100 if k >= f"{first}06" else 0) for k, v in monthly.items()}
            if compare(yearly, broken, sgg, quiet=True) != len(yearly):
                print(f"[X] {sgg}: 자체 시험 — 100호를 틀어도 다 잡지 못했습니다")
                bad += 1
    print(f"\n{'통과' if not bad else '실패'} — {checked}해 대조, 어긋남 {bad} · 자체 시험(100호 틀기) 포함")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
