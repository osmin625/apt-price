"""Alpha Vantage — 미국 개별 종목 주가의 출처(2026-11-14). 문서가 있는 API 이고 무료 키(`ALPHAVANTAGE_API_KEY`)로 받는다.

## 왜 이것인가

미국 개별 종목 주가는 **공식 무료 출처가 없다** — FRED 에는 지수(SP500)만, EDGAR 에는 재무만 있다.
2026-11-14 에 재 본 것:

- Stooq CSV — 이제 자바스크립트 작업 증명(봇 차단) 화면만 돌려준다.
- Nasdaq 사이트 API·야후 차트 API — 키 없이 값이 오지만 **브라우저인 척해야** 받는다(파이썬 요청에는 Nasdaq 가
  403). 사이트가 자동 요청을 막아 둔 것이라 쓰지 않는다. 처음에 Nasdaq 를 주 출처로 정했다가 이 때문에 바꿨다.
- **Alpha Vantage** — 자동 요청을 위한 API. 무료 키는 하루 25번·초당 1번이다.

## 무료로 되는 것과 안 되는 것(같은 날 재 봄)

- 일봉 `TIME_SERIES_DAILY` 는 **최근 100일(compact)만** 무료다. 전체(full)는 유료. 값은 분할 조정이 안 됐다.
- 월봉 `TIME_SERIES_MONTHLY_ADJUSTED` 는 **상장 때부터 전부** 무료이고 분할·배당을 반영한 수정 종가가 있다
  (테슬라 2020-07: 종가 1,430.76 → 수정 95.38 = ÷15, 5:1·3:1 분할).

그래서 **지금 주가는 일봉 마지막 날, 과거는 월봉 수정 종가**를 쓴다. 베타·그림·반영 분해가 모두 월 단위라
월봉으로 충분하다. 종목당 하루 두 번(일봉·월봉)이면 네 종목이 여덟 번이다.

## 조용히 실패한다

한도를 넘거나 키가 틀리거나 유료 기능을 부르면 오류 코드가 아니라 200 과 함께 `Information`·`Note` 한 줄이
온다(초당 1번을 넘겼을 때도). 그래서 시계열 칸이 없으면 그 문구를 담아 실패로 던진다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ...core.config import settings

BASE = "https://www.alphavantage.co/query?"
PAUSE = 1.2   # 초당 1번 — 2026-11-14 에 연달아 부르자 '1 request per second' 안내가 왔다


class AlphaVantageError(RuntimeError):
    pass


def available() -> bool:
    return bool((settings.alphavantage_api_key or "").strip())


def _get(params: dict, key: str) -> dict:
    if not available():
        raise AlphaVantageError("ALPHAVANTAGE_API_KEY 가 없습니다 — backend/.env.example")
    q = urllib.parse.urlencode({**params, "apikey": settings.alphavantage_api_key.strip()})
    try:
        with urllib.request.urlopen(BASE + q, timeout=60) as r:
            body = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise AlphaVantageError(f"Alpha Vantage {params.get('symbol')}: {exc}") from exc
    finally:
        time.sleep(PAUSE)
    if key not in body:
        msg = body.get("Information") or body.get("Note") or body.get("Error Message") or "빈 응답"
        raise AlphaVantageError(f"Alpha Vantage {params.get('symbol')}: {str(msg)[:140]}")
    return body[key]


def recent(symbol: str) -> list[tuple[str, float]]:
    """최근 100 거래일 (YYYYMMDD, 종가) — 분할 조정 안 됨."""
    ts = _get({"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact"}, "Time Series (Daily)")
    return sorted((d.replace("-", ""), float(v["4. close"])) for d, v in ts.items())


def monthly(symbol: str) -> list[tuple[str, float, float]]:
    """상장 때부터 (YYYYMM, 그달 마지막 종가, 수정 종가). 이번 달은 진행 중인 값으로 온다."""
    ts = _get({"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": symbol}, "Monthly Adjusted Time Series")
    return sorted((d.replace("-", "")[:6], float(v["4. close"]), float(v["5. adjusted close"])) for d, v in ts.items())
