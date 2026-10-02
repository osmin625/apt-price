"""호가 누적 — 실거래가 못 잡는 것을 잡는다.

실거래는 **팔린 것만** 남긴다. 값을 못 받는 매도자는 싸게 파는 대신 물건을 거둬들이므로,
거래가 뜸한 동의 관측 거래가는 위로 편향된다. 내려간 물건은 거래가 아니라 호가에만 있다.

그래서 붙여넣기마다 호가를 쌓아, 거래가 뜸한 동의 **선행지표**로 실거래 옆에 놓는다.
실거래를 대체하지 않는다 — 호가는 희망가와 급매가 섞여 있고 성사 여부를 모른다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import pricing
from ..models import Quote

# 이보다 오래된 호가는 '현재 호가' 집계에서 뺀다. 매물은 팔리거나 내려가는데
# 우리는 내려간 걸 알 방법이 없어서, 시간으로 끊는 수밖에 없다.
ACTIVE_DAYS = 90


def record(db: Session, *, complex_id: int, dong: str | None, exclusive_area: float,
           floor: int | None, floor_band: str | None, asking_price: int,
           confirmed_on=None) -> str:
    """호가 하나를 기록한다. 반환값은 'created' | 'seen' — 화면에 알려 주려고 구분한다.

    같은 (단지·동·평형·층·호가) 면 새로 쌓지 않고 마지막 목격 시각만 올린다.
    **가격이 다르면 새 행**이 된다 — 그 변화가 보고 싶은 신호다.
    """
    key = (dong or "").strip().removesuffix("동").strip()
    area_key = pricing.area_type_key(exclusive_area)
    fl = int(floor) if floor else 0

    row = db.execute(
        select(Quote).where(
            Quote.complex_id == complex_id,
            Quote.dong == key,
            Quote.area_key == area_key,
            Quote.floor == fl,
            Quote.asking_price == asking_price,
        )
    ).scalar_one_or_none()

    if row is not None:
        row.last_seen_at = datetime.now()
        row.seen_count += 1
        # 같은 매물이 더 최근에 확인됐다면 그 날짜로 올린다.
        if confirmed_on and (row.confirmed_on is None or confirmed_on > row.confirmed_on):
            row.confirmed_on = confirmed_on
        db.commit()
        return "seen"

    db.add(Quote(
        complex_id=complex_id, dong=key, area_key=area_key,
        exclusive_area=round(float(exclusive_area), 2), floor=fl,
        floor_band=floor_band or pricing.floor_band(floor, None),
        asking_price=int(asking_price),
        confirmed_on=confirmed_on,
    ))
    db.commit()
    return "created"


def summary(db: Session, complex_id: int, area_key: int | None = None) -> dict:
    """단지의 호가 현황. 동별로 나눠 본다 — 그게 이 데이터를 쌓는 이유다.

    평당가는 **전용 기준**이다(이 서비스의 모든 평당가와 같다).
    """
    since = datetime.now() - timedelta(days=ACTIVE_DAYS)
    stmt = select(Quote).where(Quote.complex_id == complex_id, Quote.last_seen_at >= since)
    if area_key is not None:
        stmt = stmt.where(Quote.area_key == area_key)
    records = db.execute(stmt).scalars().all()
    # 값을 내린 집의 **옛 호가는 이미 없는 가격**이다. 함께 집계하면 분포가 위로
    # 끌리는데, 그건 이 데이터를 쌓는 목적과 정반대 방향이다.
    rows = latest_per_unit(records)

    by_dong: dict[str, list[Quote]] = {}
    for q in rows:
        by_dong.setdefault(q.dong or "미상", []).append(q)

    def pack(arr: list[Quote]) -> dict:
        ppps = sorted(pricing.price_per_pyeong(q.asking_price, q.exclusive_area) for q in arr)
        prices = sorted(q.asking_price for q in arr)
        return {
            "n": len(arr),
            "median_price": prices[len(prices) // 2],
            "min_price": prices[0],
            "max_price": prices[-1],
            "median_ppp": round(median(ppps), 1),
            "latest": max(q.last_seen_at for q in arr).date().isoformat(),
        }

    dongs = {d: pack(a) for d, a in sorted(by_dong.items()) if a}
    return {
        "complex_id": complex_id,
        "area_key": area_key,
        "active_days": ACTIVE_DAYS,
        "total": len(rows),
        "records": len(records),
        "by_dong": dongs,
        "overall": pack(rows) if rows else None,
        "note": (
            f"최근 {ACTIVE_DAYS}일 안에 확인된 호가만 집계합니다. 호가는 희망가와 급매가 "
            "섞여 있고 성사 여부를 모르므로 실거래를 대체하지 않습니다 — 거래가 뜸한 동의 "
            "선행지표로 실거래 옆에 놓고 보세요."
        ),
    }


def history(db: Session, complex_id: int, dong: str, area_key: int | None = None) -> list[dict]:
    """그 동 호가의 시간 경로. 같은 층이 값을 내렸는지 보는 용도다."""
    key = (dong or "").strip().removesuffix("동").strip()
    stmt = select(Quote).where(Quote.complex_id == complex_id, Quote.dong == key)
    if area_key is not None:
        stmt = stmt.where(Quote.area_key == area_key)
    rows = db.execute(stmt.order_by(Quote.first_seen_at)).scalars().all()
    return [
        {
            "floor": q.floor or None,
            "floor_band": q.floor_band,
            "exclusive_area": q.exclusive_area,
            "asking_price": q.asking_price,
            "ppp": round(pricing.price_per_pyeong(q.asking_price, q.exclusive_area), 1),
            "first_seen": q.first_seen_at.date().isoformat(),
            "last_seen": q.last_seen_at.date().isoformat(),
            "seen_count": q.seen_count,
        }
        for q in rows
    ]


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Quote)) or 0


# ---------------------------------------------------------------------------
# 유닛 묶기 — 같은 집이 값을 바꿔 다시 올라온 경우를 한 줄로 만든다
# ---------------------------------------------------------------------------

# 같은 붙여넣기(혹은 잇달아 한 붙여넣기)에서 온 기록을 '동시에 살아 있던 매물' 로
# 보는 시간 여유.
#
# 한 붙여넣기 안의 기록들은 몇 초 안에 들어오므로 여유가 넉넉해도 안전하다. 그리고
# 두 방향의 오류는 값이 다르다 — 여유가 **짧아서** 동시 매물을 가격 변동으로 오인하면
# 없는 이력을 만들어 내고 실재하는 매물 두 건을 한 건으로 지워 버린다. 여유가
# **길어서** 실제 변동을 못 잡으면 지금과 똑같이 두 줄로 보일 뿐이다. 그래서 길게 잡는다.
CONCURRENT_TOLERANCE_SEC = 600


def unit_key(q: Quote) -> tuple:
    """'같은 집' 을 가리키는 키 — 호가를 뺀 나머지.

    호까지 알면 좋겠지만 목록에 호는 안 나온다. 층이 '고층' 처럼 구간으로만 적힌
    매물은 대표층으로 채워지므로, 같은 구간의 **서로 다른 집**이 같은 키를 갖는다.
    그래서 이 키만으로 합치면 안 되고, 시간이 겹치는지를 반드시 함께 본다.
    """
    return (q.complex_id, q.dong or "", q.area_key, q.floor or 0)


@dataclass
class UnitChain:
    """한 집의 호가 이력. `rows` 는 시간순, 마지막이 최신이다."""

    rows: list[Quote]
    # 이 사슬을 이을 때 후보 매물이 둘 이상이었는가. 그렇다면 '누가 누구의 다음
    # 호가인지' 는 추측이다 — 줄 수는 어느 쪽을 골라도 같지만 이력은 달라진다.
    ambiguous: bool = False

    @property
    def latest(self) -> Quote:
        return self.rows[-1]


def unit_chains(rows: list[Quote]) -> tuple[list[UnitChain], int]:
    """호가 기록을 **유닛** 단위로 묶는다. 반환: (유닛별 사슬, 동시 매물이 있던 유닛키 수)

    ## 왜 키만으로는 안 되는가

    `Quote` 는 값이 바뀌면 새 행이 된다(그게 보고 싶은 신호다). 그래서 한 집이
    3.8억 → 3.55억 으로 내리면 두 줄이 된다. 순위표에는 **최신 하나만** 있어야 한다.

    그런데 같은 (단지·동·평형·층) 에 값이 다른 행이 여러 개 있다고 해서 값이 바뀐
    것은 아니다. 실제 데이터를 보면 130동 40㎡ '고층' 에 3.4~3.8억 다섯 줄이 있었고,
    다섯 줄 모두 **한 번의 붙여넣기에서 같은 초에** 들어왔다. 동시에 올라와 있던
    서로 다른 매물이다. 이것을 합치면 실재하는 매물 네 건이 사라진다.

    ## 시간으로 가른다

    한 집의 호가가 바뀌면 옛 호가는 **사라진다** — 목록에 더 이상 안 나오므로
    `last_seen_at` 이 그 시점에 멈춘다. 반대로 동시에 올라온 매물들은 같은 목록에
    함께 있으므로 `last_seen_at` 이 같이 갱신된다.

    그래서 생존 구간 `[first_seen, last_seen]` 이 **겹치지 않고 이어질 때만** 같은
    유닛의 연속된 호가로 본다. 겹치면 서로 다른 매물이다. 구간 분할(interval
    partitioning) 과 같은 문제로, 겹치는 구간의 최대 개수가 곧 유닛 수가 된다.

    ## 이어붙일 후보가 여럿일 때

    사슬 개수는 어느 후보를 골라도 같다(구간 분할의 성질). 하지만 **어느 호가가
    어느 호가의 다음인지**는 달라진다. 사라진 직후에 나타난 쪽이 이어졌을 가능성이
    높으므로 **가장 늦게 비워진** 사슬에 붙이고, 후보가 둘 이상이었으면 그 사슬을
    `ambiguous` 로 표시한다 — 추측을 사실처럼 보여 주지 않기 위해서다.
    """
    tol = timedelta(seconds=CONCURRENT_TOLERANCE_SEC)
    groups: dict[tuple, list[Quote]] = defaultdict(list)
    for q in rows:
        groups[unit_key(q)].append(q)

    chains: list[UnitChain] = []
    concurrent = 0
    for arr in groups.values():
        arr.sort(key=lambda q: (q.first_seen_at, q.id))
        local: list[UnitChain] = []
        for q in arr:
            # 이미 사라진 뒤에 나타난 기록만 같은 유닛의 '다음 호가' 로 본다.
            free = [c for c in local if c.latest.last_seen_at + tol <= q.first_seen_at]
            if free:
                free.sort(key=lambda c: c.latest.last_seen_at, reverse=True)
                free[0].rows.append(q)
                if len(free) > 1:
                    free[0].ambiguous = True
            else:
                local.append(UnitChain(rows=[q]))
        if len(local) > 1:
            concurrent += 1
        chains.extend(local)
    return chains, concurrent


def chain_payload(chain: UnitChain) -> dict:
    """사슬 하나를 화면용으로 펼친다 — 최신 호가와 **최신을 기준으로 한** 변동."""
    rows = chain.rows
    latest = rows[-1]
    out: dict = {
        "quote_id": latest.id,
        "quote_ids": [q.id for q in rows],
        "revisions": len(rows),
        "ambiguous": chain.ambiguous,
        "asking_price": latest.asking_price,
        "seen_count": sum(q.seen_count for q in rows),
        "confirmed_on": latest.confirmed_on.isoformat() if latest.confirmed_on else None,
        "first_seen": rows[0].first_seen_at.date().isoformat() if rows[0].first_seen_at else None,
        "last_seen": latest.last_seen_at.date().isoformat() if latest.last_seen_at else None,
        "price_history": [
            {
                "asking_price": q.asking_price,
                "first_seen": q.first_seen_at.date().isoformat() if q.first_seen_at else None,
                "last_seen": q.last_seen_at.date().isoformat() if q.last_seen_at else None,
                "seen_count": q.seen_count,
                "confirmed_on": q.confirmed_on.isoformat() if q.confirmed_on else None,
            }
            for q in rows
        ],
    }
    if len(rows) > 1:
        prev = rows[-2].asking_price
        first = rows[0].asking_price
        out["prev_price"] = prev
        out["price_change"] = latest.asking_price - prev
        out["price_change_pct"] = round((latest.asking_price - prev) / prev * 100, 1)
        out["first_price"] = first
        out["total_change_pct"] = round((latest.asking_price - first) / first * 100, 1)
    return out


def display_units(rows: list[Quote]) -> list[dict]:
    """순위표에 **한 줄씩** 올릴 단위로 묶는다.

    두 가지 묶음이 겹쳐 있다.

    1. **시간 사슬** — 한 집이 값을 바꿔 다시 올라온 경우. 생존 구간이 겹치지 않는
       기록들이라 확실히 같은 집이다(`unit_chains`).
    2. **동시 매물** — 같은 (단지·동·평형·층)에 지금 함께 올라와 있는 매물들. 목록에
       호가 안 나오므로 같은 집인지 알 수 없고, 실제로 130동 40㎡ 고층대에는 확인일자가
       같은 날(09-21)인 매물이 네 건 있었다. 다른 집일 가능성이 높다.

    둘을 한 줄로 접고 나머지는 호버로 내린다. 표가 한 층대 매물로 도배되지 않으면서도
    실재하는 매물이 사라지지는 않는다 — 숫자 배지로 몇 건인지 밝히고 전부 펼쳐 보인다.

    대표는 **가장 최근 확인된 것**, 같은 날이면 **가장 싼 것**을 고른다. 사는 쪽이
    실제로 관심을 갖는 값이고, 무엇보다 결정적이라 새로고침해도 순서가 흔들리지 않는다.
    """
    by_key: dict[tuple, list[UnitChain]] = defaultdict(list)
    for ch in unit_chains(rows)[0]:
        by_key[unit_key(ch.latest)].append(ch)

    def rank_of(ch: UnitChain):
        q = ch.latest
        # 확인일자가 없으면 가장 오래된 것으로 친다 — 있는 쪽에 대표를 양보한다.
        return (q.confirmed_on or date.min, -q.asking_price)

    out: list[dict] = []
    for chains in by_key.values():
        chains.sort(key=rank_of, reverse=True)
        rep = chains[0]
        item = chain_payload(rep)
        others = [
            {
                "asking_price": c.latest.asking_price,
                "confirmed_on": c.latest.confirmed_on.isoformat() if c.latest.confirmed_on else None,
                "revisions": len(c.rows),
                "is_rep": c is rep,
            }
            for c in chains
        ]
        prices = [o["asking_price"] for o in others]
        item["group_count"] = len(chains)
        item["group_min"] = min(prices)
        item["group_max"] = max(prices)
        item["group"] = others
        # 삭제는 이 줄이 대표하는 **모든** 행을 지운다. 대표만 지우면 나머지가 다음
        # 조회에서 각자 한 줄로 되살아나 지운 것처럼 보이지 않는다.
        item["quote_ids"] = [q.id for c in chains for q in c.rows]

        # 이 줄을 **언제 처음 넣었나**. chain_payload 의 first_seen 은 대표 사슬의
        # 것이라, 같은 층대에 나중에 올라온 매물이 대표가 되면 날짜가 앞당겨진 것처럼
        # 보인다. 줄 전체 기준이어야 "이 줄이 언제부터 있었나" 에 답이 된다.
        seen = [q.first_seen_at for c in chains for q in c.rows if q.first_seen_at]
        item["added_on"] = min(seen).date().isoformat() if seen else None

        # 비고를 붙일 키. unit_key 와 **같아야** 한다 — 어긋나면 메모가 엉뚱한 줄에 간다.
        k = unit_key(rep.latest)
        item["note_key"] = {
            "complex_id": k[0], "dong": k[1], "area_key": k[2], "floor": k[3],
        }
        out.append(item)
    return out


def latest_per_unit(rows: list[Quote]) -> list[Quote]:
    """유닛마다 **최신 호가 행만** 남긴다. 집계에서 지난 호가를 빼는 용도다.

    값을 내린 집의 옛 호가는 이미 없는 가격이다. 그것을 중앙값에 함께 넣으면 호가
    분포가 위로 끌린다 — 하필 이 데이터를 쌓는 이유(내려간 값 포착)와 반대 방향이다.
    """
    return [c.latest for c in unit_chains(rows)[0]]
