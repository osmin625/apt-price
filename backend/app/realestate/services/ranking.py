"""매물 여러 건을 한꺼번에 평가하고 줄 세운다.

일괄 붙여넣기(`/api/model/parse-bulk`)와 누적 순위(`/api/quotes/ranking`)가 같은
계산을 쓴다. 두 곳에 같은 로직을 두면 한쪽만 고쳐져 값이 달라진다.

## 성능

한 건씩 `estimate_fair_price` 를 부르면 매물마다 **구 전체 거래를 다시 읽고**
시점지수·층계수를 새로 만든다. 46건에 12초가 들었다. (구, 기간) 단위 표본은
요청 안에서 공유한다 — 5.3초로 줄었다.

## 중복

한 물건을 중개사 여러 곳이 올리므로 목록에는 같은 매물이 반복된다. 합치지 않으면
순위 상위가 같은 값 여러 줄로 채워져 아무것도 알 수 없다. `Quote` 테이블은 이미
같은 키로 중복을 막지만, 일괄 붙여넣기의 **그 자리 결과**에도 같은 규칙을 적용한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import pricing
from ..models import Complex, DongTag, Quote, QuoteNote
from . import analysis, memo_tags, quotes
from . import model_view as mv


def verdict_of(pct: float) -> str:
    if pct <= -10:
        return "저평가"
    if pct <= -3:
        return "다소 저렴"
    if pct < 3:
        return "적정"
    if pct < 10:
        return "다소 비쌈"
    return "고평가"


def evaluate_many(db, rows: list[dict], months: int, basis: str = "market") -> dict:
    """`rows` 를 평가해 순위를 매긴다.

    rows 의 각 항목: complex_id, dong, exclusive_area, floor, asking_price
    그 밖의 키(seen_count, first_seen 등)는 결과에 그대로 실어 보낸다.
    """
    ctx: dict = {}
    fit = mv.peek_fit(db, months=months)
    dong_effects = (fit or {}).get("dong_effects")

    items, skipped = [], []
    # 단지 id → 단지 수준 요인 분해. 행마다 같은 것을 되풀이해 보내지 않는다.
    complex_parts: dict[int, dict] = {}
    for r in rows:
        cid = r.get("complex_id")
        area = r.get("exclusive_area")
        ask = r.get("asking_price")
        if not (cid and area and ask):
            skipped.append({"text": r.get("complex_name") or str(cid), "reason": "정보 부족"})
            continue

        fair = analysis.estimate_fair_price(
            db, complex_id=cid, exclusive_area=area, floor=r.get("floor"),
            months=months, dong=r.get("dong"), dong_effects=dong_effects, ctx=ctx,
        )
        if not fair or not fair.get("fair_price"):
            skipped.append({
                "text": (fair or {}).get("complex", {}).get("name") or str(cid),
                "reason": "비교 실거래 없음",
            })
            continue

        gap_pct = (ask - fair["fair_price"]) / fair["fair_price"] * 100
        item = {
            **{k: v for k, v in r.items() if k not in ("complex_id",)},
            "complex_id": cid,
            "complex_name": fair["complex"]["name"],
            "exclusive_area": area,
            "pyeong": round(pricing.to_pyeong(area), 1),
            "floor_band": fair.get("floor_band"),
            "fair_price": fair["fair_price"],
            "gap_pct": round(gap_pct, 1),
            "verdict": verdict_of(gap_pct),
            "sample_count": fair.get("sample_count"),
            "confidence": fair.get("confidence"),
        }

        # 요인 기준. 면적 곡선은 전 단지 공통이라 특정 평형에서 어긋나므로,
        # 같은 평형 실거래로 교정한 값을 쓴다(단건 진단과 같은 방식).
        m = mv.model_price(db, fit, {
            "complex_id": cid, "exclusive_area": area,
            "floor": r.get("floor"), "dong": r.get("dong"),
        }) if fit else None
        if m and m.get("market_ppp") and fair.get("fair_ppp"):
            k = float(fair["fair_ppp"]) / float(m["market_ppp"])
            if 0.5 <= k <= 2.0:
                fp = round(m["factor_price"] * k)
                item["factor_price"] = fp
                item["gap_factor_pct"] = round((ask - fp) / fp * 100, 1)
                # 판정도 기준별로 따로 낸다. 'verdict' 는 늘 실거래 기준인데,
                # 표에서 선택한 기준의 열만 보이게 되면서 요인 기준을 고른 화면에
                # 실거래 판정이 남으면 **숫자와 판정이 어긋나 보인다** — 대비가
                # -12% 인데 '적정' 이라고 적히는 식이다.
                item["verdict_factor"] = verdict_of(item["gap_factor_pct"])
                # 요인 분해도 같이 보낸다. 표에서 행에 호버하면 "왜 이 값인지" 를
                # 바로 볼 수 있어야 한다 — 순위만 보고는 납득할 수 없다.
                # 유닛 몫만 행에 싣는다. 단지 몫은 **같은 단지면 같은 값**이라
                # 아래 `complex_parts` 로 한 번만 보낸다(매물 1,018건이 단지
                # 39곳에 몰려 있어 스냅샷의 0.79MB 가 0.03MB 가 된다).
                item["factor_parts"] = {"unit": m.get("unit_parts")}
                if cid not in complex_parts:
                    complex_parts[cid] = {
                        "complex": m.get("complex_parts"),
                        "premium_pct": m.get("complex_premium_pct"),
                        # 이 시세가 **몇 건의 중개거래에 얹혀 있는지.** 직거래는
                        # Stage 1 에서 할인을 걷어내지만 단지 수준을 관측해 주지는
                        # 않는다.
                        "market_count": m.get("market_count"),
                        "trade_count": m.get("trade_count"),
                    }

        items.append(item)

    key = "gap_factor_pct" if basis == "factor" else "gap_pct"
    ranked = [i for i in items if i.get(key) is not None]
    rest = [i for i in items if i.get(key) is None]
    ranked.sort(key=lambda i: i[key])
    for n, i in enumerate(ranked, 1):
        i["rank"] = n
    for i in rest:
        i["rank"] = None

    return {
        "count": len(items),
        # 요인 기준 열이 어느 기간 적합에서 나왔는지. 캐시에 요청한 기간이
        # 없으면 다른 기간 것을 쓰므로, 무엇을 썼는지는 밝혀야 한다.
        "factor_months": (fit or {}).get("months"),
        "basis": basis,
        "basis_label": "요인 기준" if basis == "factor" else "실거래 기준",
        "items": ranked + rest,
        # 단지 수준 분해. 행의 `complex_id` 로 찾아 쓴다.
        "complex_parts": complex_parts,
        "skipped": skipped,
    }


def merge_duplicates(items: list[dict]) -> tuple[list[dict], int]:
    """같은 (단지·동·평형·층·호가)를 한 줄로 합치고 몇 건이었는지 센다.

    층을 '저/중/고' 로만 밝힌 매물은 같은 구간이 같은 대표층이 되므로 서로 다른
    물건이 합쳐질 수 있다. 가격까지 같아야 합치므로 실무상 문제는 적지만 완전하지는
    않다 — 그래서 합친 건수를 화면에 드러낸다.
    """
    merged: dict[tuple, dict] = {}
    for i in items:
        k = (i.get("complex_id"), i.get("dong"), round(i.get("exclusive_area") or 0),
             i.get("floor"), i.get("asking_price"))
        if k in merged:
            merged[k]["listing_count"] = merged[k].get("listing_count", 1) + 1
            # 메모는 **합친다.** 여기서 합쳐지는 것이 바로 '한 물건을 중개사 여러
            # 곳이 올린 경우' 이고, 메모는 중개사마다 다르다. 첫 줄만 남기면
            # 다른 곳이 적은 '급매' 가 조용히 사라진다.
            a, b = merged[k].get("memo"), i.get("memo")
            if b and b.strip() and b.strip() not in (a or ""):
                merged[k]["memo"] = (a + "\n" + b.strip()) if a else b.strip()
        else:
            i.setdefault("listing_count", 1)
            merged[k] = i
    out = list(merged.values())
    return out, sum(i.get("listing_count", 1) - 1 for i in out)


def rank_saved(db: Session, months: int, basis: str = "market",
               days: int | None = None, complex_id: int | None = None) -> dict:
    """쌓인 매물 전체를 평가해 **더 저평가된 순서**로 돌려준다(`/api/quotes/ranking`).

    `Quote` 테이블은 붙여넣기마다 중복 없이 쌓인다. 그러니 지금까지 본 모든 매물의
    순위는 따로 저장할 것 없이 여기서 언제든 다시 계산할 수 있다. 비고·메모 태그·
    민간임대 표시도 읽을 때마다 붙인다.
    """

    stmt = select(Quote)
    if days:
        # 확인일자 기준이다. `last_seen_at` 은 우리가 붙여넣은 시각이라 전부 오늘이
        # 되어 버려 거르는 의미가 없었다. 날짜를 못 읽은 매물은 남긴다 — 읽기
        # 실패를 '오래된 매물' 로 바꿔 조용히 숨기면 안 된다.
        cut = (datetime.now() - timedelta(days=days)).date()
        stmt = stmt.where(or_(Quote.confirmed_on.is_(None), Quote.confirmed_on >= cut))
    if complex_id:
        stmt = stmt.where(Quote.complex_id == complex_id)
    rows = db.execute(stmt).scalars().all()

    # 한 (단지·동·평형·층)당 한 줄. 값이 바뀐 이력도, 동시에 올라와 있는 매물도
    # 대표 한 줄로 접고 나머지는 호버로 내린다 — `quotes.display_units` 참조.
    units = quotes.display_units(rows)

    names = {
        c.id: c.name
        for c in db.execute(select(Complex)).scalars().all()
    }
    rep_of = {q.id: q for q in rows}
    payload = []
    for u in units:
        q = rep_of[u["quote_id"]]
        payload.append({
            **u,
            "complex_id": q.complex_id,
            "complex_name": names.get(q.complex_id, ""),
            "dong": q.dong or None,
            "exclusive_area": q.exclusive_area,
            "floor": q.floor or None,
        })

    out = evaluate_many(db, payload, months=months, basis=basis)

    # 비고를 붙인다. 유닛 키로 맞추므로 호가가 바뀌어도 메모는 그 줄에 남는다.
    notes = {
        (n.complex_id, n.dong, n.area_key, n.floor): n.text
        for n in db.execute(select(QuoteNote)).scalars().all()
    }
    by_quote = {p["quote_id"]: p.get("note_key") for p in payload}
    # 중개사 메모에서 뽑은 키워드. 사람이 쓴 비고와 **같은 칸에 다른 모양으로** 둔다 —
    # 우리가 확인한 사실이 아니라 올린 사람이 그렇게 적었다는 뜻이기 때문이다.
    # 뽑는 것은 읽을 때마다 한다. 저장할 때 뽑아 두면 사전을 고쳐도 옛 줄은 안 바뀐다.
    memos_of = {p["quote_id"]: p.get("memos") or [] for p in payload}
    # 끈 태그는 비고에서 뺀다. **원문(memos)은 그대로 보낸다** — 호버에서 왜 그
    # 키워드가 붙었는지 보려면 원문이 있어야 하고, 끈 것은 '안 보여 주기' 지
    # '안 읽기' 가 아니다. 사전을 다시 켜면 그 자리에서 되살아난다.
    off = quotes.disabled_tags(db)
    # 민간임대 표시는 **동에 붙어 있고 여기서 파생한다.** 비고에 글자를 써 넣으면
    # 표시를 끈 뒤에도 남고, 사용자가 직접 쓴 메모와 구분되지 않는다.
    rental = {
        (t.complex_id, t.dong)
        for t in db.execute(select(DongTag).where(DongTag.rental.is_(True)))
        .scalars()
        .all()
    }

    for item in out.get("items", []):
        k = by_quote.get(item.get("quote_id"))
        if not k:
            continue
        item["note_key"] = k
        item["note"] = notes.get(
            (k["complex_id"], k["dong"], k["area_key"], k["floor"]), ""
        )
        item["note_auto"] = (
            ["민간임대"] if (k["complex_id"], k["dong"]) in rental else []
        )
        memos = memos_of.get(item.get("quote_id")) or []
        item["note_tags"] = [t for t in memo_tags.merge(memos) if t not in off]
        item["memos"] = memos
    out["months"] = months
    out["total_quotes"] = len(rows)
    out["revised_units"] = sum(1 for p in payload if p["revisions"] > 1)
    out["grouped_away"] = sum(len(p["quote_ids"]) for p in payload) - len(payload)
    out["days"] = days
    return out
