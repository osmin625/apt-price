"""CLI 스크립트 모음.

윈도우 기본 콘솔 코드페이지(cp949)는 '—' 같은 문자를 인코딩하지 못해
print 한 줄에서 UnicodeEncodeError 로 스크립트가 죽는다. 패키지를 import 하는
시점에 표준 출력을 UTF-8로 고정해 둔다 — 스크립트마다 반복하지 않으려고 여기 둔다.
"""

import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 파이프로 리디렉션된 경우 등
        pass


# 의존성은 backend/.venv 에만 설치된다. 시스템 파이썬으로 스크립트를 돌리면
# 'No module named sqlalchemy' 만 나와서 원인을 짐작하기 어렵다. 먼저 잡아서
# 무엇을 어떻게 실행해야 하는지 알려 준다.
try:
    import sqlalchemy  # noqa: F401
except ImportError:
    _venv = Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe"
    _hint = (
        f'  "{_venv}" -m scripts.<스크립트명>'
        if _venv.exists()
        else "  setup.bat 을 먼저 실행해 의존성을 설치하세요."
    )
    print(
        "\n의존성을 찾을 수 없습니다.\n"
        f"지금 실행에 쓰인 파이썬: {sys.executable}\n\n"
        "이 프로젝트의 라이브러리는 시스템 파이썬이 아니라 backend/.venv 에 설치됩니다.\n"
        "다음 중 하나로 실행하세요.\n\n"
        f"{_hint}\n"
        "  또는 먼저 가상환경 활성화: .venv\\Scripts\\activate\n",
        file=sys.stderr,
    )
    raise SystemExit(1)
