"""국토교통부 건축HUB — 건축물대장 표제부.

멸실이 시군구로 공표되지 않아서 쓴다. 공표 통계(R-ONE·KOSIS·통계누리)는 셋 다
시도 단위다. 그래서 **우리가 직접 전수를 떠서 해마다 비교한다** — 지난번에 있었는데
이번에 없는 건축물이 그 사이 멸실된 것이다.

## 이 API 는 **조용히 0 을 돌려준다**

가장 중요한 성질이다. 간헐적으로 `totalCount: 0` 을 `resultCode: "00"`(NORMAL
SERVICE)과 함께 보낸다. 오류가 아니라 **정상 응답 모양의 빈 결과**다.

실제로 겪었다. 법정동 439개를 두 번 세었더니 265,799동과 295,324동이 나왔다 —
**10% 차이**다. 수원 권선구 세류동은 5,565동인데 어떤 호출에서는 0 이었고, 화성
동탄구 능동(938동)은 한 번에 통째로 0 으로 와서 '건축물이 없는 구' 로 보였다.

K-apt 에서 겪은 것과 같은 모양이다(일시 오류에 재시도가 없어 시군구 6곳이 통째로
빠졌다). 그래서 여기서는 **0 을 성공으로 받지 않는다.**

- 0 이 오면 쉬었다가 다시 묻는다(기본 4번)
- 그래도 0 이면 **빈 결과가 아니라 실패**로 돌려준다. 부르는 쪽이 판단한다
- 호출 사이에 간격을 둔다. 몰아치면 0 이 늘어난다(재서 확인했다)

## 한도

응답 헤더에 `x-ratelimit-limit: 10000`, `x-ratelimit-remaining` 이 온다. 전수 한 번이
약 2,700~3,000콜이라 하루 한 번은 넉넉하다. 남은 수를 읽어 두면 중간에 끊길지
미리 알 수 있다.

## 조회 단위

(시군구코드 5자리 + 법정동코드 5자리)다. 법정동 목록은 행정표준코드관리시스템에서
받아 `backend/data/manual/bjdong_*.tsv` 에 둔다 — API 가 목록을 주지 않는다.
우리 17개 구에 439개(동 198 + 리 241)가 있다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..config import settings

BASE = "http://apis.data.go.kr/1613000/BldRgstHubService"

# 한 번에 받는 행. **상한이 100 이다** — 500·1000 을 줘도 100행만 온다(재서 확인).
PAGE = 100

# 0 이 왔을 때 다시 묻는 횟수와 간격. 간격 없이 재시도하면 또 0 이 온다.
ZERO_RETRY = 4
ZERO_WAIT = 0.6

# 호출 사이 간격. 몰아치면 0 이 늘어난다 — 439콜을 24초에 끝냈을 때 뒤쪽이
# 통째로 0 이었다.
PACE = 0.15


class BldError(RuntimeError):
    pass


@dataclass(frozen=True)
class Building:
    pk: str            # mgmBldrgstPk — 관리건축물대장 PK. 스냅샷 비교의 키다.
    sigungu_cd: str
    bjdong_cd: str
    plat_plc: str      # 지번 주소
    bld_nm: str
    main_purps: str    # 주용도명(공동주택·단독주택·제1종근린생활시설 …)
    hhld_cnt: int      # 세대수
    tot_area: float
    use_apr_day: str   # 사용승인일 YYYYMMDD


def available() -> bool:
    return bool((settings.molit_service_key or "").strip())


def _get(op: str, params: dict) -> tuple[dict, str | None]:
    """(body, 남은 호출수). JSON 이 아니면 올린다."""
    q = {"serviceKey": settings.molit_service_key, "_type": "json", **params}
    r = httpx.get(f"{BASE}/{op}", params=q, timeout=60.0)
    if not r.text.lstrip().startswith("{"):
        raise BldError(f"{op}: JSON 이 아닙니다 — {r.text[:120]}")
    data = r.json()
    head = ((data.get("response") or {}).get("header") or {})
    if head.get("resultCode") not in (None, "00", "0"):
        raise BldError(f"{op}: {head.get('resultCode')} {head.get('resultMsg')}")
    body = (data.get("response") or {}).get("body") or {}
    return body, r.headers.get("x-ratelimit-remaining")


def count(sigungu_cd: str, bjdong_cd: str) -> tuple[int, str | None]:
    """그 법정동의 건축물 수.

    **0 을 믿지 않는다.** 쉬었다 다시 묻고, 끝까지 0 이면 그대로 0 을 돌려주되
    부르는 쪽이 '빈 동네' 와 '못 받았다' 를 구분할 수 있도록 재시도를 다 썼다는
    사실을 남긴다 — 여기서는 숫자만 주고 판단은 `scripts/ingest_bldrgst.py` 가 한다.
    """
    rem = None
    for attempt in range(ZERO_RETRY):
        body, rem = _get("getBrTitleInfo", {
            "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
            "numOfRows": 1, "pageNo": 1})
        n = int(body.get("totalCount") or 0)
        if n:
            return n, rem
        if attempt < ZERO_RETRY - 1:
            time.sleep(ZERO_WAIT)
    return 0, rem


def _rows(body: dict) -> list[dict]:
    items = body.get("items")
    if not isinstance(items, dict):
        return []
    it = items.get("item")
    if isinstance(it, list):
        return it
    return [it] if it else []


def _one(r: dict, sigungu_cd: str, bjdong_cd: str) -> Building | None:
    pk = str(r.get("mgmBldrgstPk") or "").strip()
    if not pk:
        return None

    def num(v, cast):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return cast(0)

    return Building(
        pk=pk,
        sigungu_cd=str(r.get("sigunguCd") or sigungu_cd),
        bjdong_cd=str(r.get("bjdongCd") or bjdong_cd),
        plat_plc=str(r.get("platPlc") or "").strip()[:160],
        bld_nm=str(r.get("bldNm") or "").strip()[:80],
        main_purps=str(r.get("mainPurpsCdNm") or "").strip()[:40],
        hhld_cnt=num(r.get("hhldCnt"), int),
        tot_area=num(r.get("totArea"), float),
        use_apr_day=str(r.get("useAprDay") or "").strip()[:8],
    )


def fetch_dong(sigungu_cd: str, bjdong_cd: str, expect: int | None = None
               ) -> tuple[list[Building], str | None]:
    """한 법정동의 건축물 전부.

    `expect` 를 주면 **받은 수가 그만큼인지 대조한다.** 페이지 하나가 조용히 비어도
    총합만 보고는 모른다 — 이 API 는 빈 결과를 정상으로 돌려주기 때문이다.
    """
    total, rem = count(sigungu_cd, bjdong_cd)
    if not total:
        return [], rem
    if expect is not None and total != expect:
        # 기대와 다르면 알린다. 건축물은 늘고 줄므로 틀렸다고 단정하지 않는다.
        pass

    out: list[Building] = []
    pages = (total + PAGE - 1) // PAGE
    for page in range(1, pages + 1):
        got: list[dict] = []
        for attempt in range(ZERO_RETRY):
            body, rem = _get("getBrTitleInfo", {
                "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
                "numOfRows": PAGE, "pageNo": page})
            got = _rows(body)
            if got:
                break
            if attempt < ZERO_RETRY - 1:
                time.sleep(ZERO_WAIT)
        if not got:
            raise BldError(
                f"{sigungu_cd}/{bjdong_cd} {page}쪽이 {ZERO_RETRY}번 모두 비었습니다. "
                f"총 {total}동 중 {len(out)}동만 받았습니다 — 빈 결과를 성공으로 "
                f"넘기면 그만큼 멸실로 잘못 세어집니다.")
        for r in got:
            b = _one(r, sigungu_cd, bjdong_cd)
            if b:
                out.append(b)
        time.sleep(PACE)
    return out, rem
