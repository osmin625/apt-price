"""적합 워커가 **부모가 죽으면 같이 끝나는지** 본다.

사용법:
    python -m scripts.verify_fit_orphan

## 왜

`services/fit_worker.py` 의 워커는 부모가 강제 종료되면 고아로 남았다. 2026-10-18 에
부모 없는 워커 8개가 잡혔고, 각자 `.claude/wt-*/backend` 를 작업 디렉터리로 쥐고 있어
워크트리를 지울 수 없었다. 지금은 워커가 부모의 센티널을 기다리다 스스로 끝난다
(`fit_worker._watch_parent`).

정상 종료 경로(`shutdown()`)는 매번 잘 돌았다. 문제는 **강제 종료**에서만 나고, 그건
아무도 일부러 해 보지 않는다. 그래서 여기서 일부러 한다 — 부모를 띄워 풀을 만들게
하고, 부모를 TerminateProcess 로 죽인 뒤 워커 pid 가 사라지는지 본다.

## 세 가지를 본다

1. **대조군** — 감시 없는 맨 `ProcessPoolExecutor` 의 워커는 부모가 죽어도 **남아야**
   한다. 안 남으면 이 환경에서는 고아가 생기지 않는 것이라, 아래 '사라졌다' 가 고친
   덕인지 알 수 없다. 이 검사가 걸릴 수 있다는 증거다.
2. **부모가 살아 있는 동안** 워커도 살아 있어야 한다. 감시가 헛걸려 멀쩡한 워커를
   죽이면 적합마다 spawn 비용(몇 초)을 다시 문다 — 걸리지 말아야 할 때 안 걸리는지.
3. **부모를 죽이면** 워커가 몇 초 안에 사라져야 한다.

고치기 전 코드(`_watch_parent` 호출을 뺀 것)로 돌리면 3 이 실패하는 것을 확인했다.

여기서 죽이는 프로세스는 **이 스크립트가 띄운 것뿐**이다. 대조군 워커는 남기 마련이라
끝에 직접 거둔다 — 안 그러면 이 검사가 고아를 만든다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# 부모 역할. `-c` 로 띄우면 spawn 이 자식에서 메인 모듈을 다시 돌리지 않는다.
PARENT = r"""
import multiprocessing, os, sys, time
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, sys.argv[2])
from app.services import fit_worker
if sys.argv[1] == "bare":
    pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
else:
    pool = fit_worker._pool_unlocked()
print(pool.submit(os.getpid).result(timeout=120), flush=True)
time.sleep(600)
"""

ALIVE_S = 3.0  # 부모가 살아 있는 동안 워커가 버티는지 볼 시간
GONE_S = 5.0  # 부모를 죽인 뒤 워커가 사라지기를 기다릴 상한. 실측은 1초 안쪽이다.


if os.name == "nt":
    import ctypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.restype = ctypes.c_void_p

    def alive(pid: int) -> bool:
        h = _k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            _k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            _k32.CloseHandle(ctypes.c_void_p(h))

    def kill(pid: int) -> None:
        h = _k32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if h:
            _k32.TerminateProcess(ctypes.c_void_p(h), 1)
            _k32.CloseHandle(ctypes.c_void_p(h))
else:
    import signal

    def alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        # 좀비(거둬 가지 않은 종료 프로세스)도 kill 0 에는 살아 있다고 답한다.
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            return stat.rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return True

    def kill(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def wait_gone(pid: int, limit: float) -> float | None:
    """사라질 때까지 걸린 초. `limit` 안에 안 사라지면 None."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        if not alive(pid):
            return time.monotonic() - t0
        time.sleep(0.1)
    return None


def trial(mode: str) -> dict:
    """부모를 띄워 워커 pid 를 받고, ALIVE_S 동안 지켜본 뒤 부모를 죽인다."""
    p = subprocess.Popen([sys.executable, "-c", PARENT, mode, str(BACKEND)],
                         stdout=subprocess.PIPE, text=True)
    wpid = None
    try:
        wpid = int(p.stdout.readline())
        t0 = time.monotonic()
        stayed = True
        while time.monotonic() - t0 < ALIVE_S:
            if not alive(wpid):
                stayed = False
                break
            time.sleep(0.2)
        p.kill()
        p.wait()
        gone = wait_gone(wpid, GONE_S)
        return {"stayed": stayed, "gone": gone}
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        if wpid is not None and alive(wpid):
            kill(wpid)


def main() -> int:
    ok = True

    def check(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"  {name:<36}{'통과' if passed else '[X] 실패'}  {detail}")

    print("\n== 적합 워커 — 부모가 죽으면 같이 끝나나 ==")
    bare = trial("bare")
    check("대조군: 감시 없는 워커는 남는다",
          bare["gone"] is None,
          "남음" if bare["gone"] is None
          else f"{bare['gone']:.1f}초 만에 사라짐 — 이 환경에서는 고아가 안 생겨 검사가 무의미")

    fit = trial("fit")
    check("부모가 살아 있는 동안 워커도 산다",
          fit["stayed"], f"{ALIVE_S:.0f}초 관찰" if fit["stayed"] else "부모보다 먼저 끝남")
    check("부모를 죽이면 워커도 끝난다",
          fit["gone"] is not None,
          f"{fit['gone']:.1f}초 만에 끝남" if fit["gone"] is not None
          else f"{GONE_S:.0f}초가 지나도 남음 — 고아")

    print(f"\n{'전부 통과' if ok else '실패한 경우가 있습니다'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
