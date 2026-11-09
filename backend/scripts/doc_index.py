"""에이전트가 처음 읽는 지침서(CLAUDE.md)가 어디 있나 — 검사들이 같은 목록을 쓰게.

지침서는 계층이다. 루트 CLAUDE.md 는 자산과 무관한 방식만 들고, 자산마다 그 자산의
라우팅 표와 규칙을 담은 CLAUDE.md 가 자산 폴더에 있다(`backend/app/<자산>/CLAUDE.md`,
프론트 쪽은 그것을 `@` 로 가져오는 한 줄).

예전에는 검사 셋(verify_docs·verify_sync·checkup)이 각자 `ROOT / "CLAUDE.md"` 하나만
봤다. 지침서를 나누는 순간 셋 다 새 파일을 못 보고 조용히 통과했을 것이다 — 그래서
목록을 여기 한 곳에 두고 셋이 가져다 쓴다.

자산 폴더만 뒤진다. 저장소 전체를 rglob 하면 `node_modules`·`.venv`·`.claude/wt-*` 의
남의 CLAUDE.md 까지 잡는다(남은 워크트리는 옛 지침서 그 자체다).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# `@경로` 한 줄 — Claude Code 가 지침서 안에서 다른 파일을 가져오는 문법.
IMPORT = re.compile(r"^@(\S+)\s*$", re.M)


def agent_guides(root: Path = ROOT) -> list[Path]:
    """루트 CLAUDE.md 와 자산 폴더의 CLAUDE.md 전부. 루트가 맨 앞이다."""
    nested = [*(root / "backend" / "app").rglob("CLAUDE.md"),
              *(root / "frontend" / "src").rglob("CLAUDE.md")]
    return [root / "CLAUDE.md", *sorted(p for p in nested if "__pycache__" not in p.parts)]


def imports_of(path: Path) -> list[tuple[str, Path]]:
    """지침서가 `@` 로 가져오는 파일 — (적힌 글자, 가리키는 경로)."""
    text = path.read_text(encoding="utf-8")
    return [(m.group(1), (path.parent / m.group(1)).resolve()) for m in IMPORT.finditer(text)]
