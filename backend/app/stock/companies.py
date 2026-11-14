"""기술주 가치 탭이 다루는 종목 — 기대가 주가의 큰 몫인 기술주(2026-11-14 요청).

    알파벳   GOOGL  CIK 1652044   주가 Alpha Vantage · 재무 EDGAR
    테슬라   TSLA   CIK 1318605
    IBM      IBM    CIK 51143
    디웨이브 QBTS   CIK 1907982   2022-08 상장(SPAC) — 일봉이 그때부터

CIK 는 기억이 아니라 SEC 의 티커 표(company_tickers.json)에서 골랐다 — 같은 이름의 옛 법인·
자회사가 따로 등록돼 있어서다(알파벳은 GOOGL·GOOG 두 티커가 한 CIK 다).

삼성전자는 공식 출처(공공데이터포털 금융위원회_주식시세정보·OpenDART)의 활용신청이 승인되면 붙인다 —
2026-11-14 에 지금 키로 시세를 불러 보니 403(미신청)이었다. 미국이 먼저다(backend/app/stock/CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    id: str
    symbol: str      # Alpha Vantage·stock.db 의 티커
    cik: int         # EDGAR
    label: str
    market: str = "US"
    currency: str = "USD"


COMPANIES: tuple[Company, ...] = (
    Company("googl", "GOOGL", 1652044, "알파벳"),
    Company("tsla", "TSLA", 1318605, "테슬라"),
    Company("ibm", "IBM", 51143, "IBM"),
    Company("qbts", "QBTS", 1907982, "디웨이브"),
)
BY_ID = {c.id: c for c in COMPANIES}
