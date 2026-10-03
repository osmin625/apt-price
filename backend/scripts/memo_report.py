"""쌓인 중개사 메모에 사전을 다시 재 본다.

## 왜 이 스크립트가 있나

`services/memo_tags.py` 의 규칙은 실제 메모 50건을 재서 만들었다. 메모가 더 쌓이면
그 50건에 없던 말이 들어온다 — 그때 **눈으로 보고 규칙을 늘리지 말고 재서 늘린다.**
이 저장소에서 추측이 틀린 적이 여러 번 있고 그때마다 잰 쪽이 맞았다.

이 스크립트가 답하는 것 셋.

1. 규칙마다 지금 몇 건이나 걸리나. **0건인 규칙**은 지워도 되는 것이거나,
   패턴이 실제 표기와 어긋난 것이다.
2. 태그를 하나도 못 받은 메모는 무엇인가. 거기에 새 규칙감이 있다.
3. 어떤 낱말이 자주 나오는데 아직 아무 규칙에도 안 걸리나.

## 사용

    python -m scripts.memo_report
    python -m scripts.memo_report --file 메모모음.txt   # DB 대신 파일에서
    python -m scripts.memo_report --min 3               # 3번 이상 나온 낱말만
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Quote
from app.services import memo_tags

# 낱말 후보. 한글 2자 이상, 또는 'P3000' 같은 영문+숫자.
_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z]{1,3}\d{3,5}")

# 세면 많이 나오지만 규칙으로 만들 가치가 없는 말. 보고에서 뺀다 — 안 빼면
# '좋아요'·'있어요' 가 상위를 채워 정작 볼 것이 안 보인다.
_STOP = {
    "좋아요", "있어요", "합니다", "입니다", "드실", "쏙드는", "맘에", "완죤",
    "완전", "강추", "최고", "최상", "추천", "하시면", "같아요", "언제든",
    "언제든지", "가능", "가능합니다", "주세요", "보시면", "그대로",
}


def collect(db) -> list[str]:
    out: list[str] = []
    for q in db.execute(select(Quote).where(Quote.memo != "")).scalars().all():
        for line in (q.memo or "").split("\n"):
            t = line.strip()
            if t and t not in out:
                out.append(t)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="중개사 메모에 사전을 재 본다")
    ap.add_argument("--file", help="DB 대신 읽을 텍스트 파일(한 줄 = 메모 하나)")
    ap.add_argument("--min", type=int, default=2, help="이 횟수 이상 나온 낱말만")
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            memos = [l.strip() for l in f if l.strip()]
    else:
        with SessionLocal() as db:
            memos = collect(db)

    if not memos:
        print("메모가 없습니다. 매물을 붙여넣으면 쌓입니다.")
        print("  (북마클릿 v3 이상이어야 메모를 담습니다 — tools/bookmarklet.html)")
        return 1

    hits = Counter()
    untagged: list[str] = []
    for s in memos:
        tags = memo_tags.extract(s)
        hits.update(tags)
        if not tags:
            untagged.append(s)

    print(f"메모 {len(memos)}건 (중복 제거)\n")
    print(f"{'태그':<14}{'적중':>5}{'비율':>7}")
    for name, _ in memo_tags.RULES:
        n = hits[name]
        print(f"{name:<14}{n:>5}{n / len(memos) * 100:>6.0f}%")

    dead = [n for n, _ in memo_tags.RULES if not hits[n]]
    if dead:
        print(f"\n[!] 한 번도 안 걸린 규칙: {', '.join(dead)}")
        print("    지울 것이거나, 패턴이 실제 표기와 어긋난 것입니다.")

    print(f"\n태그를 못 받은 메모 {len(untagged)}건"
          f" ({len(untagged) / len(memos) * 100:.0f}%)")
    for s in untagged[:20]:
        print(f"   {s[:70]}")
    if len(untagged) > 20:
        print(f"   ... {len(untagged) - 20}건 더")

    # 아직 아무 규칙에도 안 걸리는 낱말. 새 규칙감은 여기에 있다.
    tagged_text = " ".join(memos)
    free = Counter()
    for s in memos:
        for w in set(_WORD.findall(s)):
            if w in _STOP:
                continue
            # 이미 어떤 규칙에든 걸리는 낱말이면 새 규칙감이 아니다.
            if memo_tags.extract(w):
                continue
            free[w] += 1
    common = [(w, n) for w, n in free.most_common(40) if n >= args.min]
    print(f"\n아직 규칙에 없는 낱말 ({args.min}번 이상)")
    if not common:
        print("   없습니다.")
    for w, n in common:
        print(f"   {n:>3}회  {w}")
    print("\n규칙을 늘릴 때는 app/services/memo_tags.py 의 RULES 에 더하고"
          " 이 스크립트를 다시 돌려 적중 수를 주석에 남길 것.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
