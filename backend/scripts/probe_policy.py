"""정책 연표의 원문 링크(`policy.POLICY[*].official`)가 아직 그 보도자료를 가리키는지 대조한다.

## 왜 따로 있나

원문 링크는 정책브리핑(korea.kr) 보도자료의 `newsId` 로 적었다. 고를 때 부처·제목·날짜와 첨부 본문을
대조했지만 그것은 한 번이다. 사이트가 개편되면 **링크는 열리는데 다른 글이나 오류 안내 페이지**가 뜰
수 있다 — 오류가 아니라 200 으로 돌아오므로 눈으로 눌러 보기 전에는 모른다(`/etc/openApi.do` 가 실제로
200 과 '삭제되었거나 조회가 되지 않는 자료' 를 함께 돌려줬다).

그래서 링크마다 세 가지를 본다.

1. 열리고, 오류 안내 페이지가 아닌가
2. 본문 머리의 부처명이 `org` 와 같은가
3. 제목이 `title` 과 같은가(공백만 무시) · 게시일이 `date` 와 같은가

네트워크를 쓰므로 `checkup` 이 찾는 `verify_*` 가 아니라 `probe_*` 로 둔다(`probe_ecos` 와 같다).
링크를 더하거나 고쳤을 때, 그리고 가끔 돌린다.

## 사용

    python -m scripts.probe_policy
"""

from __future__ import annotations

import html
import re
import sys
import time
import urllib.request

from app.services.policy import POLICY

UA = {"User-Agent": "Mozilla/5.0"}
GONE = "삭제되었거나 조회가 되지 않는 자료"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", html.unescape(s))


def fetch(url: str) -> str:
    # 정책브리핑이 가끔 느리다 — 한 번 더 시도하고, 그래도 안 되면 실패로 센다.
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except OSError:
            if attempt:
                raise
            time.sleep(2)
    return ""


def check(o: dict) -> list[str]:
    body = fetch(o["url"])
    if GONE in body:
        return ["삭제·조회 불가 안내 페이지"]
    flat = re.sub(r"\s+", " ", body)
    info = re.search(r'class="info">(.{0,700})', flat)
    parts = [p.strip() for p in re.sub(r"<[^>]+>", "|", info.group(1)).split("|") if p.strip()] if info else []
    title = re.search(r"<title>(.*?) - 보도자료", body, re.S)
    errs = []
    if len(parts) < 2:
        errs.append("본문 머리(날짜·부처)를 못 찾음")
    else:
        if parts[0].replace(".", "-") != o["date"]:
            errs.append(f"게시일 {parts[0]} ≠ {o['date']}")
        if parts[1] != o["org"]:
            errs.append(f"부처 {parts[1]} ≠ {o['org']}")
    if not title:
        errs.append("제목을 못 찾음")
    elif norm(title.group(1)) != norm(o["title"]):
        errs.append(f"제목 '{html.unescape(title.group(1)).strip()}'")
    return errs


def main() -> int:
    links = [(p, o) for p in POLICY for o in p.get("official", ())]
    bad = 0
    for p, o in links:
        try:
            errs = check(o)
        except OSError as exc:
            errs = [f"열리지 않음 ({exc})"]
        mark = "[X]" if errs else "   "
        print(f"{mark} {p['date']} {p['name']} — {o['org']}" + (f": {'; '.join(errs)}" if errs else ""))
        bad += bool(errs)
    missing = [p["name"] for p in POLICY if not p.get("official")]
    for name in missing:
        print(f"[!] 원문 없음 — {name}")
    print(f"\n링크 {len(links)}개 중 문제 {bad}개 · 원문 없는 대책 {len(missing)}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
