from datetime import date, datetime

from sqlalchemy import (
    Date,
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
    # 동은 적정가를 바꾼다(역거리 + 동 프리미엄). 저장해 두지 않으면 나중에 다시
    # 계산할 때 단지 중심점 기준으로 떨어져 저장 시점과 다른 값이 나온다.
    dong: Mapped[str | None] = mapped_column(String(20))
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

    # 매물에 적힌 확인일자. 우리가 언제 봤는지(`first_seen_at`)와 다르다 — 한 번에
    # 붙여넣은 매물은 목격 시각이 전부 같지만 확인일자는 제각각이다.
    confirmed_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    seen_count: Mapped[int] = mapped_column(Integer, default=1)


class RebStat(Base):
    """한국부동산원 공표 통계 — 시군구·월 단위.

    ## 왜 우리 DB 에 넣나

    KB부동산 데이터허브에서 경기 남부 17개 시군구를 모아 보려다 막혔다. 시군구
    선택은 되는데 차트가 5개까지만 그려지고, 무엇보다 **선택이 URL 에도 공유링크에도
    남지 않아** 열 때마다 17번을 다시 클릭해야 했다. 그래서 공표 통계를 직접 받아
    한 화면에 놓는다.

    ## 한 행의 뜻

    (시군구, 지표, 월) 하나에 값 하나. 지표는 `reb.TABLES` 의 이름을 쓴다
    (sale_index, jeonse_index, jeonse_ratio, avg_sale_price, avg_unit_price,
    med_sale_price).

    지표를 세로로 쌓는(long) 구조인 이유: 한국부동산원이 표를 늘리면 컬럼이 아니라
    행만 늘어난다. 가로로(wide) 두면 표가 추가될 때마다 마이그레이션이 필요하다.

    ## 유니크 키에 NULL 을 두지 않는다

    SQLite 의 UNIQUE 는 NULL 끼리를 서로 다른 값으로 보므로, 키에 들어가는 세 컬럼은
    전부 NOT NULL 이다. 값이 없으면 행을 만들지 않는다 — 0 으로 채우면 '그 달에
    지수가 0' 이라는 거짓이 된다.
    """

    __tablename__ = "reb_stats"
    __table_args__ = (
        UniqueConstraint("sgg_cd", "metric", "ym", name="uq_reb_stat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sgg_cd: Mapped[str] = mapped_column(String(5), index=True)
    metric: Mapped[str] = mapped_column(String(32), index=True)
    ym: Mapped[str] = mapped_column(String(6), index=True)  # "YYYYMM"
    value: Mapped[float] = mapped_column(Float)

    # 받은 그대로의 지역 경로(경기>경부2권>수원시>영통구). 나중에 코드가 낡아
    # 엉뚱한 지역이 들어왔는지 **사후에도** 확인할 수 있게 남긴다.
    region_name: Mapped[str] = mapped_column(String(60), default="")

    # 한국부동산원이 붙여 주는 단위(UI_NM). '지수' / '%' / '천원' / '천원/㎡'.
    #
    # 값을 우리 단위(만원)로 바꿔서 저장하지 않는다. 받은 숫자를 그대로 두고 단위를
    # 같이 적는 쪽이 안전하다 — 처음에 천원을 만원으로 읽어 평당 2.2억이라는 값을
    # 만들 뻔했다. 공표값과 저장값이 같아야 나중에 대조할 수 있다.
    # 화면에 쓸 때 `services/macro.py` 가 한 곳에서 환산한다.
    unit: Mapped[str] = mapped_column(String(16), default="")

    # 공표 기준시점 문구(RPSTUI_NM). 지수에만 있다 — '기준시점 : 2026.06.=100.0'.
    #
    # 코드에 "2026년 1월 = 100" 이라고 박았다가 틀렸다. 한국부동산원은 주기적으로
    # 기준을 옮기므로(리베이스) 기억으로 적으면 언젠가 거짓이 된다. 받아서 저장하면
    # 리베이스될 때 다음 적재에서 저절로 따라간다.
    base: Mapped[str] = mapped_column(String(40), default="")

    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
