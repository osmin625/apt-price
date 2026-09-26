"""국토교통부 실거래가를 내려받아 DB에 적재한다.

사용법:
    python -m scripts.ingest_trades --months 24
    python -m scripts.ingest_trades --months 12 --district 41117
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app import pricing  # noqa: E402
from app.clients.molit import SUWON_DISTRICTS, MolitError, RawTrade, fetch_month  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base, Complex, Trade  # noqa: E402


def month_range(months: int) -> list[str]:
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(months):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


# 합치는 기준이 아니라 '사람이 봐야 할 만큼 비슷한' 기준.
NEAR_MISS_THRESHOLD = 0.85


def get_or_create_complex(
    db: Session, raw: RawTrade, cache: dict, fuzzy_log: list
) -> Complex:
    """단지 3단계 매칭.

    카카오 POI 와 국토부 실거래가는 같은 단지를 다르게 적는다
    ('래미안영통마크원2단지' vs '래미안 영통 마크원 2단지'). 완전일치로만 찾으면
    국토부가 **고아 중복 단지**를 만들고, 좌표·도보경로를 채워 둔 행에는 거래가
    하나도 붙지 않는다.

      1) 완전일치 (sgg, umd, name)      — 기존 동작 보존
      2) 정규화 키 일치 (name_key)       — 공백/'아파트' 접미/'제1단지' 변형 흡수

    ## 유사도 매칭은 쓰지 않는다 — 실측으로 폐기했다

    처음엔 3단계로 difflib 유사도 0.85 이상이면 같은 단지로 합쳤다. 수원 24개월
    실데이터로 돌려 보니 **발동한 10건이 전부 오답**이었다.

        영통아이파크캐슬3단지 -> 영통아이파크캐슬1단지 (0.909)
        꽃뫼양지마을현대     -> 꽃뫼양지마을대우    (0.875)  ← 시공사가 다름
        가림26차나동        -> 가림26차가동       (0.857)  ← 동이 다름

    이유는 단순하다. 한국 아파트 이름은 길고, 단지를 가르는 정보(숫자·동·시공사)가
    짧은 접미사라 유사도가 거의 안 떨어진다. 반대로 **정당한 표기 차이는 name_key
    정규화만으로 전부 1.000 으로 일치**한다. 즉 유사도 단계는 정답을 하나도 더
    잡지 못하면서 오답만 만들었다.

    그래서 합치지 않고 **근접 후보를 출력만** 한다. 잘못 합치면 남의 거래가 섞여
    시세가 통째로 망가지지만, 안 합치면 단지가 하나 더 생길 뿐이다.
    """
    key = (raw.sgg_cd, raw.umd_nm, raw.apt_nm)
    if key in cache:
        return cache[key]

    nkey = pricing.name_key(raw.apt_nm)

    cx = db.execute(
        select(Complex).where(
            Complex.sgg_cd == raw.sgg_cd,
            Complex.umd_nm == raw.umd_nm,
            Complex.name == raw.apt_nm,
        )
    ).scalar_one_or_none()

    if cx is None:
        cx = db.execute(
            select(Complex).where(
                Complex.sgg_cd == raw.sgg_cd,
                Complex.umd_nm == raw.umd_nm,
                Complex.name_key == nkey,
            )
        ).scalar_one_or_none()

    if cx is None:
        # 합치지는 않고 근접 후보만 기록한다. 사람이 보고 판단할 몫이다.
        candidates = db.execute(
            select(Complex).where(
                Complex.sgg_cd == raw.sgg_cd, Complex.umd_nm == raw.umd_nm
            )
        ).scalars().all()
        best, score = None, 0.0
        for c in candidates:
            r = SequenceMatcher(None, nkey, c.name_key or "").ratio()
            if r > score:
                best, score = c, r
        if best is not None and score >= NEAR_MISS_THRESHOLD:
            fuzzy_log.append((raw.apt_nm, best.name, round(score, 3)))

    if cx is None:
        cx = Complex(
            name=raw.apt_nm,
            name_key=nkey,
            sgg_cd=raw.sgg_cd,
            sgg_name=SUWON_DISTRICTS.get(raw.sgg_cd, ""),
            umd_nm=raw.umd_nm,
            jibun=raw.jibun,
            build_year=raw.build_year,
            source="molit",
        )
        db.add(cx)
        db.flush()
    elif not cx.name_key:
        cx.name_key = nkey

    cache[key] = cx
    return cx


def ingest(
    months: int,
    districts: list[str],
    sleep: float,
    keep_seed: bool,
    refetch_recent: int = 3,
    refetch_all: bool = False,
) -> None:
    Base.metadata.create_all(engine)
    months_list = month_range(months)

    with SessionLocal() as db:
        cache: dict = {}
        fuzzy_log: list = []
        # uq_trade 와 같은 자연키. DB 조회만으로는 **같은 배치 안의** 중복을 못 잡는다
        # (아직 flush 전이라 select 에 안 보인다). 국토부 응답에는 같은 날·같은 면적·
        # 같은 층·같은 금액 거래가 실제로 들어온다(동이 다른 경우).
        seen: set = set()
        inserted = skipped = failed_months = 0

        # 이미 적재된 (구, 월) 조합. 같은 달을 매번 다시 내려받지 않기 위한 캐시.
        done = {
            (sgg, ym.replace("-", ""))
            for sgg, ym in db.execute(
                select(Complex.sgg_cd, Trade.deal_ym)
                .join(Complex, Complex.id == Trade.complex_id)
                .distinct()
            ).all()
        }
        recent = set(months_list[-refetch_recent:]) if refetch_recent > 0 else set()
        reused_months = 0

        for lawd in districts:
            for ym in months_list:
                # 최근 몇 달은 항상 다시 받는다. 실거래 신고 기한이 계약 후 30일이라
                # 지난달 데이터도 계속 늘어나기 때문이다. 그보다 오래된 달은 확정본이다.
                if (lawd, ym) in done and ym not in recent and not refetch_all:
                    reused_months += 1
                    continue
                try:
                    rows = fetch_month(lawd, ym)
                except MolitError as exc:
                    print(f"  [{SUWON_DISTRICTS.get(lawd, lawd)} {ym}] 실패: {exc}")
                    continue

                for raw in rows:
                    cx = get_or_create_complex(db, raw, cache, fuzzy_log)
                    deal_date = date(raw.deal_year, raw.deal_month, raw.deal_day)

                    nat_key = (
                        cx.id, deal_date, raw.exclusive_area, raw.floor, raw.deal_amount
                    )
                    if nat_key in seen:
                        skipped += 1
                        continue

                    exists = db.execute(
                        select(Trade.id).where(
                            Trade.complex_id == cx.id,
                            Trade.deal_date == deal_date,
                            Trade.exclusive_area == raw.exclusive_area,
                            Trade.floor == raw.floor,
                            Trade.deal_amount == raw.deal_amount,
                        )
                    ).first()
                    if exists:
                        seen.add(nat_key)
                        skipped += 1
                        continue
                    seen.add(nat_key)

                    db.add(
                        Trade(
                            complex_id=cx.id,
                            deal_date=deal_date,
                            deal_ym=f"{raw.deal_year:04d}-{raw.deal_month:02d}",
                            exclusive_area=raw.exclusive_area,
                            floor=raw.floor,
                            deal_amount=raw.deal_amount,
                            build_year=raw.build_year,
                            apt_dong=raw.apt_dong,
                            source="molit",
                        )
                    )
                    inserted += 1

                # 한 달치가 실패해도 24개월 × 4개 구 작업 전체를 버리지 않는다.
                try:
                    db.commit()
                    print(f"  [{SUWON_DISTRICTS.get(lawd, lawd)} {ym}] {len(rows)}건 처리")
                except IntegrityError as exc:
                    db.rollback()
                    cache.clear()  # 롤백으로 떨어져 나간 Complex 객체를 버린다
                    failed_months += 1
                    print(f"  [{SUWON_DISTRICTS.get(lawd, lawd)} {ym}] 커밋 실패, 건너뜀: "
                          f"{str(exc.orig)[:90]}")
                time.sleep(sleep)

        refresh_complex_stats(db)
        tail = f" / 커밋 실패한 달 {failed_months}개" if failed_months else ""
        print(f"\n적재 완료: 신규 {inserted}건 / 중복 {skipped}건{tail}")

        if fuzzy_log:
            print(f"\n이름이 비슷하지만 **합치지 않은** 단지 {len(fuzzy_log)}건 (참고용)")
            print("  국토부가 별개 단지로 보고한 것들이다. 같은 단지로 합쳐야 한다면 직접 확인할 것.")
            for molit_name, existing, score in fuzzy_log[:20]:
                print(f"  {molit_name:28} ~ {existing:28} ({score})")
            if len(fuzzy_log) > 20:
                print(f"  ... 외 {len(fuzzy_log) - 20}건")

        # 합성 가격과 실거래가가 한 DB에 섞이면 모든 분석이 무의미해진다.
        # 실거래가 들어왔으면 시드 거래는 치우는 것이 기본값이다.
        seed_count = db.scalar(
            select(func.count()).select_from(Trade).where(Trade.source == "seed")
        ) or 0
        molit_count = db.scalar(
            select(func.count()).select_from(Trade).where(Trade.source == "molit")
        ) or 0

        if seed_count and molit_count:
            if keep_seed:
                print(f"\n[!] 합성 거래 {seed_count}건이 실거래 {molit_count}건과 섞여 있습니다.")
                print("    --keep-seed 로 남겨 두었지만, 분석 결과는 신뢰할 수 없습니다.")
            else:
                db.query(Trade).filter(Trade.source == "seed").delete()
                db.commit()
                print(f"\n합성 거래 {seed_count}건 삭제 (실거래 {molit_count}건으로 대체)")
                print("    남겨 두려면 --keep-seed 를 쓰세요.")
            refresh_complex_stats(db)


def refresh_complex_stats(db: Session) -> None:
    """관측된 최고 거래층을 단지 최고층 추정치로, 최빈 건축년도를 준공년도로 갱신."""
    rows = db.execute(
        select(Trade.complex_id, func.max(Trade.floor), func.max(Trade.build_year))
        .group_by(Trade.complex_id)
    ).all()
    for complex_id, max_floor, build_year in rows:
        cx = db.get(Complex, complex_id)
        if cx:
            cx.max_floor = max_floor
            cx.build_year = cx.build_year or build_year
    db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=24, help="최근 N개월")
    parser.add_argument("--district", action="append", help="법정동 시군구 코드 (반복 가능)")
    parser.add_argument("--sleep", type=float, default=0.3, help="요청 간 대기(초)")
    parser.add_argument(
        "--keep-seed",
        action="store_true",
        help="합성 거래를 지우지 않는다 (실거래와 섞이므로 분석 결과는 무의미)",
    )
    parser.add_argument(
        "--refetch-recent",
        type=int,
        default=3,
        help="최근 N개월은 이미 받았어도 다시 조회 (신고 기한 30일이라 계속 늘어남)",
    )
    parser.add_argument("--refetch-all", action="store_true", help="모든 달을 다시 조회")
    args = parser.parse_args()

    ingest(
        args.months,
        args.district or list(SUWON_DISTRICTS),
        args.sleep,
        args.keep_seed,
        args.refetch_recent,
        args.refetch_all,
    )
