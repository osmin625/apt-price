"""단지명 매칭에서 **동 번호를 떼는 것**이 멀쩡한 매칭을 깨지 않는지 대조한다.

## 왜 있나

`_name_candidates` 가 첫 줄의 동 표기를 떼고 나서 DB 이름을 찾도록 바꿨다. 안 떼면
동 번호가 이름의 일부로 먹혀 **남의 단지에 붙는다**.

    성원 102동        -> 성원102동     ⊃ `성원1`(안양 만안구)
    신나무실5단지주공 514동 -> ...주공514동 ⊃ `주공5`(과천시)

고치는 쪽이 분명하지만, 고치면서 **원래 맞던 것까지 깨질 수** 있다. 이름이 숫자로
끝나는 단지(2,469곳 중 187곳)는 동을 떼도 여전히 맞아야 한다 — `청구2 201동`,
`주공그린빌5 505동` 처럼.

이 저장소의 규칙이다: "빠르게 만든 것은 같은 답을 내는지 대조한다." 여기서는 빠르게가
아니라 올바르게 만든 것이지만, **값이 달라지는 변경이면 전수로 본다**는 점은 같다.

## 무엇을 하나

DB 의 모든 단지에 대해 `"{이름} {동}동"` 꼴의 첫 줄을 만들어, 떼기 전/후가 같은
단지를 고르는지 본다. 동 번호는 실제 등록된 동(`complex_dongs`)을 쓰고, 없으면
101·201·501 등을 넣어 본다 — 숫자로 끝나는 이름을 일부러 때린다.

## 사용

    python -m scripts.verify_name_match
    python -m scripts.verify_name_match --paste 붙여넣기.txt   # 실제 붙여넣기로도
"""

from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import select

from app import pricing
from app.clients.molit import DISTRICTS
from app.db import SessionLocal
from app.models import Complex, ComplexDong
from app.services import listing_parse as LP

def _pick(line: str, complexes: list, *, old: bool) -> Complex | None:
    """그 첫 줄로 **실제로 어느 단지가 선택되는지**. `parse_listing` 과 같은 길이다.

    1번 규칙만 떼어 보면 안 된다. 떼면 `삼익 1동` 이 '고쳐졌는데도 None' 으로 보인다 —
    1번이 비면 2번(두 글자 정확일치)이 받기 때문이다. 처음에 그렇게 재서 '깨진 것
    78건' 이라는 틀린 숫자를 봤다.
    """
    text = line + "\n매매 4억\n84㎡ 5/10층"
    if old:
        # 떼기 전 구현 — 첫 줄의 동을 남긴 채로 본다.
        orig = LP._strip_head_dong
        LP._strip_head_dong = lambda t: t
        try:
            p = LP.parse_listing(text, complexes)
        finally:
            LP._strip_head_dong = orig
    else:
        p = LP.parse_listing(text, complexes)
    return next((c for c in complexes if c.id == p.complex_id), None) if p.complex_id else None


def main() -> int:
    ap = argparse.ArgumentParser(description="단지명 매칭 대조")
    ap.add_argument("--paste", help="실제 붙여넣기 텍스트 파일로도 대조")
    args = ap.parse_args()

    with SessionLocal() as db:
        cxs = db.execute(select(Complex)).scalars().all()
        dongs: dict[int, list[str]] = {}
        for d in db.execute(select(ComplexDong)).scalars().all():
            dongs.setdefault(d.complex_id, []).append(d.dong)

        numeric = [c for c in cxs if re.search(r"\d$", c.name_key or c.name or "")]
        print(f"단지 {len(cxs):,}곳 · 이름이 숫자로 끝나는 곳 {len(numeric)}곳\n")

        # **정답은 출처 단지(cx)** 다. 그 단지의 이름과 동으로 줄을 만들었으니까.
        # 그래야 '오답 -> 거절' 과 '정답 -> 오답' 이 갈린다. 처음엔 old 와 new 가
        # 다르기만 하면 '깨짐' 으로 세서, 오답을 거절로 바꾼 63건을 깨진 것으로
        # 읽을 뻔했다.
        same, fixed, refused, broke = 0, [], [], []
        for cx in cxs:
            cands = dongs.get(cx.id) or ["101", "201", "501", "1"]
            for dong in cands[:4]:
                line = f"{cx.name} {dong}동"
                o = _pick(line, cxs, old=True)
                n = _pick(line, cxs, old=False)
                if o is n:
                    same += 1
                elif n is cx:
                    fixed.append((line, o, n))        # 오답/거절 -> 정답
                elif o is cx:
                    broke.append((line, o, n))        # 정답 -> 오답/거절  ← 있으면 안 된다
                else:
                    refused.append((line, o, n))      # 오답 -> 거절(또는 다른 오답)

        def show(rows, n=10):
            for line, o, nw in rows[:n]:
                so = DISTRICTS.get(getattr(o, "sgg_cd", ""), "?") if o else ""
                sn = DISTRICTS.get(getattr(nw, "sgg_cd", ""), "?") if nw else ""
                print(f"   {line:<26} {(o.name if o else '거절'):<14}{so:<12} -> "
                      f"{(nw.name if nw else '거절'):<14}{sn}")
            if len(rows) > n:
                print(f"   ... {len(rows) - n}건 더")

        print(f"같은 답 {same:,}건")
        print(f"\n[고쳐짐] 오답/거절 -> 제 단지  {len(fixed)}건")
        show(fixed)
        print(f"\n[오답을 거절로] {len(refused)}건 — 남의 단지에 붙던 것이 안 붙는다")
        show(refused)
        print(f"\n[깨짐] 제 단지였는데 틀려짐  {len(broke)}건", "<- 0 이어야 한다" if not broke else "*** 확인 필요 ***")
        show(broke, 20)

        if args.paste:
            print(f"\n--- 실제 붙여넣기: {args.paste} ---")
            text = open(args.paste, encoding="utf-8").read()
            for block in LP.split_listings(text):
                head = block["text"].splitlines()[0]
                o = _pick(head, cxs, old=True)
                n = _pick(head, cxs, old=False)
                if o is not n:
                    so = DISTRICTS.get(getattr(o, "sgg_cd", ""), "?") if o else ""
                    sn = DISTRICTS.get(getattr(n, "sgg_cd", ""), "?") if n else ""
                    print(f"   {head:<26} {(o.name if o else '—'):<12}{so:<12} -> "
                          f"{(n.name if n else '—'):<12}{sn}")

        return 1 if broke else 0


if __name__ == "__main__":
    sys.exit(main())
