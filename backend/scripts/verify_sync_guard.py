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
     # 순위 payload 를 단지/유닛 두 조각으로 나누면서 `premium_pct` 가 사라졌다.
     # 이 시험이 "못 바꿨다" 로 죽어서 알았다 — 시험도 같이 뒤처진다.
     lambda s: s.replace("p.complex", "p.없는키", 1), "없는키", True),
    ("죽은 API — 호출을 지움", "frontend/src/api.js",
     lambda s: s.replace("/model/groups", "/model/groups_DISABLED", 1), "groups"),
    # 실제로 겪은 모양 그대로 — 닫는 `*/` 가 선택자와 함께 지워지면 뒤따르는
    # 규칙들이 주석에 먹힌다. 호가 분석 탭 버튼이 이렇게 죽었다.
    ("CSS — 주석을 닫지 않음", "frontend/src/styles.css",
     lambda s: s.replace("/* 자동 계산 중 표시 — 버튼이 없으니 진행 상태가 보여야 한다 */",
                         "/* 자동 계산 중 표시 — 버튼이 없으니 진행 상태가 보여야 한다", 1),
     "주석이"),  # 파일 끝까지 열리든(1) 규칙을 먹든(2) 둘 중 하나로 잡힌다
    ("CSS — 선택자 자리에 산문", "frontend/src/styles.css",
     lambda s: s.replace(".chip {", "더 높아서 {", 1), "선택자 자리에"),
    # 준공선이 통째로 사라졌던 모양. 쓰는 쪽의 이름을 없는 것으로 바꿔 본다.
    ("CSS 변수 — 없는 것을 쓴다", "frontend/src/components/Charts.jsx",
     lambda s: s.replace("var(--series-1)", "var(--없는변수)", 1), "없는변수"),
    ("문구 — note 에 마크다운", "backend/app/routers/supply.py",
     lambda s: s.replace("적정 공급량은 가구", "**적정 공급량**은 가구", 1), "마크다운"),
    ("조사 — 받침에 안 맞는 조사", "docs/performance.md",
     lambda s: s.replace("**호가 분석**은 쌓인", "**호가 분석**는 쌓인", 1),
     "호가 분석**는"),
    # **걸리지 말아야 할 때** — ㄹ 받침은 '로' 가 맞다('분해 모델로'). 이것까지
    # 잡으면 조사 검사는 전부 잡아 놓고 통과했다고 하는 셈이 된다.
    ("조사 — ㄹ 받침 '로' 는 그냥 둔다(통과해야 함)", "docs/performance.md",
     lambda s: s.replace("모델링 경로,", "분해 모델로 가는 모델링 경로,", 1), None),
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
            if needle is None:
                # **걸리면 안 되는** 경우. 통과해야 맞다.
                good = code == 0
                ok &= good
                print(f"  {name:<34} {'통과' if good else '잘못 잡음'}")
                if not good:
                    tail = [l for l in out.splitlines() if l.startswith("[X]")]
                    print(f"      종료 {code} · 보고 {tail[:2]}")
                continue
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
