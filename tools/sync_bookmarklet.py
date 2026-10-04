"""`bookmarklet.js` 를 `bookmarklet.html` 의 인라인 사본에 맞춘다.

## 왜 필요한가

설치 페이지는 같은 폴더의 `bookmarklet.js` 를 `fetch` 해서 링크를 만든다. 그런데
`file://` 로 열면 fetch 가 막히므로 HTML 안에 **인라인 사본**을 두고 그쪽으로 떨어진다.

사본이 둘이면 어긋난다. 실제로 어긋났다 — `findPanel` 을 고친 뒤 HTML 을 갱신하지
않아, 웹서버로 열면 고친 코드가 들어가고 `file://` 로 열면 **매물 3건짜리 패널에서
1건만 담던 옛 코드**가 들어갔다. 둘 다 조용히 동작하므로 쓰는 사람은 어느 쪽을 쓰고
있는지 알 수 없다.

그래서 `.js` 를 유일한 원본으로 두고 이 스크립트로 HTML 을 맞춘다.
**`bookmarklet.js` 를 고쳤으면 이것을 돌린다.**

    python tools/sync_bookmarklet.py
    python tools/sync_bookmarklet.py --check   # 어긋났는지만 본다(고치지 않는다)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JS = HERE / "bookmarklet.js"
HTML = HERE / "bookmarklet.html"

BLOCK = re.compile(
    r'(<script type="text/plain" id="inline-src">\n)(.*?)(\n</script>)',
    re.S,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="북마클릿 인라인 사본 동기화")
    ap.add_argument("--check", action="store_true", help="고치지 않고 어긋났는지만 본다")
    args = ap.parse_args()

    js = JS.read_text(encoding="utf-8").strip()
    html = HTML.read_text(encoding="utf-8")

    m = BLOCK.search(html)
    if not m:
        print("[X] bookmarklet.html 에서 inline-src 블록을 찾지 못했습니다.")
        return 1

    # `</script>` 가 본문에 섞이면 HTML 이 거기서 끊긴다. 지금은 없지만 방어해 둔다.
    safe = js.replace("</script>", "<\\/script>")

    if m.group(2).strip() == safe.strip():
        print("일치합니다. 고칠 것이 없습니다.")
        return 0

    if args.check:
        print("[X] 인라인 사본이 bookmarklet.js 와 다릅니다.")
        print("    python tools/sync_bookmarklet.py 로 맞추세요.")
        return 1

    HTML.write_text(
        html[: m.start(2)] + safe + html[m.end(2) :],
        encoding="utf-8",
        newline="\n",
    )
    print(f"맞췄습니다 — {len(safe):,}자")
    return 0


if __name__ == "__main__":
    sys.exit(main())
