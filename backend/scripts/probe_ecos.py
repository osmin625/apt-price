"""한국은행 ECOS 통계표 코드가 아직 맞는지 목록과 대조한다.

## 왜 따로 있나

`ecos.TABLES` 의 (통계표, 항목) 코드는 ECOS 가 돌려주는 목록에서 골라 적은 것이다.
그 대조는 적을 때 한 번 한 것이고, **ECOS 는 개편 때 계열을 새 표로 옮긴다.** M2 가
그 예다 — 검색 결과에 나오는 `101Y003` 도 'M2' 라는 이름으로 지금도 목록에 있지만
항목 끝 시점이 200409 에서 멈춘 구지표다. 이름만 보면 맞아 보이므로, 옛 코드를 적어도
오류가 아니라 **오래된 값**이 조용히 들어온다.

그래서 세 가지를 본다.

1. 통계표가 `StatisticTableList` 에 실재하고 조회 가능한가(`SRCH_YN`)
2. 항목이 `StatisticItemList` 에 있고, 이름이 `EXPECT` 와 같고, 우리가 쓰는 주기가 있나
3. 그 주기의 끝 시점이 최근인가 — 끊긴 계열을 잡는다(위의 101Y003)

## 키 없이도 돈다

`sample` 키는 한 번에 10행이 상한이다(`ecos.SAMPLE_PAGE`). CPI 표(901Y009)는 항목 행이
1,743개라 전부 받으면 175번을 부른다. 그래서 항목 목록은 **찾는 항목을 지나면 멈춘다** —
목록이 항목코드별로 주기(A·D·M·Q)를 붙여 내려오므로, 찾은 뒤 다른 코드가 나오면 끝이다.
쓰는 항목은 전부 표의 첫 항목 근처라 키 없이도 몇 번이면 끝난다.

## 사용

    python -m scripts.probe_ecos
"""

from __future__ import annotations

import sys
import time
from datetime import date

from app.clients import ecos

# 항목 이름의 기대값. ECOS 의 ITEM_NAME 과 **글자 그대로** 비교한다.
#
# TABLES 와 따로 적는 이유: 코드가 맞는지를 코드로 확인하면 순환이다. 이름은 사람이
# 고를 때 본 것이라 독립된 근거가 된다. 지표를 더했는데 여기 안 적으면 [X] 로 걸린다 —
# 대조 없이 들어간 코드가 생기지 않게.
EXPECT: dict[str, str] = {
    "m2": "M2(평잔, 원계열)",
    "base_rate": "한국은행 기준금리",
    "cpi": "총지수",  # 901Y009 소비자물가지수(2020=100)
    "mortgage_rate": "주택담보대출",   # 121Y006 예금은행 대출금리(신규취급액)
    "jeonse_loan_rate": "전세자금대출",
    "deposit_rate": "정기예금",        # 121Y002 예금은행 수신금리(신규취급액)
}

# 월간 계열의 끝 시점이 이보다 오래되면 끊긴 것으로 본다. M2 는 두 달 남짓 늦게
# 나오므로(2026-10 에 202607 까지) 6개월이면 정상 지연과 겹치지 않는다. 구지표
# 101Y003 은 20년 넘게 멈춰 있어 여유가 크다.
STALE_MONTHS = 6


def _rows(service: str, path: str) -> tuple[list[dict], int]:
    """한 쪽. 없는 코드는 오류가 아니라 INFO-200 으로 오므로 빈 목록으로 돌린다."""
    try:
        d = ecos._get(f"{service}/{ecos.api_key() or 'sample'}/json/kr/{path}")
    except ecos.EcosError as exc:
        if "INFO-200" in str(exc):
            return [], 0
        raise
    body = d[service]
    return body["row"], int(body.get("list_total_count") or 0)


def _item_rows(code: str, item: str) -> list[dict]:
    """그 항목의 행(주기별)만. 지나치면 멈춘다 — 모듈 docstring 참조."""
    page = ecos.REAL_PAGE if ecos.available() else ecos.SAMPLE_PAGE
    found: list[dict] = []
    start = 1
    while True:
        rows, total = _rows("StatisticItemList", f"{start}/{start + page - 1}/{code}")
        for r in rows:
            if r.get("ITEM_CODE") == item:
                found.append(r)
            elif found:
                return found
        start += page
        if not rows or start > total:
            return found
        if not ecos.available():
            time.sleep(0.12)


def _months_ago(ym: str) -> int:
    today = date.today()
    return (today.year - int(ym[:4])) * 12 + today.month - int(ym[4:6])


def check(metric: str) -> bool:
    code, item, cycle = ecos.TABLES[metric]
    print(f"{metric}  ({code} / {item}, 주기 {cycle})")
    ok = True

    tables, _ = _rows("StatisticTableList", f"1/10/{code}")
    tbl = next((t for t in tables if t.get("STAT_CODE") == code), None)
    if tbl is None:
        print(f"  [X] 통계표 {code} 가 목록에 없습니다.")
        return False
    srch = tbl.get("SRCH_YN") == "Y"
    print(f"  [{'O' if srch else 'X'}] 통계표  {tbl.get('STAT_NAME')}"
          f"{'' if srch else '  — 조회 불가(SRCH_YN != Y)'}")
    ok &= srch

    rows = _item_rows(code, item)
    if not rows:
        print(f"  [X] 항목 {item} 이 {code} 의 항목 목록에 없습니다.")
        return False

    name = rows[0].get("ITEM_NAME")
    want = EXPECT.get(metric)
    if want is None:
        print(f"  [X] 항목 이름 '{name}' — EXPECT 에 기대값이 없습니다. 확인 후 적으세요.")
        ok = False
    elif name != want:
        print(f"  [X] 항목 이름 '{name}' — 기대 '{want}'")
        ok = False
    else:
        print(f"  [O] 항목    {name}")

    row = next((r for r in rows if r.get("CYCLE") == cycle), None)
    if row is None:
        have = ", ".join(sorted(str(r.get("CYCLE")) for r in rows))
        print(f"  [X] 주기 {cycle} 가 없습니다(있는 주기: {have}).")
        return False

    end = str(row.get("END_TIME") or "")
    span = (f"{row.get('START_TIME')}~{end}  {row.get('DATA_CNT')}건  "
            f"단위 {row.get('UNIT_NAME')}")
    if cycle == "M" and len(end) == 6 and _months_ago(end) > STALE_MONTHS:
        print(f"  [X] 계열    {span}  — 끝이 {_months_ago(end)}개월 전. 끊긴(구)지표일 수 있습니다.")
        ok = False
    else:
        print(f"  [O] 계열    {span}")
    return ok


def main() -> int:
    keyed = ecos.available()
    print(f"인증키: {'있음' if keyed else '없음 (sample 키 — 10행씩)'}")
    print()

    bad = 0
    for metric in ecos.TABLES:
        try:
            good = check(metric)
        except ecos.EcosError as exc:
            print(f"  [X] {exc}")
            good = False
        bad += not good
        print()

    print(f"지표 {len(ecos.TABLES)}개 중 문제 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
