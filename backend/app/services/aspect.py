"""향에 따른 가격 — **호가로** 잰다.

## 왜 모델이 아니라 호가인가

국토교통부 실거래에는 **향이 없다.** 그래서 헤도닉 계수로는 향 효과를 추정할 길이
없고, 추정할 수 없는 것을 요인으로 넣으면 다른 계수가 그 자리를 대신 먹는다.

향이 적혀 있는 유일한 자료는 사용자가 붙여넣은 **매물(호가)** 이다. 그래서 여기서만
잰다. 대신 그게 무엇인지 화면에 분명히 적는다 — 이것은 '거래된 값' 이 아니라
'부르는 값' 이다.

## 무엇과 비교하나

호가를 그냥 평균 내면 안 된다. 남향 매물이 마침 비싼 단지에 몰려 있으면 '남향이
비싸다' 가 나오는데 그건 단지 효과다. 동 위치 카드를 뺀 이유가 바로 그 교란이었다.

그래서 **적정가 대비 괴리율**(`gap_pct`)을 쓴다. 적정가는 그 매물과 **같은 단지·같은
평형**의 실거래를 모아 시점과 층을 보정한 값이라, 단지·평형·층·시점이 이미 빠져 있다.
남는 차이를 향으로 읽는다.

    괴리율 = (호가 - 적정가) / 적정가

남향 매물의 괴리율 중위가 +2%, 북향이 -3% 라면 '같은 조건에서 남향을 2% 더 비싸게
부르고 북향은 3% 싸게 부른다' 가 된다.

## 그래도 인과는 아니다

- 호가는 **받고 싶은 값**이지 받은 값이 아니다. 남향을 비싸게 불러도 안 팔릴 수 있다.
- 향이 적힌 매물만 들어온다. 안 적는 쪽에 치우침이 있으면 그대로 들어온다.
- 표본이 작다. 무리마다 건수를 같이 내보내고, 화면에서 그 수를 보여 준다.
"""

from __future__ import annotations

from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Quote

# 좋은 쪽부터. 프론트의 `rankSelect.js` 와 **같은 순서**여야 한다 — 두 곳이 다른
# 순서를 쓰면 같은 매물이 화면마다 다른 무리에 들어간다.
ORDER = ["남", "동", "서", "북"]

# 한 무리를 하나의 값으로 말하려면 최소 몇 건이 필요한가. 3건으로 "남향이 +5%" 라고
# 적으면 그 숫자가 혼자 걸어다닌다. 적은 무리도 **숨기지는 않고** 건수와 함께 내보내되
# 화면이 흐리게 그린다.
MIN_N = 5


def group_of(aspect: str | None) -> str | None:
    """향 → 무리. 두 글자면 **나쁜 쪽**을 남긴다.

    매물을 올리는 쪽은 조금이라도 걸치면 좋은 쪽을 함께 적는 경향이 있다. '남서향' 은
    대개 서향에 남쪽이 조금 걸친 집이다. 그래서 좋은 쪽을 떼고 나쁜 쪽을 무리로 본다.

        남서 -> 서   남동 -> 동   북서 -> 북   북동 -> 북
    """
    if not aspect:
        return None
    t = str(aspect).strip().removesuffix("향")
    found = [c for c in t if c in ORDER]
    if not found:
        return None
    return max(found, key=ORDER.index)


# 한 무리를 말하려면 **칸이** 몇 개 필요한가. 칸 = (단지·평형)이다.
# 5칸으로 "남향 +0.7%" 라고 적으면 그 숫자가 혼자 걸어다닌다.
MIN_CELLS = 20


