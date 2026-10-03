"""API 가 내보내는 적합 페이로드가 **정말로 JSON 이 되는지** 검사한다.

사용법:
    python -m scripts.verify_payloads

## 왜 필요한가

적합 dict 는 캐시에 오래 살아 있고, 계산하는 쪽이 파생값을 거기에 붙인다.
`fit_index` 가 붙이는 `_index` 가 실제로 그랬다 — 이름 목록에 없어서 응답에 그대로
실렸고, 그 안의 NaN 때문에 `/api/model/fit` 이 500 을 냈다.

고약한 점은 **두 번째 요청부터** 터졌다는 것이다. 거리 모델을 처음 열 때는 `_index`
가 아직 없어 멀쩡하고, 매물 분석이나 순위가 같은 적합을 한 번 집어 가면 그때 붙는다.
한 번만 호출해 보는 검사로는 못 잡는다.

그래서 이 검사는 **순서를 만든다**: 적합 → 페이로드 확인 → 파생값을 붙이는 호출 →
페이로드 다시 확인 → 디스크 캐시를 거친 뒤 또 확인.

`allow_nan=False` 로 인코딩한다. 파이썬 기본 `json.dumps` 는 NaN 을 `NaN` 이라고
써 버리는데 그건 JSON 이 아니고, FastAPI 는 거부한다.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("FIT_IN_PROCESS", "1")

from app.db import SessionLocal  # noqa: E402
from app.services import model_view as mv  # noqa: E402

MONTHS = 24


def bad_floats(o, path=""):
    """NaN/Inf 가 있는 경로를 전부 찾는다."""
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            yield path or "(root)"
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from bad_floats(v, f"{path}.{k}")
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            yield from bad_floats(v, f"{path}[{i}]")


def check(label: str, payload) -> bool:
    paths = list(bad_floats(payload))
    try:
        json.dumps(payload, allow_nan=False, ensure_ascii=False)
        encodable = True
        why = ""
    except (ValueError, TypeError) as exc:
        encodable = False
        why = str(exc)

    ok = encodable and not paths
    print(f"  [{'OK ' if ok else '실패'}] {label}")
    if paths:
        print(f"         NaN/Inf {len(paths)}곳: {paths[:4]}")
    if not encodable:
        print(f"         인코딩 실패: {why}")
    return ok


def main() -> int:
    ok = True
    with SessionLocal() as db:
        mv._cache.clear()
        fit = mv.get_fit(db, months=MONTHS)

        ok &= check("fit_payload (갓 적합)", mv.fit_payload(fit))
        ok &= check("factor_payload", mv.factor_payload(fit))
        ok &= check("map_payload", mv.map_payload(db, fit))

        # 파생 조회표를 붙이는 경로들. 여기서 붙은 것이 새어 나가면 안 된다.
        side = {"complex_id": int(fit["alpha"]["complex_id"].iloc[0]),
                "exclusive_area": 84.9, "floor": 10, "dong": None}
        mv.model_price(db, fit, side)
        other = dict(side, exclusive_area=59.9, floor=3)
        mv.compare_listings(db, fit, side, other)
        print(f"  (파생값이 붙었나: {'_index' in fit})")

        ok &= check("fit_payload (파생값이 붙은 뒤)", mv.fit_payload(fit))
        ok &= check("factor_payload (파생값이 붙은 뒤)", mv.factor_payload(fit))

        # 디스크 캐시를 한 바퀴 돌고 와도 같아야 한다.
        key = mv._cache_key(db, MONTHS, mv.hedonic.DEFAULT_SPEC)
        mv._disk_store(key, fit)
        back = mv._disk_load(key)
        if back is None:
            print("  [실패] 디스크 캐시를 다시 읽지 못했습니다")
            ok = False
        else:
            ok &= check("fit_payload (디스크 왕복 후)", mv.fit_payload(back))

    print(f"\n{'통과' if ok else '실패'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
