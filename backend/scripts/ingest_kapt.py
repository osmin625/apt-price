"""K-apt 에서 단지 세대수·동수를 받아 기존 단지에 붙인다.

사용법:
    python -m scripts.ingest_kapt --check       # 활용신청 여부만 확인
    python -m scripts.ingest_kapt               # 수원시 4개 구 전체
    python -m scripts.ingest_kapt --district 41117

세대수는 국토부 실거래가 API 에 없어서 별도로 받아야 한다. 대단지 프리미엄은
커뮤니티 시설·관리비 규모의 경제·거래 유동성·학군 형성까지 딸려 오는 큰 설명변수다.

data.go.kr 은 계정당 인증키가 하나이므로 **기존 MOLIT 키를 그대로 쓴다.**
다만 아래 두 서비스에 활용신청이 따로 필요하다(자동승인).

  공동주택 단지 목록제공 서비스  https://www.data.go.kr/data/15057332/openapi.do
  공동주택 기본 정보제공 서비스  https://www.data.go.kr/data/15058453/openapi.do

단지 매칭은 실거래가 적재와 같은 `pricing.name_key` 정규화를 쓴다. 이름이
정확히 맞는 것만 붙이고, 애매한 것은 합치지 않고 보고만 한다 — 잘못 붙이면
엉뚱한 단지의 세대수가 들어가 모델이 조용히 틀어진다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import pricing  # noqa: E402
from app.clients.kapt import KaptError, KaptNotSubscribed, basis_info, list_complexes  # noqa: E402
from app.clients.molit import SUWON_DISTRICTS  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Complex  # noqa: E402


def check() -> int:
    print("K-apt 활용신청 상태 확인")
    for label, fn in [
        ("단지 목록 서비스", lambda: list_complexes("41117", rows=1)),
        ("기본 정보 서비스", lambda: basis_info("A13880303")),
    ]:
        try:
            fn()
            print(f"  [O] {label} — 사용 가능")
        except KaptNotSubscribed as exc:
            print(f"  [X] {label} — {exc}")
        except KaptError as exc:
            print(f"  [!] {label} — {exc}")
        except Exception as exc:
            print(f"  [!] {label} — {type(exc).__name__}: {exc}")
    return 0


def candidate_keys(name: str, umd: str | None) -> list[str]:
    """K-apt 단지명에서 만들어 볼 정규화 키 후보들.

    K-apt 이름에는 국토부에 없는 **지역 접두어**가 붙는다.
      '정자동 송학아파트' vs '송학',  '파장현대아파트' vs '현대'(파장동)
    국토부는 법정동을 별도 필드로 갖고 있어 이름에 넣지 않기 때문이다.

    법정동 이름(과 '동'을 뗀 형태)만 접두어로 벗긴다. '수원'·'북수원' 같은 것까지
    벗기면 '동수원자이1차' 처럼 지역명이 단지명의 일부인 경우를 망가뜨린다.
    """
    keys = [pricing.name_key(name)]
    if umd:
        for prefix in (pricing.name_key(umd), pricing.name_key(umd.removesuffix("동"))):
            if prefix and keys[0].startswith(prefix) and len(keys[0]) > len(prefix) + 1:
                keys.append(keys[0][len(prefix):])
    return keys


def year_ok(a: int | None, b: int | None) -> bool:
    """준공년도 교차검증. 둘 다 알면 1년 이내여야 한다.

    이름만으로 붙이면 엉뚱한 단지가 섞인다(앞서 실거래가 적재에서 유사도 매칭이
    10건 전부 오답이었다). K-apt 와 국토부가 독립적으로 보고한 준공년도가
    일치하는지를 추가 근거로 쓴다.
    """
    if a is None or b is None:
        return True
    return abs(a - b) <= 1


def run(districts: list[str], sleep: float) -> int:
    with SessionLocal() as db:
        by_key: dict[tuple[str, str], Complex] = {}
        suffix_index: dict[str, list[Complex]] = {}
        for cx in db.execute(select(Complex)).scalars().all():
            if cx.name_key:
                by_key[(cx.sgg_cd, cx.name_key)] = cx
                suffix_index.setdefault(cx.sgg_cd, []).append(cx)

        matched = missed = 0
        unmatched_names: list[str] = []
        rejected: list[tuple] = []

        for sgg in districts:
            page = 1
            while True:
                try:
                    items, last = list_complexes(sgg, page=page)
                except KaptNotSubscribed as exc:
                    print(f"\n{exc}")
                    return 1
                except KaptError as exc:
                    print(f"  [{sgg} p{page}] {exc}")
                    break

                for it in items:
                    code = str(it.get("kaptCode") or "").strip()
                    name = str(it.get("kaptName") or "").strip()
                    if not code or not name:
                        continue

                    umd = str(it.get("as3") or "").strip() or None
                    keys = candidate_keys(name, umd)
                    cx = next((by_key[(sgg, k)] for k in keys if (sgg, k) in by_key), None)

                    if cx is None:
                        # 접두어를 벗겨도 안 맞으면, 한쪽이 다른 쪽의 접미사인 경우를
                        # 마지막으로 본다. 단, **유일해야** 하고 준공년도가 맞아야 한다.
                        # 후보가 둘 이상이면 포기한다 — 잘못 붙이면 엉뚱한 단지의
                        # 세대수가 들어가 모델이 조용히 틀어진다.
                        k0 = keys[0]
                        hits = [
                            c
                            for c in suffix_index.get(sgg, [])
                            if c.umd_nm == umd
                            and len(c.name_key) >= 3
                            and (k0.endswith(c.name_key) or c.name_key.endswith(k0))
                        ]
                        if len(hits) == 1:
                            cx = hits[0]

                    if cx is None:
                        missed += 1
                        unmatched_names.append(name)
                        continue

                    try:
                        info = basis_info(code)
                    except KaptError as exc:
                        print(f"  [{name}] 기본정보 실패: {exc}")
                        continue
                    time.sleep(sleep)
                    if info is None:
                        continue
                    if not year_ok(info.build_year, cx.build_year):
                        rejected.append(
                            (name, cx.name, info.build_year, cx.build_year)
                        )
                        continue
                    cx.kapt_code = info.kapt_code
                    cx.household_count = info.household_count
                    cx.dong_count = info.dong_count
                    cx.apt_type = info.apt_type
                    if info.build_year and not cx.build_year:
                        cx.build_year = info.build_year
                    matched += 1

                db.commit()
                print(f"  [{SUWON_DISTRICTS.get(sgg, sgg)} p{page}] {len(items)}곳 처리 "
                      f"(누적 매칭 {matched})")
                if last or not items:
                    break
                page += 1
                time.sleep(sleep)

        have = sum(
            1
            for c in db.execute(select(Complex)).scalars().all()
            if c.household_count
        )
        print(f"\n세대수 확보 {have}곳 / 이번 실행 매칭 {matched}곳 / K-apt 에만 있는 단지 {missed}곳")
        if unmatched_names:
            print("  우리 DB 에 없는 K-apt 단지 예시:")
            for n in unmatched_names[:8]:
                print(f"    {n}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="활용신청 여부만 확인")
    parser.add_argument("--district", action="append")
    parser.add_argument("--sleep", type=float, default=0.12)
    args = parser.parse_args()
    if args.check:
        sys.exit(check())
    sys.exit(run(args.district or list(SUWON_DISTRICTS), args.sleep))
