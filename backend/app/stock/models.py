"""stock.db 의 표. 일봉 종가 한 줄이 (시장, 종목, 날짜) 다."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class StockBase(DeclarativeBase):
    """apt.db·macro.db 의 Base 와 따로 둔다 — 같은 Base 면 create_all 이 다른 파일에 이 표를 만든다."""


class Bar(StockBase):
    __tablename__ = "bars"
    __table_args__ = (UniqueConstraint("market", "symbol", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # 'KR' · 'US'. 종목 코드는 시장마다 겹칠 수 있어(숫자 코드 vs 티커) 키에 시장을 넣는다.
    market: Mapped[str] = mapped_column(String(4))
    symbol: Mapped[str] = mapped_column(String(16))
    date: Mapped[str] = mapped_column(String(8), index=True)  # YYYYMMDD — 문자열 순서가 시간 순서
    # 현지 통화 그대로. 원화 환산은 화면에서만 한다(합의: 예측은 현지 통화).
    close: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(8))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
