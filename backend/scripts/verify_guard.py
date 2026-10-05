"""넣어 둔 검사들이 **실제로 걸리는지** 시험한다.

사용법:
    python -m scripts.verify_guard

## 왜 이 시험이 따로 있나

검사를 넣어 놓고 **안 걸리면 없는 것과 같다.** 실제로 한 번 그랬다.

`verify_absorb` 에 더미 회귀 실패를 잡는 가드를 넣으면서 `try/except` 로 감쌌는데,
정작 겪은 실패(LAPACK `init_gesdd failed init`)는 **예외를 던지지 않았다.**
statsmodels 가 pinv 결과로 그냥 진행했고, 계수는 0 과 NaN 이 섞인 채 돌아왔고,
스크립트는 종료 코드 0 으로 끝나며 비교 네 개를 전부 FAIL 로 찍었다. 메모리 부족이
정확성 실패와 똑같이 보였고, 가드는 한 번도 걸리지 않았다.

이 저장소의 다른 검사들도 사정이 비슷하다. 적재가 매번 깨끗하게 끝나니 **좌표 범위
검사·0건 검사·페이징 상한 검사가 걸리는 것을 한 번도 본 적이 없다.** 그것들이 실제로
동작하는지는 짐작이지 측정이 아니었다.

그래서 실패 모양을 직접 만들어 넣어 본다. 걸려야 할 때 걸리고, **걸리지 말아야 할 때
안 걸리는지**도 같이 본다 — 후자가 없으면 '전부 걸리게' 만들어 놓고 통과했다고 할 수
있다.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

import numpy as np  # noqa: E402

from app.clients import sdsc  # noqa: E402
from app.services import hedonic  # noqa: E402

import ingest_amenity  # noqa: E402
import verify_absorb as V  # noqa: E402


class Case:
    __slots__ = ("name", "fn", "should_raise", "exc")

    def __init__(self, name, fn, should_raise, exc=Exception):
        self.name = name
        self.fn = fn
        self.should_raise = should_raise
        self.exc = exc


def run_group(title: str, cases: list[Case]) -> bool:
    print(f"\n== {title} ==")
    print(f"  {'경우':<34}{'걸려야':>7}{'걸림':>6}  판정")
    ok = True
    for c in cases:
        msg = ""
        try:
            c.fn()
            raised = False
        except c.exc as exc:  # noqa: BLE001
            raised = True
            msg = str(exc).replace("\n", " ")[:62]
        except Exception as exc:  # noqa: BLE001
            raised = True
            msg = f"[다른 예외 {type(exc).__name__}] {exc}"[:62]
        good = raised == c.should_raise
        ok &= good
        print(f"  {c.name:<34}{'O' if c.should_raise else 'X':>7}"
              f"{'O' if raised else 'X':>6}  {'통과' if good else '실패'}")
        if raised and good:
            print(f"      → {msg}...")
    return ok


# ──────────────────────────────────────────────────────────
# 1. verify_absorb — 더미 회귀가 실제로 풀렸는지
# ──────────────────────────────────────────────────────────
SHAPE = (116919, 2055)


def absorb_cases() -> list[Case]:
    def c(params, rss_d, rss_a):
        return lambda: V.check_dummy_fit(np.array(params, dtype=float),
                                         rss_d, rss_a, SHAPE)

    return [
        Case("정상", c([1.0, -2.0, 0.5], 100.0, 100.0), False, V.DummyPathFailed),
        Case("부동소수 오차만큼 다름", c([1.0, -2.0], 100.0000001, 100.0),
             False, V.DummyPathFailed),
        Case("허용 오차 안(0.5%)", c([1.0, -2.0], 100.5, 100.0),
             False, V.DummyPathFailed),
        Case("NaN 섞임", c([1.0, np.nan, 0.5], 100.0, 100.0), True, V.DummyPathFailed),
        Case("inf 섞임", c([1.0, np.inf], 100.0, 100.0), True, V.DummyPathFailed),
        Case("계수가 0 으로 뭉개짐(RSS 악화)", c([0.0, 0.0], 180.0, 100.0),
             True, V.DummyPathFailed),
        Case("조금 악화(2%)", c([1.0, -2.0], 102.0, 100.0), True, V.DummyPathFailed),
    ]


# ──────────────────────────────────────────────────────────
# 2. 소상공인 API — 인증·한도·페이징
# ──────────────────────────────────────────────────────────
class _Resp:
    """httpx.Response 흉내. 본문과 JSON 만 있으면 된다."""

    def __init__(self, payload: dict | None, text: str | None = None):
        import json as _json
        self._payload = payload
        self.text = text if text is not None else _json.dumps(payload or {})
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    """반경 조회 응답을 흉내내는 가짜 클라이언트.

    `total` 과 실제로 돌려줄 `pages` 를 따로 줘서, **총건수에 못 미치는** 상황을
    만들 수 있다. 그게 조용히 적게 세어지는 실패 모양이다.
    """

    def __init__(self, total: int, pages: list[list[dict]]):
        self.total = total
        self.pages = pages
        self.calls = 0

    def get(self, url, params=None, **kw):
        i = int((params or {}).get("pageNo", 1)) - 1
        items = self.pages[i] if i < len(self.pages) else []
        return _Resp({"body": {"totalCount": self.total, "items": items}})


def sdsc_cases() -> list[Case]:
    item = {"lon": 127.0, "lat": 37.2, "indsLclsNm": "음식",
            "indsMclsNm": "주점", "indsSclsNm": "요리 주점"}

    def auth(text):
        return lambda: sdsc._check_auth(text)

    def radius(total, pages):
        return lambda: sdsc.stores_in_radius(
            127.0, 37.2, 500, client=_Client(total, pages)
        )

    return [
        Case("정상 응답", auth('{"body":{"items":[]}}'), False, sdsc.SdscError),
        Case("활용신청 안 됨", auth('{"errMsg":"SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}'),
             True, sdsc.SdscError),
        Case("일일 한도 초과",
             auth('{"errMsg":"LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}'),
             True, sdsc.SdscError),
        Case("페이징 — 한 장에 다 옴", radius(2, [[item, item]]), False, sdsc.SdscError),
        Case("페이징 — 두 장에 나눠 옴", radius(3, [[item, item], [item]]),
             False, sdsc.SdscError),
        Case("페이징 — 총건수에 못 미침", radius(2000, [[item] * 3]),
             True, sdsc.SdscError),
    ]


# ──────────────────────────────────────────────────────────
# 3. 입지 적재 — 좌표 범위
# ──────────────────────────────────────────────────────────
def coord_cases() -> list[Case]:
    class OutOfRange(RuntimeError):
        pass

    def chk(lng, lat):
        def f():
            if ingest_amenity.out_of_range(lng, lat):
                raise OutOfRange(f"({lng}, {lat}) 가 경기 남부 밖")
        return f

    return [
        Case("수원 영통 (정상)", chk(127.0714, 37.2497), False, OutOfRange),
        Case("과천 (정상)", chk(126.9890, 37.4260), False, OutOfRange),
        Case("경도/위도 뒤바뀜", chk(37.2497, 127.0714), True, OutOfRange),
        Case("서울 강북 (범위 밖)", chk(127.0, 37.9), True, OutOfRange),
        Case("0, 0", chk(0.0, 0.0), True, OutOfRange),
    ]


# ──────────────────────────────────────────────────────────
# 4. 요인 유의성 — '검출 안 됨' 경로
# ──────────────────────────────────────────────────────────
def joint_cases() -> list[Case]:
    class NotDetected(RuntimeError):
        pass

    def chk(p):
        def f():
            d = hedonic._joint_fields(p)
            if d.get("significant") is False:
                raise NotDetected(d["joint_note"])
            if d.get("significant") is None and p is not None:
                raise AssertionError("p 를 줬는데 판정이 없습니다")
        return f

    return [
        Case("p=0.0 (뚜렷)", chk(0.0), False, NotDetected),
        Case("p=0.0138 (유흥주점 수준)", chk(0.0138), False, NotDetected),
        Case("p=0.049 (경계 안)", chk(0.049), False, NotDetected),
        Case("p=0.051 (경계 밖)", chk(0.051), True, NotDetected),
        Case("p=0.9 (전혀 아님)", chk(0.9), True, NotDetected),
    ]


# ──────────────────────────────────────────────────────────
# 5. 적재 중단 조건 — 더 돌려도 소용없는 오류인가
# ──────────────────────────────────────────────────────────
def fatal_cases() -> list[Case]:
    """`is_fatal` 은 **메시지 문자열로 가린다.** 클라이언트 쪽 문구를 고치면 이
    판정이 조용히 틀어져, 한도를 넘긴 뒤에도 2,469곳을 끝까지 때리게 된다.
    그래서 가짜 문구가 아니라 **sdsc 가 실제로 던지는 예외**로 시험한다.
    """
    class ShouldStop(RuntimeError):
        pass

    def chk(make_exc):
        def f():
            try:
                make_exc()
            except Exception as exc:  # noqa: BLE001
                if ingest_amenity.is_fatal(exc):
                    raise ShouldStop(str(exc)) from None
        return f

    def auth(text):
        return lambda: sdsc._check_auth(text)

    return [
        Case("활용신청 안 됨 → 멈춰야",
             chk(auth('{"errMsg":"SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}')),
             True, ShouldStop),
        Case("일일 한도 초과 → 멈춰야",
             chk(auth('{"errMsg":"LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}')),
             True, ShouldStop),
        Case("페이징 미달 → 계속해야",
             chk(lambda: sdsc.stores_in_radius(
                 127.0, 37.2, 500,
                 client=_Client(2000, [[{"lon": 127.0, "lat": 37.2}]]))),
             False, ShouldStop),
        Case("일시적 호출 실패 → 계속해야",
             chk(lambda: (_ for _ in ()).throw(
                 sdsc.SdscError("호출 실패(page 1): ReadTimeout "))),
             False, ShouldStop),
    ]


def main() -> int:
    groups = [
        ("verify_absorb — 더미 풀이가 실제로 풀렸나", absorb_cases()),
        ("소상공인 API — 인증·한도·페이징", sdsc_cases()),
        ("입지 적재 — 좌표 범위", coord_cases()),
        ("입지 적재 — 멈출 오류와 넘길 오류", fatal_cases()),
        ("요인 유의성 — '검출 안 됨' 경로", joint_cases()),
    ]
    ok = True
    for title, cases in groups:
        ok &= run_group(title, cases)

    n = sum(len(c) for _, c in groups)
    print(f"\n{'전부 통과' if ok else '실패한 경우가 있습니다'} — {n}개 경우")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
