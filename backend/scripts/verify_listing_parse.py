"""매물 파서가 **주석에 적은 사례를 주석대로** 읽는지 대조한다.

사용법:
    python -m scripts.verify_listing_parse

## 왜 있나

`listing_parse.py` 의 정규식은 거의 전부 '실제로 겪었다' 에서 나왔다. '매매 13억' 다음
줄의 112 를 만원으로 먹어 130,112 가 됐고, '평당가' 와 이어 붙어 0평이 됐고, 메모의
'피3000' 이 호가로 잡혔다. 고칠 때마다 사례를 주석에 남겼지만 **주석은 실행되지
않는다.** 다음에 정규식을 고치는 사람이 옛 사례를 다시 깨도 아무도 모른다.

그래서 주석의 사례를 그대로 입력으로 쓰고, **주석이 말하는 값**을 기대값으로 둔다.
지금 파서를 돌려 나온 값을 얼려 두지 않는다 — 그러면 지금의 버그까지 '정답' 이 된다.

## 무엇을 하지 않나

- **DB 를 보지 않는다.** 단지 맞추기(`listing_match`)는 DB 가 있어야 하고,
  `verify_name_match` 가 따로 본다. 여기는 글자만 읽는 단계다.
- **붙여넣기 원문을 저장해 두지 않는다.** 우리는 원문을 DB 에 남기지 않는다
  (`Quote` 는 읽은 값만 남긴다). 그래서 사례는 주석에서만 온다.

## 알려진 결함

기대값과 다르지만 **아직 고치지 않기로 한 것**은 `KNOWN` 에 이유와 함께 둔다.
실패가 아니라 `[!]` 로 보고한다 — 고치면 그 사례가 통과하면서 `[!]` 가 '이제
통과한다' 로 바뀌니, 그때 `KNOWN` 에서 빼면 된다.
"""

from __future__ import annotations

import sys
from datetime import date

from app.services import listing_parse as LP

PY = 3.305785
TODAY = date(2026, 10, 15)

