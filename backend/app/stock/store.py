"""stock.db 읽기·쓰기. 파일이 없으면 시끄럽게 실패한다(`core/dbfile.py`)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.dbfile import DbFile, DbMissing
from .models import Bar, Fact, MonthBar, StockBase

StockMissing = DbMissing

FILE = DbFile(lambda: settings.stock_url, StockBase,
              "backend 에서 `python -m scripts.ingest_stock` 으로 만들거나 STOCK_DATABASE_URL 을 거세요.")
reader = FILE.reader
writer = FILE.writer


def upsert(db: Session, market: str, symbol: str, source: str,
           bars: Iterable[tuple[str, float]]) -> int:
    rows = [{"market": market, "symbol": symbol, "date": d, "close": c, "source": source}
            for d, c in bars]
    for i in range(0, len(rows), 2000):  # SQLite 변수 상한 — macro.store.upsert 와 같은 이유
        stmt = sqlite_insert(Bar).values(rows[i:i + 2000])
        stmt = stmt.on_conflict_do_update(
            index_elements=["market", "symbol", "date"],
            set_={"close": stmt.excluded.close, "source": stmt.excluded.source,
                  "fetched_at": func.now()},
        )
        db.execute(stmt)
    return len(rows)


def daily(market: str, symbol: str) -> list[tuple[str, float]]:
    with reader() as db:
        return [(d, float(c)) for d, c in db.execute(
            select(Bar.date, Bar.close)
            .where(Bar.market == market, Bar.symbol == symbol)
            .order_by(Bar.date)).all()]


def last_dates() -> dict[tuple[str, str], str]:
    with reader() as db:
        return {(m, s): d for m, s, d in db.execute(
            select(Bar.market, Bar.symbol, func.max(Bar.date))
            .group_by(Bar.market, Bar.symbol)).all()}


def upsert_facts(db: Session, symbol: str, rows: Iterable[dict]) -> int:
    """EDGAR 재무 줄(`clients/edgar.extract`). 같은 (개념·기간·제출일·양식)이면 값을 덮는다 — 두 번 돌려도 같다."""
    rows = [{"symbol": symbol, **r} for r in rows]
    for i in range(0, len(rows), 2000):
        stmt = sqlite_insert(Fact).values(rows[i:i + 2000])
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "concept", "start", "end", "filed", "form"],
            set_={"value": stmt.excluded.value, "fp": stmt.excluded.fp, "fy": stmt.excluded.fy,
                  "fetched_at": func.now()},
        )
        db.execute(stmt)
    return len(rows)


def facts(symbol: str) -> list[dict]:
    with reader() as db:
        return [{"concept": c, "start": s, "end": e, "value": float(v), "form": f, "filed": fd}
                for c, s, e, v, f, fd in db.execute(
                    select(Fact.concept, Fact.start, Fact.end, Fact.value, Fact.form, Fact.filed)
                    .where(Fact.symbol == symbol)).all()]


def last_filed() -> dict[str, tuple[str, str]]:
    """종목별 (마지막 제출일, 그 제출들 가운데 가장 늦은 기간 끝). 신선도 검진이 쓴다."""
    with reader() as db:
        return {s: (f, e) for s, f, e in db.execute(
            select(Fact.symbol, func.max(Fact.filed), func.max(Fact.end)).group_by(Fact.symbol)).all()}


def upsert_monthly(db: Session, market: str, symbol: str, source: str,
                   rows: Iterable[tuple[str, float, float]]) -> int:
    """(YYYYMM, 종가, 수정 종가). 진행 중인 이번 달은 다음 적재 때 덮인다."""
    rows = [{"market": market, "symbol": symbol, "month": m, "close": c, "adj_close": a, "source": source}
            for m, c, a in rows]
    if rows:
        stmt = sqlite_insert(MonthBar).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["market", "symbol", "month"],
            set_={"close": stmt.excluded.close, "adj_close": stmt.excluded.adj_close,
                  "source": stmt.excluded.source, "fetched_at": func.now()},
        )
        db.execute(stmt)
    return len(rows)


def monthly(market: str, symbol: str) -> list[tuple[str, float]]:
    """(YYYYMM, 수정 종가)."""
    with reader() as db:
        return [(m, float(a)) for m, a in db.execute(
            select(MonthBar.month, MonthBar.adj_close)
            .where(MonthBar.market == market, MonthBar.symbol == symbol)
            .order_by(MonthBar.month)).all()]

