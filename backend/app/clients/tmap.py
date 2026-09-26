"""TMap 보행자 경로안내 클라이언트.

SK open API. https://openapi.sk.com — 앱 등록 후 appKey 발급.

## 왜 직선거리로는 부족한가

카카오 로컬이 주는 distance 는 **직선거리**다. 같은 직선 600m라도 경부선 철로나
원천리천을 건너야 하면 실제 도보는 900m가 넘는다. 이건 랜덤 노이즈가 아니라
특정 단지에만 체계적으로 걸리는 **편향**이라, 단지별로 세세하게 비교하겠다는
목적에서는 직선거리 보정계수로 덮을 수 없다.

다만 정밀도에는 어차피 한계가 있다: 카카오가 주는 단지 좌표는 중심점 하나인데
한국 아파트 단지는 폭이 200~400m라 보행 출입구가 중심에서 300m 떨어질 수 있다.
TMap을 써도 ±150m는 남는다. 기대할 것은 R² 상승이 아니라 **특정 단지들의 위치가
크게 바뀌는 것**이다.

## 함정

- `startName`/`endName` 에 한글을 넣으면 400이 난다. ASCII 고정.
- **X가 경도, Y가 위도.** kakao.py 의 geocode()는 (lat, lng) 순으로 돌려주므로
  이 모듈에 넘길 때 순서가 뒤집힌다. 조용히 틀리기 딱 좋은 지점이다.
- 보행 경로는 약 10km 상한이 있다. 이 프로젝트 최대 후보는 2.5km라 문제없지만
  에러 코드는 처리한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import settings


class TmapError(RuntimeError):
    pass


@dataclass
class WalkRoute:
    distance_m: float
    seconds: int
    path_geojson: str | None  # LineString


def available() -> bool:
    return bool(settings.tmap_app_key)


def _headers() -> dict[str, str]:
    if not settings.tmap_app_key:
        raise TmapError("TMAP_APP_KEY 가 설정되지 않았습니다. backend/.env 를 확인하세요.")
    return {"appKey": settings.tmap_app_key, "Content-Type": "application/json"}


def pedestrian_route(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    timeout: float = 15.0,
) -> WalkRoute | None:
    """도보 경로. 위경도 순서로 받아 내부에서 X/Y로 뒤집는다."""
    body = {
        "startX": start_lng,
        "startY": start_lat,
        "endX": end_lng,
        "endY": end_lat,
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        # 한글을 넣으면 400. 경로 자체는 이 이름에 의존하지 않는다.
        "startName": "S",
        "endName": "E",
        "searchOption": "0",
    }
    resp = httpx.post(
        settings.tmap_base_url,
        params={"version": 1},
        json=body,
        headers=_headers(),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise TmapError(f"TMap {resp.status_code}: {resp.text[:200]}")

    features = resp.json().get("features") or []
    if not features:
        return None

    props = features[0].get("properties") or {}
    total_distance = props.get("totalDistance")
    total_time = props.get("totalTime")
    if total_distance is None or total_time is None:
        return None

    coords: list[list[float]] = []
    for f in features:
        geom = f.get("geometry") or {}
        if geom.get("type") == "LineString":
            coords.extend(geom.get("coordinates") or [])

    import json

    return WalkRoute(
        distance_m=float(total_distance),
        seconds=int(total_time),
        path_geojson=(
            json.dumps({"type": "LineString", "coordinates": coords}, separators=(",", ":"))
            if coords
            else None
        ),
    )
