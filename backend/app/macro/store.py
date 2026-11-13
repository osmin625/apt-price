"""macro.db 읽기·쓰기. 자산은 이 모듈만 부른다 — 표나 엔진을 직접 만지지 않는다.

파일이 없으면 빈 계열 대신 `MacroMissing` 을 던진다 — 이유는 `core/dbfile.py` 머리말.
DB 를 나눈 경위·이유는 docs/engineering/architecture.md '자산 구조'.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.dbfile import DbFile, DbMissing
from .models import MacroBase, MacroPoint

MacroMissing = DbMissing

FILE = DbFile(lambda: settings.macro_url, MacroBase,
              "backend 에서 `python -m scripts.ingest_macro` 로 만들거나 MACRO_DATABASE_URL 을 거세요.")
reader = FILE.reader
writer = FILE.writer
db_path = FILE.path


def upsert(db: Session, rows: Iterable[dict]) -> int:
    """rows: series·freq·period·value·unit·source. (series, freq, period) 가 같으면 값을 덮는다."""
    rows = list(rows)
    if not rows:
        return 0
    n = 0
    # SQLite 는 한 문장에 변수 32,766개까지다 — 일별 계열(수천 행 × 6열)을 한 번에 넣으면 넘는다.
    for i in range(0, len(rows), 2000):
        stmt = sqlite_insert(MacroPoint).values(rows[i:i + 2000])
        stmt = stmt.on_conflict_do_update(
            index_elements=["series", "freq", "period"],
            set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit,
                  "source": stmt.excluded.source, "fetched_at": func.now()},
        )
        db.execute(stmt)
        n += len(rows[i:i + 2000])
    return n


def monthly(series: str) -> dict[str, float]:
    """{'YYYYMM': 값}. 없는 달을 채우지 않는다."""
    with reader() as db:
        rows = db.execute(
            select(MacroPoint.period, MacroPoint.value)
            .where(MacroPoint.series == series, MacroPoint.freq == "M")
        ).all()
    return {p: float(v) for p, v in rows}


def quarterly(series: str) -> dict[str, float]:
    """{'YYYYQn': 값}. 분기 계열(FRED 자금순환표·GDP, ECOS 명목 GDP)."""
    with reader() as db:
        rows = db.execute(
            select(MacroPoint.period, MacroPoint.value)
            .where(MacroPoint.series == series, MacroPoint.freq == "Q")
        ).all()
    return {p: float(v) for p, v in rows}


def last_period(series: Iterable[str], freq: str = "M") -> dict[str, str]:
    """계열별 마지막 시점. 신선도 검진이 쓴다."""
    with reader() as db:
        return dict(db.execute(
            select(MacroPoint.series, func.max(MacroPoint.period))
            .where(MacroPoint.series.in_(list(series)), MacroPoint.freq == freq)
            .group_by(MacroPoint.series)).all())
