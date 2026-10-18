"""매매·전세·월세 탭의 가격 수준이 표본 개편에 끊기지 않았는지.

사용법:
    python -m scripts.verify_tenure

## 왜 있나

R-ONE 평균 매매가격은 2021-07 표본 개편으로 한 달 새 18% 뛴다(13개 구 평균). 처음에 그대로 써서
'같은 집 월 비용' 이 그 달 한꺼번에 뛰었고, 오류 없이 그림만 틀렸다. 그래서 수준을 마지막 달 한
점에서 지수로 거슬러 낸다(`tenure.chained`). 이 검사는 셋을 본다.

1. 이어 붙인 값이 **마지막 달에는 원래 평균가와 같다** — 거스르는 기준점이 맞나.
2. 이어 붙인 매매가·전세가에 한 달 새 `JUMP` 넘는 변화가 없다.
3. **걸려야 할 때 걸리나** — 원래 평균가(개편 전후를 그대로 이은 것)를 넣으면 2번이 잡아야 한다.
   못 잡으면 문턱이 너무 높아 2번이 아무것도 안 보는 셈이다.

## 문턱 8%

실제 시장에서 13개 구 평균이 한 달에 가장 크게 움직인 것은 이어 붙인 값으로 전세 −5.1%
(2023-01, 금리 급등 직후)다. 개편 튐은 매매 +18%·전세 +21% 라 그 사이 8% 에 둔다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import tenure as T  # noqa: E402

JUMP = 0.08


def worst_jump(rows: list[tuple[str, float, float]]) -> tuple[float, str]:
    out = (0.0, "")
    for a, b in zip(rows, rows[1:]):
        for i in (1, 2):
            g = abs(b[i] / a[i] - 1)
            if g > out[0]:
                out = (g, b[0])
    return out


def main() -> int:
    bad = 0
    with SessionLocal() as db:
        lv = T._load(db, T.LEVELS, by_sgg=True)
        ix = T._load(db, T.INDICES, by_sgg=True)
    sggs, months = T._panel(lv)
    isggs, imonths = T._panel(ix)
    use = [s for s in sggs if s in isggs]
    months = [m for m in months if m in imonths]
    rows = T.chained(lv, ix, use, months)

    last = months[-1]
    raw_sale = sum(lv["avg_sale_price"][s][last] for s in use) / len(use) / 10
    gap = abs(rows[-1][1] - raw_sale)
    print(f"  {len(use)}개 구 · {months[0]}~{last} — 마지막 달 원래 평균가와 차이 {gap:.2e}만원")
    bad += gap > 1e-6

    g, ym = worst_jump(rows)
    print(f"  이어 붙인 값의 한 달 최대 변화 {g:.1%} ({ym}) — 문턱 {JUMP:.0%}")
    bad += g > JUMP

    raw = [(m, sum(lv["avg_sale_price"][s][m] for s in use) / len(use) / 10,
            sum(lv["avg_sale_price"][s][m] * lv["jeonse_ratio"][s][m] / 100 for s in use) / len(use) / 10)
           for m in months]
    g, ym = worst_jump(raw)
    caught = g > JUMP
    print(f"  자체 시험(원래 평균가의 개편 튐을 잡나) — {'잡음' if caught else '못 잡음'}: {g:.1%} ({ym})")
    bad += not caught

    print(f"\n{'통과' if not bad else '실패'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
