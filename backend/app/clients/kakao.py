"""카카오 로컬 API 클라이언트 — 단지 좌표 변환 + 최근접 지하철역 탐색."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import settings

ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"
SUBWAY_CATEGORY = "SW8"  # 카카오 카테고리 그룹 코드: 지하철역
SCHOOL_CATEGORY = "SC4"  # 학교 — 초·중·고·대학교가 한 코드에 들어 있다


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


# 연결을 재사용한다. `httpx.get` 은 호출마다 TCP+TLS 를 새로 맺는데, 카카오 호출은
# 한 번에 수천 번 돈다(단지 2,469곳 × 2~3회). 재 보니 **6.3배** 차이였다.
#
#   매번 새 연결  321ms/회
#   연결 재사용     51ms/회
#
# 입지 적재가 분당 20곳으로 기어가서 알았다. 같은 적재가 분당 170곳이 됐다.
_client: httpx.Client | None = None


def _session() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=15.0)
    return _client


def _get(url: str, params: dict) -> dict:
    resp = _session().get(url, params=params, headers=_headers())
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


def available() -> bool:
    return bool(settings.kakao_rest_key)


def search_category(
    code: str,
    *,
    lat: float,
    lng: float,
    radius: int,
    page: int = 1,
    size: int = 15,
) -> tuple[list[dict], dict]:
    """카테고리 그룹 코드로 반경 검색. (documents, meta)

    키워드 검색과 달리 질의어가 없다. 학교처럼 '그 종류 전부' 를 받을 때 쓴다.

    ## meta 를 함께 돌려주는 이유

    `meta.total_count` 는 **45개 상한과 무관하게 정확하다.** 반경 1km 안 학원
    335건을 문서는 45개만 주면서 수는 335 로 돌려준다(재서 확인했다). 그래서 수만
    필요하면 `size=1` 로 한 번 부르면 되고, 페이지를 넘길 이유가 없다.

    문서가 필요한 경우(학교까지 거리처럼)에만 끝까지 넘긴다. 좌표를 함께 보내면
    문서마다 `distance` 가 실려 와서 거리를 따로 계산하지 않아도 된다.
    """
    data = _get(CATEGORY_URL, {
        "category_group_code": code,
        "x": lng, "y": lat,
        "radius": min(radius, 20000),
        "size": min(size, 15), "page": min(page, 3),
    })
    return data.get("documents", []), data.get("meta", {})


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
