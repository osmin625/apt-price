"""반영 분해를 이론 시차로 / 같은 달로 나란히 — docs/analysis/macro-model.md '반영 분해' 의 숫자를 다시 낸다.

사용법:
    python -m scripts.cv_reflect

방향(`Factor.sign`)과 시차(`Factor.lag`)는 측정 전에 이론으로 정했다(2026-10-19). 이 스크립트는
시차를 모두 0(같은 달)으로 바꾼 판을 옆에 놓아, 시차가 무엇을 바꿨는지 보인다. 시차를 **고르는**
도구가 아니다 — 여기서 결과를 보고 시차를 바꾸면 '우연을 탄 시차'(macro-model.md '합치는 법을
바꿔 봤다' 의 24개월)와 같은 함정이다.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import regime as R  # noqa: E402


def show(name: str, o: dict) -> None:
    print(f"\n== {name} — {o['from']}~{o['to']} ({o['months']}개월) · R² {o['r2']} · 평균일 때 {o['base']:+.2f}%"
          f" · 맞춘 값 {o['fitted']:+.2f}% · 실제 {o['actual']:+.2f}% · 설명 안 됨 {o['residual']:+.2f}%p")
    print(f"  {'요인':<14}{'방향':>4}{'시차':>5}{'크기':>7}{'흔들림 10~90%':>16}{'0 비율':>8}{'위치 z':>8}{'반영 %p':>9}")
    for f in o["factors"]:
        print(f"  {f['label']:<14}{'+' if f['sign'] > 0 else '−':>4}{f['lag']:>5}{f['b']:>7.2f}"
              f"{f['b_lo']:>8.2f}~{f['b_hi']:<7.2f}{f['zero_pct']:>7}%{f['z']:>+8.2f}{f['contrib']:>+9.2f}")
    for h in o["halves"]:
        print(f"  {h['from']}~{h['to']} R² {h['r2']}: " + " · ".join(f"{k} {v}" for k, v in h["b"].items()))


def main() -> int:
    with SessionLocal() as db:
        show("이론 시차(화면)", R.reflect(db))
        show("같은 달(시차 0)", R.reflect(db, factors=tuple(replace(f, lag=0) for f in R.FACTORS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
