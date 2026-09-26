"""ORM 모델에 있는데 DB 테이블에 없는 컬럼을 추가한다.

사용법:
    python -m scripts.migrate --dry-run
    python -m scripts.migrate

## 왜 필요한가

SQLAlchemy 의 `create_all` 은 없는 **테이블**만 만들고 기존 테이블에 **컬럼**은
추가하지 않는다. 그래서 모델에 컬럼을 하나 넣으면 앱이 시작될 때가 아니라
**쿼리할 때** `no such column` 으로 죽는다.

합성 데이터만 쓰던 동안에는 `seed_demo --recreate-schema` 로 통째로 다시 만드는 게
답이었다. 몇 초면 재생성되니까. 하지만 지금 DB 에는 국토부·카카오 API 를 수십 분
호출해 받은 실데이터가 들어 있다. 컬럼 하나 때문에 그걸 버리고 다시 받는 건 말이 안 된다.

Alembic 을 붙일 수도 있지만 PoC 에 마이그레이션 버전 관리는 과하다. SQLite 의
`ALTER TABLE ... ADD COLUMN` 으로 빠진 컬럼만 채우는 것으로 충분하다.

## 한계

컬럼 **추가**만 한다. 타입 변경, 컬럼 삭제, 제약조건 변경은 하지 않는다.
그런 변경이 필요하면 `seed_demo --recreate-schema` 로 다시 만들고 데이터를 다시 받아야 한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Base  # noqa: E402


def sqlite_type(col) -> str:
    try:
        return col.type.compile(dialect=engine.dialect)
    except Exception:
        return "TEXT"


def plan() -> list[tuple[str, str, str]]:
    """(테이블, 컬럼, DDL 타입) 목록."""
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    todo = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all 이 만들 것
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            if not col.nullable and col.default is None and col.server_default is None:
                print(f"  [건너뜀] {table.name}.{col.name} — NOT NULL 인데 기본값이 없어"
                      f" 기존 행을 채울 수 없습니다. 재생성이 필요합니다.")
                continue
            todo.append((table.name, col.name, sqlite_type(col)))
    return todo


def run(dry_run: bool) -> int:
    Base.metadata.create_all(engine)  # 새 테이블은 이걸로 충분하다
    todo = plan()

    if not todo:
        print("추가할 컬럼이 없습니다. 스키마가 모델과 일치합니다.")
        return 0

    print(f"추가할 컬럼 {len(todo)}개")
    for tbl, col, typ in todo:
        print(f"  {tbl}.{col}  {typ}")

    if dry_run:
        print("\n--dry-run: 아무것도 바꾸지 않았습니다.")
        return 0

    with engine.begin() as conn:
        for tbl, col, typ in todo:
            conn.execute(text(f'ALTER TABLE "{tbl}" ADD COLUMN "{col}" {typ}'))
    print(f"\n완료: {len(todo)}개 컬럼 추가")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(run(args.dry_run))
