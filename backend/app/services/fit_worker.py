"""헤도닉 적합을 **별도 프로세스**에서 돌린다.

## 왜

적합은 14초쯤 걸리는데, 그 대부분이 numpy/statsmodels 안에서 GIL 을 쥔 채 도는
연산이다. FastAPI 가 동기 엔드포인트를 스레드풀에 넘겨도 GIL 은 풀리지 않으므로,
적합이 도는 동안 **다른 모든 요청이 같이 멈춘다**. 실제로 적합 중에 `/api/complexes`
가 1.4초 → 29초로 늘어나는 것을 확인했다.

프로세스를 나누면 GIL 이 갈라진다. 요청 스레드는 결과를 기다리며 블록되지만 GIL 을
쥐고 있지 않으므로, 그 사이 다른 요청은 정상 속도로 처리된다.

## 설계 메모

- **워커는 자기 세션을 연다.** SQLAlchemy 세션·커넥션은 프로세스 경계를 넘길 수 없다.
  넘기는 것은 `(months, spec)` 뿐이고 결과는 피클로 돌아온다(119KB, 3ms).
- **워커 1개.** 적합은 무거워서 여러 개를 동시에 돌릴 이유가 없고, 같은 키의 동시
  요청은 `_inflight` 로 묶어 한 번만 계산한다.
- **풀은 재사용한다.** 윈도우는 spawn 이라 자식이 pandas/statsmodels 를 다시
  import 하는 데 몇 초 걸린다. 풀을 살려 두면 그 비용은 첫 적합 한 번뿐이다.
- **실패하면 인프로세스로 떨어진다.** 프로세스 생성이 막힌 환경에서도 앱은 돌아야
  한다. 느려질 뿐 기능이 죽지는 않는다.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
from concurrent.futures import Future, ProcessPoolExecutor

log = logging.getLogger(__name__)

# 적합 하나가 이보다 오래 걸리면 뭔가 잘못된 것이다(정상 14초 안팎).
FIT_TIMEOUT_S = float(os.environ.get("FIT_TIMEOUT_S", "600"))
# 디버깅용 탈출구. 1 이면 예전처럼 요청 스레드에서 그대로 돈다.
IN_PROCESS = os.environ.get("FIT_IN_PROCESS", "").strip() in {"1", "true", "yes"}

_lock = threading.Lock()
_pool: ProcessPoolExecutor | None = None
_inflight: dict[tuple, Future] = {}

# 이 프로세스가 **워커 자신**인지. 풀을 만들 때 초기화 함수로 켠다.
_IS_WORKER = False


def _mark_worker() -> None:
    global _IS_WORKER
    _IS_WORKER = True


def is_worker() -> bool:
    """이 프로세스가 적합 워커인가.

    ## 모듈 전역만으로는 못 막는다

    `_IS_WORKER` 는 `app.services.fit_worker` 라는 **모듈 객체**에 붙은 값이다. 워커가
    같은 모듈을 다른 이름으로(다른 sys.path 경로로) 한 번 더 import 하면 전역이 둘이
    되고, `run()` 이 읽는 쪽은 여전히 False 다. 그러면 워커가 풀을 또 만든다.

    실제로 그렇게 됐다. 프로세스 목록에서 앱(18008) → 워커(4356) → **또 워커(3336)**
    가 잡혔고, 3336 의 커맨드라인은 `spawn_main(parent_pid=4356)` 이었다. 워커가 워커에
    적합을 맡기고 기다리는 동안 서버 전체가 멈췄다.

    `multiprocessing.parent_process()` 는 모듈 정체성과 무관하게 **프로세스 단위**로
    답한다 — 메인 프로세스에서만 None 이고, spawn/fork 로 뜬 자식에서는 항상 부모가
    잡힌다. 어떤 경로로 import 되었든 이 판정은 흔들리지 않는다.
    """
    if _IS_WORKER:
        return True
    try:
        return multiprocessing.parent_process() is not None
    except Exception:  # 아주 오래된/특이한 런타임 대비
        return False


def compute(months: int, spec: str) -> dict:
    """적합 본체. **자식 프로세스에서 실행된다** — 모듈 최상위 함수여야 피클된다.

    세션을 인자로 받지 않고 직접 여는 이유는 위 모듈 주석 참조.
    """
    from ..db import SessionLocal
    from . import hedonic

    with SessionLocal() as db:
        rows = hedonic.load_rows(db, months=months)
    return hedonic.fit(rows, spec=spec)


def _pool_unlocked() -> ProcessPoolExecutor:
    global _pool
    # 워커는 풀을 만들지 않는다. `run()` 에서 이미 걸러지지만, 풀이 생기는 곳은 여기
    # 한 곳뿐이므로 여기에도 못을 박아 둔다 — 한 번 뚫려서 서버가 멈춘 적이 있다.
    if is_worker():
        raise RuntimeError("적합 워커 안에서는 워커를 또 만들지 않는다")
    if _pool is None:
        # 시작 방식을 명시한다. 플랫폼 기본값에 맡기면 리눅스에서 fork 가 걸려
        # 부모의 DB 커넥션·스레드 상태를 그대로 물려받는다.
        _pool = ProcessPoolExecutor(
            max_workers=1,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_mark_worker,
        )
    return _pool


def shutdown() -> None:
    """앱 종료 시 워커를 정리한다. 안 하면 리로드 때 프로세스가 남는다."""
    global _pool
    with _lock:
        pool, _pool = _pool, None
        _inflight.clear()
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def run(months: int, spec: str, key: tuple) -> dict:
    """적합을 워커에 맡기고 결과를 받는다.

    `key` 는 호출자의 캐시 키다. 같은 키로 동시에 들어온 요청은 **하나의 계산을
    공유한다** — 안 그러면 탭 두 개만 열어도 14초짜리 적합이 두 번 돈다.
    """
    if IN_PROCESS or is_worker():
        return compute(months, spec)

    with _lock:
        fut = _inflight.get(key)
        mine = fut is None
        if mine:
            try:
                fut = _pool_unlocked().submit(compute, months, spec)
            except Exception:
                log.exception("적합 워커를 띄우지 못했습니다. 인프로세스로 돌립니다.")
                return compute(months, spec)
            _inflight[key] = fut

    try:
        return fut.result(timeout=FIT_TIMEOUT_S)
    except Exception:
        # 워커가 죽으면(메모리·강제종료) 풀 전체가 망가진다. 버리고 다시 만든다.
        global _pool
        with _lock:
            if _pool is not None:
                _pool.shutdown(wait=False, cancel_futures=True)
                _pool = None
        log.exception("적합 워커 실패. 이번 요청은 인프로세스로 처리합니다.")
        return compute(months, spec)
    finally:
        with _lock:
            if _inflight.get(key) is fut:
                _inflight.pop(key, None)
