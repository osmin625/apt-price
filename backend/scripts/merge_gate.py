"""머지 관문 — `gh pr merge` 를 부르기 직전에 CI 와 검진을 확인하고, 안 되면 막는다.

Claude Code 의 PreToolUse 훅이 부른다(`.claude/settings.json`). 셸 명령에 `gh pr merge` 가
없으면 아무것도 안 하고 끝난다. 있으면 셋을 본다.

1. **CI 가 그 PR 에서 통과했나** — `gh pr checks`. 돌고 있거나 실패면 막는다. CI 는 DB 없이
   되는 검사(`checkup --no-db`)와 프론트 빌드를 본다(`.github/workflows/check.yml`).
2. **PR 머리를 체크아웃한 작업 트리가 있나** — 로컬 검진은 **머지할 코드**를 봐야 한다.
   본 체크아웃(main)에서 `gh pr merge 74` 를 치면 검진이 main 을 본다 — 검사한 척하고
   다른 것을 통과시키는 모양이라 막는다. 그 브랜치의 워크트리에서 머지한다.
3. **그 작업 트리에서 `checkup --fast` 가 통과하나** — CI 에 없는 DB 가 있어야 하는 검사를
   여기서 돈다. 워크트리에 DB 가 없으면 본 체크아웃의 `apt.db` 를 **읽기만** 한다.

## 왜 훅인가

규칙은 CLAUDE.md 에 이미 있었다('PR 을 열기 전 — 전체'). 그런데 규칙은 기억에 기대고,
기억은 바쁠 때 빠진다. 머지는 되돌리기 어렵고(`main` 이 10분 안에 공개 사이트로 간다)
검진은 몇 분이면 된다 — 막는 비용이 작다. 막혔을 때 이유를 stderr 로 돌려주면 에이전트가
읽고 고친다(종료 코드 2).

## 판단이 안 서면 막는다

`gh` 가 없거나 PR 을 못 읽으면 통과시키지 않는다. 관문이 조용히 열리면 없는 것과 같다
(CLAUDE.md '검사를 넣었으면 걸리는 것까지 본다'). 우회 장치는 두지 않는다 — 꼭 필요하면
사람이 직접 머지한다.

표준 라이브러리만 쓴다. 훅은 PATH 의 `python` 으로 돌고, 무거운 검진은 저장소의 `.venv`
파이썬으로 따로 띄운다.
"""

from __future__ import annotations

import sys

# 이 훅은 **모든** 셸 명령 앞에서 돈다. 처음 쟀을 때 머지가 아닌 명령에도 241ms 씩
# 붙었다. 입력에 'merge' 가 없으면 무거운 import 전에 끝내고, 훅 명령에 `-I -S` 를 줘
# site 를 건너뛰니 평균 155ms — 맨 파이썬 시작(137ms)에 거의 붙었다(2026-11-10, 5회 평균).
RAW = sys.stdin.buffer.read().decode("utf-8", "replace")
if __name__ == "__main__" and "merge" not in RAW:
    sys.exit(0)

# 막을 때 쓰는 stderr 를 Claude Code 가 읽는다. 윈도우 콘솔 기본(cp949)으로 내보내면
# 한국어가 깨진 채 전달된다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MERGE = re.compile(r"\bgh\s+pr\s+merge\b(?P<rest>[^;&|\n]*)")
# 검진 --fast 가 이보다 오래 걸리면 고장으로 본다. 2026-11-10 에 31초였다 — 서른 배 가까이
# 둔 것은 첫 실행의 import·캐시 데우기가 몇 배로 늘어도 '고장' 으로 잡지 않으려고다.
# 훅 쪽 timeout(settings.json 960초)이 이보다 커야 이 메시지가 에이전트에게 간다.
CHECKUP_TIMEOUT = 900


