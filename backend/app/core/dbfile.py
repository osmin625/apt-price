"""apt.db 옆에 두는 DB 파일 하나(macro.db·stock.db) — 열기·만들기·없을 때 실패하기.

거시가 처음 이 모양을 썼고(`app/macro/store.py`), 주식이 두 번째로 같은 것을 쓰게 되어
여기로 뽑았다('겹치면 그때 뽑는다').

## 파일이 없으면 시끄럽게 실패한다

읽을 때 파일이 없으면 **무엇을 고치라는지 적힌 `DbMissing` 을 던진다.** 이 확인을 빼고
재 봤다 — SQLite 는 없는 파일을 열면 **빈 파일을 새로 만들고** 오류는 'no such table' 로 난다.
무엇이 빠졌는지 안 보이고, 빈 파일이 남아 다음에 누가 표만 만들면(`writer()` 를 한 번 부르면)
그때부터는 오류 없이 0행이다 — 화면이 '아직 적재되지 않음' 으로 멀쩡히 뜨고 정적 내보내기가
그 빈 화면을 배포한다. 그래서 엔진을 열기 전에 파일부터 본다. 만드는 것은 적재(`writer()`)만 한다.

## 왜 apt.db 옆인가

`DATABASE_URL` 하나로 워크트리·머지 관문이 본 저장소의 DB 를 가리킨다. 다른 파일만 워크트리의
빈 `data/` 를 보면 그 자산만 조용히 빈다(docs/engineering/architecture.md '자산 구조').
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .db import make_engine


class DbMissing(RuntimeError):
    pass


class DbFile:
    def __init__(self, url: Callable[[], str], base: type[DeclarativeBase], fix: str):
        # url 은 함수다 — 검사가 설정을 바꿔 끼울 수 있게 부를 때마다 읽는다.
        self._url = url
        self._base = base
        self._fix = fix
        self._made: tuple[str, sessionmaker] | None = None

    def path(self) -> Path | None:
        u = self._url()
        return Path(u[len("sqlite:///"):]) if u.startswith("sqlite:///") else None

    def _sessions(self) -> sessionmaker:
        u = self._url()
        if self._made is None or self._made[0] != u:
            self.dispose()
            self._made = (u, sessionmaker(bind=make_engine(u), autoflush=False,
                                          expire_on_commit=False))
        return self._made[1]

    def dispose(self) -> None:
        """연결을 닫는다. 윈도우는 열린 SQLite 파일을 지우지 못한다."""
        if self._made is not None:
            self._made[1].kw["bind"].dispose()
            self._made = None

    def reader(self) -> Session:
        p = self.path()
        if p is not None and not p.exists():
            raise DbMissing(f"{p.name} 가 없습니다({p}). {self._fix}")
        return self._sessions()()

    def writer(self) -> Session:
        """적재용. 없으면 파일과 표를 만든다."""
        p = self.path()
        if p is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
        s = self._sessions()
        self._base.metadata.create_all(s.kw["bind"])
        return s()
