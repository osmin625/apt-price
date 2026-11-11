"""지수 분석이 견주는 경제지표 — 목록·짝·변화의 정의·발표 시차·**상식의 방향**이 여기 한 곳에 있다.

응답(`service.effects_of`)과 적재(`ingest_stock` 의 한국은행 계열)가 이 목록을 읽는다. 받는 코드는 출처의
표(`ecos.TABLES`·`fred.SERIES`)에 따로 있어서, 여기만 더하고 거기를 빼먹으면 화면에 '표본이 짧아 재지
않음' 만 조용히 뜬다. `scripts/verify_index_effects.py` 가 모든 지표가 제 출처의 표에 있는지 본다.

## 미국이 먼저다

목록과 짝은 **미국 지표를 앞에** 둔다(2026-11-12 요청 — 주식의 모든 정보는 미국 우선). 화면이 이 순서
그대로 카드를 깐다. 함께 넣은 회귀(`effects.joint`)는 열 순서와 무관하다.

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

## 상식의 방향 — `expect`·`why`

지표가 오를 때 주가가 **같이 가는가(+1, 정방향) 거꾸로 가는가(−1, 역방향)** — 교과서·시장에서 흔히
말하는 쪽이다. 잰 값이 아니라 **잰 값과 견줄 기준**이라 손으로 적는다(2026-11-12 요청). 화면은 카드마다
이 방향과 잰 막대를 나란히 두고, 맞는지(`service._agree`)를 응답이 센다.

이유(`why`)는 화면 ⓘ 에 그대로 나간다 — 시간이 지나도 맞는 말만 적는다. 반론이 널리 알려진 것(환율 —
수출 기업에는 이롭다)은 이유에 같이 적는다. 방향을 잰 값에 맞춰 고치지 않는다 — 그러면 기준이 아니게 된다.
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
    expect: int    # 상식의 방향: +1 정방향(같이 간다) · −1 역방향(거꾸로 간다)
    why: str       # 그 방향의 이유 — 화면 ⓘ


_POLICY = "기준금리가 오르면 돈을 빌리는 값이 비싸지고, 기업의 미래 이익을 지금 값으로 깎는 할인율도 높아집니다."
_LONG = "장기 금리가 오르면 할인율이 높아지고, 주식 대신 채권으로도 높은 수익을 얻을 수 있어 주식의 매력이 줄어듭니다."
_CPI = "물가가 빨리 오르면 중앙은행이 금리를 올릴 것이 예상되고, 기업의 원가 부담도 커집니다."
_M2 = "시중에 풀린 돈이 늘면 그 돈이 주식 같은 자산으로 흘러 가격을 밀어 올린다고 봅니다."

INDICATORS: tuple[Indicator, ...] = (
    Indicator("us_fedfunds", "미국 기준금리", "금리", "diff", 0, "FRED", -1, _POLICY),
    Indicator("us_10y", "미국 10년 국채", "금리", "diff", 0, "FRED", -1, _LONG),
    Indicator("us_term_spread", "미국 장단기 금리차", "금리", "level", 0, "FRED", +1,
              "장기 금리가 단기 금리보다 높은 것이 정상입니다. 역전(음수)은 경기 침체를 앞서 알리는 신호로 "
              "알려져 있어, 금리차가 클수록 주가에 좋다고 봅니다."),
    Indicator("us_cpi", "미국 소비자물가", "물가", "growth", 1, "FRED", -1, _CPI),
    Indicator("us_m2", "미국 M2", "통화량", "growth", 1, "FRED", +1, _M2),
    Indicator("us_unrate", "미국 실업률", "환율·경기", "diff", 1, "FRED", -1,
              "실업률이 오르면 경기가 식고 소비와 기업 이익이 줄어든다는 뜻입니다."),
    Indicator("base_rate", "한국 기준금리", "금리", "diff", 0, "ECOS", -1, _POLICY),
    Indicator("cpi", "한국 소비자물가", "물가", "growth", 1, "ECOS", -1, _CPI),
    Indicator("m2", "한국 M2", "통화량", "growth", 1, "ECOS", +1, _M2),
    Indicator("krw_usd", "원/달러 환율", "환율·경기", "growth", 0, "ECOS", -1,
              "환율이 오르면(원화 약세) 외국인이 달러로 셈한 수익이 줄어 자금이 빠진다고 봅니다. "
              "수출 기업의 이익에는 이로워 반대로 보는 견해도 있습니다."),
)
BY_ID = {i.id: i for i in INDICATORS}

# 지수 → 견줄 지표. KOSPI 는 한국 지표에 미국 10년 금리를 더한다 — 외국인 자금이 KOSPI 를 크게
# 움직여서다(합의). S&P 500 은 미국 지표만. 둘 다 미국이 먼저다(위 '미국이 먼저다').
PAIRS: dict[str, tuple[str, ...]] = {
    "spx": ("us_fedfunds", "us_10y", "us_term_spread", "us_cpi", "us_m2", "us_unrate"),
    "kospi": ("us_10y", "base_rate", "cpi", "m2", "krw_usd"),
}


def unit_of(ind: Indicator) -> str:
    """x 의 화면 단위."""
    return "%" if ind.kind == "growth" else "%p"
