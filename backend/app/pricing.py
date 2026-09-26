"""평당가 산출 도메인 로직.

이 서비스의 모든 평당가는 **전용면적** 기준이다(공급면적 아님).
금액 단위는 국토교통부 실거래가 원본을 따라 '만원'을 사용한다.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Sequence

PYEONG_M2 = 3.305785  # 1평 = 3.305785㎡

# 부동산 광고 관행(1분 = 80m)이 아니라 실보행 기준.
# 카카오 로컬 API가 주는 값은 직선거리이므로 실제 도보 경로 보정계수를 곱한다.
WALK_DETOUR_FACTOR = 1.25
WALK_METERS_PER_MIN = 67.0

# 도보 30분을 넘으면 역은 사실상 통근 수단이 아니라(다들 차를 탄다) 가격 기울기도
# 평평해진다. 자르지 않으면 스플라인 매듭이 40분대로 밀려 유연성이 표본 몇 개뿐인
# 구간에 소모되고 정작 3~15분 구간이 뭉개진다.
#
# 시드와 모델이 **반드시 같은 값으로 잘라야** 한다. 한쪽만 자르면 측정오차가
# 생겨 회귀가 참값을 복원하지 못하고, 추정량과 무관한 이유로 검증이 실패한다.
WALK_CAP_MIN = 30.0

FLOOR_BANDS = ["1층", "저층", "중층", "고층", "최상층", "정보없음"]
STATION_BANDS = [
    "초역세권(도보 5분)",
    "역세권(도보 10분)",
    "준역세권(도보 15분)",
    "비역세권(15분 초과)",
    "정보없음",
]
AGE_BANDS = [
    "신축(5년 이하)",
    "준신축(6~10년)",
    "10~15년",
    "15~20년",
    "20~30년",
    "30년 초과",
    "정보없음",
]
AREA_BANDS = [
    "초소형(~40㎡)",
    "소형(40~60㎡)",
    "중소형(60~85㎡)",
    "중형(85~102㎡)",
    "중대형(102~135㎡)",
    "대형(135㎡~)",
]
HOUSEHOLD_BANDS = [
    "소규모(300세대 미만)",
    "중소규모(300~600)",
    "중규모(600~1000)",
    "대단지(1000~1500)",
    "초대형(1500세대 이상)",
    "정보없음",
]


def to_pyeong(area_m2: float) -> float:
    return area_m2 / PYEONG_M2


def price_per_pyeong(deal_amount_manwon: float, exclusive_area_m2: float) -> float:
    """전용면적 평당가(만원/평)."""
    if exclusive_area_m2 <= 0:
        raise ValueError("전용면적은 0보다 커야 합니다")
    return deal_amount_manwon / to_pyeong(exclusive_area_m2)


def walk_minutes(distance_m: float | None) -> int | None:
    if distance_m is None:
        return None
    return max(1, math.ceil(distance_m * WALK_DETOUR_FACTOR / WALK_METERS_PER_MIN))


def walk_minutes_from_seconds(seconds: float | None) -> float | None:
    """실제 도보 경로 소요시간(초) → 분. 회귀 입력이므로 반올림하지 않는다."""
    if seconds is None:
        return None
    return seconds / 60.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 위경도 사이 대권 거리(m)."""
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def name_key(name: str) -> str:
    """단지명 정규화 키.

    카카오 POI와 국토부 실거래가는 같은 단지를 다르게 표기한다
    ('래미안영통마크원2단지' vs '래미안 영통 마크원 2단지'). 조인하려면 둘을
    같은 문자열로 접어야 한다.

    주의: 'N차'는 **제거하지 않는다**. 래미안1차와 래미안2차는 실제로 다른
    단지이므로 지우면 서로 다른 단지가 하나로 합쳐진다. 표기만 통일한다.
    """
    s = unicodedata.normalize("NFKC", name).lower()
    s = re.sub(r"[()\[\]{}·,.\-_/'\"]", "", s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"제(\d+)(단지|차)", r"\1\2", s)
    s = re.sub(r"아파트$", "", s)
    return s


def name_digits(name: str) -> tuple[str, ...]:
    """단지명 속 숫자열. '2단지', '1차' 처럼 단지를 **가르는** 정보다.

    유사도 매칭의 안전장치로 쓴다. 이름이 길면 숫자 한 글자 차이는 유사도를
    거의 떨어뜨리지 못해서('영통아이파크캐슬3단지' vs '...1단지' = 0.909)
    전혀 다른 단지가 하나로 합쳐진다. 실제로 그렇게 합쳐졌었다.

    숫자가 다르면 다른 단지로 본다. 틀려도 단지가 하나 더 생길 뿐이지만,
    반대로 잘못 합치면 남의 거래가 섞여 시세가 통째로 망가진다.
    """
    return tuple(re.findall(r"\d+", name_key(name)))


