"""문서 사이 링크가 **실제로 가 닿는지** 검사한다.

사용법:
    python -m scripts.verify_docs

## 왜 필요한가

문서를 나누면 링크가 조용히 깨진다. 404 가 나는 것도 아니고 (GitHub 에서는 그냥
눌리지 않는다) 누가 눌러 보기 전까지 아무 일도 일어나지 않는다 — 이 저장소가
가장 경계하는 모양이다.

문서 셋을 나누면서(`design.md` → `+ui-log.md`, `model.md` → `+factors.md`,
`data.md` → `+reb.md`) 상호 참조가 열 군데 넘게 생겼다. 손으로 확인하면 다음에 또
나눌 때 다시 손으로 확인해야 한다.

## 무엇을 보나

- 상대 링크가 가리키는 **파일이 있는가**
- `#앵커` 가 그 파일의 **제목에서 실제로 만들어지는가**
- CLAUDE.md 라우팅 표가 **있는 문서를 가리키는가**, 그리고 `docs/` 의 문서가
  표에서 **빠져 있지 않은가** (나눠 놓고 표에 안 넣으면 아무도 못 찾는다)
- 문서가 **묶음 폴더 한 단계 아래**에 있는가 — `docs/<묶음>/<문서>.md`
- **코드 주석**이 가리키는 `docs/…` 경로와 `'절 제목'` 이 아직 있는가

## 계층을 검사로 지킨다

문서가 열둘이 되자 `docs/` 한 폴더에 평평하게 늘어서서, 비슷한 문서(공급·거시·
공표 통계)가 이름순으로 흩어졌다. 그래서 '무엇에 답하나' 로 묶었다 — 화면(screens),
추정(model), 데이터 출처(data), 공급·거시 탭(analysis), 코드 다루기(engineering).

묶어 놓아도 다음 문서를 `docs/` 바로 아래에 두면 다시 평평해진다. 사람이 기억하는
규칙은 반드시 뒤처지므로 여기서 막는다. 두 단계 이상도 막는다 — 깊게 파면 이번에는
어느 폴더에 있는지 찾느라 길을 잃는다. 묶음이 모자라면 폴더를 **옆으로** 더한다.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# 링크 검사에서 뺀다. 외부 링크와 코드 파일은 여기서 볼 것이 아니다.
SKIP = re.compile(r"^(https?:|mailto:|#)")

LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")


def anchor_of(title: str) -> str:
    """GitHub 의 제목 → 앵커 규칙.

    소문자로 바꾸고, 공백을 `-` 로, 그 밖의 문장부호를 지운다. 한글은 그대로 남는다.
    `**굵게**` 같은 마크다운은 먼저 벗긴다 — 앵커에는 안 들어간다.
    """
    t = re.sub(r"`([^`]*)`", r"\1", title)
    t = re.sub(r"\*\*([^*]*)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]*)\*", r"\1", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = unicodedata.normalize("NFC", t).lower().strip()
    t = re.sub(r"[^\w\s가-힣-]", "", t)
    # 공백을 **하나씩** 바꾼다. `\s+` 로 줄이면 안 된다 — GitHub 은 연속 공백을
    # 합치지 않는다. '적정가 — 매물' 처럼 em dash 를 지운 자리에 공백이 둘 남으면
    # 앵커도 `--` 가 된다. 처음에 `\s+` 로 썼다가 멀쩡한 링크를 깨졌다고 했다.
    return re.sub(r"\s", "-", t)


def anchors_of(path: Path) -> set[str]:
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEADING.match(line)
        if m:
            out.add(anchor_of(m.group(1)))
    return out


def layout_problems(rels: list[str]) -> list[str]:
    """`docs/` 아래 상대 경로들 중 계층 규칙을 어긴 것. 순수 함수라 자체 시험이 쉽다."""
    bad = []
    for r in rels:
        depth = r.count("/")
        if depth == 0:
            bad.append(f"docs/{r}  묶음 폴더 없이 docs/ 바로 아래에 있습니다 — "
                       f"비슷한 문서의 폴더에 넣으세요")
        elif depth > 1:
            bad.append(f"docs/{r}  폴더가 두 단계 이상입니다 — 묶음은 한 단계만 둡니다")
    return bad


# 코드가 문서를 가리키는 모양. `docs/engineering/deploy.md` 와, 거기에 절 제목을 붙인
# `docs/engineering/deploy.md '스케줄러가 띄운 PowerShell 이 죽는다'`(`의` 가 끼기도 한다).
CODE_DOC_REF = re.compile(r"(docs/[\w/.-]+?\.md)(?:#[\w-]+)?(?:\s*의)?(?:\s*'([^'\n]{2,80})')?")


def _plain(title: str) -> str:
    return re.sub(r"[`*]", "", title).strip()


def code_doc_problems(items: list[tuple[str, str]],
                      heads: dict[str, list[str]]) -> list[str]:
    """코드(주석·독스트링)가 가리키는 문서 경로와 절 제목이 아직 있나. 순수 함수다.

    문서를 옮기거나 절 제목을 바꾸면 **문서끼리의 링크는 위에서 잡히지만 코드 주석은
    아무도 안 본다.** 문서를 묶음 폴더로 옮길 때 주석 속 경로 13개 파일을 손으로
    고쳤고, CLAUDE.md 는 그 확인을 이 스크립트가 한다고 적었는데 실제로는 문서만 보고
    있었다. 주석이 '경위는 deploy.md 의 그 절' 이라고 하는데 그 절이 없으면, 읽는
    사람은 경위가 지워진 줄 안다.

    `items` 는 (어디, 본문), `heads` 는 문서 경로 → 제목 목록.
    """
    bad = []
    for where, text in items:
        for m in CODE_DOC_REF.finditer(text):
            path, quote = m.group(1), m.group(2)
            if path not in heads:
                bad.append(f"{where}  없는 문서 → {path}")
                continue
            if quote and not any(_plain(quote) in _plain(h) for h in heads[path]):
                bad.append(f"{where}  {path} 에 '{quote}' 절이 없습니다")
    return bad


def self_test() -> bool:
    """계층 검사와 코드→문서 검사가 **걸리는지**, 그리고 멀쩡한 것은 **안 걸리는지**."""
    caught = (len(layout_problems(["new.md"])) == 1
              and len(layout_problems(["model/deep/x.md"])) == 1)
    clean = layout_problems(["model/method.md", "screens/ui-log.md"]) == []
    heads = {"docs/a/x.md": ["# 문서", "## 스케줄러가 **죽는다**"]}
    ref_caught = (len(code_doc_problems([("f", "docs/a/gone.md 참조")], heads)) == 1
                  and len(code_doc_problems([("f", "docs/a/x.md '없는 절'")], heads)) == 1)
    ref_clean = code_doc_problems([
        ("f", "경위는 docs/a/x.md '스케줄러가 죽는다'"),
        ("f", "docs/a/x.md 의 '스케줄러가 죽는다' 참조"),
        ("f", "(docs/a/x.md — 설명)"),
    ], heads) == []
    return caught and clean and ref_caught and ref_clean


def main() -> int:
    docs = sorted((ROOT / "docs").rglob("*.md"))
    targets = [ROOT / "CLAUDE.md", ROOT / "README.md", *docs]
    anchors = {p.resolve(): anchors_of(p) for p in targets}

    bad: list[str] = []
    n_links = 0
    for src in targets:
        rel = src.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            for _text, href in LINK.findall(line):
                if SKIP.match(href):
                    continue
                n_links += 1
                path_part, _, frag = href.partition("#")
                tgt = (src.parent / path_part).resolve() if path_part else src.resolve()
                if not tgt.exists():
                    bad.append(f"{rel}:{line_no}  파일 없음 → {href}")
                    continue
                if frag and tgt.suffix == ".md":
                    have = anchors.get(tgt)
                    if have is None:
                        have = anchors_of(tgt)
                        anchors[tgt] = have
                    if frag.lower() not in have:
                        bad.append(f"{rel}:{line_no}  앵커 없음 → {href}")

    print(f"링크 {n_links}개 검사 · 문서 {len(targets)}개")
    for b in bad:
        print(f"  [X] {b}")

    # 라우팅 표가 모든 문서를 덮는가
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    listed = {m for _t, m in LINK.findall(claude) if m.startswith("docs/")}
    missing = [
        d.relative_to(ROOT).as_posix() for d in docs
        if d.relative_to(ROOT).as_posix() not in listed
    ]
    if missing:
        print(f"\n  [!] CLAUDE.md 라우팅 표에 없는 문서 {len(missing)}개 — "
              f"나눠 놓고 표에 안 넣으면 아무도 못 찾습니다:")
        for m in missing:
            print(f"      {m}")

    # 코드 → 문서 — 주석이 가리키는 경로와 절
    heads = {d.relative_to(ROOT).as_posix(): [m.group(1) for line in
                                             d.read_text(encoding="utf-8").splitlines()
                                             if (m := HEADING.match(line))]
             for d in docs}
    code = [p for p in [*(ROOT / "backend" / "app").rglob("*.py"),
                        *(ROOT / "backend" / "scripts").glob("*.py"),
                        *(ROOT / "frontend" / "src").rglob("*.js*"),
                        *(ROOT / "frontend" / "src").rglob("*.css"),
                        *ROOT.glob("*.ps1"), *(ROOT / "tools").glob("*.*"),
                        ROOT / "backend" / "data" / "manual" / "README.md"]
            if p.is_file() and "__pycache__" not in p.parts and p.name != "verify_docs.py"]
    items = [(p.relative_to(ROOT).as_posix(), p.read_text(encoding="utf-8", errors="replace"))
             for p in code]
    refs = code_doc_problems(items, heads)
    # 본 개수를 찍는다 — 0 이면 검사가 아무것도 안 보고 통과한 것이다
    found = [m for _w, t in items for m in CODE_DOC_REF.finditer(t)]
    print(f"\n코드 {len(code)}개 파일 · 문서 경로 {len(found)}개(절 인용 "
          f"{sum(1 for m in found if m.group(2))}개) · 없는 것 {len(refs)}")
    for b in refs:
        print(f"  [X] {b}")

    # 계층 — 묶음 폴더 한 단계 아래
    layout = layout_problems([d.relative_to(ROOT / "docs").as_posix() for d in docs])
    groups = sorted({d.parent.name for d in docs if d.parent != ROOT / "docs"})
    print(f"\n묶음 {len(groups)}개 ({' · '.join(groups)}) · 규칙 어긴 문서 {len(layout)}개")
    for b in layout:
        print(f"  [X] {b}")
    tested = self_test()
    print(f"자체 시험 — 계층·코드→문서 검사가 {'걸려야 할 때 걸리고, 아닐 때 안 걸림' if tested else '제대로 걸리지 않음'}")
    if not tested:
        print("  [X] 계층·코드→문서 검사가 일부러 어긴 경우를 못 잡거나 멀쩡한 것을 잡습니다")

    ok = not bad and not missing and not layout and not refs and tested
    print("\n" + ("전부 통과" if ok else "고칠 것이 있습니다"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
