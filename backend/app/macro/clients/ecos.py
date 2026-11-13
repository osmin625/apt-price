"""한국은행 ECOS — 통화량(M2)·기준금리·소비자물가.

## 왜 이것만 ECOS 인가

거시 요인 여섯 중 다섯은 한국부동산원(R-ONE)에 있었다(`realestate/clients/reb.py` 의
`MACRO_TABLES`). **M2 와 기준금리만 없어서** 여기로 온다.

## 코드를 기억으로 적지 않는다

통계표 코드는 검색해서 나온 것을 베끼지 않고 **ECOS 가 돌려주는 목록에서 골랐다**
(`scripts/probe_ecos.py`). 실제로 검색 결과에는 M2 가 `101Y003` 이라고 적혀 있었는데
그것은 **구지표**(1.7.x)였다. 지금 쓰는 신지표는 `161Y006` 이다. 둘 다 M2 라는
이름으로 존재하므로, 기억에 의존했으면 조용히 옛 계열을 썼을 것이다.

    161Y006 / BBHA00   M2(평잔, 원계열)       월 200310~
    722Y001 / 0101000  한국은행 기준금리        월 199905~
    901Y009 / 0        소비자물가지수 총지수   월 196501~

## 키가 없어도 막히지는 않는다

ECOS 는 `sample` 을 키 자리에 넣으면 **진짜 값**을 돌려준다. 다만 한 번에 10행이
상한이라(재서 확인했다. 11행을 달라고 하면 ERROR-301) 느리다. 그래서

- `ECOS_API_KEY` 가 있으면 1,000행씩 받는다
- 없으면 `sample` 로 10행씩 받는다. 되긴 하지만 **정식 경로가 아니다** — 적재할 때
  경고를 찍는다.

TMAP 키가 없을 때 직선거리로 폴백하는 것과 같은 생각이다. 키를 받기 전에도 화면을
완성해 볼 수 있어야 한다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ...core.config import settings

BASE = "https://ecos.bok.or.kr/api"

# 샘플 키의 1회 상한. 재서 확인했다 — 11을 달라고 하면 ERROR-301 이 온다.
SAMPLE_PAGE = 10
REAL_PAGE = 1000


class EcosError(RuntimeError):
    pass


@dataclass(frozen=True)
class EcosPoint:
    metric: str
    ym: str
    value: float
    unit: str


# (통계표, 항목, 주기). 전부 `probe_ecos.py` 가 목록에서 확인한 값이다.
TABLES: dict[str, tuple[str, str, str]] = {
    "m2": ("161Y006", "BBHA00", "M"),        # M2 평잔 원계열(십억원)
    "base_rate": ("722Y001", "0101000", "M"),  # 한국은행 기준금리(연%)
    # 소비자물가 총지수(전국, 2020=100). 거시 요인을 실질로 바꾸면 결론이 달라지나
    # 재려고 받는다(docs/analysis/macro.md). 물가 절(4.)의 **4.1 은 생산자물가**이고 소비자
    # 물가는 4.2 다 — 이름이 비슷한 표가 나란히 있어 목록에서 골랐다. 통계청이 5년
    # 마다 기준연도를 바꾸지만 매번 처음부터 다시 받으므로 기준이 섞이지 않는다.
    "cpi": ("901Y009", "0", "M"),
    # 매매·전세·월세 탭의 '같은 집 월 주거비'(2026-10-19). 예금은행 **신규취급액** 기준 — 지금
    # 빌리거나 맡기는 사람이 마주하는 금리다(잔액 기준은 예전 계약이 섞인다). 목록에서 골랐다.
    "mortgage_rate": ("121Y006", "BECBLA0302", "M"),     # 주택담보대출(연%) 2001-09~
    "jeonse_loan_rate": ("121Y006", "BECBLA03041", "M"),  # 전세자금대출(연%) 2015-01~
    "deposit_rate": ("121Y002", "BEABAA211", "M"),       # 정기예금(연%) — 자기 돈의 기회비용
    # 주식 '지수 분석' 의 원/달러(2026-11). 한 항목 아래 **평균자료(0000100)·말일자료(0000200)** 두
    # 줄이 온다 — 항목 코드 하나만 주면 달마다 두 값이 섞인다(받아 보고 알았다). 지수가 월말
    # 종가라 말일자료를 고른다. 항목 자리에 '/' 로 둘째 코드를 이어 붙이면 ECOS 가 받는다.
    "krw_usd": ("731Y004", "0000001/0000200", "M"),
    # 주식 '장기 투자' 의 KOSPI 지수 평가(2026-11-13, app/stock/valuation.py). 전부 목록에서 골랐다.
    # 901Y014 는 한 항목에 연(A)·월(M) 두 줄이 있다 — 월은 시가총액 2005-01~, PER 2004-01~ 부터다.
    "kospi_mcap": ("901Y014", "1040000", "M"),   # KOSPI 시가총액(천원) — 버핏 지표의 분자
    "kospi_per": ("901Y014", "1110000", "M"),    # KOSPI 주가이익비율(배) — 이익 수익률·CAPE
    "kr_10y": ("721Y001", "5050000", "M"),       # 국고채 10년(연%) 2000-10~
    # 명목 GDP(계절조정, 분기, 십억원) — 분기 값 그대로라 연 GDP 는 ×4. **속보치는 실질만** 내므로
    # 명목은 분기 끝에서 두 달 남짓 뒤 잠정치로 들어온다.
    "kr_gdp": ("200Y107", "10601", "Q"),
}


def api_key() -> str:
    # **`os.getenv` 가 아니라 `settings`** 다. 이 저장소는 pydantic Settings 가
    # `.env` 를 읽는다 — 처음에 os.getenv 로 썼다가 키를 넣어도 `available()` 이
    # False 였다. 다른 클라이언트(reb·kakao·tmap)와 같은 길을 쓴다.
    return (getattr(settings, "ecos_api_key", "") or "").strip()


def available() -> bool:
    """정식 키가 있나. 없어도 `sample` 로 돌지만 그것과는 구분한다."""
    return bool(api_key())


def _get(path: str) -> dict:
    url = f"{BASE}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise EcosError(f"ECOS 연결 실패: {exc}") from exc
    if "RESULT" in data:
        res = data["RESULT"]
        raise EcosError(f"ECOS {res.get('CODE')}: {res.get('MESSAGE', '')[:120]}")
    return data


def fetch_table(code: str, item: str, cycle: str, start: str, end: str) -> list[tuple[str, float, str]]:
    """통계표 하나의 (시점, 값, 단위). 시점은 ECOS 꼴 그대로 — 월 'YYYYMM', 일 'YYYYMMDD'.

    거시 지표(`fetch`)와 주식 지수(KOSPI 일별, `app/stock/indices.py`)가 같이 쓴다.
    **빈 결과를 성공으로 넘기지 않는다.** 코드가 바뀌면 오류가 아니라 0행이 온다.
    """
    key = api_key() or "sample"
    page = REAL_PAGE if available() else SAMPLE_PAGE
    width = {"M": 6, "D": 8}.get(cycle)

    out: list[tuple[str, float, str]] = []
    first = 1
    while True:
        d = _get(f"StatisticSearch/{key}/json/kr/{first}/{first + page - 1}/"
                 f"{code}/{cycle}/{start}/{end}/{item}")
        rows = d["StatisticSearch"]["row"]
        for r in rows:
            v = r.get("DATA_VALUE")
            t = str(r.get("TIME") or "")
            if v in (None, "") or (width and len(t) != width):
                continue
            out.append((t, float(v), str(r.get("UNIT_NAME") or "")))
        total = int(d["StatisticSearch"].get("list_total_count") or 0)
        first += page
        if first > total or not rows:
            break
        if not available():
            time.sleep(0.12)

    if not out:
        raise EcosError(f"{code}/{item}: 0행. 통계표 코드를 "
                        f"`python -m scripts.probe_ecos` 로 다시 확인하세요.")
    return out


# 주기마다 시점 꼴이 다르다 — 분기는 '2026Q2'. 월 꼴('200001')을 분기 표에 주면 ECOS 가 오류를 낸다.
SPAN = {"M": ("200001", "209912"), "Q": ("1960Q1", "2099Q4")}


def fetch(metric: str, start_ym: str | None = None, end_ym: str | None = None) -> list[EcosPoint]:
    """한 지표의 시계열. 월은 'YYYYMM', 분기는 'YYYYQn'."""
    code, item, cycle = TABLES[metric]
    a, b = SPAN[cycle]
    return [EcosPoint(metric=metric, ym=t, value=v, unit=u)
            for t, v, u in fetch_table(code, item, cycle, start_ym or a, end_ym or b)]
