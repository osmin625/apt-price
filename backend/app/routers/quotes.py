"""붙여넣어 쌓인 매물(호가)의 순위.

`Quote` 테이블은 붙여넣기마다 중복 없이 쌓인다. 그러니 **지금까지 본 모든 매물**의
순위는 따로 저장할 것 없이 여기서 언제든 다시 계산할 수 있다. 기간을 바꾸면 그
기간의 실거래로 전부 다시 계산된다.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Complex, MemoTagPref, Quote, QuoteNote
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
    return ranking.rank_saved(db, months=months, basis=basis, days=days,
                              complex_id=complex_id)


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


@router.get("/memo-tags")
def memo_tag_list(db: Session = Depends(get_db)):
    """메모 사전 현황 — 태그마다 몇 번 나왔고, 비고에 띄우고 있는지.

    횟수는 **쌓인 메모를 그때그때 다시 세서** 낸다. 저장해 두면 사전을 고쳤을 때
    옛 숫자가 남고, 그 숫자를 보고 사전을 또 고치게 된다.
    """
    memos = quotes_svc.all_memos(db)
    t = memo_tags.tally(memos)
    off = quotes_svc.disabled_tags(db)
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
