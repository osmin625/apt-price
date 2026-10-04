"""붙여넣어 쌓인 매물(호가)의 순위.

`Quote` 테이블은 붙여넣기마다 중복 없이 쌓인다. 그러니 **지금까지 본 모든 매물**의
순위는 따로 저장할 것 없이 여기서 언제든 다시 계산할 수 있다. 기간을 바꾸면 그
기간의 실거래로 전부 다시 계산된다.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Complex, DongTag, MemoTagPref, Quote, QuoteNote
from ..services import memo_tags
from ..services import quotes as quotes_svc
from ..services import ranking

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.get("/ranking")
def ranking_all(
    months: int = Query(24, ge=6, le=120),
    basis: str = Query("market", pattern="^(market|factor)$"),
    days: int | None = Query(None, ge=1, le=3650, description="최근 N일 안에 본 매물만"),
    complex_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """쌓인 매물 전체를 평가해 **더 저평가된 순서**로 돌려준다."""
    from datetime import datetime, timedelta

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
    # 대표 한 줄로 접고 나머지는 호버로 내린다 — `quotes_svc.display_units` 참조.
    units = quotes_svc.display_units(rows)

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

    out = ranking.evaluate_many(db, payload, months=months, basis=basis)

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
    off = disabled_tags(db)
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


@router.delete("/{quote_id}")
def delete_quote(
    quote_id: int,
    unit: bool = Query(True, description="같은 집의 지난 호가까지 함께 지운다"),
    db: Session = Depends(get_db),
):
    """매물 하나를 지운다.

    순위표의 한 줄은 행 하나가 아니라 **그 (단지·동·평형·층)에 묶인 전부**다.
    지난 호가와 동시에 올라온 매물이 함께 접혀 있다. 대표 행만 지우면 나머지가
    다음 조회에서 각자 한 줄로 되살아나 지운 것처럼 보이지 않는다.
    """
    q = db.get(Quote, quote_id)
    if not q:
        return {"ok": True, "deleted": 0}

    targets = [q]
    if unit:
        siblings = db.execute(
            select(Quote).where(
                Quote.complex_id == q.complex_id,
                Quote.dong == q.dong,
                Quote.area_key == q.area_key,
                Quote.floor == q.floor,
            )
        ).scalars().all()
        ids = {x.id for x in siblings}
        if quote_id in ids:
            targets = siblings

    for x in targets:
        db.delete(x)
    db.commit()
    return {"ok": True, "deleted": len(targets)}


@router.delete("")
def clear_quotes(db: Session = Depends(get_db)):
    """전부 비운다. 잘못 붙여넣은 목록을 통째로 되돌릴 때 쓴다."""
    n = quotes_svc.count(db)
    db.query(Quote).delete()
    db.commit()
    return {"deleted": n}


class NoteIn(BaseModel):
    """비고 한 줄. 키는 `quotes.unit_key()` 와 같아야 한다."""

    complex_id: int
    dong: str = ""
    area_key: int
    floor: int = 0
    text: str = Field(default="", max_length=300)


def disabled_tags(db: Session) -> set[str]:
    """비고에 안 띄우기로 한 태그. **행이 없으면 켜진 것**으로 본다.

    규칙을 새로 더했을 때 행이 없다고 꺼져 있으면, 더해 놓고 왜 안 보이는지 한참
    찾게 된다. 끈 것만 행으로 남긴다.
    """
    return {
        r.name
        for r in db.execute(select(MemoTagPref).where(MemoTagPref.enabled.is_(False)))
        .scalars()
        .all()
    }


def _all_memos(db: Session) -> list[str]:
    """쌓인 매물의 중개사 메모 전부(중복 제거).

    `Quote.memo` 는 같은 유닛에 여러 중개사 메모가 줄바꿈으로 쌓인 것이라 쪼갠다.
    같은 글이 여러 매물에 붙어 있으면 한 번만 센다 — 같은 중개사가 같은 문구를
    여러 매물에 돌려 쓰면 그 말이 사전을 통째로 왜곡한다.
    """
    out: list[str] = []
    seen: set[str] = set()
    for (memo,) in db.execute(select(Quote.memo).where(Quote.memo != "")).all():
        for line in (memo or "").split("\n"):
            t = line.strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


@router.get("/memo-tags")
def memo_tag_list(db: Session = Depends(get_db)):
    """메모 사전 현황 — 태그마다 몇 번 나왔고, 비고에 띄우고 있는지.

    횟수는 **쌓인 메모를 그때그때 다시 세서** 낸다. 저장해 두면 사전을 고쳤을 때
    옛 숫자가 남고, 그 숫자를 보고 사전을 또 고치게 된다.
    """
    memos = _all_memos(db)
    t = memo_tags.tally(memos)
    off = disabled_tags(db)
    return {
        # RULES 순서를 그대로 쓴다. 이 순서가 곧 비고에 나가는 우선순위라,
        # 화면에서 다른 순서로 보여 주면 왜 저것이 먼저 나오는지 알 수 없다.
        "tags": [
            {
                "name": name,
                "n": t["counts"][name],
                "enabled": name not in off,
                "priority": i + 1,
            }
            for i, (name, _) in enumerate(memo_tags.RULES)
        ],
        "n_memos": t["n_memos"],
        "n_untagged": len(t["untagged"]),
        "untagged": t["untagged"][:12],
        "unknown": t["unknown"][:12],
        "max_badges": memo_tags.MAX_BADGES,
    }


class MemoTagIn(BaseModel):
    enabled: bool


@router.put("/memo-tags/{name}")
def memo_tag_set(name: str, body: MemoTagIn, db: Session = Depends(get_db)):
    """태그 하나를 비고에 띄울지 바꾼다."""
    known = {n for n, _ in memo_tags.RULES}
    if name not in known:
        raise HTTPException(404, f"모르는 태그입니다: {name}")

    row = db.execute(
        select(MemoTagPref).where(MemoTagPref.name == name)
    ).scalar_one_or_none()
    if row is None:
        row = MemoTagPref(name=name, enabled=body.enabled)
        db.add(row)
    else:
        row.enabled = body.enabled
    db.commit()
    return {"name": name, "enabled": body.enabled}


@router.put("/note")
def put_note(body: NoteIn, db: Session = Depends(get_db)):
    """비고를 쓰거나 지운다. 빈 문자열이면 지운다.

    유닛 키에 붙이므로 같은 집의 호가가 바뀌어도 메모는 그 줄에 남는다 —
    `quote_id` 에 붙이면 값이 바뀌는 순간 조용히 사라진다.
    """
    if not db.get(Complex, body.complex_id):
        raise HTTPException(status_code=404, detail="단지를 찾을 수 없습니다.")

    key = (QuoteNote.complex_id == body.complex_id,
           QuoteNote.dong == (body.dong or ""),
           QuoteNote.area_key == body.area_key,
           QuoteNote.floor == (body.floor or 0))
    row = db.execute(select(QuoteNote).where(*key)).scalar_one_or_none()

    text = body.text.strip()
    if not text:
        if row:
            db.delete(row)
            db.commit()
        return {"text": ""}

    if row:
        row.text = text
    else:
        db.add(QuoteNote(
            complex_id=body.complex_id, dong=body.dong or "",
            area_key=body.area_key, floor=body.floor or 0, text=text,
        ))
    db.commit()
    return {"text": text}