def rcs_basis(x: float, knots: Sequence[float]) -> list[float]:
    """제한 3차 스플라인(restricted cubic spline) 기저. Harrell 방식.

    매듭 k개에서 열 k-1개를 만든다(첫 열은 x 자신). 매듭 3개 → 열 2개.
    양 끝단에서 선형으로 제한되므로 외삽이 폭주하지 않는다.

    시드와 모델이 **같은 함수**를 써야 참값 복원 검증이 성립하므로
    의존성 없는 이 모듈에 둔다.
    """
    k = len(knots)
    if k < 3:
        raise ValueError("매듭은 3개 이상이어야 합니다")
    t = list(knots)
    denom = (t[-1] - t[0]) ** 2
    if denom <= 0:
        raise ValueError("매듭이 서로 달라야 합니다")

    def cube_plus(u: float) -> float:
        return u**3 if u > 0 else 0.0

    out = [x]
    for j in range(k - 2):
        span = t[-1] - t[-2]
        term = (
            cube_plus(x - t[j])
            - cube_plus(x - t[-2]) * (t[-1] - t[j]) / span
            + cube_plus(x - t[-1]) * (t[-2] - t[j]) / span
        )
        out.append(term / denom)
    return out


def floor_band(floor: int | None, max_floor: int | None = None) -> str:
    if floor is None:
        return "정보없음"
    if floor <= 1:
        return "1층"
    if max_floor and max_floor >= 8:
        if floor >= max_floor:
            return "최상층"
        ratio = floor / max_floor
        if ratio <= 0.25:
            return "저층"
        if ratio <= 0.65:
            return "중층"
        return "고층"
    if floor <= 3:
        return "저층"
    if floor <= 7:
        return "중층"
    return "고층"


def station_band(distance_m: float | None) -> str:
    if distance_m is None:
        return "정보없음"
    if distance_m <= 400:
        return "초역세권(도보 5분)"
    if distance_m <= 800:
        return "역세권(도보 10분)"
    if distance_m <= 1200:
        return "준역세권(도보 15분)"
    return "비역세권(15분 초과)"


def age_band(build_year: int | None, ref_year: int) -> str:
    if not build_year:
        return "정보없음"
    age = ref_year - build_year
    if age <= 5:
        return "신축(5년 이하)"
    if age <= 10:
        return "준신축(6~10년)"
    if age <= 15:
        return "10~15년"
    if age <= 20:
        return "15~20년"
    if age <= 30:
        return "20~30년"
    return "30년 초과"


def area_band(exclusive_area_m2: float) -> str:
    if exclusive_area_m2 < 40:
        return "초소형(~40㎡)"
    if exclusive_area_m2 < 60:
        return "소형(40~60㎡)"
    if exclusive_area_m2 < 85:
        return "중소형(60~85㎡)"
    if exclusive_area_m2 < 102:
        return "중형(85~102㎡)"
    if exclusive_area_m2 < 135:
        return "중대형(102~135㎡)"
    return "대형(135㎡~)"


def household_band(count: int | None) -> str:
    """단지 규모 구간.

    경계를 300/600/1000/1500 으로 잡은 이유: 한국에서 '대단지'의 실질적 분기점이
    이 근처다. 300세대 아래는 커뮤니티 시설이 사실상 없고, 1000세대를 넘으면
    상가·학교 배치가 달라지며 거래도 잦아 가격 발견이 빠르다.

    모델에서는 구간이 아니라 log(세대수) 연속값을 쓴다(수원 실측 +11.7%/2배).
    이 구간은 화면에서 필터로 고르기 위한 것이다.
    """
    if not count:
        return "정보없음"
    if count < 300:
        return "소규모(300세대 미만)"
    if count < 600:
        return "중소규모(300~600)"
    if count < 1000:
        return "중규모(600~1000)"
    if count < 1500:
        return "대단지(1000~1500)"
    return "초대형(1500세대 이상)"


def area_type_key(exclusive_area_m2: float) -> int:
    """같은 단지 안에서 동일 평형(타입)끼리 묶기 위한 키. 전용면적을 1㎡ 단위로 반올림."""
    return round(exclusive_area_m2)


@dataclass
class TradePoint:
    """분석에 필요한 최소 거래 정보."""

    complex_id: int
    complex_name: str
    deal_ym: str  # "YYYY-MM"
    deal_date: str  # "YYYY-MM-DD"
    exclusive_area: float
    floor: int | None
    deal_amount: int  # 만원
    build_year: int | None
    max_floor: int | None = None
    station_distance_m: float | None = None
    # 동 라벨. 적정가에서 동 프리미엄을 중화·적용하는 데 쓴다(층 보정과 같은 방식).
    apt_dong: str | None = None

    @property
    def ppp(self) -> float:
        return price_per_pyeong(self.deal_amount, self.exclusive_area)


