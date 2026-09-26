"""K-apt(공동주택관리정보시스템) 클라이언트 — 단지 세대수·동수.

공공데이터포털, 국토교통부 제공. data.go.kr 은 **계정당 인증키가 하나**라
MOLIT_SERVICE_KEY 를 그대로 쓴다. 다만 서비스마다 활용신청은 따로 해야 한다.

  국토교통부_공동주택 단지 목록제공 서비스   https://www.data.go.kr/data/15057332/openapi.do
  국토교통부_공동주택 기본 정보제공 서비스   https://www.data.go.kr/data/15058453/openapi.do

## 왜 세대수인가

대단지 프리미엄은 한국 아파트 가격의 큰 설명변수다. 커뮤니티 시설, 관리비의
규모의 경제, 거래 유동성(표본이 많아 가격 발견이 빠르다), 학군 형성까지
세대수에 딸려 온다. 그런데 국토부 실거래가 API 는 세대수를 주지 않는다.

## 미신청 상태를 어떻게 구분하는가

data.go.kr 오류 코드로 판별한다.
  30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR  → 활용신청이 안 된 서비스 (엔드포인트는 맞음)
  12 NO_OPENAPI_SERVICE_ERROR             → 경로가 틀렸거나 폐기된 서비스
  22 LIMITED_NUMBER_OF_SERVICE_REQUESTS   → 일일 한도 초과

두 오류를 구분해서 알려 줘야 사용자가 '신청을 더 해야 하는지' '코드가 틀렸는지'
판단할 수 있다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from ..config import settings

BASE = "https://apis.data.go.kr/1613000"
LIST_SERVICE = "AptListService4"
INFO_SERVICE = "AptBasisInfoServiceV5"


class KaptError(RuntimeError):
    pass


class KaptNotSubscribed(KaptError):
    """엔드포인트는 맞지만 이 서비스에 활용신청이 안 된 상태."""


@dataclass
class KaptBasis:
    kapt_code: str
    name: str
    household_count: int | None
    dong_count: int | None
    build_year: int | None
    address: str | None
    # codeAptNm: '아파트' / '도시형생활주택' / '주상복합' 등.
    # 국토부 실거래가에는 이 구분이 없어서 전용면적으로 추정할 수밖에 없었는데,
    # 여기서는 실제 유형이 그대로 온다.
    apt_type: str | None


def _check(payload: str) -> None:
    m = re.search(r'"?returnReasonCode"?\s*[:>]\s*"?(\d+)', payload)
    code = m.group(1) if m else None
    if code == "30":
        raise KaptNotSubscribed(
            "이 서비스에 활용신청이 되어 있지 않습니다(코드 30). "
            "data.go.kr 에서 '공동주택 기본 정보제공 서비스'와 '공동주택 단지 목록제공 "
            "서비스'를 활용신청하세요. 인증키는 기존 MOLIT 키를 그대로 씁니다."
        )
    if code == "12":
        raise KaptError(
            "해당 오픈API 서비스가 없거나 폐기됨(코드 12). 엔드포인트 경로를 확인하세요."
        )
    if code == "22":
        raise KaptError("일일 트래픽 한도를 초과했습니다(코드 22).")
    if code and code != "00":
        raise KaptError(f"K-apt 오류 코드 {code}")


def _get(url: str, params: dict) -> dict:
    if not settings.molit_service_key:
        raise KaptError("MOLIT_SERVICE_KEY 가 설정되지 않았습니다.")
    resp = httpx.get(
        url,
        params={
            "serviceKey": settings.molit_service_key,
            "_type": "json",
            **params,
        },
        timeout=20.0,
    )
    _check(resp.text)
    resp.raise_for_status()
    return resp.json()


def _items(data: dict) -> list[dict]:
    """응답에서 item 목록을 꺼낸다.

    두 서비스의 응답 모양이 다르다. 단지목록은 `body.items.item`, 기본정보는
    `body.item` 이다(복수형이 아니다). 한쪽만 보면 조용히 빈 결과가 돌아온다.
    """
    body = (data.get("response") or {}).get("body") or {}
    items = body.get("items")
    if not items:
        items = body.get("item")
    if not items:
        return []
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else [items]


def _int(v) -> int | None:
    """세대수는 '1240.0' 처럼 실수 형태로 온다. int('1240.0') 은 ValueError 라
    float 을 거쳐야 한다. 이걸 놓치면 세대수가 통째로 None 이 되는데,
    호출은 성공하므로 오류 없이 조용히 비어 버린다."""
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def list_complexes(sigungu_code: str, page: int = 1, rows: int = 100) -> tuple[list[dict], bool]:
    """시군구 단위 단지 목록. (items, is_last)

    오퍼레이션 이름 끝의 **`4`** 를 빠뜨리면 안 된다. 서비스명(AptListService4)의
    버전 숫자가 오퍼레이션 이름에도 붙는 형태라(`getSigunguAptList4`), 흔한
    `getSigunguAptList` 로 호출하면 '서비스 없음'(코드 12)이 돌아온다.
    미신청(코드 30)과 구분되지 않아 원인을 찾기 어렵다.
    """
    data = _get(
        f"{BASE}/{LIST_SERVICE}/getSigunguAptList4",
        {"sigunguCode": sigungu_code, "pageNo": page, "numOfRows": rows},
    )
    items = _items(data)
    body = (data.get("response") or {}).get("body") or {}
    total = _int(body.get("totalCount")) or 0
    return items, page * rows >= total


def basis_info(kapt_code: str) -> KaptBasis | None:
    data = _get(f"{BASE}/{INFO_SERVICE}/getAphusBassInfoV5", {"kaptCode": kapt_code})
    items = _items(data)
    if not items:
        return None
    it = items[0]
    use_date = str(it.get("kaptUsedate") or "")
    return KaptBasis(
        kapt_code=str(it.get("kaptCode") or kapt_code),
        name=str(it.get("kaptName") or "").strip(),
        household_count=_int(it.get("kaptdaCnt")),
        dong_count=_int(it.get("kaptDongCnt")),
        build_year=_int(use_date[:4]) if len(use_date) >= 4 else None,
        address=(it.get("kaptAddr") or it.get("doroJuso") or None),
        apt_type=(str(it.get("codeAptNm")).strip() or None) if it.get("codeAptNm") else None,
    )
