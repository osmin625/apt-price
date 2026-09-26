from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLite 는 쓰기를 한 번에 하나만 허용한다. 적재 스크립트가 도는 동안 API 나 다른
# 스크립트가 읽기만 해도 커밋이 `database is locked` 로 즉시 실패한다.
# 실제로 동 좌표 수집(수 분짜리 작업)이 이 때문에 중간에 죽었다.
#   - timeout: 즉시 실패하지 말고 30초까지 기다린다.
#   - WAL: 읽기와 쓰기가 서로를 막지 않게 한다.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30.0} if _is_sqlite else {},
)

if _is_sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