# (이름, 입력, 기대값). 기대값에 없는 필드는 보지 않는다.
CASES: list[tuple[str, str, dict]] = [
    # 모듈 첫머리의 '파싱 대상 예시' 세 가지
    ("버튼 문구가 섞인 네이버 카드",
     "힐스테이트푸르지오수원 103동\n매매 9억\n3,360만원/3.3㎡평당가 도움말\n"
     "알림관심매물\n공유하기\n아파트88B㎡ (전용59B)8/15층남향",
     {"exclusive_area": 59.0, "supply_area": 88.0, "area_is_explicit": True,
      "floor": 8, "total_floor": 15, "dong": "103", "asking_price": 90000,
      "stated_ppp": 3360}),
    ("공급/전용 쌍과 층 구간",
     "래미안영통마크원 105동\n매매 8억 5,000\n아파트 · 84.97/59.94㎡, 중층, 남향",
     {"exclusive_area": 59.94, "supply_area": 84.97, "area_is_explicit": True,
      "floor": None, "floor_band": "중층", "dong": "105", "asking_price": 85000}),
    ("'/' 가 항목 구분자일 때 3000 을 잃지 않는다",
     "광교자연앤힐스테이트\n12억 3000 / 전용 84.9㎡ / 15층",
     {"asking_price": 123000, "exclusive_area": 84.9, "area_is_explicit": True,
      "floor": 15}),
    # 면적
    ("평 쌍 — 전용 쪽 단위 생략을 앞에서 물려받는다",
     "X 101동\n매매 3억\n아파트17평 (전용12)3/25층남서향",
     {"exclusive_area": round(12 * PY, 2), "supply_area": round(17 * PY, 2),
      "area_pyeong": 12, "floor": 3, "total_floor": 25}),
    ("'전용 112.40㎡' 에서 112 만 떼지 않는다",
     "X\n매매 9억\n전용 112.40㎡", {"exclusive_area": 112.4}),
    ("'34평/25.7평' 은 뒤쪽이 전용",
     "X\n매매 9억\n34평/25.7평 10/20층",
     {"exclusive_area": round(25.7 * PY, 2), "supply_area": round(34 * PY, 2)}),
    ("'30평대' 는 범위라 면적이 아니다",
     "X\n매매 5억\n30평대 고층", {"exclusive_area": None, "floor_band": "고층"}),
    ("다음 줄 '평당가' 와 이어 붙여 0평을 만들지 않는다",
     "X\n매매 3억 9,000\n평당가 2,100만원\n84㎡ 5/10층",
     {"asking_price": 39000, "exclusive_area": 84.0}),
    # 가격
    ("억 뒤 만원 자리는 같은 줄에서만 — 130,112 가 되지 않는다",
     "X\n매매 13억\n112.9/84.9㎡ 7/15층",
     {"asking_price": 130000, "exclusive_area": 84.9}),
    ("범위 호가는 낮은 쪽, 사실은 남긴다",
     "X\n매매 3억 2,500 ~ 3억 8,000\n84㎡ 5/10층",
     {"asking_price": 32500, "price_is_range": True}),
    # 층
    ("'고/23층' — 층은 숨기고 총 층수는 준다",
     "X\n매매 4억\n84㎡ 고/23층", {"floor": None, "total_floor": 23, "floor_band": "고층"}),
    ("'탑층' 은 최상층", "X\n매매 4억\n84㎡ 탑층", {"floor_band": "최상층"}),
    # 동 — 첫 줄에서만, 숫자·한 글자만
    ("법정동은 동 번호가 아니다", "인계동 래미안\n매매 4억\n84㎡ 5/10층", {"dong": None}),
    ("본문의 '남동향' 은 동이 아니다", "X\n매매 4억\n84㎡ 5/10층남동향", {"dong": None}),
    ("한 글자 동", "X 가동\n매매 4억\n84㎡ 5/10층", {"dong": "가"}),
    # 알려진 결함 — 아래 KNOWN 참조
    ("㎡ 공급 뒤의 단위 없는 전용은 평이 아니다",
     "X 101동\n매매 2억\n아파트49㎡ (전용36)3/15층",
     {"exclusive_area": 36.0, "area_pyeong": None}),
]

# 사례마다 이유. **고치지 않은 이유**를 적는다.
KNOWN: dict[str, str] = {
    "㎡ 공급 뒤의 단위 없는 전용은 평이 아니다":
        "`area_pyeong` 을 잡는 정규식이 단위를 안 본다. `_PAIR_PYEONG` 주석은 "
        "'88B㎡ (전용59B) 는 ㎡ 로 읽힌다' 고 하는데, 같은 숫자가 area_pyeong=59 로도 "
        "잡혀 `_resolve_area` 가 [195, 198㎡] 구간부터 찾는다. 2026-10-15 실측: 2,472개 "
        "단지 중 그 구간에 다른 평형이 있는 곳은 1곳(권선자이e편한세상 59.96 ↔ "
        "195.49㎡)이고, 그곳 195㎡ 호가 10건은 메모·가격으로 보아 진짜 큰 평형이었다. "
        "고치면 값이 바뀌므로 따로 정한다.",
}


