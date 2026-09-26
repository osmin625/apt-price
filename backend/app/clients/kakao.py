"""카카오 로컬 API 클라이언트 — 단지 좌표 변환 + 최근접 지하철역 탐색."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import settings

ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
SUBWAY_CATEGORY = "SW8"  # 카카오 카테고리 그룹 코드: 지하철역


class KakaoError(RuntimeError):
    pass


@dataclass
class Station:
    name: str
    line: str | None
    distance_m: float
    lat: float
    lng: float


def _headers() -> dict[str, str]:
    if not settings.kakao_rest_key:
        raise KakaoError("KAKAO_REST_KEY 가 설정되지 않았습니다. backend/.env 를 확인하세요.")
    return {"Authorization": f"KakaoAK {settings.kakao_rest_key}"}


def _get(url: str, params: dict) -> dict:
    resp = httpx.get(url, params=params, headers=_headers(), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def geocode(address: str, fallback_keyword: str | None = None) -> tuple[float, float] | None:
    """주소 → (위도, 경도). 지번 주소로 실패하면 키워드 검색으로 재시도한다."""
    docs = _get(ADDRESS_URL, {"query": address, "size": 1}).get("documents", [])
    if not docs:
        query = fallback_keyword or address
        docs = _get(KEYWORD_URL, {"query": query, "size": 1}).get("documents", [])
    if not docs:
        return None
    return float(docs[0]["y"]), float(docs[0]["x"])


def search_keyword(
    query: str,
    *,
    page: int = 1,
    size: int = 15,
    x: float | None = None,
    y: float | None = None,
    radius: int | None = None,
    sort: str | None = None,
    category_group_code: str | None = None,
) -> tuple[list[dict], bool]:
    """키워드 검색 원본 결과. (documents, is_end)

    카카오는 한 질의에서 **최대 45건**만 준다(size≤15, page≤3). 그보다 많은
    결과가 있는 지역은 질의를 공간적으로 쪼개야 전부 건질 수 있다.
    """
    params: dict = {"query": query, "size": min(size, 15), "page": min(page, 3)}
    if x is not None and y is not None:
        params["x"], params["y"] = x, y
    if radius is not None:
        params["radius"] = min(radius, 20000)
    if sort:
        params["sort"] = sort
    if category_group_code:
        params["category_group_code"] = category_group_code

    data = _get(KEYWORD_URL, params)
    meta = data.get("meta", {})
    return data.get("documents", []), bool(meta.get("is_end", True))


def find_station(name: str, line_hint: str | None = None) -> Station | None:
    """역 이름으로 좌표를 찾는다. seed_stations 에서 35쌍을 손으로 타이핑하지 않으려고 쓴다."""
    docs, _ = search_keyword(name, size=5, category_group_code=SUBWAY_CATEGORY)
    if not docs:
        return None

    def score(doc: dict) -> tuple[int, int]:
        cat = doc.get("category_name") or ""
        nm = (doc.get("place_name") or "").strip()
        return (
            0 if line_hint and line_hint in cat else 1,
            0 if nm == name or nm.startswith(name) else 1,
        )

    doc = sorted(docs, key=score)[0]
    parts = [p.strip() for p in (doc.get("category_name") or "").split(">")]
    return Station(
        name=doc.get("place_name", "").strip(),
        line=parts[-1] if len(parts) >= 3 else None,
        distance_m=float(doc.get("distance") or 0),
        lat=float(doc["y"]),
        lng=float(doc["x"]),
    )


def nearest_station(lat: float, lng: float, radius: int = 3000) -> Station | None:
    """반경 내 가장 가까운 지하철역. 카카오가 주는 distance 는 직선거리(m)."""
    docs = _get(
        KEYWORD_URL,
        {
            "query": "지하철역",
            "category_group_code": SUBWAY_CATEGORY,
            "x": lng,
            "y": lat,
            "radius": min(radius, 20000),
            "sort": "distance",
            "size": 1,
        },
    ).get("documents", [])
    if not docs:
        return None

    doc = docs[0]
    # category_name 예: "교통,수송 > 지하철,전철 > 수도권1호선"
    parts = [p.strip() for p in (doc.get("category_name") or "").split(">")]
    return Station(
        name=doc.get("place_name", "").strip(),
        line=parts[-1] if len(parts) >= 3 else None,
        distance_m=float(doc.get("distance") or 0),
        lat=float(doc["y"]),
        lng=float(doc["x"]),
    )
