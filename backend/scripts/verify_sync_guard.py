"""싱크·검진 검사가 **일부러 깨뜨렸을 때 걸리는지** 본다.

사용법:
    python -m scripts.verify_sync_guard

저장소 파일을 잠깐 고쳤다가 되돌린다. 끝에 기준 상태로 돌아왔는지도 확인한다.

## 왜 필요한가

넣어 놓고 안 걸리면 없는 것과 같다. 이 시험에서 실제로 둘이 안 걸렸다.

- **계약 검사**가 안 걸렸다 — 시험이 `--no-model` 로 돌려 그 검사를 건너뛰고 있었다
- **죽은 API 검사**가 안 걸렸다 — 경로를 부분 문자열로 찾아서 `/model/groups` 를
  `/model/groups_DISABLED` 로 바꿔도 '살아 있다' 고 했다. 진짜 버그였다

넣어 놓고 안 걸리면 없는 것과 같다 — 이 저장소에서 한 번 당했다.
저장소를 건드리므로 **끝나면 반드시 되돌린다**(try/finally).
"""
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"E:\workspace\apt-price")
PY = str(ROOT / "backend" / ".venv" / "Scripts" / "python.exe")


def run(with_model: bool = False, cmd: list[str] | None = None) -> tuple[int, str]:
    env = {**os.environ, "FIT_IN_PROCESS": "1", "PYTHONIOENCODING": "utf-8"}
    cmd = cmd or (["-m", "scripts.verify_sync"]
                  + ([] if with_model else ["--no-model"]))
    p = subprocess.run([PY, *cmd], cwd=ROOT / "backend",
                       capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def check_freshness() -> bool:
    """신선도는 파일을 고치지 않고 **기준일을 미래로** 줘서 깨뜨린다.

    데이터를 건드리지 않아도 되는 유일한 검사라 이렇게 따로 둔다.
    """
    code, out = run(cmd=["-m", "scripts.checkup", "--only", "신선도",
                         "--today", "2099-01-01"])
    caught = code != 0 and out.count("뒤처짐") >= 3
    print(f"  {'신선도 — 기준일을 미래로':<34} {'잡음' if caught else '못 잡음'}")
    if not caught:
        print(f"      종료 {code}")
    # 되돌릴 것이 없다 — 오늘 기준으로 다시 돌려 통과하는지만 본다
    code2, _ = run(cmd=["-m", "scripts.checkup", "--only", "신선도"])
    if code2 != 0:
        print("      [X] 오늘 기준으로도 실패합니다 — 실제로 뒤처져 있습니다")
        return False
    return caught


def edit(rel: str, fn):
    p = ROOT / rel
    before = p.read_text(encoding="utf-8")
    after = fn(before)
    assert after != before, f"{rel} 를 못 바꿨다"
    tmp = p.with_suffix(p.suffix + ".tmp")
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(after)
    os.replace(tmp, p)
    return p, before


CASES = [
    ("목록 — 테이블을 하나 지움", "docs/architecture.md",
     lambda s: s.replace("ComplexAmenity /", "/", 1), "ComplexAmenity"),
    ("이름 — 문서에 옛 탭 이름", "docs/performance.md",
     lambda s: s + "\n옛 이름 시장 분석 을 적어 본다.\n", "시장 분석"),
    ("계약 — 프론트가 없는 키를 읽음", "frontend/src/components/FactorHint.jsx",
     lambda s: s.replace("parts.premium_pct", "parts.없는키", 1), "없는키", True),
    ("죽은 API — 호출을 지움", "frontend/src/api.js",
     lambda s: s.replace("/model/groups", "/model/groups_DISABLED", 1), "groups"),
]


def main() -> int:
    code, out = run()
    print(f"기준 상태: 종료 코드 {code} ({'통과' if code == 0 else '실패'})")
    if code != 0:
        print("  [X] 깨뜨리기 전부터 실패 상태입니다. 먼저 고치세요.")
        print(out[-800:])
        return 1

    ok = True
    for name, rel, fn, needle, *rest in CASES:
        with_model = bool(rest and rest[0])
        p, before = edit(rel, fn)
        try:
            code, out = run(with_model)
            caught = code != 0 and needle in out
            ok &= caught
            print(f"  {name:<34} {'잡음' if caught else '못 잡음'}")
            if not caught:
                tail = [l for l in out.splitlines() if l.startswith("[X]")]
                print(f"      종료 {code} · 보고 {tail[:2]}")
        finally:
            tmp = p.with_suffix(p.suffix + ".tmp")
            with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(before)
            os.replace(tmp, p)

    ok &= check_freshness()

    code, out = run()
    print(f"\n되돌린 뒤: 종료 코드 {code} ({'통과' if code == 0 else '실패 — 복구 안 됨!'})")
    ok &= code == 0
    print("전부 통과" if ok else "걸리지 않은 검사가 있습니다")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
