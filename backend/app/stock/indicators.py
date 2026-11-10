"""지수 분석이 견주는 경제지표 — 목록·짝·변화의 정의·발표 시차가 **여기 한 곳**에 있다.

응답(`service.effects_of`)과 적재(`ingest_stock` 의 한국은행 계열)가 이 목록을 읽는다. 받는 코드는 출처의
표(`ecos.TABLES`·`fred.SERIES`)에 따로 있어서, 여기만 더하고 거기를 빼먹으면 화면에 '표본이 짧아 재지
않음' 만 조용히 뜬다. `scripts/verify_index_effects.py` 가 모든 지표가 제 출처의 표에 있는지 본다.

## 움직임의 정의 — `kind`

지수는 수익률(변화)이므로 지표도 변화로 맞춘다(2026-11 합의). 단위가 달라 둘로 나눈다.

- `diff`   — 1년 새 몇 %p 변했나. 금리·실업률처럼 이미 % 인 것
- `growth` — 1년 상승률(%). 물가지수·M2·환율처럼 수준이 단위를 가진 것
- `level`  — 수준 그대로. **미국 장단기 금리차만**이다. 역전(음수) 여부가 널리 알려진 신호라
  변화로 바꾸면 그 신호를 버린다. 화면이 예외라고 적는다

## 발표 시차 — `pub_lag`

그 달 값을 언제 알 수 있나(개월). 물가·M2·실업률은 다음 달 중순에야 나와서 1 이다. '그 뒤'
수익률을 그 달 말부터 재면 아직 몰랐던 값으로 미래를 맞힌 셈이 된다. 금리·환율은 그날
알려지므로 0 이다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Indicator:
    id: str        # macro.db 계열 이름
    label: str
    group: str     # 금리 · 물가 · 통화량 · 환율·경기
    kind: str      # diff · growth · level
    pub_lag: int   # 개월
    source: str    # ECOS · FRED


INDICATORS: tuple[Indicator, ...] = (
    Indicator("base_rate", "한국 기준금리", "금리", "diff", 0, "ECOS"),
    Indicator("cpi", "한국 소비자물가", "물가", "growth", 1, "ECOS"),
    Indicator("m2", "한국 M2", "통화량", "growth", 1, "ECOS"),
    Indicator("krw_usd", "원/달러 환율", "환율·경기", "growth", 0, "ECOS"),
    Indicator("us_fedfunds", "미국 기준금리", "금리", "diff", 0, "FRED"),
    Indicator("us_10y", "미국 10년 국채", "금리", "diff", 0, "FRED"),
    Indicator("us_term_spread", "미국 장단기 금리차", "금리", "level", 0, "FRED"),
    Indicator("us_cpi", "미국 소비자물가", "물가", "growth", 1, "FRED"),
    Indicator("us_m2", "미국 M2", "통화량", "growth", 1, "FRED"),
    Indicator("us_unrate", "미국 실업률", "환율·경기", "diff", 1, "FRED"),
)
BY_ID = {i.id: i for i in INDICATORS}

# 지수 → 견줄 지표. KOSPI 는 한국 지표에 미국 10년 금리를 더한다 — 외국인 자금이 KOSPI 를 크게
# 움직여서다(합의). S&P 500 은 미국 지표만.
PAIRS: dict[str, tuple[str, ...]] = {
    "kospi": ("base_rate", "cpi", "m2", "krw_usd", "us_10y"),
    "spx": ("us_fedfunds", "us_10y", "us_term_spread", "us_cpi", "us_m2", "us_unrate"),
}


def unit_of(ind: Indicator) -> str:
    """x 의 화면 단위."""
    return "%" if ind.kind == "growth" else "%p"