def describe(values: Sequence[float]) -> dict | None:
    """평당가 분포 요약. 표본이 없으면 None."""
    if not values:
        return None
    xs = sorted(values)
    n = len(xs)

    def q(p: float) -> float:
        if n == 1:
            return xs[0]
        pos = p * (n - 1)
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return xs[lo]
        return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)

    return {
        "count": n,
        "median": round(median(xs), 1),
        "mean": round(sum(xs) / n, 1),
        "p25": round(q(0.25), 1),
        "p75": round(q(0.75), 1),
        "min": round(xs[0], 1),
        "max": round(xs[-1], 1),
    }


def market_index(trades: Iterable[TradePoint]) -> dict[str, float]:
    """월별 시장 지수. 최신 월을 1.0으로 두고 오래된 거래를 현재 시점으로 환산하는 데 쓴다.

    월별 평당가 중앙값을 그대로 쓰면 그 달에 어떤 단지가 거래됐는지에 지수가 흔들린다
    (비싼 단지가 몰린 달은 시장이 오른 것처럼 보인다). 그래서 각 거래를
    자기 (단지, 평형)의 중앙 평당가로 나눈 **상대 평당가**를 월별로 집계해
    단지·평형 구성 편향을 제거한다.

    표본이 부족한 달은 직전 달 지수를 이어받아 튀는 값을 막는다.
    """
    trades = list(trades)
    groups: dict[tuple[int, int], list[float]] = {}
    for t in trades:
        groups.setdefault((t.complex_id, area_type_key(t.exclusive_area)), []).append(t.ppp)

    baselines = {k: median(v) for k, v in groups.items() if len(v) >= 3}
    if not baselines:
        return {}

    buckets: dict[str, list[float]] = {}
    for t in trades:
        base = baselines.get((t.complex_id, area_type_key(t.exclusive_area)))
        if base and base > 0:
            buckets.setdefault(t.deal_ym, []).append(t.ppp / base)
    if not buckets:
        return {}

    months = sorted(buckets)
    raw: dict[str, float] = {}
    last: float | None = None
    for ym in months:
        vals = buckets[ym]
        if len(vals) >= 5 or last is None:
            last = median(vals)
        raw[ym] = last

    anchor = raw[months[-1]]
    return {ym: v / anchor for ym, v in raw.items()} if anchor else {}


def adjusted_ppp(trade: TradePoint, index: dict[str, float]) -> float:
    """시점 보정 평당가 — 과거 거래를 최신 월 가격 수준으로 환산."""
    factor = index.get(trade.deal_ym) or 1.0
    return trade.ppp / factor if factor else trade.ppp


def estimate_floor_factors(
    trades: Sequence[TradePoint], index: dict[str, float] | None = None
) -> dict[str, float]:
    """층 구간별 가격 보정계수.

    단지·평형마다 절대 평당가 수준이 다르므로, (단지, 전용면적타입) 그룹 안에서
    각 거래의 평당가를 그룹 중앙값으로 나눈 '상대 평당가'를 구한 뒤
    층 구간별로 중앙값을 낸다. 단지 효과와 평형 효과가 제거된 순수 층 프리미엄.
    """
    index = index or {}
    groups: dict[tuple[int, int], list[tuple[str, float]]] = {}
    for t in trades:
        key = (t.complex_id, area_type_key(t.exclusive_area))
        band = floor_band(t.floor, t.max_floor)
        if band == "정보없음":
            continue
        groups.setdefault(key, []).append((band, adjusted_ppp(t, index)))

    relatives: dict[str, list[float]] = {}
    for rows in groups.values():
        if len(rows) < 4:
            continue
        base = median([v for _, v in rows])
        if base <= 0:
            continue
        for band, v in rows:
            relatives.setdefault(band, []).append(v / base)

    return {
        band: round(median(vals), 4)
        for band, vals in relatives.items()
        if len(vals) >= 5
    }


def group_stats(
    trades: Sequence[TradePoint],
    key_fn,
    order: Sequence[str],
    index: dict[str, float] | None = None,
) -> list[dict]:
    """구간별 평당가 분포. order에 정의된 순서대로, 표본이 있는 구간만 반환."""
    index = index or {}
    buckets: dict[str, list[float]] = {}
    for t in trades:
        buckets.setdefault(key_fn(t), []).append(adjusted_ppp(t, index))

    out = []
    for band in order:
        stats = describe(buckets.get(band, []))
        if stats:
            out.append({"band": band, **stats})
    return out
