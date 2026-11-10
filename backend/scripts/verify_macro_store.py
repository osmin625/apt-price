"""macro.db 가 없을 때 조용히 비지 않는지, 있을 때 받은 값을 그대로 돌려주는지.

## 왜

한국은행 계열을 apt.db 에서 macro.db 로 꺼냈다(docs/engineering/architecture.md '자산 구조').
파일이 둘이 되면 새로 생기는 실패가 하나 있다 — **한쪽 파일만 못 찾는 것.** SQLite 는 없는
파일을 열면 빈 파일을 새로 만든다. 첫 오류('no such table')는 무엇이 빠졌는지 말하지 않고,
남은 빈 파일에 누가 표를 만들면 그다음부터 거시 계열은 오류 없이 0행이 되어 화면이 '적재 전'
으로 멀쩡히 뜬다(`store.py` 머리말). 워크트리처럼 `data/` 가 빈 곳이 그 자리다.

그래서 본다.

1. 없는 경로를 가리키면 `reader()` 가 `MacroMissing` 을 던지고, **파일을 만들지 않는다**
2. `writer()` 는 만든다 — 적재는 막히면 안 된다
3. 쓴 값을 그대로 읽는다(주기가 다른 같은 계열은 섞이지 않는다)
4. `MACRO_DATABASE_URL` 이 비면 apt.db **옆**이다 — 워크트리가 DATABASE_URL 하나로 본 DB 를 가리킨다

옮길 때의 값 대조(정적 내보내기 전후 바이트 비교)는 한 번 하고 커밋에 남겼다. 그것을 여기
얼리지 않는 이유: 한국은행은 M2 같은 계열을 소급 수정하므로, 옛 행과 새 행을 영원히 같다고
검사하면 언젠가 멀쩡한 적재가 실패한다.

DB 없이 돈다(임시 폴더에 만든다).
"""

from __future__ import annotations

NEEDS_DB = False  # 임시 폴더에 macro.db 를 만들어 본다 — 실제 DB 는 안 연다

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.macro import store  # noqa: E402


def drop_engine() -> None:
    # 윈도우는 열린 SQLite 파일을 지우지 못한다 — 임시 폴더를 치우기 전에 연결을 닫는다.
    if store._sessions.cache_info().currsize:
        store._sessions().kw["bind"].dispose()
    store._sessions.cache_clear()


def point_to(url: str) -> None:
    settings.macro_database_url = url
    drop_engine()


def main() -> int:
    bad = 0

    def check(ok: bool, what: str) -> None:
        nonlocal bad
        print(f"  {'OK  ' if ok else 'FAIL'} {what}")
        bad += not ok

    saved = (settings.macro_database_url, settings.database_url)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            # 폴더는 있고 파일만 없는 곳 — SQLite 가 조용히 빈 파일을 만드는 바로 그 경우다.
            path = Path(tmp) / "macro.db"
            point_to(f"sqlite:///{path}")
            try:
                store.monthly("base_rate")
                check(False, "없는 macro.db 를 읽으면 MacroMissing")
            except store.MacroMissing:
                check(True, "없는 macro.db 를 읽으면 MacroMissing")
            except Exception as exc:  # 'no such table' — 확인을 빼면 이리로 온다
                check(False, f"없는 macro.db 를 읽으면 MacroMissing (실제: {type(exc).__name__})")
            check(not path.exists(), "읽기 시도가 빈 파일을 만들지 않는다")

            with store.writer() as db:
                store.upsert(db, [
                    {"series": "base_rate", "freq": "M", "period": "202401", "value": 3.5,
                     "unit": "연%", "source": "ECOS"},
                    {"series": "base_rate", "freq": "M", "period": "202402", "value": 3.25,
                     "unit": "연%", "source": "ECOS"},
                    {"series": "base_rate", "freq": "D", "period": "20240215", "value": 9.0,
                     "unit": "연%", "source": "ECOS"},
                ])
                db.commit()
            check(path.exists(), "writer() 는 파일을 만든다")
            got = store.monthly("base_rate")
            check(got == {"202401": 3.5, "202402": 3.25},
                  f"쓴 월 값을 그대로 읽고 일 값은 섞지 않는다 ({got})")
            with store.writer() as db:
                store.upsert(db, [{"series": "base_rate", "freq": "M", "period": "202402",
                                   "value": 3.0, "unit": "연%", "source": "ECOS"}])
                db.commit()
            check(store.monthly("base_rate")["202402"] == 3.0, "같은 시점은 덮어쓴다(소급 수정)")
            check(store.last_period(["base_rate", "m2"]) == {"base_rate": "202402"},
                  "마지막 시점 — 없는 계열은 빠진다(검진이 '비어 있음' 으로 잡는다)")

            settings.macro_database_url = ""
            settings.database_url = f"sqlite:///{Path(tmp) / 'copy' / 'apt.db'}"
            check(Path(settings.macro_url[len("sqlite:///"):]) == Path(tmp) / "copy" / "macro.db",
                  "MACRO_DATABASE_URL 이 비면 apt.db 옆의 macro.db")
        finally:
            settings.macro_database_url, settings.database_url = saved
            drop_engine()

    print("\n이상 없음" if not bad else f"\n[X] 실패 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
