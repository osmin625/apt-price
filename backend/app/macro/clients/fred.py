"""미국 연준 세인트루이스 FRED — 키 없이 받는 CSV.

## 왜 API 가 아니라 CSV 인가

FRED API 는 키가 필요하지만, 그래프 화면이 쓰는 `fredgraph.csv` 는 **키 없이 같은 계열을**
준다(재서 확인했다 — SP500·TB3MS 모두). 키가 없어도 적재가 막히지 않게 이 길을 쓴다. ECOS 가
키 없이 `sample` 로 도는 것과 같은 생각이다.

## 받는 것

    TB3MS   미국 3개월 국채 금리(유통, 월평균, 연%)   1934~  — S&P 500 의 무위험 금리
    SP500   S&P 500 지수(일별 종가)                 최근 10년 — 주식 쪽(`app/stock/indices.py`)

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
}


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


def fetch_monthly(name: str) -> list[tuple[str, float, str]]:
    """macro.db 용 (YYYYMM, 값, 단위). 월 계열은 그 달 1일 날짜로 온다."""
    sid, freq, unit = SERIES[name]
    assert freq == "M", name
    return [(d[:6], v, unit) for d, v in fetch_csv(sid)]
