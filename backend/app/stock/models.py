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


class Fact(StockBase):
    """EDGAR 재무 한 값 — 한 기간(시작·끝)이 여러 제출에 거듭 실리므로 제출일까지 키다(`clients/edgar.py`)."""
    __tablename__ = "facts"
    __table_args__ = (UniqueConstraint("symbol", "concept", "start", "end", "filed", "form"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    concept: Mapped[str] = mapped_column(String(24))     # 우리 이름(edgar.CONCEPTS) — 'net_income' …
    start: Mapped[str] = mapped_column(String(8), default="")  # 기간 값의 시작 YYYYMMDD. 시점 값(주식 수)은 ''
    end: Mapped[str] = mapped_column(String(8))
    value: Mapped[float] = mapped_column(Float)
    form: Mapped[str] = mapped_column(String(12), default="")   # 10-Q · 10-K · 10-K/A …
    fp: Mapped[str] = mapped_column(String(4), default="")      # Q1·Q2·Q3·FY — 그 제출의 회계 기간(값의 기간과 다를 수 있다)
    fy: Mapped[int] = mapped_column(default=0)
    filed: Mapped[str] = mapped_column(String(8), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MonthBar(StockBase):
    """종목 월봉 — 분할·배당을 반영한 수정 종가가 있다(Alpha Vantage 월봉, `clients/alphavantage.py`).

    일봉 표(`Bar`)와 따로 둔다. 무료 일봉은 최근 100일·분할 미조정이라 과거를 잇는 데 못 쓰고, 월봉은 수정 종가가
    있어 상장 때부터 이어진다 — 두 꼴을 한 표에 섞으면 같은 종목의 날짜 열에 일·월이 섞인다.
    """
    __tablename__ = "month_bars"
    __table_args__ = (UniqueConstraint("market", "symbol", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(4))
    symbol: Mapped[str] = mapped_column(String(16))
    month: Mapped[str] = mapped_column(String(6), index=True)  # YYYYMM
    close: Mapped[float] = mapped_column(Float)                # 그달 마지막 종가(조정 안 됨)
    adj_close: Mapped[float] = mapped_column(Float)            # 수정 종가 — 수익률은 이것으로
    source: Mapped[str] = mapped_column(String(8))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
