"""macro.db 읽기·쓰기. 자산은 이 모듈만 부른다 — 표나 엔진을 직접 만지지 않는다.

## 파일이 없으면 시끄럽게 실패한다

읽을 때 macro.db 가 없으면 **무엇을 고치라는지 적힌 `MacroMissing` 을 던진다.** 이 확인을
빼고 재 봤다 — SQLite 는 없는 파일을 열면 **빈 파일을 새로 만들고** 오류는 'no such table:
macro_points' 로 난다. 무엇이 빠졌는지 안 보이고, 빈 파일이 남아 다음에 누가 표만 만들면
(`writer()` 를 한 번 부르면) 그때부터는 오류 없이 0행이다 — 거시 탭이 '아직 적재되지 않음'
으로 멀쩡히 뜨고 정적 내보내기가 그 빈 화면을 배포한다. 그래서 엔진을 열기 전에 파일부터
본다. 만드는 것은 적재(`writer()`)만 한다.

DB 를 나눈 경위·이유는 docs/engineering/architecture.md '자산 구조'.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import settings
from ..core.db import make_engine
from .models import MacroBase, MacroPoint


class MacroMissing(RuntimeError):
    pass


def db_path() -> Path | None:
    url = settings.macro_url
    return Path(url[len("sqlite:///"):]) if url.startswith("sqlite:///") else None


@lru_cache(maxsize=1)
def _sessions() -> sessionmaker:
    return sessionmaker(bind=make_engine(settings.macro_url),
                        autoflush=False, expire_on_commit=False)


def reader() -> Session:
    p = db_path()
    if p is not None and not p.exists():
        raise MacroMissing(f"macro.db 가 없습니다({p}). backend 에서 "
                           f"`python -m scripts.ingest_macro` 로 만들거나 "
                           f"MACRO_DATABASE_URL 을 거세요.")
    return _sessions()()


def writer() -> Session:
    """적재용. 없으면 파일과 표를 만든다."""
    p = db_path()
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
    MacroBase.metadata.create_all(_sessions().kw["bind"])
    return _sessions()()


def upsert(db: Session, rows: Iterable[dict]) -> int:
    """rows: series·freq·period·value·unit·source. (series, freq, period) 가 같으면 값을 덮는다."""
    rows = list(rows)
    if not rows:
        return 0
    stmt = sqlite_insert(MacroPoint).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["series", "freq", "period"],
        set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit,
              "source": stmt.excluded.source, "fetched_at": func.now()},
    )
    db.execute(stmt)
    return len(rows)


def monthly(series: str) -> dict[str, float]:
    """{'YYYYMM': 값}. 없는 달을 채우지 않는다."""
    with reader() as db:
        rows = db.execute(
            select(MacroPoint.period, MacroPoint.value)
            .where(MacroPoint.series == series, MacroPoint.freq == "M")
        ).all()
    return {p: float(v) for p, v in rows}


def last_period(series: Iterable[str], freq: str = "M") -> dict[str, str]:
    """계열별 마지막 시점. 신선도 검진이 쓴다."""
    with reader() as db:
        return dict(db.execute(
            select(MacroPoint.series, func.max(MacroPoint.period))
            .where(MacroPoint.series.in_(list(series)), MacroPoint.freq == freq)
            .group_by(MacroPoint.series)).all())
