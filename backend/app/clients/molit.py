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

# 수원시 법정동 시군구 코드
SUWON_DISTRICTS: dict[str, str] = {
    "41111": "수원시 장안구",
    "41113": "수원시 권선구",
    "41115": "수원시 팔달구",
    "41117": "수원시 영통구",
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
