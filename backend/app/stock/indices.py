"""지수 목록과 받는 곳. 공식 출처만 — 비공식(야후 등)은 대조용(`scripts/probe_stock_crosscheck.py`).

    S&P 500  FRED SP500                      일별 최근 10년   무위험 금리: 미국 3개월 국채(TB3MS)
    KOSPI    한국은행 ECOS 802Y001 / 0001000  일별 1995-01~   무위험 금리: 한국은행 기준금리

KOSPI 항목 코드는 기억이 아니라 ECOS 목록(StatisticItemList 802Y001)에서 골랐다 — 같은 표에
KOSDAQ·거래대금·외국인 순매수가 나란히 있다. 공공데이터포털 '금융위원회 지수시세정보' 는 따로
활용신청이 필요해서, 이미 키가 있는 ECOS 를 먼저 썼다.

무위험 금리를 왜 붙이나: 후보 모델 하나(`forecast.py` 의 rf·vol)가 '지금 금리 + 과거 위험
프리미엄' 을 중심으로 쓴다. 그래서 거시 계열의 두 번째 쓰임이 생겼고 `app/macro` 로 뽑았다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..macro.clients import ecos, fred


@dataclass(frozen=True)
class Index:
    id: str
    market: str
    symbol: str
    label: str
    currency: str
    source: str
    rf: str          # macro.db 계열 이름(월, 연%)
    rf_label: str


# 미국이 먼저다(2026-11-12 요청 — 주식의 모든 정보는 미국 우선). 화면·적재·검진이 이 순서를 따른다.
INDICES: tuple[Index, ...] = (
    Index("spx", "US", "SPX", "S&P 500", "USD", "FRED", "us_tbill3m", "미국 3개월 국채"),
    Index("kospi", "KR", "KOSPI", "KOSPI", "KRW", "ECOS", "base_rate", "한국은행 기준금리"),
)
BY_ID = {i.id: i for i in INDICES}


def fetch(ix: Index, start: str = "19950101", end: str = "20991231") -> list[tuple[str, float]]:
    """(YYYYMMDD, 종가). 빈 결과는 각 클라이언트가 실패로 던진다."""
    if ix.id == "kospi":
        return [(t, v) for t, v, _ in ecos.fetch_table("802Y001", "0001000", "D", start, end)]
    if ix.id == "spx":
        return [(d, v) for d, v in fred.fetch_csv("SP500") if start <= d <= end]
    raise ValueError(ix.id)
