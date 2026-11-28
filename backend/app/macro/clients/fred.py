"""미국 연준 세인트루이스 FRED — 키 없이 받는 CSV.

## 왜 API 가 아니라 CSV 인가

FRED API 는 키가 필요하지만, 그래프 화면이 쓰는 `fredgraph.csv` 는 **키 없이 같은 계열을**
준다(재서 확인했다 — SP500·TB3MS 모두). 키가 없어도 적재가 막히지 않게 이 길을 쓴다. ECOS 가
키 없이 `sample` 로 도는 것과 같은 생각이다.

## 받는 것

    TB3MS   미국 3개월 국채 금리(유통, 월평균, 연%)   1934~  — S&P 500 의 무위험 금리
    FEDFUNDS·GS10·T10Y3MM·CPIAUCSL·M2SL·UNRATE        — 지수 분석의 미국 지표(`SERIES`)
    VIXCLS·BAA10YM·NFCI  VIX·회사채 신용 스프레드·금융여건지수 — 같은 지표의 '위험·여건' 묶음
    NCBEILQ027S·GDP  시가총액·명목 GDP(분기)          — 장기 투자의 버핏 지표
    SP500   S&P 500 지수(일별 종가)                 최근 10년 — 주식 쪽(`app/stock/indices.py`)

## 날마다·주마다 나오는 계열 — `MONTH_END`

macro.db 는 월 계열만 받는다. VIX(날마다)·금융여건지수(주마다)는 **그 달의 마지막 관측값**을 그 달 값으로
둔다. 지수가 월말 종가라 같은 날에 맞춘 것이다(달 평균이면 x 가 y 보다 반 달 앞선 값이 된다). 날짜를
그냥 'YYYYMM' 으로 자르면 한 달에 스무 행이 같은 시점으로 들어가 upsert 순서가 값을 정한다 — 그래서 여기서
하나로 줄인다.

## 하이일드 스프레드가 아닌 이유

처음 고른 것은 ICE BofA 하이일드 스프레드(BAMLH0A0HYM2)였다. 2026-11-29 에 받아 보니 **최근 3년치(786행,
2023-11~)만** 왔다 — ICE 가 FRED 에 주는 과거를 3년으로 줄였다. 지수 분석은 3년(36개월)이 재는 최소라
'그 뒤 12개월' 은 아예 못 잰다. 그래서 같은 '신용 위험의 값' 을 1953년부터 주는 **무디스 Baa 회사채 − 10년
국채(BAA10YM, 월평균)** 를 쓴다. 투자 등급의 맨 아래 칸이라 하이일드보다 폭이 작지만 같은 때 같이 벌어진다.

**SP500 은 FRED 에 최근 10년만 있다**(S&P 다우존스 지수의 사용 조건). 그보다 긴 공식 무료
출처를 찾지 못했다. 그래서 S&P 500 의 백테스트 기점은 KOSPI 보다 훨씬 적다 — 화면이 기점 수를
같이 적는다.

빈 값은 '.' 또는 빈 칸으로 온다(휴장일). 0 으로 채우지 않고 건너뛴다.
"""

from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request

BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

# 우리 이름 → (FRED 계열 id, 주기, 단위). macro.db 에 우리 이름으로 들어간다.
SERIES: dict[str, tuple[str, str, str]] = {
    "us_tbill3m": ("TB3MS", "M", "연%"),
    # 주식 '지수 분석' 의 미국 지표(2026-11, app/stock/indicators.py). 전부 월 계열이다 — 금리는
    # 월평균, 물가·M2 는 계절조정. 장단기 금리차는 일별(T10Y3M) 말고 월평균(T10Y3MM)을 쓴다.
    "us_fedfunds": ("FEDFUNDS", "M", "연%"),
    "us_10y": ("GS10", "M", "연%"),
    "us_term_spread": ("T10Y3MM", "M", "%p"),
    "us_cpi": ("CPIAUCSL", "M", "1982-84=100"),
    "us_m2": ("M2SL", "M", "십억달러"),
    "us_unrate": ("UNRATE", "M", "%"),
    # 같은 탭의 '위험·여건' 묶음(2026-11-29 요청). VIX·금융여건지수는 날·주 계열이라 그 달 마지막 값으로 줄인다
    # (`MONTH_END`). 신용 스프레드는 FRED 의 월평균 그대로다 — 위 '하이일드 스프레드가 아닌 이유'.
    "us_vix": ("VIXCLS", "M", "pt"),
    "us_credit_spread": ("BAA10YM", "M", "%p"),
    "us_nfci": ("NFCI", "M", "표준편차"),
    # 주식 '장기 투자' 의 버핏 지표(2026-11-13, app/stock/valuation.py). 둘 다 분기다.
    # 시가총액은 연준 자금순환표(Z.1)의 **비금융 법인 주식(부채 쪽, 시가)** 이다. 모든 부문 합계
    # (BOGZ1FL893064105Q)는 미국인이 든 **외국 주식**까지 들어 있어 GDP(국내)와 맞지 않는다 — 2026Q2 에
    # 124조 달러로, 비금융 법인(83조)의 1.5배였다. 윌셔 5000(WILL5000IND)은 FRED 에서 내려갔다(404).
    "us_mcap": ("NCBEILQ027S", "Q", "백만달러"),
    "us_gdp": ("GDP", "Q", "십억달러(연율)"),  # 명목, 계절조정 연율 — 분기 값이 이미 1년치 크기다
}


# 날·주 계열 → 그 달의 마지막 관측값(위 'MONTH_END'). 값은 원래 주기 — 적는 곳은 여기뿐이다.
MONTH_END: dict[str, str] = {"us_vix": "D", "us_nfci": "W"}


class FredError(RuntimeError):
    pass


def fetch_csv(series_id: str) -> list[tuple[str, float]]:
    """(YYYYMMDD, 값). 날짜 오름차순. 빈 결과는 실패다."""
    try:
        with urllib.request.urlopen(BASE + series_id, timeout=60) as r:
            text = r.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise FredError(f"FRED 연결 실패({series_id}): {exc}") from exc
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2 or rows[0][1] != series_id:
        # 계열 id 가 틀리면 FRED 는 오류 대신 HTML 이나 다른 머리를 준다.
        raise FredError(f"FRED {series_id}: 머리가 예상과 다릅니다 — {rows[0][:2] if rows else '빈 응답'}")
    out = []
    for d, v, *_ in rows[1:]:
        if v in ("", "."):
            continue
        out.append((d.replace("-", ""), float(v)))
    if not out:
        raise FredError(f"FRED {series_id}: 0행")
    return sorted(out)


def period(d: str, freq: str) -> str:
    """FRED 날짜(그 기간의 첫날)를 macro.db 시점으로 — 월 'YYYYMM', 분기 'YYYYQn'(ECOS 와 같은 꼴)."""
    if freq == "M":
        return d[:6]
    if freq == "Q":
        return f"{d[:4]}Q{(int(d[4:6]) - 1) // 3 + 1}"
    raise ValueError(freq)


def fetch_series(name: str) -> list[tuple[str, float, str]]:
    """macro.db 용 (시점, 값, 단위). 월·분기 계열은 그 기간의 첫날 날짜로 온다."""
    sid, freq, unit = SERIES[name]
    rows = fetch_csv(sid)
    if name in MONTH_END:
        # 오름차순이라 같은 달의 뒤 값이 앞 값을 덮는다 — 남는 것이 그 달 마지막 관측값이다.
        last = {d[:6]: v for d, v in rows}
        return [(p, v, unit) for p, v in sorted(last.items())]
    return [(period(d, freq), v, unit) for d, v in rows]