def split_cases() -> list[tuple[str, bool, str]]:
    """`split_listings` — 3줄 블록·메모 울타리·확인일자."""
    card = (
        "수원센트럴아이파크자이 129동\n매매 4억 2,000\n아파트17평 (전용12)3/25층남서향\n"
        '"\n달리는 황소 입주가능,시에2대 지동사거리 접근 좋아 대중교통용이\n"\n'
        "집주인확인매물 2026.09.23\n"
    )
    noisy = (
        "임광 8동\n매매 3억\n84㎡ 5/10층\n임대분양가27,000 홍보문구\n"
        '"\n세끼고 피3000 확정가500할인됨\n"\n'
    )
    unclosed = 'X 101동\n매매 4억\n84㎡ 5/10층\n"\n닫지 않은 메모\n'
    out = []
    b = LP.split_listings(card)
    ok = (len(b) == 1 and b[0]["confirmed_on"] == date(2026, 9, 23)
          and b[0]["memo"] == "달리는 황소 입주가능,시에2대 지동사거리 접근 좋아 대중교통용이")
    out.append(("메모 울타리와 확인일자를 따로 싣는다", ok, repr(b)[:160]))

    b = LP.split_listings(noisy)
    p = LP.parse_listing(b[0]["text"], []) if b else None
    ok = bool(b) and p.asking_price == 30000 and "피3000" in (b[0]["memo"] or "")
    out.append(("홍보문구·메모의 숫자를 호가로 집지 않는다", ok,
                f"호가 {p.asking_price if p else None} · 메모 {b[0]['memo'] if b else None}"))

    b = LP.split_listings(unclosed)
    ok = len(b) == 1 and b[0]["memo"] is None
    out.append(("닫지 않은 울타리는 메모로 보지 않는다", ok, repr(b)[:160]))

    ok = (LP.parse_confirmed_on("등록 2027.01.01", today=TODAY) is None
          and LP.parse_confirmed_on("5일 전", today=TODAY) == date(2026, 10, 10))
    out.append(("미래 날짜는 버리고 '5일 전' 은 셈한다", ok, ""))

    ok = (LP.name_fragments("신성,신안,쌍용,진흥 543동") == ["신성", "신안", "쌍용", "진흥"]
          and LP.head_name_text("현대 104동") == "현대")
    out.append(("합동 단지 이름 조각·보이는 그대로의 이름", ok, ""))
    return out


def run() -> tuple[list[str], list[str], int]:
    fails, notes, n = [], [], 0
    for name, text, want in CASES:
        n += 1
        got = LP.parse_listing(text, []).as_dict()
        bad = {k: (v, got.get(k)) for k, v in want.items()
               if (round(got.get(k), 2) if isinstance(got.get(k), float) else got.get(k)) != v}
        if name in KNOWN:
            if bad:
                notes.append(f"알려진 결함 '{name}' — {KNOWN[name][:60]}…")
            else:
                notes.append(f"'{name}' 가 이제 통과합니다 — KNOWN 에서 빼세요")
            continue
        if bad:
            fails.append(f"{name}: " + ", ".join(f"{k} 기대 {w!r} · 실제 {g!r}"
                                                 for k, (w, g) in bad.items()))
    for name, ok, detail in split_cases():
        n += 1
        if not ok:
            fails.append(f"{name}: {detail}")
    return fails, notes, n


def self_test() -> bool:
    """이 검사가 **걸리는지**. 실제로 겪은 버그를 되살려 넣어 본다.

    억 뒤 만원 자리를 줄바꿈 너머까지 찾게 하면 '매매 13억' + 다음 줄 112 가
    130,112 가 된다. 이것을 못 잡으면 검사가 없는 것과 같다.
    """
    import re

    orig = LP._PRICE_EOK
    LP._PRICE_EOK = re.compile(r"(\d{1,2})\s*억(?:\s*([\d,]{3,6}))?")
    try:
        fails, _, _ = run()
    finally:
        LP._PRICE_EOK = orig
    return any("130,112" in f or "130112" in f for f in fails)


def main() -> int:
    fails, notes, n = run()
    print(f"매물 파서 사례 {n}개 · 실패 {len(fails)} · 알려진 결함 {len(notes)}")
    for f in fails:
        print(f"[X] {f}")
    for w in notes:
        print(f"[!] {w}")
    caught = self_test()
    print(f"자체 시험 — 옛 버그(130,112)를 되살리면 {'잡음' if caught else '못 잡음'}")
    if not caught:
        print("[X] 검사가 옛 버그를 못 잡습니다")
    return 1 if fails or not caught else 0


if __name__ == "__main__":
    sys.exit(main())
