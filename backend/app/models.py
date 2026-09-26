from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Complex(Base):
    """아파트 단지."""

    __tablename__ = "complexes"
    # 단지명 완전일치가 아니라 정규화 키로 묶는다. 카카오 POI와 국토부 실거래가의
    # 표기가 달라(공백·'아파트' 접미·'제1단지') 완전일치로는 같은 단지가 갈라진다.
    __table_args__ = (UniqueConstraint("sgg_cd", "umd_nm", "name_key", name="uq_complex"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    name_key: Mapped[str] = mapped_column(String(120), index=True, default="")
    sgg_cd: Mapped[str] = mapped_column(String(10), index=True)  # 법정동 시군구코드
    sgg_name: Mapped[str] = mapped_column(String(40), default="")
    umd_nm: Mapped[str] = mapped_column(String(40), default="")  # 법정동
    jibun: Mapped[str | None] = mapped_column(String(40))
    road_address: Mapped[str | None] = mapped_column(String(200))

    build_year: Mapped[int | None] = mapped_column(Integer)
    max_floor: Mapped[int | None] = mapped_column(Integer)  # 관측된 최고 거래층 = 최고층 추정

    # 단지 규모. 국토부 실거래가 API 에는 없어서 K-apt(공동주택관리정보시스템)에서 받는다.
    # 대단지 프리미엄은 한국 아파트 가격의 큰 설명변수다 — 커뮤니티 시설, 관리비 규모의
    # 경제, 거래 유동성, 학군 형성까지 세대수에 딸려 온다.
    household_count: Mapped[int | None] = mapped_column(Integer)
    dong_count: Mapped[int | None] = mapped_column(Integer)
    kapt_code: Mapped[str | None] = mapped_column(String(20), index=True)
    # K-apt 의 codeAptNm — '아파트' / '도시형생활주택' / '주상복합' 등.
    # 국토부 실거래가에는 이 구분이 없어 전용면적으로 추정했는데, 실제 값이 있으면
    # 그걸 쓴다(hedonic.MIN_MAX_AREA_M2 휴리스틱보다 정확하다).
    apt_type: Mapped[str | None] = mapped_column(String(40), index=True)

    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geocoded_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 'kakao' = POI 수집, 'molit' = 실거래가 적재 중 생성, 'seed' = 데모 시드
    source: Mapped[str] = mapped_column(String(20), default="seed", index=True)
    kakao_place_id: Mapped[str | None] = mapped_column(String(32), index=True)

    # 직선거리 기반 레거시 필드 — 기존 3개 탭이 의존하므로 의미를 바꾸지 않는다.
    station_name: Mapped[str | None] = mapped_column(String(60))
    station_line: Mapped[str | None] = mapped_column(String(60))
    station_distance_m: Mapped[float | None] = mapped_column(Float)

    # 도보 실거리 기반 — complex_stations에서 비정규화. 지도·모델이 조인 없이 읽는다.
    nearest_station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"))
    walk_distance_m: Mapped[float | None] = mapped_column(Float)
    walk_seconds: Mapped[int | None] = mapped_column(Integer)
    best_access_station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"))
    total_access_min: Mapped[float | None] = mapped_column(Float)

    trades: Mapped[list["Trade"]] = relationship(back_populates="complex")
    nearest_station: Mapped["Station | None"] = relationship(
        foreign_keys=[nearest_station_id]
    )
    best_access_station: Mapped["Station | None"] = relationship(
        foreign_keys=[best_access_station_id]
    )


class Station(Base):
    """지하철역. 강남 접근성 계산의 기준점."""

    __tablename__ = "stations"
    __table_args__ = (UniqueConstraint("name", "line", name="uq_station"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    line: Mapped[str] = mapped_column(String(40))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)

    # 강남역 도착 기준 전철 소요시간(분). 수기 관리 — 시드 참값이 여기 의존하므로
    # 실행 때마다 값이 흔들리면 복원 검증이 불안정해진다.
    minutes_to_gangnam: Mapped[int | None] = mapped_column(Integer)
    transfers_to_gangnam: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="curated")


class ComplexDong(Base):
    """단지 안의 개별 동(101동, 나동, A동…)과 그 동의 좌표·역거리.

    같은 단지라도 동에 따라 역까지 거리가 100~330m 차이난다. 단지 중심점 하나로는
    이 차이가 통째로 사라지는데, 이건 단순한 정밀도 문제가 아니다 — **같은 단지
    안에서의 비교**는 학군·브랜드·관리상태·조망이 자동으로 통제되는, 이 데이터에서
    얻을 수 있는 가장 깨끗한 식별이다.

    국토부는 소유권 이전등기가 끝난 거래에만 동을 공개하므로 84% 정도만 채워진다.
    카카오 동 단위 좌표 조회 성공률은 표본 기준 87%다.
    """

    __tablename__ = "complex_dongs"
    __table_args__ = (UniqueConstraint("complex_id", "dong", name="uq_complex_dong"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complexes.id"), index=True)
    dong: Mapped[str] = mapped_column(String(20), index=True)

    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geocoded_at: Mapped[datetime | None] = mapped_column(DateTime)
    # 카카오가 돌려준 이름. 엉뚱한 곳을 잡지 않았는지 사람이 확인할 근거로 남긴다.
    matched_name: Mapped[str | None] = mapped_column(String(120))

    station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"))
    straight_distance_m: Mapped[float | None] = mapped_column(Float)
    walk_distance_m: Mapped[float | None] = mapped_column(Float)
    walk_seconds: Mapped[int | None] = mapped_column(Integer)
    walk_source: Mapped[str] = mapped_column(String(20), default="estimate")

    complex: Mapped[Complex] = relationship()
    station: Mapped["Station | None"] = relationship()


class ComplexStation(Base):
    """단지↔역 쌍의 도보 경로. 최근접역만이 아니라 N개 후보를 저장한다.

    먼 신분당선 역이 가까운 수인분당선 역보다 강남 접근성이 좋은 경우가 있어,
    도보시간 argmin과 접근성 argmin이 서로 다른 역을 가리킨다.
    """

    __tablename__ = "complex_stations"
    __table_args__ = (
        UniqueConstraint("complex_id", "station_id", name="uq_cx_station"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complexes.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)

    straight_distance_m: Mapped[float] = mapped_column(Float)  # 하버사인, 항상 채움
    walk_distance_m: Mapped[float | None] = mapped_column(Float)
    walk_seconds: Mapped[int | None] = mapped_column(Integer)
    walk_source: Mapped[str] = mapped_column(String(20), default="estimate")  # tmap|estimate
    path_geojson: Mapped[str | None] = mapped_column(Text)  # LineString — 지도 오버레이
    routed_at: Mapped[datetime | None] = mapped_column(DateTime)
    rank: Mapped[int] = mapped_column(Integer, default=0)  # 직선거리 순위(1 = 최근접)

    complex: Mapped[Complex] = relationship()
    station: Mapped[Station] = relationship()


class Trade(Base):
    """아파트 매매 실거래."""

    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint(
            "complex_id",
            "deal_date",
            "exclusive_area",
            "floor",
            "deal_amount",
            name="uq_trade",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complexes.id"), index=True)

    deal_date: Mapped[date] = mapped_column(Date, index=True)
    deal_ym: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM

    exclusive_area: Mapped[float] = mapped_column(Float)  # 전용면적 ㎡
    floor: Mapped[int | None] = mapped_column(Integer)
    deal_amount: Mapped[int] = mapped_column(Integer)  # 만원
    build_year: Mapped[int | None] = mapped_column(Integer)
    apt_dong: Mapped[str | None] = mapped_column(String(20))

    # 'seed' = 합성 거래, 'molit' = 실거래가. 둘이 한 DB에 공존할 수 있어야 한다.
    source: Mapped[str] = mapped_column(String(20), default="seed", index=True)

    complex: Mapped[Complex] = relationship(back_populates="trades")


class Listing(Base):
    """사용자가 직접 입력한 매물(호가). 실거래 기반 적정가와 비교하는 대상."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complexes.id"), index=True)

    label: Mapped[str] = mapped_column(String(120), default="")
    exclusive_area: Mapped[float] = mapped_column(Float)
    supply_area: Mapped[float | None] = mapped_column(Float)  # 참고용 — 전용률 표시에만 사용
    floor: Mapped[int | None] = mapped_column(Integer)
    asking_price: Mapped[int] = mapped_column(Integer)  # 만원
    memo: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    complex: Mapped[Complex] = relationship()


class Quote(Base):
    """붙여넣은 매물의 **호가 기록**. 실거래가 못 잡는 것을 잡으려고 쌓는다.

    ## 왜 필요한가

    안 팔리는 물건의 가격은 실거래에 안 남는다. 값을 못 받는 매도자는 싸게 파는 대신
    거둬들이기 때문에, 유동성이 낮은 동의 관측 거래가는 **위로 편향**된다. 실제로
    수원센트럴아이파크자이 130동은 129동과 구조가 같은데도 같은 기간 거래가 3건 대 42건
    이고, 그 3건은 129동보다 오히려 비싸게 찍혔다. 내려간 물건은 거래가 아니라
    **호가에만** 있다.

    그래서 사용자가 매물을 붙여넣을 때마다 호가를 남긴다. 실거래를 대체하지 않고,
    거래가 뜸한 동의 선행지표로 나란히 쓴다.

    ## 중복 처리

    같은 (단지·동·평형·층·호가) 가 다시 들어오면 **새로 쌓지 않고** `last_seen_at`
    과 `seen_count` 만 올린다. 같은 매물을 여러 번 붙여넣어도 표본이 부풀지 않는다.
    반대로 **가격이 바뀌면 새 행**이 된다 — 그 변화가 바로 보고 싶은 신호다.

    층이나 동을 모르면 NULL 이 아니라 빈 값/0 을 쓴다. SQLite 의 UNIQUE 제약은
    NULL 끼리를 서로 다른 값으로 보기 때문에, NULL 을 두면 중복이 그대로 쌓인다.
    """

    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint(
            "complex_id", "dong", "area_key", "floor", "asking_price", name="uq_quote"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    complex_id: Mapped[int] = mapped_column(ForeignKey("complexes.id"), index=True)
    dong: Mapped[str] = mapped_column(String(20), default="", index=True)
    area_key: Mapped[int] = mapped_column(Integer, index=True)  # 전용면적 반올림(㎡)
    exclusive_area: Mapped[float] = mapped_column(Float)
    floor: Mapped[int] = mapped_column(Integer, default=0)  # 0 = 모름
    floor_band: Mapped[str] = mapped_column(String(20), default="정보없음")
    asking_price: Mapped[int] = mapped_column(Integer)  # 만원

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
