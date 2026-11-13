"""로버트 실러 교수의 공개 자료(ie_data.xls) — S&P 500 의 1871년부터의 월별 주가·이익·물가·10년 금리·CAPE.

## 왜 비공식 출처를 받나

이 저장소는 공식 출처만 받고 비공식은 대조에만 쓴다(backend/app/stock/CLAUDE.md '출처는 공식, 대조는 비공식').
실러 자료는 **그 규칙의 예외**다(2026-11-12 grilling). 이유는 둘이다.

- S&P 500 의 주당 이익은 공식 무료 출처가 없다. FRED 의 기업이익(국민계정, CP)은 S&P 500 이 아니라
  미국 법인 전체이고, 시가총액과 짝지으면 금융·해외 주식이 어긋난다(`fred.SERIES` 의 us_mcap 주석).
- FRED 의 S&P 500 은 최근 10년뿐이다. 그 뒤 10년 수익률을 재려면 수십 년이 필요하다.

그래서 **받을 때마다 공식 출처와 맞춰 본다**(`scripts/ingest_stock.py`) — 주가는 FRED SP500 의 달 평균,
10년 금리는 FRED GS10. 어긋나면 적재하지 않는다.

## 받는 곳

예일 대학의 옛 주소(econ.yale.edu/~shiller/data/ie_data.xls)는 **2023-10 에 멈췄다** — 지금도 파일을 주지만
그 뒤 달이 없다(2026-11-13 에 Last-Modified 2023-10-17). 지금은 shillerdata.com 이 내려받기 주소를 걸어 두고,
그 주소에 판 번호(`?ver=`)가 붙어 바뀐다. 그래서 **첫 화면에서 ie_data.xls 링크를 찾아** 받는다. 못 찾으면
옛 주소로 조용히 돌아가지 않고 실패한다 — 돌아가면 3년 묵은 값이 오류 없이 들어온다.

## 표의 꼴

'Data' 시트, 머리 8줄 뒤 한 달 한 줄. 날짜는 1871.01 꼴의 수(**10월은 2026.1** — 소수 둘째 자리까지 읽는다).
P 는 그 달 일별 종가의 평균, E 는 지난 12개월 주당 이익(분기 값을 달로 나눠 이은 것), 마지막 몇 달은 E 가
비어 있다(이익 발표가 늦다). 열 위치는 머리 글자로 확인한다 — 열이 하나 끼면 CAPE 자리에 다른 값이 들어온다.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

PAGE = "https://shillerdata.com/"
SHEET = "Data"
HEAD_ROW = 7     # 0부터. 'Date', 'P', 'D', 'E', 'CPI', … 가 있는 줄
FIRST_ROW = 8

# 우리 이름 → (열, 그 열 머리 글자, 단위). 머리 글자는 HEAD_ROW 의 값 그대로다.
SERIES: dict[str, tuple[int, str, str]] = {
    "shiller_p": (1, "P", "지수"),
    "shiller_e": (3, "E", "지수 주당 달러"),
    "shiller_cpi": (4, "CPI", "지수"),
    "shiller_gs10": (6, "Rate GS10", "연%"),
    "shiller_cape": (12, "CAPE", "배"),
}


class ShillerError(RuntimeError):
    pass


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.URLError as exc:
        raise ShillerError(f"실러 자료 연결 실패({url[:60]}): {exc}") from exc


def file_url() -> str:
    html = _get(PAGE).decode("utf-8", "replace")
    found = re.findall(r'href="((?:https?:)?//[^"]+/ie_data\.xls[^"]*)"', html)
    if not found:
        raise ShillerError("shillerdata.com 에서 ie_data.xls 링크를 못 찾았습니다 — 페이지가 바뀌었는지 보세요.")
    u = found[0].replace("&amp;", "&")
    return "https:" + u if u.startswith("//") else u


def month_of(x: float) -> str:
    """1871.01 → '187101'. 2026.1 은 10월이다(2026.10 이 수로 줄어든 것)."""
    y = int(x)
    m = int(round((x - y) * 100))
    if not 1 <= m <= 12:
        raise ShillerError(f"날짜 {x} 를 달로 못 읽었습니다")
    return f"{y:04d}{m:02d}"


def parse(raw: bytes) -> dict[str, list[tuple[str, float]]]:
    """{우리 이름: [(YYYYMM, 값)]}. 빈 칸은 건너뛴다. 머리가 다르면 실패."""
    import xlrd  # 지연 import — 실러 자료를 받을 때만 필요하다

    book = xlrd.open_workbook(file_contents=raw)
    sh = book.sheet_by_name(SHEET)
    if str(sh.cell_value(HEAD_ROW, 0)).strip() != "Date":
        raise ShillerError(f"머리 줄이 바뀌었습니다: {sh.row_values(HEAD_ROW)[:6]}")
    for name, (col, head, _) in SERIES.items():
        got = str(sh.cell_value(HEAD_ROW, col)).strip()
        if got != head:
            raise ShillerError(f"{name}: {col}번 열 머리가 '{got}' — 기대 '{head}'. 열이 옮겨졌습니다.")
    out: dict[str, list[tuple[str, float]]] = {k: [] for k in SERIES}
    prev = None
    for r in range(FIRST_ROW, sh.nrows):
        d = sh.cell_value(r, 0)
        if not isinstance(d, float):
            continue  # 맨 끝의 각주 줄
        ym = month_of(d)
        if prev and ym <= prev:
            raise ShillerError(f"달이 거꾸로 갑니다: {prev} → {ym}")
        prev = ym
        for name, (col, _, _) in SERIES.items():
            v = sh.cell_value(r, col)
            if isinstance(v, float):
                out[name].append((ym, v))
    for name, rows in out.items():
        if len(rows) < 1000:
            raise ShillerError(f"{name}: {len(rows)}행 — 1871년부터면 1,800행이 넘어야 합니다")
    return out


def fetch() -> dict[str, list[tuple[str, float]]]:
    return parse(_get(file_url()))
