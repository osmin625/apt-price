"""헤도닉 회귀 — 역까지의 거리와 평당가의 관계를 연속적으로 모델링한다.

`pricing.station_band()`가 400/800/1200m로 잘라 버리는 정보를 복원하는 것이 목적이다.
거리는 구간이 아니라 연속 변수로 들어가고, 결과는 도보 1분당 몇 %라는 계수와
신뢰구간이 있는 곡선이다.

## 왜 2단계인가

단지 중심점 기준 도보거리는 **단지 안에서 상수**다. 거래 단위 단일 회귀를 돌리면
같은 단지의 거래들이 독립 관측치인 척하게 되어(Moulton 문제) 단지 수준 변수의
표준오차가 2~4배 작게 나온다. 변수가 실제로 변하는 층위로 회귀를 나눈다.

  Stage 1 (거래 단위, 단지 내):
      log(평당가) = α_c + φ·log(전용/84) + Σ φ_b·층구간 + δ_월
                   + ω·(동 도보분 − 단지평균) + ε
      → α̂_c = 전용 84㎡·중층·최신월 기준으로 환산한 단지별 평당가 수준
      → ω  = **같은 단지 안에서** 역에 가까운 동 vs 먼 동의 차이

  Stage 2 (단지 단위, 가중최소제곱):
      α̂_c = μ + s(도보분) + γ·강남분 + θ₁·연식 + θ₂·연식² + Σ ψ·구 + u_c
      → s(·)가 구간화를 대체하는 연속 곡선, u_c가 단지별 잔차

α̂_c의 정밀도는 단지마다 다르다(거래 3건 vs 60건). Stage 2는 이를
w_c = 1/(se(α̂_c)² + τ̂²)로 가중한다.

## 두 개의 도보거리 추정치는 서로 다른 질문의 답이다

ω(단지 내)는 학군·브랜드·관리상태·연식·구 입지가 전부 단지 더미에 흡수된 상태에서
나오므로 교란이 원천적으로 없다. 대신 범위가 좁다 — 단지 내 동 간 편차는 보통 1~3분이다.

Stage 2 의 계수는 범위가 넓지만(도보 1~30분) 단지 간 비교라 관측되지 않은 차이가
섞일 수 있다. 어느 하나가 '정답'이 아니라, 둘을 나란히 보는 것이 정직하다.

## 의존성

이 모듈만 numpy/pandas/statsmodels를 쓴다. import는 `fit()` 안에서 지연 수행하므로
패키지가 없어도 앱의 나머지는 정상 동작한다. `pricing.py`는 의존성 없이 유지하고,
스플라인 기저(`pricing.rcs_basis`)는 시드와 모델이 **같은 함수**를 공유한다 —
그래야 참값 복원 검증이 성립한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import pricing

PYEONG_REF_AREA = 84.0  # 전용 84㎡ = 국민평형, α_c의 기준점
FLOOR_REF = "중층"
MIN_TRADES_PER_COMPLEX = 3
CURVE_POINTS = 48

# 단지에 이 크기 이상의 주택이 하나도 없으면 분석에서 뺀다.
#
# 국토부 '아파트' 실거래가에는 원룸형 **도시형생활주택**이 섞여 들어온다.
# 법적으로 아파트로 등록되기 때문이다. 수원 24개월 기준 24곳(거래 256건, 0.9%)이고
# 전용 10.9~30㎡ 단일 평형이 대부분이며 21곳이 2009년 제도 도입 이후 준공이다.
#
# 이들을 빼는 이유는 '유형이 달라서'가 아니라 **외삽이기 때문**이다. α̂_c 는
# 전용 84㎡ 기준으로 환산한 값인데, 11㎡짜리 원룸만 있는 건물에는 84㎡ 주택이
# 존재하지 않는다. 없는 평형으로 환산한 숫자가 잔차 순위 상위를 독차지하면서
# '가장 저평가된 단지' 목록을 망가뜨렸다.
MIN_MAX_AREA_M2 = 40.0


# 스플라인·다항 동반항은 설계상 서로 상관이 높다(walk_min↔walk_rcs2, age↔age_sq).
# 이건 구조적이라 경고할 일이 아니다. 진짜 문제는 서로 다른 개념 간의 공선성이다.
# 스플라인 동반항은 설계상 서로 상관이 높다. 구조적이라 경고할 일이 아니고,
# 진짜 문제는 서로 다른 개념 사이의 공선성이다.
_SPLINE_BASES = {"walk_min", "gangnam_min", "age", "log_households", "top_floor",
                 "elem_dist", "mid_dist", "academy", "adult"}

# 대형 건설사 브랜드. 단지명에 **이미 들어 있어서** 따로 받아올 것이 없다.
#
# 왜 넣나: 잔차로 재 보니 브랜드 단지의 잔차 중위가 +5.27%, 나머지가 -0.99% 였다
# (차이 6.26%p). 모델이 층·면적·도보·강남·연식·세대수·노선·구를 통제한 **뒤에** 남는
# 값이라, 넣지 않으면 그 6%p 가 통째로 잔차로 흘러간다.
#
# 다만 **연식·최고층과 겹친다.** 브랜드 단지는 대개 신축이고 고층이다. 겹침이 얼마나
# 되는지도 쟀다 — 최고층을 먼저 넣고 같은 것을 다시 재니 브랜드 단지 664곳 +2.55%,
# 그 외 1,182곳 -1.25% 로 차이가 **3.81%p 로 줄었다.** 즉 6.26%p 중 2.4%p 가량은
# 브랜드가 아니라 '고층 단지' 였다. 그래서 하나씩 넣어 보면 둘 다 커 보인다. 같이 넣고
# 각자 살아남는지 보는 것이 이 변수를 넣는 진짜 이유다.
#
# 그래서 둘을 같이 넣고 쟀다. **둘 다 살아남았다** — 단지 고유분산 tau 가
# 0.2015 -> 0.1846 (-8.4%), adj R2 0.8190 -> 0.8477. 일은 대부분 최고층이 하고
# (0.8447), 브랜드가 그 위에 얹는다. 네 조합의 표는 docs/model.md.
#
# 이름 매칭이라 놓치는 것이 있다. 2,469곳 중 701곳(28.4%)이 걸린다.

# 따로 계수를 줄 최소 단지 수. 이보다 적은 브랜드는 '기타브랜드' 로 묶는다.
# 20곳이면 그 브랜드의 계수가 한두 단지에 끌려가지 않는다. 지금 독립 더미를 받는 것은
# 9개(자이 56·푸르지오 50·아이파크 45·힐스테이트 40·래미안 32·e편한세상 27·
# 아너스빌 22·롯데캐슬 21·더샵 20)이고, 나머지 50개 브랜드 388곳이 '기타브랜드' 다.
_BRAND_MIN = 20

# 브랜드 → 단지명에서 찾을 표기들. **별칭을 묶는 것이 핵심이다** — 처음에는
# `e편한세상` 과 `이편한세상` 을 따로 두었는데, 그러면 같은 브랜드가 더미 두 개로
# 갈려 각각의 표본이 반토막 난다. `SK뷰`/`SKVIEW` 도 같았다.
#
# 목록은 실측으로 넓혔다. 2,469곳 중 어떤 이름이 안 걸리는지 세 보니 경남아너스빌
# 22곳·우남퍼스트빌 13곳·현대홈타운 19곳·신안인스빌 9곳처럼 **큰 브랜드가 통째로**
# 빠져 있었다. 걸릴 이름을 하나하나 눈으로 확인하고 넣었다(오매칭 0).
#
# **건설사명은 넣지 않는다.** `현대`(85곳)·`삼성`(53곳)·`대우`·`한양`·`벽산`·`쌍용`
# 같은 이름이 더 흔하지만, 1990년대 '현대아파트' 는 지금의 힐스테이트와 다른 것이다.
# 그것까지 브랜드로 세면 기준군('브랜드 없음')이 거의 비고, 계수는 '브랜드값' 이
# 아니라 '구축이 아님' 을 재게 된다 — 연식이 이미 그 일을 하고 있다. 시공사를 보고
# 싶으면 K-apt `kaptBcompany` 가 맞는 출처다(커버리지 35%).
#
# `센트럴`(77곳)도 뺐다. 브랜드가 아니라 작명에 쓰는 낱말이다.
_BRANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("자이", ("자이",)),
    ("래미안", ("래미안",)),
    ("푸르지오", ("푸르지오",)),
    ("힐스테이트", ("힐스테이트",)),
    ("e편한세상", ("e편한세상", "이편한세상")),
    ("아이파크", ("아이파크",)),
    ("롯데캐슬", ("롯데캐슬",)),
    ("더샵", ("더샵",)),
    ("SK뷰", ("sk뷰", "skview")),
    ("스위첸", ("스위첸",)),
    ("위브", ("위브",)),
    ("센트레빌", ("센트레빌",)),
    ("한라비발디", ("비발디",)),
    ("리슈빌", ("리슈빌",)),
    ("데시앙", ("데시앙",)),
    ("베르디움", ("베르디움",)),
    ("해모로", ("해모로",)),
    ("우미린", ("우미린",)),
    ("호반", ("호반",)),
    ("중흥", ("중흥",)),
    ("유보라", ("유보라",)),
    ("칸타빌", ("칸타빌",)),
    ("하늘채", ("하늘채",)),
    ("꿈에그린", ("꿈에그린",)),
    ("어울림", ("어울림",)),
    ("포레나", ("포레나",)),
    ("아크로", ("아크로",)),
    ("트리마제", ("트리마제",)),
    # 아래는 실측으로 찾아 넣은 것들. 대부분 20곳 미만이라 '기타브랜드' 로 묶이지만,
    # 그래도 넣는 이유는 **기준군을 깨끗하게** 하기 위해서다. 브랜드 단지를 '브랜드
    # 없음' 에 남겨 두면 기준 자체가 올라가 모든 계수가 작아진다.
    ("아너스빌", ("아너스빌",)),
    ("현대홈타운", ("홈타운",)),
    ("퍼스트빌", ("퍼스트빌",)),
    ("블루밍", ("블루밍",)),
    ("수자인", ("수자인",)),
    ("스타힐스", ("스타힐스",)),
    ("해링턴", ("해링턴",)),
    ("펜테리움", ("펜테리움",)),
    ("미래도", ("미래도",)),
    ("노블랜드", ("노블랜드",)),
    ("휴먼빌", ("휴먼빌",)),
    ("인스빌", ("인스빌",)),
    ("풍경채", ("풍경채",)),
    ("쉐르빌", ("쉐르빌",)),
    ("로얄듀크", ("로얄듀크",)),
    ("그린코아", ("그린코아",)),
    ("베라체", ("베라체",)),
    ("휴튼", ("휴튼",)),
    ("코아루", ("코아루",)),
    ("리첼", ("리첼",)),
    ("이안", ("이안",)),
    ("동일하이빌", ("하이빌",)),
    ("아이유쉘", ("아이유쉘",)),
    ("파밀리에", ("파밀리에",)),
    ("굿모닝힐", ("굿모닝힐",)),
    ("메르디앙", ("메르디앙",)),
    ("예가", ("예가",)),
    ("더휴", ("더휴",)),
    ("스타클래스", ("스타클래스",)),
    ("더플래티넘", ("더플래티넘",)),
    ("나우빌", ("나우빌",)),
    ("코오롱", ("코오롱",)),
)


def brand_of(name: str | None) -> str | None:
    """단지명에서 브랜드. 없으면 None.

    공백을 지우고 대소문자를 무시한다 — 'SK 뷰'·'skview' 가 같은 것이기 때문이다.
    두 브랜드가 함께 적힌 이름(`우미린제일풍경채`)은 목록에서 먼저 나오는 쪽으로
    간다. 합작 단지라 어느 쪽도 틀리지 않고, 둘을 쪼개면 표본만 얇아진다.
    """
    if not name:
        return None
    n = name.replace(" ", "").lower()
    for canon, pats in _BRANDS:
        if any(pat.lower() in n for pat in pats):
            return canon
    return None


def _is_structural(name: str) -> bool:
    return "__nl" in name or name in _SPLINE_BASES


class ModelUnavailable(RuntimeError):
    """numpy/pandas/statsmodels 미설치."""


class UnderIdentified(ValueError):
    """표본 대비 설명변수가 많아 계수가 유일하게 정해지지 않음."""


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    use_controls: bool  # 면적·층·월 (stage 1 전체 통제)
    use_age: bool
    use_gangnam: bool
    use_sgg_fe: bool
    use_umd_fe: bool
    use_households: bool = True
    use_line_fe: bool = False
    # 단지 최고층과 브랜드. 둘 다 **단지 단위**라 Stage 2 에 들어간다.
    use_top_floor: bool = False
    use_brand: bool = False
    # 입지(학교 거리·학원 수·유흥주점 수). 적재가 없으면 자동으로 빠진다.
    use_amenity: bool = False


# 스펙 사다리 — 통제를 늘려가며 도보계수가 어떻게 변하는지 보여준다.
# 계수가 스펙에 따라 얼마나 움직이는지가 곧 그 추정치를 얼마나 믿을 수 있는지다.
#
# 설계 단계에서는 M3(법정동 FE)에서 계수가 0으로 무너질 것이라 예상했으나
# 수원 실거래로 검증해 보니 틀렸다. 단지 521곳이 56개 법정동에 퍼져 있어
# 동 내부 편차만으로도 식별되고, 오히려 동 단위 교란이 빠지며 계수가 커졌다.
SPECS: dict[str, Spec] = {
    "M0": Spec("M0", "도보거리만", False, False, False, False, False, False),
    "M1": Spec("M1", "+ 면적·층·시점", True, False, False, False, False, False),
    "M2": Spec(
        "M2", "+ 연식·세대수·강남접근성·노선·구 FE",
        True, True, True, True, False, True, True,
        use_top_floor=True, use_brand=True, use_amenity=True,
    ),
    "M3": Spec("M3", "+ 법정동 FE", True, True, True, True, True, True, True,
               use_top_floor=True, use_brand=True, use_amenity=True),
}
DEFAULT_SPEC = "M2"


def _deps():
    try:
        import numpy as np
        import pandas as pd
        import statsmodels.api as sm
    except ImportError as exc:  # pragma: no cover
        raise ModelUnavailable(
            "모델 의존성이 설치되지 않았습니다. pip install -r requirements.txt"
        ) from exc
    return np, pd, sm


def available() -> bool:
    try:
        _deps()
    except ModelUnavailable:
        return False
    return True


# --------------------------------------------------------------------------
# 입력 프레임
# --------------------------------------------------------------------------
# rows 의 각 항목이 가져야 하는 키:
#   complex_id, complex_name, sgg_cd, sgg_name, umd_nm,
#   deal_ym('YYYY-MM'), exclusive_area, floor, max_floor, deal_amount,
#   build_year, walk_min(float|None), gangnam_min(float|None), lat, lng,
#   elem_dist(float|None), mid_dist(float|None), academy(int|None), adult(int|None)
#
# 시드 생성기도 **이 스키마 그대로** 소비해야 한다. 시드가 모델과 다른 컬럼을
# 읽으면 측정오차가 계수를 감쇠시켜, 추정량과 무관한 이유로 복원 검증이 실패한다.


def load_rows(db, months: int = 24) -> list[dict]:
    """DB → 모델 입력 행. SQLAlchemy만 쓰므로 numpy 없이도 import 된다.

    시드 생성기도 같은 walk_seconds 컬럼을 읽는다. 두 경로가 갈라지면
    측정오차가 생겨 참값 복원이 실패한다.
    """
    from datetime import date, timedelta

    from sqlalchemy import select

    from ..models import Complex, ComplexAmenity, ComplexDong, Station, Trade

    stations = {s.id: s for s in db.execute(select(Station)).scalars().all()}
    cutoff = date.today() - timedelta(days=31 * months)

    # 단지 주변 입지. 아직 안 받은 단지는 빠지고, 그 단지는 입지 항 없이 적합된다
    # (결측 표시자로 처리한다 — 세대수와 같은 방식이다).
    amenity: dict[int, tuple] = {
        a.complex_id: (a.elem_dist_m, a.mid_dist_m, a.academy_500, a.adult_500)
        for a in db.execute(select(ComplexAmenity)).scalars().all()
    }

    # 동 단위 도보시간. 같은 단지라도 동에 따라 역까지 100~330m 차이난다.
    dong_walk: dict[tuple[int, str], float] = {}
    for d in db.execute(select(ComplexDong)).scalars().all():
        if d.walk_seconds is not None:
            dong_walk[(d.complex_id, d.dong)] = pricing.walk_minutes_from_seconds(
                d.walk_seconds
            )

    rows = []
    # **엔티티가 아니라 컬럼만 읽는다.** `select(Trade, Complex)` 는 행마다 ORM 객체
    # 두 개를 만들어 식별 맵에 넣는데, 여기서 쓰는 것은 열 열여섯 개뿐이다. 경기
    # 남부 24개월치 11.7만 행에서 이 비용이 6초였고, 적합 전체(12.9초)의 절반이었다.
    # `analysis.load_points` 와 같은 이유·같은 방식이다.
    stmt = (
        select(
            Trade.deal_ym, Trade.exclusive_area, Trade.floor, Trade.deal_amount,
            Trade.build_year, Trade.apt_dong,
            Complex.id, Complex.name, Complex.sgg_cd, Complex.sgg_name,
            Complex.umd_nm, Complex.max_floor, Complex.build_year,
            Complex.walk_seconds, Complex.household_count, Complex.lat, Complex.lng,
            Complex.best_access_station_id, Complex.nearest_station_id,
        )
        .join(Complex, Complex.id == Trade.complex_id)
        .where(Trade.deal_date >= cutoff)
    )
    for (deal_ym, area, floor, amount, t_year, apt_dong,
         cx_id, cx_name, sgg_cd, sgg_name, umd_nm, max_floor, cx_year,
         walk_seconds, households, lat, lng, best_sid, near_sid) in db.execute(stmt):
        if walk_seconds is None:
            continue
        gangnam = None
        for sid in (best_sid, near_sid):
            if sid and stations.get(sid) and stations[sid].minutes_to_gangnam is not None:
                gangnam = stations[sid].minutes_to_gangnam
                break
        near = stations.get(near_sid)
        dong = (apt_dong or "").strip()
        rows.append(
            {
                "complex_id": cx_id,
                "complex_name": cx_name,
                "sgg_cd": sgg_cd,
                "sgg_name": sgg_name,
                "umd_nm": umd_nm,
                "deal_ym": deal_ym,
                "exclusive_area": area,
                "floor": floor,
                "max_floor": max_floor,
                "deal_amount": amount,
                "build_year": t_year or cx_year,
                "walk_min": pricing.walk_minutes_from_seconds(walk_seconds),
                "gangnam_min": gangnam,
                "household_count": households,
                "line": near.line if near else None,
                "lat": lat,
                "lng": lng,
                "apt_dong": dong or None,
                # 그 거래가 속한 동의 도보시간. 좌표를 못 찾은 동은 None 이고,
                # 그 거래는 단지 내 비교에 기여하지 않는다(다른 항 추정에는 계속 쓰인다).
                "dong_walk_min": dong_walk.get((cx_id, dong)),
                **_amenity_fields(amenity.get(cx_id)),
            }
        )
    return rows


def _amenity_fields(row: tuple | None) -> dict:
    if row is None:
        return {"elem_dist": None, "mid_dist": None, "academy": None, "adult": None}
    elem, mid, academy, adult = row
    return {
        "elem_dist": float(elem) if elem is not None else None,
        "mid_dist": float(mid) if mid is not None else None,
        "academy": float(academy) if academy is not None else None,
        "adult": float(adult) if adult is not None else None,
    }


def _build_frame(rows, ref_year: int):
    np, pd, _ = _deps()

    recs = []
    for r in rows:
        area = r.get("exclusive_area")
        amount = r.get("deal_amount")
        walk = r.get("walk_min")
        if not area or area <= 0 or not amount or amount <= 0:
            continue
        if walk is None:
            continue
        ppp = pricing.price_per_pyeong(amount, area)
        if ppp <= 0:
            continue
        build_year = r.get("build_year")
        recs.append(
            {
                "complex_id": r["complex_id"],
                "complex_name": r.get("complex_name", ""),
                "sgg_cd": str(r.get("sgg_cd") or ""),
                "sgg_name": r.get("sgg_name", ""),
                "umd_nm": r.get("umd_nm", ""),
                "line": r.get("line") or "정보없음",
                "deal_ym": r["deal_ym"],
                "log_ppp": math.log(ppp),
                "exclusive_area": float(area),
                "log_area": math.log(area / PYEONG_REF_AREA),
                "floor_band": pricing.floor_band(r.get("floor"), r.get("max_floor")),
                "walk_min": min(float(walk), pricing.WALK_CAP_MIN),
                "gangnam_min": (
                    float(r["gangnam_min"]) if r.get("gangnam_min") is not None else np.nan
                ),
                "dong_walk_min": (
                    float(r["dong_walk_min"]) if r.get("dong_walk_min") is not None else np.nan
                ),
                # 동 라벨 자체도 들고 간다. 거리로 설명되지 않는 동 고유 효과
                # (조망·향·소음·단지 내 위치)를 잔차에서 뽑는 데 쓴다.
                "apt_dong": r.get("apt_dong"),
                "age": (ref_year - build_year) if build_year else np.nan,
                # 대단지 프리미엄. 로그로 넣는다 - 300세대와 600세대의 차이가
                # 2,000세대와 2,300세대의 차이보다 크다.
                "log_households": (
                    math.log(float(r["household_count"]))
                    if r.get("household_count")
                    else np.nan
                ),
                # 단지 최고층. 지금까지는 **층 구간을 만드는 데만** 썼다
                # (`pricing.floor_band` 위에서). 단지 수준 요인으로는 안 들어갔는데,
                # 잔차로 재 보니 25층+ 가 +8.98%, 14층 이하가 -9.95% 로 가장 크게
                # 갈렸다. 연식·브랜드와 겹치므로 함께 넣어 각자 남는지 본다.
                "top_floor": (
                    float(r["max_floor"]) if r.get("max_floor") else np.nan
                ),
                "brand": brand_of(r.get("complex_name")),
                # 입지는 단지 속성이라 거래마다 같은 값이다. Stage 2 에서
                # 단지당 first 로 집는다.
                "elem_dist": r.get("elem_dist"),
                "mid_dist": r.get("mid_dist"),
                "academy": r.get("academy"),
                "adult": r.get("adult"),
                "lat": r.get("lat"),
                "lng": r.get("lng"),
            }
        )

    df = pd.DataFrame.from_records(recs)
    if df.empty:
        return df

    # 표본이 너무 적은 단지는 α̂_c 가 사실상 관측치 하나라 stage 2 에 노이즈만 더한다.
    counts = df.groupby("complex_id")["log_ppp"].transform("size")
    df = df[counts >= MIN_TRADES_PER_COMPLEX].copy()

    # 원룸형 도시형생활주택 제외 (위 MIN_MAX_AREA_M2 주석 참조)
    max_area = df.groupby("complex_id")["exclusive_area"].transform("max")
    dropped = df.loc[max_area < MIN_MAX_AREA_M2, "complex_id"].nunique()
    df = df[max_area >= MIN_MAX_AREA_M2].copy()
    df.attrs["dropped_small_complexes"] = int(dropped)
    return df


# --------------------------------------------------------------------------
# Stage 1 — 거래 단위, 단지 내 변동
# --------------------------------------------------------------------------
# 동 고유 프리미엄 추정에 쓸 최소 거래 수. 1건짜리는 수축하면 어차피 0 에 가까워
# 지지만, 계산해 두면 화면에 "이 동은 1건" 이라고 말해 줄 수 있다.
DONG_MIN_TRADES = 2
# 이 표본의 동 효과 검출 한계(%). 참 효과를 심고 되찾는 시뮬레이션으로 쟀다 —
# τ=1.5% 는 0.94% 로, τ=1.0% 는 0 으로 잡힌다. 이보다 작은 효과는 잡음과 구분되지 않는다.
DONG_DETECTION_FLOOR_PCT = 1.2


def _dong_effects(df, resid):
    """**평형을 통제한** 동 고유 프리미엄. 지금 데이터에서는 사실상 0 이 나온다.

    ## 처음 판이 왜 틀렸나

    처음에는 단지 안에서만 잔차를 평균 냈다. 그랬더니 τ=2.50% 라는 그럴듯한 값이
    나왔는데, **전부 평형 교란이었다.**

    수원센트럴아이파크자이를 보면 40㎡ 는 129동·130동에만 있고 나머지 28개 동은
    60~103㎡ 뿐이다. 전역 면적 스플라인이 이 단지의 40㎡ 를 10%쯤 비싸게 예측하면,
    그 오차가 갈 곳은 129·130동의 '동 효과' 밖에 없다. 실제로 129동은 -10.33% 가
    찍혔지만 129동과 130동의 실거래 평당가 중앙값은 3,076 으로 **똑같다**.
    동 위치 차이가 아니라 평형 차이를 보고 있었던 것이다.

    ## 고친 방법

    `(단지 × 평형)` 셀 안에서 잔차를 한 번 더 차감한 뒤 동별로 평균 낸다. 그러면
    같은 평형을 나눠 갖는 동끼리만 비교된다. 같은 평형이 한 동에만 있으면 그 동의
    효과는 **식별 자체가 불가능**하므로 아예 뺀다 — 찍어서 내놓는 것보다 낫다.

    ## 그래서 결과는

    τ = 0.00%. 검출력을 보정해 보면(참 효과를 심고 되찾는 시뮬레이션) 이 표본은
    τ≈1.5% 면 0.94% 로, 1.0% 면 0 으로 잡는다. 즉 **평형을 통제한 동 효과는
    1.5% 아래**라는 뜻이고, 이 데이터로는 있다/없다를 말할 수 없다.

    거리로 설명되는 부분(`dong_walk_dev`, -0.355%/분, t=-9.7)은 별개로 살아 있다.
    동 위치가 가격에 영향을 준다면, 이 표본에서 잡히는 경로는 역거리뿐이다.
    """
    np, pd, _ = _deps()

    if "apt_dong" not in df.columns:
        return {}, None
    d = df.assign(_resid=np.asarray(resid))
    d = d[d["apt_dong"].notna() & (d["apt_dong"] != "")].copy()
    if d.empty:
        return {}, None

    # (단지 × 평형) 셀. 같은 평형을 나눠 갖는 동이 2개 이상일 때만 비교가 성립한다.
    d["_cell"] = (
        d["complex_id"].astype(str) + "_"
        + d["exclusive_area"].map(pricing.area_type_key).astype(str)
    )
    n_dong_in_cell = d.groupby("_cell")["apt_dong"].transform("nunique")
    n_total = d.groupby(["complex_id", "apt_dong"]).ngroups
    d = d[n_dong_in_cell >= 2]
    if d.empty:
        return {}, None
    d["_dev"] = d["_resid"] - d.groupby("_cell")["_resid"].transform("mean")

    sigma2 = float(np.var(np.asarray(resid), ddof=1))
    g = d.groupby(["complex_id", "apt_dong"])["_dev"].agg(["mean", "size"])
    g = g[g["size"] >= DONG_MIN_TRADES]
    if g.empty:
        return {}, None

    w = g["size"].to_numpy(dtype=float)
    obs_var = float(np.average(g["mean"].to_numpy() ** 2, weights=w))
    noise = float(np.average(sigma2 / w, weights=w))
    tau2 = max(obs_var - noise, 0.0)

    out = {}
    for (cid, dong), row in g.iterrows():
        n = int(row["size"])
        raw = float(row["mean"])
        k = tau2 / (tau2 + sigma2 / n) if tau2 > 0 else 0.0
        out[(int(cid), str(dong))] = {
            "dong": str(dong),
            "n": n,
            "raw_pct": round((math.exp(raw) - 1) * 100, 2),
            "coef": round(raw * k, 6),
            "pct": round((math.exp(raw * k) - 1) * 100, 2),
            "shrink": round(k, 3),
        }

    tau_pct = math.sqrt(tau2) * 100
    summary = {
        "tau_pct": round(tau_pct, 2),
        "signal_ratio": round(tau2 / obs_var, 3) if obs_var > 0 else 0.0,
        "n_dongs": len(out),
        "n_unidentified": max(n_total - len(out), 0),
        "n_trades": int(g["size"].sum()),
        # 검출 한계. 참 효과를 심고 되찾는 시뮬레이션으로 잰 값이다.
        "detection_floor_pct": DONG_DETECTION_FLOOR_PCT,
        "detected": tau_pct >= DONG_DETECTION_FLOOR_PCT,
        "label": "같은 단지·같은 평형 안에서 동에 따른 차이",
        "note": (
            "**(단지 × 평형) 셀 안에서** 비교한 값입니다. 단지 안에서만 비교하면 "
            "평형 구성이 특이한 동이 면적 곡선의 오차를 대신 떠안습니다 — 40㎡가 "
            "두 동에만 있는 단지에서 그 동들에 -10% 가 찍히는 식입니다. "
            f"같은 평형을 나눠 갖는 동이 없어 비교 자체가 안 되는 동은 제외했습니다."
        ),
    }
    return out, summary


def _fit_stage1(df, use_controls: bool):
    """단지별 보정 평당가 α̂_c 와 그 표준오차를 낸다.

    절편을 두지 않고 단지 더미를 **전부** 넣는다. 층 기준은 중층, 월 기준은 최신월,
    면적은 log(전용/84)라 84㎡에서 0. 따라서 단지 더미의 계수가 곧
    '전용 84㎡·중층·최신월 기준 log 평당가'가 된다.
    """
    np, pd, sm = _deps()

    if not use_controls:
        # 통제 없이 단지 더미만 넣은 회귀의 해는 **각 단지의 평균**과 정확히 같다.
        # 28,707행 × 521열 OLS 를 돌릴 이유가 없다(4초 -> 10ms). 근사가 아니라 동일값.
        g = df.groupby("complex_id")
        agg = g.agg(
            alpha=("log_ppp", "mean"),
            sd=("log_ppp", "std"),
            trade_count=("log_ppp", "size"),
            complex_name=("complex_name", "first"),
            sgg_cd=("sgg_cd", "first"),
            sgg_name=("sgg_name", "first"),
            umd_nm=("umd_nm", "first"),
            line=("line", "first"),
            walk_min=("walk_min", "first"),
            dong_walk_mean=("dong_walk_min", "mean"),
            gangnam_min=("gangnam_min", "first"),
            age=("age", "first"),
            log_households=("log_households", "first"),
            top_floor=("top_floor", "first"),
            brand=("brand", "first"),
            elem_dist=("elem_dist", "first"),
            mid_dist=("mid_dist", "first"),
            academy=("academy", "first"),
            adult=("adult", "first"),
            lat=("lat", "first"),
            lng=("lng", "first"),
            ppp_median=("log_ppp", "median"),
        ).reset_index()
        agg["se_alpha"] = (agg["sd"].fillna(0.0) / np.sqrt(agg["trade_count"])).clip(lower=1e-6)
        agg["ppp_median"] = np.exp(agg["ppp_median"])
        alpha = agg.drop(columns=["sd"])
        stage1 = {
            "n_obs": int(len(df)),
            "n_complexes": int(len(alpha)),
            "within_walk": None,
            "dong_premium": None,
            "_dong_effects": {},
            "within_r2": None,
            "month_trend_pct": None,
            "floor_terms": [],
            "log_area": None,
            "reference": "통제 없음 (단지 평균)",
        }
        return alpha, stage1

    # 단지 더미는 만들지 않는다 — 아래에서 흡수한다.
    parts: list = []
    floor_terms: list[str] = []
    month_terms: list[str] = []
    within = None

    area_terms: list[str] = []
    if use_controls:
        # 면적도 형태를 가정하지 않는다. log 로 충분한지 데이터에 묻는다.
        #
        # 매듭은 Stage 2 보다 넉넉히 둔다. 여기 관측치는 **거래 건수**(경기 남부
        # 24개월 기준 11만 건)라 단지 수(2천)로 제약되는 Stage 2 와 자릿수가 다르다.
        # 다만 실제 전용면적은 59·84·114 처럼 몇 개 값에 몰려 있어서, `_knots` 가
        # 고유값 수를 보고 알아서 줄인다.
        acols: dict[str, list[float]] = {}
        aknots = _knots(df["log_area"].astype(float).to_numpy(), knots_for(len(df) // 20))
        area_terms = _spline_cols(acols, "log_area", df["log_area"], aknots)
        parts.append(pd.DataFrame(acols, index=df.index))

        # 동 단위 도보시간을 **단지 평균에서 뺀 편차**로 넣는다.
        #
        # 이렇게 하면 단지 더미와 직교해서, 이 계수는 오로지 '같은 단지 안에서
        # 역에 가까운 동 vs 먼 동' 비교로만 추정된다. 학군·브랜드·관리상태·연식·
        # 구 입지가 전부 단지 더미에 흡수되므로 교란이 원천적으로 없다 —
        # 이 데이터로 얻을 수 있는 가장 깨끗한 식별이다.
        #
        # 대신 범위가 좁다(단지 내 편차는 보통 1~3분). 넓은 범위의 추정치는
        # Stage 2 의 단지 간 비교가 담당한다. 둘은 서로 다른 질문의 답이다.
        dw = df["dong_walk_min"]
        if dw.notna().any():
            grp = dw.groupby(df["complex_id"])
            dev = (dw - grp.transform("mean")).fillna(0.0)
            if float(dev.abs().sum()) > 0:
                within = pd.DataFrame({"dong_walk_dev": dev.astype(float)}, index=df.index)
                parts.append(within)

        fb = pd.get_dummies(df["floor_band"], prefix="fb", dtype=float)
        fb = fb.drop(columns=[f"fb_{FLOOR_REF}"], errors="ignore")
        fb = fb.drop(columns=["fb_정보없음"], errors="ignore")
        floor_terms = list(fb.columns)
        parts.append(fb)

        latest = df["deal_ym"].max()
        mo = pd.get_dummies(df["deal_ym"], prefix="ym", dtype=float)
        mo = mo.drop(columns=[f"ym_{latest}"], errors="ignore")
        month_terms = list(mo.columns)
        parts.append(mo)

    Z = pd.concat(parts, axis=1)
    y = df["log_ppp"].astype(float)

    # 단지 고정효과를 **흡수(within transformation)** 한다. 더미 497개를 설계행렬에
    # 직접 넣으면 28,451×528 이 되고 statsmodels 가 pinv(SVD) 로 푸느라 2.7초가 든다.
    # 그룹 평균을 빼면 28,451×31 로 줄어 0.07초다(29배).
    #
    # Frisch-Waugh-Lovell 정리가 기울기 계수의 동일성을 보장한다 — 실측으로도
    # 1e-13 까지 같다(`scripts/verify_absorb.py`).
    gid = df["complex_id"].to_numpy()
    res = sm.OLS(y - y.groupby(gid).transform("mean"),
                 Z - Z.groupby(gid).transform("mean")).fit(cov_type="HC1")

    # α̂_c 복원: α̂_c = mean_c(y - Zβ̂). 더미 계수와 1e-13 까지 일치한다.
    _beta = res.params.to_numpy()
    _lvl = y - Z.to_numpy() @ _beta
    _alpha = _lvl.groupby(gid).mean().sort_index()
    _e = (_lvl - _alpha.reindex(gid).to_numpy()).to_numpy()

    # se(α̂_c) 는 더미 표준오차를 꺼낼 수 없으니 직접 만든다. 두 항이 모두 필요하다.
    #
    #   Var(α̂_c) = (Σ_{i∈c} e_i²)·dfc / n_c²   +   z̄_c' V(β̂) z̄_c
    #              └ 그룹 평균의 강건 분산        └ β̂ 불확실성이 옮겨온 몫
    #
    # 뒤 항은 버릴 수 없다 — 전체 se 의 절반(중앙 52%)을 차지한다. 앞 항에 그룹별
    # 잔차가 아니라 공통 σ² 를 쓰면 상관이 1.00 에서 0.72 로 떨어진다. 둘 다
    # 후보를 재서 고른 결과다(`scripts/verify_absorb.py` 참조).
    _codes, _uniq = pd.factorize(gid)
    _remap = pd.Series(np.arange(len(_uniq)), index=_uniq).reindex(_alpha.index).to_numpy()
    _n_c = np.bincount(_codes).astype(float)[_remap]
    _sum_e2 = np.bincount(_codes, weights=_e**2)[_remap]
    _n, _k, _g = len(df), Z.shape[1], len(_uniq)
    _dfc = _n / max(_n - _k - _g, 1)
    _zbar = Z.groupby(gid).mean().sort_index().to_numpy()
    _V = res.cov_params().to_numpy()
    _quad = np.maximum(np.einsum("ij,jk,ik->i", _zbar, _V, _zbar), 0.0)
    _se_alpha = np.sqrt(_sum_e2 * _dfc / _n_c**2 + _quad)

    # 결정계수는 **수준(level) 잔차**로 계산한다. 차감된 적합의 rsquared 를 그대로
    # 쓰면 단지 더미가 설명한 몫이 빠져 예전 값(0.9603)과 달라진다.
    _sst = float(((y - y.mean()) ** 2).sum())
    _within_r2 = 1.0 - float((_e**2).sum()) / _sst if _sst > 0 else 0.0

    # 단지별 집계는 **groupby 한 번**으로 끝낸다. 단지마다 `df[df.complex_id == cid]`
    # 를 돌면 28,451행을 497번 훑어(1,400만 비교) 0.25초가 날아간다.
    #
    # `first` 를 쓰는 열들은 단지 안에서 값이 하나뿐이다(역거리·연식·세대수·좌표).
    # `dong_walk_mean` 만 평균인데, 이것이 `dong_walk_dev` 의 기준선이다 — 단지
    # 중심점 도보와는 다른 값으로, 거래가 일어난 동들의 (거래 가중) 평균이다.
    agg = (
        df.groupby("complex_id")
        .agg(
            complex_name=("complex_name", "first"),
            sgg_cd=("sgg_cd", "first"),
            sgg_name=("sgg_name", "first"),
            umd_nm=("umd_nm", "first"),
            line=("line", "first"),
            trade_count=("log_ppp", "size"),
            walk_min=("walk_min", "first"),
            dong_walk_mean=("dong_walk_min", "mean"),
            gangnam_min=("gangnam_min", "first"),
            age=("age", "first"),
            log_households=("log_households", "first"),
            top_floor=("top_floor", "first"),
            brand=("brand", "first"),
            elem_dist=("elem_dist", "first"),
            mid_dist=("mid_dist", "first"),
            academy=("academy", "first"),
            adult=("adult", "first"),
            lat=("lat", "first"),
            lng=("lng", "first"),
            ppp_median=("log_ppp", "median"),
        )
        .reset_index()
    )
    agg["ppp_median"] = np.exp(agg["ppp_median"])

    # 위에서 복원한 α̂ 과 se 를 붙인다. 둘 다 complex_id 오름차순이라 순서가 맞는다.
    agg = agg.sort_values("complex_id").reset_index(drop=True)
    agg["alpha"] = _alpha.to_numpy()
    agg["se_alpha"] = _se_alpha
    alpha = agg

    # 월 더미에서 평균 월 상승률을 뽑는다(pricing.market_index 를 대체).
    month_trend = None
    if month_terms:
        yms = sorted({c[3:] for c in month_terms} | {df["deal_ym"].max()})
        idx = {ym: i for i, ym in enumerate(yms)}
        xs, ys = [], []
        for ym in yms:
            col = f"ym_{ym}"
            ys.append(float(res.params[col]) if col in res.params.index else 0.0)
            xs.append(idx[ym])
        if len(xs) >= 2:
            slope = float(np.polyfit(xs, ys, 1)[0])
            month_trend = (math.exp(slope) - 1) * 100

    floors = []
    for band in pricing.FLOOR_BANDS:
        col = f"fb_{band}"
        if col in res.params.index:
            c, s = float(res.params[col]), float(res.bse[col])
            floors.append(
                {
                    "band": band,
                    "coef": round(c, 5),
                    "se": round(s, 5),
                    "premium_pct": round((math.exp(c) - 1) * 100, 2),
                    "ci_pct": [
                        round((math.exp(c - 1.96 * s) - 1) * 100, 2),
                        round((math.exp(c + 1.96 * s) - 1) * 100, 2),
                    ],
                }
            )
        elif band == FLOOR_REF:
            floors.append(
                {"band": band, "coef": 0.0, "se": 0.0, "premium_pct": 0.0,
                 "ci_pct": [0.0, 0.0], "reference": True}
            )

    area_linearity = None
    if area_terms:
        area_linearity = _linearity_tests(res, {"log_area": area_terms}).get("log_area")
        area_linearity["knots"] = (
            [round(k, 4) for k in aknots] if aknots else None
        )
        area_linearity["terms"] = area_terms
        area_linearity["coefs"] = [
            round(float(res.params[n]), 6) for n in area_terms if n in res.params.index
        ]
        # 비선형항을 뺀 제약 적합 — 화면에서 곡선 옆 점선으로 굽은 정도를 보여 준다.
        nl = [n for n in area_terms[1:] if n in Z.columns]
        if nl:
            try:
                Zr = Z.drop(columns=nl)
                r2 = sm.OLS(y - y.groupby(gid).transform("mean"),
                            Zr - Zr.groupby(gid).transform("mean")).fit(cov_type="HC1")
                area_linearity["linear_coef"] = round(float(r2.params["log_area"]), 6)
                area_linearity["linear_se"] = round(float(r2.bse["log_area"]), 6)
            except Exception:
                pass

    within_walk = None
    if within is not None and "dong_walk_dev" in res.params.index:
        c, s = float(res.params["dong_walk_dev"]), float(res.bse["dong_walk_dev"])
        used = df["dong_walk_min"].notna().sum()
        within_walk = {
            "coef": round(c, 6),
            "se": round(s, 6),
            "t": round(c / s, 3) if s > 0 else None,
            "p": round(float(res.pvalues["dong_walk_dev"]), 5),
            "pct": round((math.exp(c) - 1) * 100, 3),
            "n_trades": int(used),
            "label": "같은 단지 안에서 도보 1분",
            "note": (
                "단지 고정효과와 직교하는 동 단위 편차로만 추정한 값입니다. "
                "학군·브랜드·연식·구 입지가 모두 통제되지만, 단지 내 거리 편차가 "
                "좁아 넓은 범위로 외삽하면 안 됩니다."
            ),
        }

    # 차감된 적합의 잔차는 수준 잔차와 같다(α̂_c 정의상 서로 상쇄된다).
    dong_effects, dong_summary = _dong_effects(df, _e)

    stage1 = {
        "n_obs": int(len(df)),
        "n_complexes": int(len(alpha)),
        "within_walk": within_walk,
        "dong_premium": dong_summary,
        "within_r2": round(_within_r2, 4),
        "month_trend_pct": round(month_trend, 4) if month_trend is not None else None,
        "floor_terms": floors,
        "log_area": (
            {"coef": round(float(res.params["log_area"]), 5),
             "se": round(float(res.bse["log_area"]), 5)}
            if "log_area" in res.params.index
            else None
        ),
        "area_linearity": area_linearity,
        "reference": f"전용 {PYEONG_REF_AREA:.0f}㎡ · {FLOOR_REF} · {df['deal_ym'].max()}",
    }
    stage1["_dong_effects"] = dong_effects
    return alpha, stage1


# --------------------------------------------------------------------------
# Stage 2 — 단지 단위, 가중최소제곱
# --------------------------------------------------------------------------
# Harrell 권장 매듭 위치. 매듭 k개 -> 열 k-1개(선형 1 + 비선형 k-2).
_KNOT_PCTS = {
    3: (10, 50, 90),
    4: (5, 35, 65, 95),
    5: (5, 27.5, 50, 72.5, 95),
    6: (5, 23, 41, 59, 77, 95),
    7: (2.5, 18.33, 34.17, 50, 65.83, 81.67, 97.5),
}
DEFAULT_KNOTS = 4

# 매듭을 몇 개까지 허용할지는 **표본이 정한다**. 매듭 k개는 열 k-1개를 쓰는데,
# Stage 2 의 관측치는 단지 수뿐이다. 수원만 볼 때는 단지 497곳이라 4개가 상한이었고,
# 경기 남부로 넓히며 2,000곳을 넘어서면서 더 촘촘하게 볼 여유가 생겼다.
#
# Harrell 의 권고(표본이 작으면 3~4개, 100을 넘으면 5개, 매우 크면 7개)를 따른다.
# 매듭 k개는 요인당 열 k-1개를 쓰므로, 연속 요인 4개면 k=7 에서 24열이다. Stage 2 의
# 관측치는 단지 수이고 여기에 노선·구 FE 20여 열이 더 붙으니, 1,500단지에서 45열이면
# 관측당 30배로 넉넉하다.
def knots_for(n_complexes: int) -> int:
    if n_complexes >= 1500:
        return 7
    if n_complexes >= 700:
        return 6
    if n_complexes >= 250:
        return 5
    return 4


def _knots(values, n: int = DEFAULT_KNOTS):
    """분포에 맞춰 매듭을 놓는다.

    고유값이 적으면(예: 강남 소요시간은 역 수만큼만 존재) 매듭을 줄인다.
    매듭이 겹치면 기저가 0으로 나뉘고, 고유값보다 매듭이 많으면 과적합이다.

    ## 분위수가 겹칠 때는 매듭을 **줄인다**

    예전에는 겹친 매듭을 1e-6 씩 밀어 떨어뜨렸다. 그러면 매듭 개수는 지켜지지만
    폭이 0 에 가까운 구간이 생겨, 그 구간의 기저열은 사실상 0 이거나 이웃 열과
    거의 같아진다. 유연성을 쓰지도 못하면서 공선성만 얻는 셈이다.

    경기 남부로 넓히며 실제로 그렇게 됐다. 도보시간은 `WALK_CAP_MIN`(30분)에서
    잘리는데 단지의 30%가 그 상한에 몰려서, p83 과 p97.5 가 **둘 다 30.0** 이 됐다.
    매듭 7개 중 2개가 같은 자리에 선 것이다.

    그래서 밀어내지 않고 **중복을 없앤 뒤 그만큼 매듭을 줄인다.** 분포가 한 점에
    몰려 있다는 것은 그 구간에 볼 것이 없다는 뜻이고, 개수는 목표가 아니다.

    ## 가까이 붙은 매듭은 **재 보고 그냥 뒀다**

    단지 최고층을 넣으니 매듭이 `[5, 14, 15, 19, 20, 25, 35.9]` 로 나왔다. 14 와 15 는
    다른 값이라 위 규칙을 통과하지만, 전체 범위 31층에서 폭 1층(3.2%)짜리 구간이다.
    최고층이 정수에 몰려 있어서다 — 1,846곳 중 20층 271곳, 15층 260곳, 25층 150곳.
    겹친 매듭과 같은 병리로 보여서 '범위의 5% 미만이면 중복' 규칙을 넣어 재 봤다.

    **차이가 없었다.** 매듭이 `[7, 15, 18, 20, 24, 30]`(최소 간격 8.7%)으로 바뀌어도
    곡선은 어디서나 2%p 이내로 같고(20층 +6.5% → +7.7%, 30층 +22.6% → +23.8%),
    adj R² 는 오히려 0.8477 → 0.8465 로 조금 낮아졌다. 비선형 p 도 0.00112 → 0.00108.

    그래서 규칙을 넣지 않았다. 대신 얻은 것이 있다 — 최고층 곡선이 **매듭 위치의
    산물이 아니라는 확인**이다. 참고로 `top_floor__nl*` 이 하나하나는 유의하지 않고
    (p 0.06~0.48) 합동 검정만 유의한 것은 매듭 간격 탓이 아니었다. 매듭을 띄워도
    그대로였다. 스플라인 기저끼리의 공선성은 원래 그렇다 — 개별 항의 p 를 읽지 말고
    합동 검정과 곡선을 읽어야 한다.
    """
    np, _, _ = _deps()
    uniq = len(set(float(v) for v in values))
    n = min(n, max(3, min(uniq - 1, max(_KNOT_PCTS))))
    if uniq < 4:
        return None  # 스플라인을 줄 만큼의 변동이 없다 — 선형으로 간다

    while n >= 3:
        qs = [float(np.percentile(values, p)) for p in _KNOT_PCTS[n]]
        # 같은 값으로 붙은 매듭을 걷어낸다. 부동소수 오차도 겹친 것으로 본다.
        uniq_qs: list[float] = []
        for q in qs:
            if not uniq_qs or q - uniq_qs[-1] > 1e-9:
                uniq_qs.append(q)
        if len(uniq_qs) == n:
            return qs
        n -= 1
    return None


def _spline_cols(cols: dict, name: str, values, knots) -> list[str]:
    """cols 에 스플라인 기저를 추가하고 컬럼 이름을 돌려준다.

    첫 열은 변수 자신(선형항), 나머지가 비선형항이다. 비선형항을 함께 0으로
    두는 Wald 검정이 곧 '이 요인이 선형인가' 검정이 된다.
    """
    np, _, _ = _deps()

    vals = np.asarray(values, dtype=float)
    if not knots:
        cols[name] = vals
        return [name]

    # `pricing.rcs_basis` 를 행마다 부르면 11.7만 행 × 매듭 수만큼 파이썬 루프가 돈다
    # (프로파일에서 2.2초, 적합 전체의 5분의 1). 같은 식을 numpy 로 한 번에 계산한다.
    # 값이 정말 같은지는 `scripts/verify_spline.py` 가 검사한다 — 이 기저는 시드와
    # 모델이 공유하는 함수라 조용히 달라지면 참값 복원 검증이 무너진다.
    t = [float(k) for k in knots]
    denom = (t[-1] - t[0]) ** 2
    span = t[-1] - t[-2]

    def cube_plus(u):
        return np.where(u > 0, u ** 3, 0.0)

    names = [name] + [f"{name}__nl{j}" for j in range(1, len(t) - 1)]
    cols[name] = vals
    last2, last1 = cube_plus(vals - t[-2]), cube_plus(vals - t[-1])
    for j in range(len(t) - 2):
        term = (
            cube_plus(vals - t[j])
            - last2 * (t[-1] - t[j]) / span
            + last1 * (t[-2] - t[j]) / span
        )
        cols[names[j + 1]] = term / denom
    return names


def _stage2_design(alpha, spec: Spec, knots: dict):
    """설계행렬 + 변수별 스플라인 열 이름.

    연속 요인은 **모두 같은 방식**으로 스플라인을 준다. 예전에는 도보만 스플라인,
    연식은 2차항, 강남은 직선으로 제각각 형태를 미리 정해 놓았는데, 그러면
    '이 요인이 실제로 비선형인가'를 물을 수 없다. 형태를 가정하지 않고 유연하게
    적합한 뒤 비선형항이 유의한지 검정하는 쪽이 맞다.
    """
    np, pd, _ = _deps()

    cols: dict[str, list[float]] = {}
    spline_terms: dict[str, list[str]] = {}

    spline_terms["walk_min"] = _spline_cols(
        cols, "walk_min", alpha["walk_min"], knots.get("walk_min")
    )

    if spec.use_gangnam and alpha["gangnam_min"].notna().all():
        spline_terms["gangnam_min"] = _spline_cols(
            cols, "gangnam_min", alpha["gangnam_min"], knots.get("gangnam_min")
        )
    if spec.use_age and alpha["age"].notna().all():
        spline_terms["age"] = _spline_cols(
            cols, "age", alpha["age"], knots.get("age")
        )
    # 세대수는 K-apt 에서만 오는데 우리 단지의 절반 정도만 매칭된다(수원 42%).
    # '전부 있을 때만 쓴다'로 두면 변수가 영영 들어가지 않고, 결측 단지를 버리면
    # 표본의 절반이 날아간다. 그래서 **중앙값 대체 + 결측 표시자**를 쓴다.
    #
    # 표시자가 중요하다. K-apt 에 없는 단지는 체계적으로 다를 수 있는데(소규모·
    # 자체관리·신축), 표시자가 그 차이를 흡수해 주므로 세대수 계수가 오염되지 않는다.
    # 표시자 없이 대체만 하면 그 차이가 세대수 계수로 새어 들어간다.
    hh = alpha["log_households"].astype(float)
    if spec.use_households and hh.notna().any():
        filled = hh.fillna(hh.median())
        spline_terms["log_households"] = _spline_cols(
            cols, "log_households", filled, knots.get("log_households")
        )
        if hh.isna().any():
            cols["households_missing"] = hh.isna().astype(float).tolist()

    # 단지 최고층. 연속이고 굽을 수 있으므로 다른 연속 요인과 **같은 방식**으로
    # 스플라인을 준다 — 형태를 미리 정하지 않고 비선형인지 검정한다.
    #
    # 세대수와 같은 자리에 있다(대단지 프리미엄). 다만 겹치지는 않는다 — 1,000세대가
    # 10동 10층일 수도 2동 30층일 수도 있다.
    if spec.use_top_floor:
        tf = alpha["top_floor"].astype(float)
        if tf.notna().any():
            filled = tf.fillna(tf.median())
            spline_terms["top_floor"] = _spline_cols(
                cols, "top_floor", filled, knots.get("top_floor")
            )
            if tf.isna().any():
                cols["top_floor_missing"] = tf.isna().astype(float).tolist()

    # 주변 입지. 세대수와 **같은 방식**으로 넣는다 — 중앙값 대체 + 결측 표시자.
    # 적재를 아직 안 돌린 단지가 있어도 나머지가 빠지지 않아야 한다.
    #
    # 무엇을 넣고 무엇을 뺐는지는 재서 정했다. 처음에는 음식점·소매·의원·숙박·
    # 오락·주점·대형마트까지 열 가지를 넣었다. 표본 밖 오차는 더 줄었지만(교차검증
    # 3.96% vs 2.87%) 그 변수들은 서로 상관이 0.92 까지 가는 '반경 안 가게 수' 의
    # 변주라, 요인 카드에 따로 올리면 혼자 읽을 수 없는 값이 된다.
    #
    # 하나씩 얹어 보니 **학교 거리 위에 아무것도 더하지 못했다** — 학교만 +1.80%
    # 인데 상권 규모·음식점·숙박·오락을 각각 더해도 1.74~1.87% 였다. 학원 수만
    # +2.71% 로 뚜렷했고, 유흥주점이 거기에 +0.16%p 를 더했다. 그래서 넷만 남겼다.
    if spec.use_amenity:
        for var in ("elem_dist", "mid_dist", "academy", "adult"):
            if var not in alpha.columns:
                continue
            v = alpha[var].astype(float)
            if not v.notna().any():
                continue
            filled = v.fillna(v.median())
            spline_terms[var] = _spline_cols(cols, var, filled, knots.get(var))
            if v.isna().any():
                cols[f"{var}_missing"] = v.isna().astype(float).tolist()

    X = pd.DataFrame(cols, index=alpha.index)

    # 브랜드 FE. 브랜드가 없는 단지가 기준이다.
    #
    # 더미를 브랜드마다 주면 2,469곳에 31개 더미라 표본이 얇은 브랜드의 계수가
    # 요동친다. 그렇다고 '브랜드 있음' 하나로 묶으면 자이와 칸타빌이 같아진다.
    # **표본이 충분한 브랜드만 따로** 두고 나머지는 '기타 브랜드' 로 묶는다 —
    # 층 구간을 저/중/고로 묶는 것과 같은 발상이다.
    if spec.use_brand and alpha["brand"].notna().any():
        b = alpha["brand"].fillna("없음")
        counts = b.value_counts()
        keep = set(counts[counts >= _BRAND_MIN].index) - {"없음"}
        lab = b.map(lambda x: x if x in keep else ("기타브랜드" if x != "없음" else "없음"))
        if lab.nunique() > 1:
            d = pd.get_dummies(lab, prefix="brand", dtype=float)
            # 기준은 **브랜드 없음**이다. 계수가 '브랜드가 붙으면 몇 %' 로 읽힌다.
            d = d.drop(columns=["brand_없음"], errors="ignore")
            X = pd.concat([X, d], axis=1)

    # 노선 FE. 강남 소요시간과 상관이 있지만(노선이 강남분 분산의 50%를 설명)
    # 완전 중복은 아니다 — 같은 노선 안에서도 역마다 소요시간이 다르기 때문이다.
    # 둘을 함께 넣으면 노선 계수는 '이동시간으로 설명되지 않는 노선 프리미엄'이 된다.
    if spec.use_line_fe and alpha["line"].nunique() > 1:
        d = pd.get_dummies(alpha["line"], prefix="line", dtype=float, drop_first=True)
        X = pd.concat([X, d], axis=1)

    # 법정동 FE 는 구 FE 를 완전히 포함한다(각 동은 정확히 한 구에 속한다).
    # 둘을 같이 넣으면 설계행렬이 반드시 rank-deficient 가 되어 M3 가 '식별 불가'로
    # 떨어진다 — 정작 M3 는 "통제를 과하게 하면 무슨 일이 생기는가"를 보여주는
    # 핵심 교보재라 적합이 되어야 한다.
    if spec.use_umd_fe:
        d = pd.get_dummies(alpha["umd_nm"], prefix="umd", dtype=float, drop_first=True)
        X = pd.concat([X, d], axis=1)
    elif spec.use_sgg_fe:
        d = pd.get_dummies(alpha["sgg_cd"], prefix="sgg", dtype=float, drop_first=True)
        X = pd.concat([X, d], axis=1)

    X.insert(0, "const", 1.0)
    return X, spline_terms


def _tau_squared(alpha, X, y) -> float:
    """단지 고유효과의 분산 τ². 가중치와 잔차 축소 양쪽에 필요.

    단순히 Var(α̂) - mean(se²) 로 두면 모델이 **설명한** 변동까지 τ² 에 들어간다.
    설명되지 않은 부분만 남기려면 1차 OLS 잔차에서 표본오차 평균을 뺀다.
    """
    np, _, sm = _deps()
    ols = sm.OLS(y, X).fit()
    n, k = X.shape
    dof = max(n - k, 1)
    resid_var = float(np.sum(ols.resid**2) / dof)
    mean_var = float(np.mean(alpha["se_alpha"] ** 2))
    return max(0.0, resid_var - mean_var)


def _curve(res, X, walk_terms, knots, alpha, truth=None):
    """적합 곡선 + 신뢰밴드.

    수준(level)에서 fit ± 1.96·se 를 그리면 절편 불확실성이 밴드를 균일하게
    부풀려 모양을 가린다. 대신 기준점 대비 **대비(contrast)** 로 계산한다:
    x₀(W) - x₀(W_ref). 도보 관련 열 말고는 전부 상쇄되므로 대비 행은 희소하다.
    밴드가 기준점에서 폭 0이 되고 '도보 N분 단지 대비 %'로 읽힌다.
    """
    np, _, _ = _deps()

    ws = alpha["walk_min"].astype(float)
    lo, hi = float(ws.min()), float(ws.max())
    w_ref = float(np.median(ws))
    # 기준점을 격자에 정확히 포함시킨다. 그래야 밴드 폭이 그 지점에서 정확히 0이 되고,
    # 근처 격자점으로 근사해 생기는 미세한 폭이 버그처럼 보이지 않는다.
    grid = np.unique(np.concatenate([np.linspace(lo, hi, CURVE_POINTS), [w_ref]]))
    ref_basis = pricing.rcs_basis(w_ref, knots)

    names = list(X.columns)
    rows = []
    for w in grid:
        b = pricing.rcs_basis(float(w), knots)
        row = np.zeros(len(names))
        for j, term in enumerate(walk_terms):
            row[names.index(term)] = b[j] - ref_basis[j]
        rows.append(row)
    R = np.vstack(rows)

    t = res.t_test(R)
    eff = np.asarray(t.effect).ravel()
    ci = np.asarray(t.conf_int())

    def pct(v):
        return [round((math.exp(float(x)) - 1) * 100, 3) for x in v]

    out = {
        "x": [round(float(w), 2) for w in grid],
        "fit_pct": pct(eff),
        "lo_pct": pct(ci[:, 0]),
        "hi_pct": pct(ci[:, 1]),
        "reference_x": round(w_ref, 2),
        "unit": "%",
        "note": f"도보 {w_ref:.0f}분 단지 대비 평당가 차이(%)",
    }
    if truth is not None:
        ref_true = truth(w_ref)
        out["truth_pct"] = [
            round((math.exp(truth(float(w)) - ref_true) - 1) * 100, 3) for w in grid
        ]
    return out


def _linear_walk_check(alpha, X, y, walk_terms, weights):
    """검증용 선형 W 계수 — 지수감쇠 exp(-λW) 는 로그에서 정확히 선형이다.

    스플라인은 모양을 보여주지만 스칼라 t-검정이 안 된다. 시드 참값 복원은
    이 λ̂ 하나로 판정한다.
    """
    np, pd, sm = _deps()
    Xl = X.drop(columns=[c for c in walk_terms if c != "walk_min"])
    cov = "HC3" if len(Xl) < 250 else "HC1"
    res = sm.WLS(y, Xl, weights=weights).fit(cov_type=cov)
    return {
        "coef": float(res.params["walk_min"]),
        "se": float(res.bse["walk_min"]),
        "t": float(res.tvalues["walk_min"]),
        "p": float(res.pvalues["walk_min"]),
    }


def _linearity_tests(res, spline_terms: dict) -> dict:
    """각 연속 요인이 선형인지 Wald 검정한다.

    귀무가설은 "비선형항 계수가 모두 0" = 직선이다. p 가 작으면 직선으로는
    설명이 안 된다는 뜻이고, 크면 굳이 곡선을 그릴 근거가 없다는 뜻이다.

    이걸 보고해야 하는 이유: 함수 형태를 사람이 미리 고르면(로그냐 2차냐 직선이냐)
    그 선택이 결론을 만든다. 유연하게 적합해 놓고 데이터에 물어보는 편이 정직하다.
    """
    out: dict[str, dict] = {}
    for var, names in spline_terms.items():
        nl = [n for n in names[1:] if n in res.params.index]
        if not nl:
            out[var] = {
                "testable": False,
                "verdict": "선형(가정)",
                "note": "변동이 적어 비선형항을 넣지 않았습니다.",
            }
            continue
        try:
            t = res.wald_test([f"{n} = 0" for n in nl], scalar=True)
            pval = float(t.pvalue)
            stat = float(t.statistic)
        except Exception:
            out[var] = {"testable": False, "verdict": "검정 실패"}
            continue
        nonlinear = pval < 0.05
        out[var] = {
            "testable": True,
            "p": round(pval, 5),
            "statistic": round(stat, 3),
            "df": len(nl),
            "nonlinear": nonlinear,
            "verdict": "비선형" if nonlinear else "선형과 구분 안 됨",
            "note": (
                "직선으로는 설명되지 않는 굽은 형태가 유의합니다."
                if nonlinear
                else "곡선으로 적합했지만 직선과 통계적으로 구분되지 않습니다. "
                     "직선으로 읽어도 무방합니다."
            ),
        }
    return out


def _vif(X):
    np, _, _ = _deps()
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    out = []
    arr = X.astype(float).to_numpy()
    for i, name in enumerate(X.columns):
        if name == "const":
            continue
        try:
            v = float(variance_inflation_factor(arr, i))
        except Exception:
            continue
        if math.isfinite(v):
            out.append({"name": name, "vif": round(v, 2)})
    return sorted(out, key=lambda d: -d["vif"])[:12]


LABELS = {
    "const": "절편",
    "walk_min": "역까지 도보(분)",
    "walk_rcs2": "도보(분) 비선형항",
    "walk_rcs3": "도보(분) 비선형항2",
    "gangnam_min": "강남까지 전철(분)",
    "age": "연식(년)",
    "age_sq": "연식²",
    "log_households": "log(세대수)",
    "households_missing": "세대수 결측 표시자",
    "top_floor": "단지 최고층(층)",
    "top_floor_missing": "최고층 결측 표시자",
    "elem_dist": "초등학교까지(m)",
    "mid_dist": "중학교까지(m)",
    "academy": "학원 수(500m)",
    "adult": "유흥주점 수(500m)",
    "elem_dist_missing": "입지 결측 표시자",
    "mid_dist_missing": "입지 결측 표시자",
    "academy_missing": "입지 결측 표시자",
    "adult_missing": "입지 결측 표시자",
}


def _label(name: str) -> str:
    if name in LABELS:
        return LABELS[name]
    if "__nl" in name:
        base = name.split("__nl")[0]
        return f"{LABELS.get(base, base)} 비선형항{name.split('__nl')[1]}"
    if name.startswith("line_"):
        return name[5:]
    if name.startswith("brand_"):
        # 이름을 그대로 두면 계수표에 'brand_자이' 가 찍힌다.
        b = name[6:]
        return "기타 브랜드" if b == "기타브랜드" else b
    if name.startswith("sgg_"):
        # 코드를 그대로 두면 '구 FE 41113' 이라 읽을 수 없다. 이름으로 바꾼다.
        from ..clients.molit import DISTRICTS

        code = name[4:]
        return DISTRICTS.get(code, f"구 {code}")
    if name.startswith("umd_"):
        return f"법정동 FE {name[4:]}"
    return name


def _fit_stage2(alpha, spec: Spec, knots, truth=None):
    np, pd, sm = _deps()

    X, spline_terms = _stage2_design(alpha, spec, knots)
    walk_terms = spline_terms.get("walk_min", ["walk_min"])
    y = alpha["alpha"].astype(float)

    # 표본보다 설명변수가 많거나 더미가 서로 종속이면 계수가 유일하게 정해지지
    # 않는다(단지 25곳에 법정동 17개를 넣는 경우). 의미 없는 숫자를 내놓는 대신
    # 식별 불가임을 알린다.
    rank = int(np.linalg.matrix_rank(X.astype(float).to_numpy()))
    if rank < X.shape[1]:
        raise UnderIdentified(
            f"설계행렬 rank {rank} < 열 {X.shape[1]} — 단지 {len(alpha)}곳으로는 "
            f"'{spec.label}' 스펙을 식별할 수 없습니다."
        )

    tau2 = _tau_squared(alpha, X, y)
    # 바닥값이 없으면 노이즈가 0에 가까운 합성 입력(추정 대상 계산용)에서 0으로 나뉜다.
    denom_w = (alpha["se_alpha"].astype(float) ** 2 + tau2).clip(lower=1e-12)
    weights = 1.0 / denom_w

    # HC1 은 표본이 작으면 표준오차를 과소추정해 신뢰구간 포함률이 95% 아래로 떨어진다.
    # 단지 수가 적은 PoC 구간에서는 HC3 를 쓴다(레버리지가 큰 관측치에 더 보수적).
    cov = "HC3" if len(alpha) < 250 else "HC1"
    res = sm.WLS(y, X, weights=weights).fit(cov_type=cov)

    terms = []
    for name in X.columns:
        c, s = float(res.params[name]), float(res.bse[name])
        row = {
            "name": name,
            "label": _label(name),
            "coef": round(c, 6),
            "se": round(s, 6),
            "t": round(float(res.tvalues[name]), 3),
            "p": round(float(res.pvalues[name]), 4),
            "ci": [round(c - 1.96 * s, 6), round(c + 1.96 * s, 6)],
        }
        if name == "gangnam_min":
            row["interpretation"] = (
                f"전철 1분 멀어질 때 평당가 {(math.exp(c) - 1) * 100:+.2f}%"
            )
        elif name == "walk_min":
            # 스플라인이 걸려 있으면 이 계수 하나만으로 '1분당 몇 %'를 말할 수 없다.
            # 비선형항과 함께 작동하기 때문이다. 해석 가능한 단일 숫자는
            # linear_walk(선형 W 스펙) 쪽이므로 그리로 안내한다.
            row["interpretation"] = (
                f"스플라인 기저 계수 — 단독 해석 불가(비선형항과 함께 작동). "
                f"1분당 변화율은 별도 선형 스펙 값을 참조."
                if len(walk_terms) > 1
                else f"도보 1분 멀어질 때 평당가 {(math.exp(c) - 1) * 100:+.2f}%"
            )
        terms.append(row)

    # 단지별 잔차 = 모델이 설명하지 못한 부분.
    # 축소(shrinkage) 없이 순위를 매기면 상위권이 전부 거래 3건짜리 단지가 된다.
    resid = np.asarray(y - res.fittedvalues, dtype=float)
    se2 = alpha["se_alpha"].astype(float).to_numpy() ** 2
    shrink = tau2 / (tau2 + se2) if tau2 > 0 else np.zeros_like(se2)
    resid_shrunk = resid * shrink
    denom = np.sqrt(tau2 + se2)

    residuals = []
    for i, (_, row) in enumerate(alpha.iterrows()):
        residuals.append(
            {
                "complex_id": int(row["complex_id"]),
                "residual": round(float(resid[i]), 5),
                "residual_pct": round((math.exp(float(resid[i])) - 1) * 100, 2),
                "residual_shrunk_pct": round(
                    (math.exp(float(resid_shrunk[i])) - 1) * 100, 2
                ),
                "residual_z": round(float(resid[i] / denom[i]), 3) if denom[i] > 0 else 0.0,
                "predicted_alpha": round(float(res.fittedvalues.iloc[i]), 5),
            }
        )

    linear = _linear_walk_check(alpha, X, y, walk_terms, weights)
    linearity = _linearity_tests(res, spline_terms)

    # 비선형항을 뺀 제약 모델의 기울기. 화면에서 곡선 옆에 점선으로 겹쳐
    # "얼마나 굽었는지"를 눈으로 보여 준다.
    cov_kind = "HC3" if len(alpha) < 250 else "HC1"
    for var, names in spline_terms.items():
        nl = [n for n in names[1:] if n in X.columns]
        if not nl or var not in linearity:
            continue
        try:
            r2 = sm.WLS(y, X.drop(columns=nl), weights=weights).fit(cov_type=cov_kind)
            linearity[var]["linear_coef"] = round(float(r2.params[var]), 6)
            linearity[var]["linear_se"] = round(float(r2.bse[var]), 6)
        except Exception:
            pass

    return {
        "res": res,
        "X": X,
        "walk_terms": walk_terms,
        "tau2": tau2,
        "terms": terms,
        "residuals": residuals,
        "linear_walk": linear,
        "linearity": linearity,
        "spline_terms": spline_terms,
        "summary": {
            "n_complexes": int(len(alpha)),
            "r2": round(float(res.rsquared), 4),
            "adj_r2": round(float(res.rsquared_adj), 4),
            "sigma": round(float(np.sqrt(np.mean(resid**2))), 5),
            "tau": round(float(math.sqrt(tau2)), 5),
            "tau_pct": round((math.exp(math.sqrt(tau2)) - 1) * 100, 2),
        },
        "curve": _curve(res, X, walk_terms, knots.get("walk_min"), alpha, truth=truth),
    }


# --------------------------------------------------------------------------
# 공개 API
# --------------------------------------------------------------------------
def _var_ranges(df, alpha) -> dict:
    """요인별 관측 범위(p1~p99)와 사분위. 화면 곡선을 데이터에 맞추기 위한 것이다.

    양 끝 1%를 잘라내는 이유는 스플라인의 **선형 꼬리** 때문이다. 극단값 하나까지
    곡선을 늘리면 데이터가 거의 없는 구간이 화면의 절반을 차지한다.
    """
    np, _, _ = _deps()
    out: dict[str, dict] = {}
    src = {
        "walk_min": alpha.get("walk_min"),
        "gangnam_min": alpha.get("gangnam_min"),
        "age": alpha.get("age"),
        "households": (
            np.exp(alpha["log_households"]) if "log_households" in alpha else None
        ),
        "area_m2": df["exclusive_area"] if "exclusive_area" in df else None,
    }
    for name, series in src.items():
        if series is None:
            continue
        v = np.asarray(series.dropna(), dtype=float)
        if v.size < 10:
            continue
        lo, q1, med, q3, hi = (float(np.percentile(v, p)) for p in (1, 25, 50, 75, 99))
        out[name] = {
            "lo": round(lo, 2), "q1": round(q1, 2), "median": round(med, 2),
            "q3": round(q3, 2), "hi": round(hi, 2), "n": int(v.size),
        }
    return out


def fit(rows, spec: str = DEFAULT_SPEC, ref_year: int | None = None, truth=None) -> dict:
    """전체 적합. rows 스키마는 모듈 상단 주석 참조."""
    np, pd, sm = _deps()

    from datetime import date

    ref_year = ref_year or date.today().year
    df = _build_frame(rows, ref_year)
    if df.empty or df["complex_id"].nunique() < 4:
        raise ValueError(
            f"표본이 부족합니다 (거래 {0 if df.empty else len(df)}건, "
            f"단지 {0 if df.empty else df['complex_id'].nunique()}곳). "
            f"단지당 최소 {MIN_TRADES_PER_COMPLEX}건, 단지 4곳 이상 필요합니다."
        )

    chosen = SPECS.get(spec, SPECS[DEFAULT_SPEC])
    alpha, stage1 = _fit_stage1(df, chosen.use_controls)
    # 연속 요인마다 매듭을 따로 놓는다. 분포가 제각각이라 공통 매듭은 맞지 않는다.
    knots = {}
    nk = knots_for(len(alpha))
    # top_floor 를 빼먹으면 매듭이 없어 **직선으로만** 들어간다 — 이 파일이
    # "형태를 가정하지 않고 적합한 뒤 비선형인지 검정한다" 고 해 놓은 것과 어긋난다.
    # 실제로 한 번 빠뜨렸고, 계수가 층당 +1.53% 직선으로 나왔다.
    for var in ("walk_min", "gangnam_min", "age", "log_households", "top_floor",
                "elem_dist", "mid_dist", "academy", "adult"):
        if var in alpha.columns and alpha[var].notna().any():
            knots[var] = _knots(alpha[var].dropna().astype(float).to_numpy(), nk)

    main = _fit_stage2(alpha, chosen, knots, truth=truth)

    # 스펙 사다리 — 전부 적합해도 n=수백이라 1ms 미만이다.
    ladder = []
    stage1_cache = {chosen.use_controls: alpha}
    for key, s in SPECS.items():
        if s.use_controls not in stage1_cache:
            stage1_cache[s.use_controls] = _fit_stage1(df, s.use_controls)[0]
        try:
            r = _fit_stage2(stage1_cache[s.use_controls], s, knots)
        except UnderIdentified as exc:
            ladder.append(
                {"spec": key, "label": s.label, "identified": False, "note": str(exc)}
            )
            continue
        lw = r["linear_walk"]
        ladder.append(
            {
                "spec": key,
                "label": s.label,
                "identified": True,
                "walk_coef": round(lw["coef"], 5),
                "se": round(lw["se"], 5),
                "walk_pct": round((math.exp(lw["coef"]) - 1) * 100, 2),
                "r2": r["summary"]["r2"],
                "significant": bool(lw["p"] < 0.05),
            }
        )

    # 도보 1분과 전철 1분의 가치 비. **스플라인 기저계수가 아니라 선형 W 계수**를
    # 써야 한다. 스플라인의 첫 열은 비선형항과 짝을 이뤄야 의미가 생기므로 단독으로
    # '1분당 기울기'가 아니다 — 실데이터에서 그 값이 +0.0008 이라 비율이 -0.1분이라는
    # 헛소리가 나왔다.
    gangnam = next((t for t in main["terms"] if t["name"] == "gangnam_min"), None)
    walk_coef = main["linear_walk"]["coef"]
    ratio = None
    if gangnam and gangnam["coef"] < 0 and walk_coef < 0:
        v = walk_coef / gangnam["coef"]
        ratio = {
            "value": round(v, 3),
            "label": f"도보 1분 ≈ 전철 {v:.1f}분",
            "note": "둘 다 음수일 때만 의미가 있다. 선형 W 계수 기준.",
        }

    out = {
        "spec": chosen.key,
        "spec_label": chosen.label,
        "dep_var": "log(전용면적 기준 평당가)",
        "n_obs": stage1["n_obs"],
        "n_complexes": stage1["n_complexes"],
        "excluded_small_complexes": int(df.attrs.get("dropped_small_complexes", 0)),
        "excluded_note": (
            f"전용 {MIN_MAX_AREA_M2:.0f}㎡ 이상 주택이 없는 단지는 제외했습니다. "
            "국토부 아파트 실거래가에 섞여 들어오는 원룸형 도시형생활주택으로, "
            "84㎡ 기준 환산이 성립하지 않습니다."
        ),
        "knots": {
            var: ([round(k, 2) for k in ks] if ks else None) for var, ks in knots.items()
        },
        "n_knots": nk,
        # 요인별 실제 분포. 화면의 곡선 범위를 코드에 박지 않고 여기서 가져간다 —
        # 지역을 넓히면 분포가 통째로 달라지는데(강남 30~65분 → 23~78분) 박아 두면
        # 곡선이 데이터 없는 구간까지 그려지거나 있는 구간을 잘라 먹는다.
        "var_range": _var_ranges(df, alpha),
        # 도보 곡선을 그리는 쪽이 기대하는 이름. 다른 요인은 factors 엔드포인트가 쓴다.
        "walk_knots": (
            [round(k, 2) for k in knots["walk_min"]] if knots.get("walk_min") else None
        ),
        **main["summary"],
        "terms": main["terms"],
        "stage1": stage1,
        "curves": {"walk_minutes": main["curve"]},
        "within_walk": stage1.get("within_walk"),
        "dong_premium": stage1.get("dong_premium"),
        # stage1 안에 두면 API 직렬화를 탄다. (단지,동) 튜플 키라 JSON 으로 못 나간다.
        "dong_effects": stage1.pop("_dong_effects", None) or {},
        "linearity": main["linearity"],
        "spline_terms": main["spline_terms"],
        "linear_walk": {
            "coef": round(main["linear_walk"]["coef"], 6),
            "se": round(main["linear_walk"]["se"], 6),
            "t": round(main["linear_walk"]["t"], 3),
            "p": round(main["linear_walk"]["p"], 5),
            "pct": round((math.exp(main["linear_walk"]["coef"]) - 1) * 100, 3),
            "note": "지수감쇠 exp(-λW) 가정. 시드 참값 복원 검증의 판정 기준.",
        },
        "walk_vs_ride_ratio": ratio,
        "spec_ladder": ladder,
        "diagnostics": {"vif": _vif(main["X"])},
        "residuals": main["residuals"],
        "alpha": alpha,
    }

    warnings = []
    for v in out["diagnostics"]["vif"]:
        # 스플라인·다항 동반항의 높은 VIF는 설계상 당연한 것이라 경고하지 않는다.
        if v["vif"] > 10 and not _is_structural(v["name"]):
            warnings.append(
                f"{_label(v['name'])}의 VIF가 {v['vif']}로 높습니다. 계수 해석에 주의하세요."
            )
    if chosen.use_umd_fe:
        warnings.append(
            "법정동 고정효과를 넣으면 계수는 '같은 동 안에서 역에 더 가까운 단지'만 "
            "비교해 나온 값이 됩니다. 동 단위 어메니티(학군·상권) 교란은 사라지지만, "
            "표본이 적은 동에서는 추정이 불안정해집니다. M2와 함께 보세요."
        )
    out["diagnostics"]["warnings"] = warnings
    return out