def by_aspect(db: Session, evaluate, months: int) -> dict:
    """향 무리별 가격 차이. `evaluate` 는 호가 목록을 받아 적정가를 매기는 함수다.

    ## 단지를 넘어서 비교하지 않는다 — 재 보고 알았다

    처음에는 향 무리별로 괴리율 중위를 그냥 냈다. 그랬더니 이렇게 나왔다.

        남향 -4.7%p   동향 +6.3%p   서향 +14.3%p   (전체 중위 대비)

    '서향이 제일 비싸다' 는 말이 되는데, 향의 좋고 나쁨과 정반대다. 들여다보니
    **서향 25건 중 18건(72%)이 한 단지**(신나무실휴먼시아)였다. 그 단지의 호가가
    적정가보다 높게 붙어 있었고, 그게 '서향 프리미엄' 으로 둔갑한 것이다.

    같은 **(단지·평형)** 칸 안에서만 비교하니 방향이 뒤집혔다.

        남향 +0.70%p   동향 +0.60%p   서향 -0.75%p

    동 위치 카드를 뺀 것과 **같은 함정**이다. 거기서도 단지 안에서만 비교하면 2.5%가
    나왔는데 평형을 통제하니 사라졌다. 적정가가 단지·평형·층·시점을 통제한다고 해도,
    그건 '그 칸의 실거래 대비' 일 뿐 **칸마다 호가가 얼마나 공격적인지**까지는 빼 주지
    않는다. 그래서 칸 안에서 비교한다.

    ## 어떻게 재나

    1. 호가마다 적정가 대비 괴리율을 낸다(순위표와 **같은 함수**로).
    2. `(단지, 반올림 평형)` 으로 칸을 만든다.
    3. 향이 **둘 이상 섞인 칸만** 쓴다. 한 가지뿐인 칸은 비교할 상대가 없다.
    4. 칸 안에서 '그 칸의 중위' 를 뺀다. 이걸로 칸마다의 호가 성향이 사라진다.
    5. 무리별로 그 값들의 중위를 낸다.

    ## 적다고 숨기지 않고, 적다고 말한다

    칸이 적으면 수치를 내되 **검출되지 않았다**고 적는다. 0짜리 막대를 그리면 '향은
    가격과 무관' 으로 읽히는데, 실제로는 '이 표본으로는 잴 수 없다' 이다.
    """
    rows = db.execute(select(Quote).where(Quote.aspect != "")).scalars().all()
    if not rows:
        return {
            "groups": [],
            "n_quotes": 0,
            "n_cells": 0,
            "detected": False,
            "months": months,
            "empty": True,
        }

    payload = [
        {
            "quote_id": q.id,
            "complex_id": q.complex_id,
            "dong": q.dong or None,
            "exclusive_area": q.exclusive_area,
            "floor": q.floor or None,
            "asking_price": q.asking_price,
            "aspect": q.aspect,
        }
        for q in rows
    ]
    out = evaluate(payload)

    # (단지, 반올림 평형) -> 무리 -> 괴리율들
    cells: dict[tuple, dict[str, list[float]]] = {}
    scored = 0
    for item in out.get("items", []):
        g = group_of(item.get("aspect"))
        gap = item.get("gap_pct")
        if not g or gap is None:
            continue
        scored += 1
        key = (item["complex_id"], round(item["exclusive_area"]))
        cells.setdefault(key, {}).setdefault(g, []).append(float(gap))

    # 향이 둘 이상 섞인 칸만. 한 가지뿐이면 비교할 상대가 없다.
    mixed = {k: v for k, v in cells.items() if len(v) >= 2}
    devs: dict[str, list[float]] = {}
    for gs in mixed.values():
        base = median([x for v in gs.values() for x in v])
        for g, v in gs.items():
            devs.setdefault(g, []).append(median(v) - base)

    groups = []
    for g in ORDER:
        v = devs.get(g) or []
        if not v:
            continue
        groups.append({
            "group": g,
            "label": f"{g}향",
            "cells": len(v),
            "n": sum(len(x) for k, gs in mixed.items() for gg, x in gs.items() if gg == g),
            # 중위를 쓴다. 호가에는 터무니없는 값이 섞이고 평균은 그것에 끌려간다 —
            # 이 저장소가 적정가에 중앙값을 쓰는 것과 같은 이유다.
            "vs_cell": round(median(v), 2),
            "thin": len(v) < MIN_CELLS,
        })

    enough = bool(groups) and min(x["cells"] for x in groups) >= MIN_CELLS

    return {
        "groups": groups,
        "n_quotes": len(rows),
        "n_scored": scored,
        "n_cells": len(mixed),
        "min_cells": MIN_CELLS,
        "detected": enough,
        "months": months,
        "empty": False,
    }
