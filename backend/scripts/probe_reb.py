"""한국부동산원(R-ONE) 연결과 지역코드 대조를 확인한다.

## 왜 따로 있나

`reb.CLS_IDS` 는 R-ONE 포털의 분류코드 조회 화면에서 받아 법정동코드로 우리
`molit.DISTRICTS` 와 대조해 적은 표다. 그 대조는 적을 때 한 번 한 것이고,
**행정구역은 바뀐다.** 화성시가 분구되면서 41590 이 죽고 4159X 가 생겼을 때 우리는
오류가 아니라 실거래 0건을 받았다. 같은 일이 여기서 일어나면 지수가 0건이 되거나
더 나쁘게는 **남의 지역 값**이 조용히 들어온다.

그래서 이 스크립트가 매번 다시 검사한다. 사람이 발견하기를 기다리는 구조를
만들지 않는다.

## 키 없이도 돈다

R-ONE 은 인증키가 없으면 샘플 모드로 응답한다 — 어떤 요청이든 **5행 고정**이고
`pIndex`·`pSize` 가 무시된다(재서 확인했다). 적재는 못 하지만 **응답 구조와 지역
대조는 그대로 검증된다.** 그래서 키를 받기 전에도 이 스크립트로 준비를 끝낼 수 있다.

## 사용

    python -m scripts.probe_reb
    python -m scripts.probe_reb --table A_2024_00072   # 전세가율만
"""

from __future__ import annotations

import argparse
import sys
import time

from app.clients import reb
from app.clients.molit import DISTRICTS


def main() -> int:
    ap = argparse.ArgumentParser(description="R-ONE 연결·지역코드 대조 확인")
    ap.add_argument("--table", default="A_2024_00045", help="통계표 코드")
    ap.add_argument("--start", default=None, help="시작 YYYYMM")
    ap.add_argument("--end", default=None, help="끝 YYYYMM")
    args = ap.parse_args()

    keyed = reb.available()
    print(f"인증키: {'있음' if keyed else '없음 (샘플 모드 — 5행 고정)'}")
    print(f"통계표: {args.table} ({reb.TABLES.get(args.table, '이름 미등록')})")
    print()

    # 1) 이 표의 분류에서 우리 17개를 다 찾았나.
    #    지역코드는 표마다 다르므로 박아 두지 않고 매번 경로로 찾는다.
    try:
        cls = reb.district_cls_ids(args.table)
    except reb.RebError as exc:
        print(f"[X] 지역코드 조회 실패: {exc}")
        return 1

    missing = [c for c in DISTRICTS if c not in cls]
    if missing:
        print(f"[X] 이 표에서 못 찾은 시군구: {[(c, DISTRICTS[c]) for c in missing]}")
    else:
        print(f"[O] 시군구 {len(DISTRICTS)}개를 {args.table} 의 분류에서 모두 찾았습니다.")
    extra: list[str] = []
    print()

    # 2) 실제로 받아 보고, 받은 값이 그 지역 것인지 경로로 검산
    ok, bad, empty = 0, 0, 0
    for sgg, name in DISTRICTS.items():
        try:
            pts = reb.fetch_district(args.table, sgg, start_ym=args.start, end_ym=args.end)
        except reb.RebError as exc:
            print(f"  [X] {name:<14} {exc}")
            bad += 1
            continue

        if not pts:
            # 빈 결과는 조용하다. 성공으로 넘기지 않는다.
            print(f"  [!] {name:<14} 0건 — 코드가 낡았거나 공표가 없는 지역입니다.")
            empty += 1
            continue

        first, last = pts[0], pts[-1]
        print(
            f"  [O] {name:<14} {len(pts):>4}건  "
            f"{first.ym}~{last.ym}  최근 {last.value:,.2f}  ({last.region_name})"
        )
        ok += 1
        time.sleep(0.1)  # 공공 API 에 몰아치지 않는다

    print()
    print(f"성공 {ok} · 실패 {bad} · 빈 결과 {empty}")
    if not keyed:
        print()
        print("샘플 모드라 지역당 5건만 돌아옵니다. 실제 적재는 REB_SERVICE_KEY 가 필요합니다.")
        print("  https://www.data.go.kr/data/15134761/openapi.do  (활용신청 -> 제공처)")
        print("  https://www.reb.or.kr/r-one  (로그인 > Open API > 인증키 발급내역)")

    return 1 if (bad or empty or missing or extra) else 0


if __name__ == "__main__":
    sys.exit(main())
