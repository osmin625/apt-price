"""`verify_absorb` 의 실패 감지가 **실제로 걸리는지** 시험한다.

사용법:
    python -m scripts.verify_guard

## 왜 이 시험이 따로 있나

검사를 넣어 놓고 **안 걸리면 없는 것과 같다.** 실제로 한 번 그랬다.

지난번 가드는 try/except 였는데, 실제 실패가 예외를 던지지 않아 안 걸렸다. 넣어 놓고
안 걸리면 없는 것과 같으므로, 이번에는 실패 모양을 직접 만들어 넣어 본다.

재현한 실패 모양은 실제로 겪은 것이다:
  - LAPACK `init_gesdd failed init` → 계수에 NaN 이 섞임
  - 계수가 0 으로 뭉개져 적합이 나빠짐(walk 계수 0.000000 이 그랬다)
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

import numpy as np  # noqa: E402

import verify_absorb as V  # noqa: E402

SHAPE = (116919, 2055)
cases = [
    ("정상", np.array([1.0, -2.0, 0.5]), 100.0, 100.0, False),
    ("부동소수 오차만큼 다름", np.array([1.0, -2.0]), 100.0000001, 100.0, False),
    ("허용 오차 안(0.5%)", np.array([1.0, -2.0]), 100.5, 100.0, False),
    ("NaN 섞임", np.array([1.0, np.nan, 0.5]), 100.0, 100.0, True),
    ("inf 섞임", np.array([1.0, np.inf]), 100.0, 100.0, True),
    ("계수가 0 으로 뭉개짐(RSS 악화)", np.array([0.0, 0.0]), 180.0, 100.0, True),
    ("조금 악화(2%)", np.array([1.0, -2.0]), 102.0, 100.0, True),
]

print(f"{'경우':<26}{'잡혀야 하나':>11}{'잡혔나':>8}  판정")
ok = True
for name, params, rss_d, rss_a, should_raise in cases:
    try:
        V.check_dummy_fit(params, rss_d, rss_a, SHAPE)
        raised = False
        msg = ""
    except V.DummyPathFailed as exc:
        raised = True
        msg = str(exc)[:60]
    good = raised == should_raise
    ok &= good
    print(f"{name:<26}{'O' if should_raise else 'X':>11}{'O' if raised else 'X':>8}  "
          f"{'통과' if good else '실패'}")
    if raised and good:
        print(f"    → {msg}...")

print("\n전부 통과" if ok else "\n실패한 경우가 있습니다")
sys.exit(0 if ok else 1)
