"""macro.db 의 표. 계열 하나가 (계열 id, 주기, 시점) 로 한 줄씩이다."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class MacroBase(DeclarativeBase):
    """apt.db 의 `Base` 와 따로 둔다 — 같은 Base 면 create_all 이 apt.db 에 이 표를 만든다."""


class MacroPoint(MacroBase):
    __tablename__ = "macro_points"
    __table_args__ = (UniqueConstraint("series", "freq", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # 계열 id. ECOS 는 우리가 붙인 이름(`base_rate`)이다 — 통계표 코드는 개편 때 바뀌므로
    # (`clients/ecos.py` 의 M2 구지표 사례) 키로 쓰지 않고 `TABLES` 가 이름 → 코드를 잇는다.
    series: Mapped[str] = mapped_column(String(32), index=True)
    # 'M'(월) · 'D'(일). 같은 계열을 두 주기로 받을 수 있게 키에 넣는다.
    freq: Mapped[str] = mapped_column(String(1), default="M")
    # 월 'YYYYMM', 일 'YYYYMMDD' — 공표처가 주는 꼴 그대로. 문자열 순서가 시간 순서다.
    period: Mapped[str] = mapped_column(String(8), index=True)
    value: Mapped[float] = mapped_column(Float)
    # 공표처가 붙인 단위 그대로('연%', '십억원'). 환산은 읽는 쪽이 한다(reb_stats 와 같은 규칙).
    unit: Mapped[str] = mapped_column(String(16), default="")
    source: Mapped[str] = mapped_column(String(8), default="ECOS")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