def run(args: list[str], cwd: str | Path, timeout: int = 120, env: dict | None = None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, env=env)
    return (p.returncode, p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def block(msg: str) -> int:
    print(f"[머지 관문] 막음 — {msg}", file=sys.stderr)
    return 2


def pr_number(rest: str) -> str | None:
    """`gh pr merge 74 --merge` → '74'. 번호 없이 치면 gh 는 지금 브랜치의 PR 을 쓴다."""
    m = re.search(r"(?<![-\w=])(\d+)\b", rest)
    return m.group(1) if m else None


def worktrees(repo: str) -> list[tuple[Path, str]]:
    """(경로, HEAD). 맨 앞이 본 체크아웃이다."""
    _, out, _ = run(["git", "worktree", "list", "--porcelain"], repo)
    res, path = [], None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line.startswith("HEAD ") and path is not None:
            res.append((path, line[len("HEAD "):].strip()))
    return res


def venv_python(tree: Path, main: Path) -> str:
    for base in (tree, main):
        for rel in (("Scripts", "python.exe"), ("bin", "python")):
            p = base / "backend" / ".venv" / Path(*rel)
            if p.exists():
                return str(p)
    return sys.executable


def check_ci(repo: str, num: str) -> str | None:
    """문제가 있으면 그 설명, 없으면 None."""
    code, out, err = run(["gh", "pr", "checks", num, "--json", "name,bucket"], repo)
    try:
        checks = json.loads(out or "[]")
    except json.JSONDecodeError:
        return f"CI 결과를 읽지 못했습니다(gh 종료 {code}): {(err or out).strip()[:200]}"
    if not checks:
        # 푸시 직후 수십 초는 CI 가 아직 등록되지 않아 이 모양이다(2026-11-10 에 겪었다).
        return ("이 PR 에 CI 결과가 없습니다 — 방금 푸시했다면 등록을 기다리고, 아니면 "
                "`.github/workflows/check.yml` 이 돌았는지 보세요"
                f" ({(err or '').strip()[:120]})")
    bad = [c for c in checks if c.get("bucket") in ("fail", "cancel")]
    wait = [c for c in checks if c.get("bucket") == "pending"]
    if bad:
        return "CI 실패: " + ", ".join(c["name"] for c in bad) + " — `gh pr checks " + num + "`"
    if wait:
        return ("CI 가 아직 돕니다: " + ", ".join(c["name"] for c in wait)
                + " — 끝난 뒤 다시 머지하세요")
    return None


def main() -> int:
    try:
        data = json.loads(RAW)
    except json.JSONDecodeError:
        return 0  # 훅 입력이 아니다 — 관문이 낄 자리가 아니다
    cmd = (data.get("tool_input") or {}).get("command") or ""
    m = MERGE.search(cmd)
    if not m:
        return 0

    cwd = data.get("cwd") or os.getcwd()
    code, top, _ = run(["git", "rev-parse", "--show-toplevel"], cwd)
    if code != 0:
        return block(f"{cwd} 가 git 저장소가 아닙니다")
    repo = top.strip()

    num = pr_number(m.group("rest"))
    view = ["gh", "pr", "view", *([num] if num else []), "--json", "number,headRefOid,headRefName"]
    code, out, err = run(view, repo)
    if code != 0:
        return block(f"PR 을 읽지 못했습니다: {(err or out).strip()[:200]}")
    pr = json.loads(out)
    num, head, branch = str(pr["number"]), pr["headRefOid"], pr["headRefName"]

    why = check_ci(repo, num)
    if why:
        return block(why)

    trees = worktrees(repo)
    main_tree = trees[0][0] if trees else Path(repo)
    tree = next((p for p, h in trees if h == head), None)
    if tree is None:
        return block(f"PR #{num} 의 머리({head[:7]}, {branch})를 체크아웃한 작업 트리가 없습니다 — "
                     "로컬 검진이 머지할 코드를 볼 수 없습니다. 그 브랜치의 워크트리를 최신으로 "
                     "맞춘 뒤 거기서 머지하세요")
    _, dirty, _ = run(["git", "status", "--porcelain"], tree)
    if dirty.strip():
        return block(f"{tree} 에 커밋하지 않은 변경이 있습니다 — 검진이 PR 과 다른 것을 봅니다")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if not (tree / "backend" / "data" / "apt.db").exists():
        db = (main_tree / "backend" / "data" / "apt.db").as_posix()
        env["DATABASE_URL"] = f"sqlite:///{db}"
    try:
        code, out, err = run([venv_python(tree, main_tree), "-m", "scripts.checkup", "--fast"],
                             tree / "backend", timeout=CHECKUP_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return block(f"검진이 {CHECKUP_TIMEOUT}초 안에 끝나지 않았습니다")
    if code != 0:
        fails = [l for l in out.splitlines() if l.startswith("[X]")] or (err or out).splitlines()[-5:]
        return block(f"{tree} 에서 `checkup --fast` 실패:\n" + "\n".join(fails[:10]))
    print(f"[머지 관문] 통과 — PR #{num} CI 통과, {tree.name} 에서 checkup --fast 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
