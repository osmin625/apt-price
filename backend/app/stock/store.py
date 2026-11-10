"""stock.db 읽기·쓰기. 파일이 없으면 시끄럽게 실패한다(`core/dbfile.py`)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.dbfile import DbFile, DbMissing
from .models import Bar, StockBase

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
