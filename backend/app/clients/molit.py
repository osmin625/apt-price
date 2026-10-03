"""국토교통부 아파트 매매 실거래가 Open API 클라이언트.

공공데이터포털 '국토교통부_아파트 매매 실거래가 상세 자료' (데이터 15126468)
https://www.data.go.kr/data/15126468/openapi.do

기본 자료(15126469, RTMSDataSvcAptTrade)가 아니라 상세 자료를 쓴다.
상세 자료에만 동(aptDong)과 계약 해제 여부(cdealType)가 들어 있고,
해제건을 걸러내지 못하면 시세가 왜곡된다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from ..config import settings

# 대상 시군구 법정동 코드 → 표시명.
#
# ## 이 표를 손으로 믿지 않는다
#
# 처음에 화성시를 `41590` 으로 적었다가 실거래 0건을 받았다. 화성시가 **구로 나뉘면서**
# 코드가 41591/41593/41595/41597 로 갈린 것이었다. 기억에 있는 코드가 현행이라는 보장이
# 없다는 뜻이다.
#
# 그래서 아래 표는 전부 **확인하고 적었다**: 코드마다 실거래를 한 달치 받아 법정동을
# 꺼낸 뒤, 카카오 주소 API 의 `b_code` 앞 5자리가 그 코드와 맞는지 대조했다.
# 코드를 추가할 때도 같은 방식으로 확인할 것 — 틀린 코드는 0건으로 조용히 지나간다.
#
# 범위는 **수원 생활권**이다. 수원과 철도·생활권으로 이어지는 인접 시만 넣는다.
# 더 멀리(평택·안성·이천) 가면 강남 소요시간 범위는 넓어지지만 시장이 이질적이라
# 단일 시장 가정이 약해진다.
DISTRICTS: dict[str, str] = {
    # 수원시
    "41111": "수원시 장안구",
    "41113": "수원시 권선구",
    "41115": "수원시 팔달구",
    "41117": "수원시 영통구",
    # 용인시 — 신분당선·수인분당선·에버라인
    "41461": "용인시 처인구",
    "41463": "용인시 기흥구",
    "41465": "용인시 수지구",
    # 화성시 — 2026년 분구. 동탄은 GTX-A·SRT 로 강남 접근성이 수원과 크게 다르다.
    "41591": "화성시 만세구",
    "41593": "화성시 효행구",
    "41595": "화성시 병점구",
    "41597": "화성시 동탄구",
    # 안양시 — 1호선·4호선
    "41171": "안양시 만안구",
    "41173": "안양시 동안구",
    # 단일 코드 시
    "41370": "오산시",
    "41430": "의왕시",
    "41410": "군포시",
    "41290": "과천시",
}



class MolitError(RuntimeError):
    pass


@dataclass
class RawTrade:
    sgg_cd: str
    umd_nm: str
    apt_nm: str
    jibun: str | None
    apt_dong: str | None
    build_year: int | None
    exclusive_area: float
    floor: int | None
    deal_amount: int  # 만원
    deal_year: int
    deal_month: int
    deal_day: int


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None and node.text else ""


def _int(item: ET.Element, tag: str) -> int | None:
    raw = _text(item, tag).replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_item(item: ET.Element) -> RawTrade | None:
    # cdealType == "O" 는 계약 해제건. 시세 왜곡을 막기 위해 제외한다.
    if _text(item, "cdealType").upper() == "O":
        return None

    area = _text(item, "excluUseAr")
    amount = _int(item, "dealAmount")
    year = _int(item, "dealYear")
    month = _int(item, "dealMonth")
    day = _int(item, "dealDay")
    if not area or amount is None or not (year and month and day):
        return None

    try:
        exclusive_area = float(area)
    except ValueError:
        return None
    if exclusive_area <= 0:
        return None

    return RawTrade(
        sgg_cd=_text(item, "sggCd"),
        umd_nm=_text(item, "umdNm"),
        apt_nm=_text(item, "aptNm"),
        jibun=_text(item, "jibun") or None,
        apt_dong=_text(item, "aptDong") or None,
        build_year=_int(item, "buildYear"),
        exclusive_area=exclusive_area,
        floor=_int(item, "floor"),
        deal_amount=amount,
        deal_year=year,
        deal_month=month,
        deal_day=day,
    )


def fetch_month(lawd_cd: str, deal_ymd: str, rows: int = 1000) -> list[RawTrade]:
    """특정 시군구·특정 월의 실거래를 모두 가져온다. deal_ymd 형식은 'YYYYMM'."""
    if not settings.molit_service_key:
        raise MolitError(
            "MOLIT_SERVICE_KEY 가 설정되지 않았습니다. backend/.env 를 확인하세요."
        )

    collected: list[RawTrade] = []
    page = 1
    while True:
        params = {
            "serviceKey": settings.molit_service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": page,
            "numOfRows": rows,
        }
        resp = httpx.get(settings.molit_base_url + "/getRTMSDataSvcAptTradeDev",
                         params=params, timeout=30.0)
        resp.raise_for_status()

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as exc:
            raise MolitError(f"응답 파싱 실패: {resp.text[:200]}") from exc

        code = root.findtext(".//resultCode") or ""
        if code not in ("00", "000", ""):
            msg = root.findtext(".//resultMsg") or "알 수 없는 오류"
            raise MolitError(f"API 오류 [{code}] {msg}")

        items = root.findall(".//item")
        for item in items:
            parsed = _parse_item(item)
            if parsed:
                collected.append(parsed)

        total = int(root.findtext(".//totalCount") or 0)
        if page * rows >= total or not items:
            break
        page += 1

    return collected
