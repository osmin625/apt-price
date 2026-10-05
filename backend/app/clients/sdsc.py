"""소상공인시장진흥공단 상가(상권)정보 API 클라이언트.

공공데이터포털 '소상공인시장진흥공단_상가(상권)정보'
https://www.data.go.kr/data/15083033/openapi.do

## 왜 카카오가 아니라 여기인가

처음에는 카카오 로컬 API 로 셀 생각이었다. `meta.total_count` 가 `size=1` 로도
정확해서(반경 1km 학원 335건을 문서 45개만 받으면서 수는 맞췄다) 세는 비용이 싸다.
실제로 '술집' 키워드가 상호명이 아니라 `category_name` 을 본다는 것도 확인했다 —
범계역 73건 중 표본 15개가 전부 `음식점 > 술집 > *` 이었고 상호에 '술집' 이 든 것은
1개뿐이었다. 전수로 대조해 7개 지점에서 모두 일치했다.

그런데 **유흥을 가를 수가 없다.** 카카오의 '술집' 한 덩어리에는 요리주점·생맥주 같은
생활 상권과 유흥주점이 섞여 있다. 여기는 식품위생법 업종이 그대로 들어온다.

    음식 > 주점 > 요리 주점 / 생맥주 전문 / 일반 유흥 주점 / 무도 유흥 주점

'일반 유흥 주점'·'무도 유흥 주점' 은 **법적 업종**이라 가게 이름이나 분류 표기에
기대지 않아도 된다. 그래서 가게는 전부 여기서 받는다.

학교·대형마트는 상가가 아니라 이 데이터에 없다. 그건 카카오로 받는다(`clients.kakao`).

## 인증키

`MOLIT_SERVICE_KEY` 와 같은 공공데이터포털 일반 인증키를 쓴다. 다만 **API 마다 따로
활용신청**이 필요하다. 신청 전에는 HTTP 403 에

    {"errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "returnAuthMsg": "등록되지 않은 서비스키"}

가 온다. 키가 틀린 것이 아니므로 그렇게 안내한다.

## 페이징

`numOfRows` 상한이 **1000** 이다. 2000 을 줘도 1000 만 온다(재서 확인했다). 반경 500m
번화가는 2,700건까지 나오므로 `totalCount` 를 보고 끝까지 넘겨야 한다. 받은 수가
총건수에 못 미치는데 멈추면 그 단지만 조용히 적게 세어진다.
"""

from __future__ import annotations

import time

import httpx

from ..config import settings

BASE = "http://apis.data.go.kr/B553077/api/open/sdsc2"
MAX_ROWS = 1000      # API 상한. 더 줘도 1000 만 온다.
MAX_PAGES = 12       # 1000×12 = 12,000건. 실측 최대가 2,981건이라 넉넉하다.
TIMEOUT = 90.0


class SdscError(RuntimeError):
    """API 가 값을 주지 못했다."""


def available() -> bool:
    return bool(settings.molit_service_key)


def _key() -> str:
    # 국토부 실거래가와 **같은 키**다. data.go.kr 일반 인증키는 계정 단위라
    # 하나로 여러 API 를 쓴다. 다만 활용신청은 API 마다 따로 해야 한다.
    if not settings.molit_service_key:
        raise SdscError("MOLIT_SERVICE_KEY 가 없습니다. backend/.env 를 확인하세요.")
    return settings.molit_service_key


def _check_auth(body: str) -> None:
    """키 문제는 오류 메시지가 본문에만 있고 상태코드로는 안 온다."""
    if "SERVICE_KEY_IS_NOT_REGISTERED" in body:
        raise SdscError(
            "이 API 에 활용신청이 되어 있지 않습니다(키가 틀린 것이 아닙니다). "
            "https://www.data.go.kr/data/15083033/openapi.do 에서 신청하세요."
        )
    if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in body:
        raise SdscError("일일 호출 한도를 넘었습니다. 내일 이어서 돌리세요.")


def stores_in_radius(
    lng: float, lat: float, radius: int, *, client: httpx.Client | None = None,
    retries: int = 4,
) -> list[dict]:
    """반경(m) 안 상가를 **전부** 돌려준다.

    총건수를 보고 끝까지 페이지를 넘긴다. 빈 결과는 조용하므로, 총건수에 못 미치는
    채로 끝나면 예외를 던진다 — 그 단지만 적게 세어진 것을 나중에 알 길이 없다.
    """
    own = client is None
    c = client or httpx.Client(timeout=TIMEOUT)
    items: list[dict] = []
    total = None
    try:
        for page in range(1, MAX_PAGES + 1):
            d = _call(c, lng, lat, radius, page, retries)
            body = d.get("body") or {}
            got = body.get("items") or []
            total = int(body.get("totalCount") or 0)
            items += got
            if len(items) >= total or not got:
                break
            time.sleep(0.05)
    finally:
        if own:
            c.close()

    if total is not None and len(items) < total:
        raise SdscError(
            f"반경 {radius}m 에 {total}건인데 {len(items)}건만 받았습니다 "
            f"(페이지 상한 {MAX_PAGES})."
        )
    return items


def _call(c: httpx.Client, lng: float, lat: float, radius: int,
          page: int, retries: int) -> dict:
    last: Exception | None = None
    for i in range(retries):
        try:
            r = c.get(
                f"{BASE}/storeListInRadius",
                params={
                    "serviceKey": _key(),
                    # cx/cy 는 경도/위도 순이다. 바꿔 넣으면 한국 밖을 찾아
                    # **0건**이 오고, 그건 오류가 아니라 빈 결과로 조용히 지나간다.
                    "cx": lng, "cy": lat,
                    "radius": radius,
                    "numOfRows": MAX_ROWS, "pageNo": page,
                    "type": "json",
                },
            )
            _check_auth(r.text)
            r.raise_for_status()
            return r.json()
        except SdscError:
            raise  # 키·한도 문제는 재시도해도 같다
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise SdscError(f"호출 실패(page {page}): {type(last).__name__} {last}")


# 업종 분류 → 우리가 세는 묶음. (대분류, 중분류, 소분류) 각각 부분일치.
#
# 소분류까지 내려가는 이유: '주점' 중분류에는 요리주점·생맥주 같은 생활 상권과
# 유흥주점·무도유흥이 **섞여 있다.** 둘은 전혀 다른 것이라 갈라야 한다. 실제로
# 모델에 넣어 보니 전자는 아무 효과가 없고 후자만 음수로 유의했다.
BUCKETS: dict[str, tuple[tuple[str, ...] | None, tuple[str, ...] | None,
                         tuple[str, ...] | None]] = {
    "edu": (("교육",), None, None),
    "adult": (("음식",), ("주점",), ("유흥 주점", "무도 유흥")),
}


def bucket_of(item: dict) -> list[str]:
    """이 상가가 속하는 묶음들."""
    lc = item.get("indsLclsNm") or ""
    mc = item.get("indsMclsNm") or ""
    sc = item.get("indsSclsNm") or ""
    out = []
    for name, (lcs, mcs, scs) in BUCKETS.items():
        if lcs and not any(a in lc for a in lcs):
            continue
        if mcs and not any(a in mc for a in mcs):
            continue
        if scs and not any(a in sc for a in scs):
            continue
        out.append(name)
    return out
