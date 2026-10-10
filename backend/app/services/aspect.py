"""향에 따른 가격 — **호가로** 잰다.

**지금 화면에서 쓰이지 않는다.** 향 카드를 만들었다가 뺐기 때문이다(경위는
docs/ui-log.md). `/api/analysis/aspect` 엔드포인트는 남아 있지만 프론트에서
호출하지 않는다.

지우지 않은 이유는 **측정이 자산이기 때문**이다. 칸 안에서만 비교해야 교란이
빠진다는 것, 부트스트랩 신뢰구간이 한 칸짜리 그룹에서 퇴화한다는 것, 이 표본의
검출 한계가 ±0.78~0.85%p 라는 것을 여기서 쟀다. 호가를 더 모아 다시 볼 때
처음부터 하지 않으려고 남긴다.

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

from random import Random
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


# 부트스트랩을 돌리기 위한 최소 칸 수. 이보다 적으면 재분배할 것이 없어 구간이
# 의미를 잃는다. "몇 칸이면 충분한가" 는 **이 숫자가 아니라 구간이** 답한다.
MIN_CELLS = 5

# **무리마다도** 최소 칸이 필요하다. 안 두면 칸 1개짜리 무리의 구간이 **한 점으로
# 무너진다** — 어느 부트스트랩 표본에서든 그 칸의 값 하나뿐이라 분산이 0이 된다.
#
# 실제로 당했다. 북향이 칸 1개·매물 1건이었는데 구간이 [+5.40, +5.40] 으로 나와
# '유의' 판정을 받았다. 매물 한 건을 통계적 사실로 보고할 뻔했다. 구간이 좁다는 것이
# 확실하다는 뜻이 아니라, **퍼질 거리가 없다**는 뜻이었다.
#
# 5칸 미만인 무리는 값은 보여 주되 구간과 판정을 내지 않는다. 숨기지 않는 이유:
# 북향이 1건이라는 사실 자체가 정보다(광고에 북향을 안 적는다는 뜻이기도 하다).
GROUP_MIN_CELLS = 5

# 부트스트랩 반복. 2,000이면 95% 구간이 소수 둘째 자리에서 안정된다(재 봤다 —
# 1,000 과 5,000 사이에서 구간 폭이 0.05%p 안에서만 움직였다).
BOOTSTRAP = 2000

# 잡고 싶은 크기. 향 프리미엄이 이보다 작으면 실무에서 쓸 일이 없다 — 같은 평형
# 호가가 1% 안에서 오가는 것은 흥정 범위다. 이 값으로 "몇 칸이 더 필요한가" 를 낸다.
TARGET_FLOOR = 1.0

# 난수를 고정한다. 같은 데이터에 같은 구간이 나와야 "어제보다 좁아졌다" 가 데이터가
# 늘어서인지 주사위 탓인지 가려진다.
SEED = 20260101


def _median(v):
    return median(v) if v else None


def _bootstrap(cell_devs: list[dict], groups: list[str]) -> dict[str, tuple[float, float]]:
    """칸을 **통째로** 복원추출해 무리별 중위의 95% 구간을 낸다.

    칸 단위로 뽑는 이유: 한 칸 안의 매물들은 서로 독립이 아니다. 같은 단지·같은
    평형이고, 중개사도 겹친다. 매물 단위로 뽑으면 표본이 실제보다 많은 척하게 되고
    구간이 거짓으로 좁아진다.
    """
    rng = Random(SEED)
    n = len(cell_devs)
    draws: dict[str, list[float]] = {g: [] for g in groups}
    for _ in range(BOOTSTRAP):
        picked = [cell_devs[rng.randrange(n)] for _ in range(n)]
        for g in groups:
            vals = [c[g] for c in picked if g in c]
            if vals:
                draws[g].append(median(vals))
    out = {}
    for g, v in draws.items():
        if len(v) < BOOTSTRAP * 0.5:  # 그 무리가 거의 안 뽑히면 구간을 말하지 않는다
            continue
        v.sort()
        out[g] = (v[int(len(v) * 0.025)], v[int(len(v) * 0.975)])
    return out


def _pairs(cells_by_group: dict, groups: list[str]) -> list[dict]:
    """두 향을 **같은 칸에 함께 있을 때만** 짝지어 비교한다.

    왜 '칸 중위 대비' 로는 모자란가. 그 값은 각 무리를 **칸 전체의 중위**와 견준
    것이라, 두 무리를 서로 빼면 그 사이에 낀 다른 무리의 영향이 섞인다. 둘만 들어
    있는 칸에서 직접 빼면 그게 없다. 같은 단지·같은 평형에서 남향과 서향을 나란히
    놓고 부르는 값을 견주는 셈이라, 묻고 싶은 것에 바로 답한다.

    짝이 3칸 미만이면 구간을 내지 않는다 — 부트스트랩이 퍼질 거리가 없어 구간이
    한 점으로 무너진다(북향 1칸이 `[+5.40, +5.40]` 으로 '유의' 가 났던 것과 같은 함정).
    """
    rng = Random(SEED)
    out = []
    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            d = [
                median(v[a]) - median(v[b])
                for v in cells_by_group.values()
                if a in v and b in v
            ]
            row = {"a": a, "b": b, "label": f"{a}향 − {b}향", "cells": len(d)}
            if len(d) >= 3:
                boots = sorted(
                    median([d[rng.randrange(len(d))] for _ in d])
                    for _ in range(BOOTSTRAP)
                )
                lo, hi = boots[int(BOOTSTRAP * 0.025)], boots[int(BOOTSTRAP * 0.975)]
                row.update({
                    "diff": round(median(d), 2),
                    "lo": round(lo, 2),
                    "hi": round(hi, 2),
                    "sig": bool(lo > 0 or hi < 0),
                })
            else:
                row.update({"diff": round(median(d), 2) if d else None,
                            "lo": None, "hi": None, "sig": False})
            out.append(row)
    return out


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

    # 칸마다 '그 칸의 중위' 를 뺀 값. 부트스트랩이 칸을 통째로 뽑아야 하므로
    # 무리별 목록이 아니라 **칸별 묶음**으로 들고 있는다.
    cell_devs: list[dict] = []
    counts: dict[str, int] = {}
    quotes_in: dict[str, int] = {}
    for gs in mixed.values():
        base = median([x for v in gs.values() for x in v])
        row = {}
        for g, v in gs.items():
            row[g] = median(v) - base
            counts[g] = counts.get(g, 0) + 1
            quotes_in[g] = quotes_in.get(g, 0) + len(v)
        cell_devs.append(row)

    present = [g for g in ORDER if counts.get(g)]
    ci = _bootstrap(cell_devs, present) if len(cell_devs) >= MIN_CELLS else {}

    groups = []
    for g in present:
        vals = [c[g] for c in cell_devs if g in c]
        thin = counts[g] < GROUP_MIN_CELLS
        lo, hi = (None, None) if thin else ci.get(g, (None, None))
        groups.append({
            "group": g,
            "label": f"{g}향",
            "cells": counts[g],
            "n": quotes_in[g],
            # 중위를 쓴다. 호가에는 터무니없는 값이 섞이고 평균은 그것에 끌려간다 —
            # 이 저장소가 적정가에 중앙값을 쓰는 것과 같은 이유다.
            "vs_cell": round(_median(vals), 2),
            "lo": round(lo, 2) if lo is not None else None,
            "hi": round(hi, 2) if hi is not None else None,
            # 구간이 0 을 건너지 않으면 '잡혔다'. 내가 정한 칸 수가 아니라 **데이터가**
            # 정한다 — 단, 칸이 너무 적은 무리는 구간 자체를 내지 않는다.
            "sig": bool(lo is not None and (lo > 0 or hi < 0)),
            "thin": thin,
        })

    detected = any(x["sig"] for x in groups)

    # 검출 한계 — 지금 표본으로 잡을 수 있는 가장 작은 차이. 구간 반폭의 중위다.
    # 칸이 적은 무리는 **뺀다**. 폭 0짜리 구간이 섞이면 한계가 거짓으로 작아진다
    # (북향 1칸이 끼었을 때 ±0.6%p 로 나왔는데, 빼고 재니 ±0.78%p 였다).
    halves = [(x["hi"] - x["lo"]) / 2 for x in groups if x["lo"] is not None]
    floor = _median(halves)

    # **얼마나 더 모아야 하나.** 구간 폭은 칸 수의 제곱근에 반비례하므로,
    # 한계를 target 까지 좁히려면 칸이 (floor/target)^2 배 필요하다. 추정이지만
    # "더 모으면 되나요" 에 숫자로 답할 수 있는 유일한 길이다.
    need = None
    if floor and floor > TARGET_FLOOR and len(cell_devs) >= MIN_CELLS:
        need = int(len(cell_devs) * (floor / TARGET_FLOOR) ** 2)

    # **단지 수**가 관건이다. 재 봤다 — 같은 단지에서 매물을 더 담아도 칸은 거의
    # 안 는다(그 단지의 평형 수만큼이 상한이고, 한 평형에 향이 하나뿐인 곳도 많다).
    # 실측: 매물 81건 · 단지 6곳에서 섞인 칸이 6개, 즉 **단지당 1개꼴**이었다.
    # 그래서 "몇 건 더"가 아니라 "몇 곳 더"로 안내한다.
    cx_all = {k[0] for k in cells}
    cx_mixed = {k[0] for k in mixed}
    per_complex = (len(cell_devs) / len(cx_mixed)) if cx_mixed else None
    complexes_needed = (
        int(need / per_complex) if (need and per_complex) else None
    )

    # 짝 비교. 구간을 낼 수 있는 무리끼리만 — 칸이 1개인 무리를 짝에 넣으면
    # 거기서도 구간이 한 점으로 무너진다.
    solid = [g for g in present if counts[g] >= GROUP_MIN_CELLS]
    pairs = _pairs(mixed, solid) if len(solid) >= 2 else []

    return {
        "groups": groups,
        "pairs": pairs,
        "n_quotes": len(rows),
        "n_scored": scored,
        "n_complexes": len(cx_all),
        "n_complexes_mixed": len(cx_mixed),
        "complexes_needed": complexes_needed,
        "n_cells": len(cell_devs),
        "min_cells": MIN_CELLS,
        "detected": detected,
        "floor_pct": round(floor, 2) if floor is not None else None,
        "target_floor_pct": TARGET_FLOOR,
        "cells_needed": need,
        "months": months,
        "empty": False,
    }
