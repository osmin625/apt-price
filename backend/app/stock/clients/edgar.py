"""SEC EDGAR 의 XBRL 재무(companyfacts) — 미국 종목 재무의 공식 출처. 키가 없다.

    https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json

회사 하나가 3~6MB 다. 필요한 개념만 뽑아 stock.db 의 `facts` 에 넣는다.

## 받는 개념

    NetIncomeLoss                                   순이익(기간) — 지금 사업의 값, 기대 몫의 바탕
    Revenues / RevenueFromContractWithCustomer...   매출(기간) — 회사·시기마다 쓰는 이름이 달라 둘 다 받는다
    OperatingIncomeLoss                             영업이익(기간)
    CommonStockSharesOutstanding                    발행 주식 수(시점, 대차대조표)
    WeightedAverageNumberOfDilutedSharesOutstanding 희석 가중평균 주식 수(기간)

**주식 수는 dei:EntityCommonStockSharesOutstanding 을 쓰지 않는다.** 알파벳처럼 주식 종류(A·B·C)가 여럿이면
그 값은 종류별로만 보고되고, companyfacts 는 종류별(차원이 붙은) 값을 빼고 준다 — 알파벳은 그 개념이 아예
없었다(2026-11-14). 대차대조표의 합계(CommonStockSharesOutstanding)를 쓰고, 그것이 희석 주식 수보다
오래됐으면(IBM 은 10-K 에만 적는다) 희석 주식 수를 쓴다(`fundamentals.shares`).

## 한 기간에 값이 여럿 온다

같은 기간(시작·끝)이 그 분기 10-Q, 다음 해 10-Q(전년 비교), 10-K 에 거듭 실린다. 고쳐 실리기도 한다.
그래서 **제출일(filed)을 키에 넣어 다 받고**, 읽는 쪽이 '그날 알던 값'(가장 이른 제출) 또는 '지금 아는 값'
(가장 늦은 제출)을 고른다.

## 요청 머리

SEC 는 자동 요청에 User-Agent 를 요구한다. 개인 정보 없이 일반 이름을 단다(2026-11-14 에 이것으로 200).
초당 10번 상한이라 회사 사이에 쉬어 간다.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request

BASE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
HEADERS = {"User-Agent": "apt-price-research/1.0", "Accept-Encoding": "gzip"}

# 우리 이름 → (택소노미, 개념 후보 — 앞의 것이 먼저, 단위)
CONCEPTS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "net_income": ("us-gaap", ("NetIncomeLoss",), "USD"),
    "revenue": ("us-gaap", ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"), "USD"),
    "operating_income": ("us-gaap", ("OperatingIncomeLoss",), "USD"),
    "shares_out": ("us-gaap", ("CommonStockSharesOutstanding",), "shares"),
    "shares_diluted": ("us-gaap", ("WeightedAverageNumberOfDilutedSharesOutstanding",), "shares"),
}


class EdgarError(RuntimeError):
    pass


def fetch(cik: int) -> dict:
    req = urllib.request.Request(BASE.format(cik=cik), headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
    except urllib.error.URLError as exc:
        raise EdgarError(f"EDGAR CIK {cik}: {exc}") from exc
    finally:
        time.sleep(0.2)
    return json.loads(raw.decode("utf-8"))


def extract(body: dict) -> list[dict]:
    """facts 표에 넣을 줄 — concept·start('' = 시점 값)·end·value·form·fp·fy·filed."""
    out: list[dict] = []
    facts = body.get("facts") or {}
    for name, (tax, candidates, unit) in CONCEPTS.items():
        seen: set[tuple] = set()
        for concept in candidates:
            for f in ((facts.get(tax) or {}).get(concept) or {}).get("units", {}).get(unit, []):
                key = (f.get("start", ""), f["end"], f["filed"])
                if key in seen:
                    continue  # 앞 후보가 이미 준 기간·제출 — 이름만 다른 같은 값
                seen.add(key)
                out.append({"concept": name, "start": f.get("start", "").replace("-", ""),
                            "end": f["end"].replace("-", ""), "value": float(f["val"]),
                            "form": f.get("form", ""), "fp": f.get("fp") or "", "fy": int(f.get("fy") or 0),
                            "filed": f["filed"].replace("-", "")})
    if not any(r["concept"] == "net_income" for r in out):
        raise EdgarError(f"{body.get('entityName')}: 순이익(NetIncomeLoss)이 없다 — 개념 이름이 바뀌었는지 보세요")
    return out
