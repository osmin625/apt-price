"""읽기 전용 응답을 정적 파일로 내보낸다.

## 무엇을 위한 것인가

모델을 돌리는 것과 결과를 보여 주는 것은 필요한 것이 다르다. 적합은 numpy·pandas·
statsmodels 와 11만 건의 실거래, 그리고 수십 초의 계산이 필요하다. 반면 **결과를
보는 쪽은 JSON 한 묶음만 있으면 된다.** 그러니 무거운 쪽은 로컬에 두고, 가벼운
쪽만 어디서나 열리게 만든다.

이 스크립트는 화면이 실제로 부르는 요청을 하나씩 실행해 응답을 파일로 떨어뜨린다.
프론트엔드는 `VITE_DATA_MODE=static` 으로 빌드하면 `/api/...` 대신 그 파일을 읽는다.

## 왜 HTTP 서버를 띄우지 않고 TestClient 인가

서비스 계층을 직접 부르면 라우터가 하는 일(기본값, 검증, 직렬화)을 여기서 다시
구현해야 하고, 그러면 **정적 사이트와 동적 사이트가 조용히 다른 값을 내기** 시작한다.
이 저장소가 가장 경계하는 실패 방식이다.

`TestClient` 는 실제 ASGI 앱을 그대로 호출한다. 라우터·의존성·직렬화가 전부 같은
코드를 지나므로 응답이 구조적으로 같다. 게다가 서버를 띄울 필요가 없어 작업
스케줄러에서 돌리기 쉽다(포트 충돌도, 종료 처리도 없다).

응답은 `r.content` 를 **바이트 그대로** 쓴다. 파싱해서 다시 쓰면 그 순간부터
부동소수점 표기나 키 순서가 달라질 수 있다. 다시 만들지 않는 것이 가장 확실하다.

## 파일 이름 규칙

`api.js` 의 `snapshotPath()` 와 **반드시 같아야 한다.** 한쪽만 바꾸면 화면은 404 를
받고, 그건 "데이터가 없다" 로 보인다 — 조용히 틀리는 쪽이다. 그래서 규칙을 양쪽
주석에 같이 적어 둔다.

    /api/health                          -> health/default.json
    /api/model/factors?months=12         -> model/factors/months=12.json
    /api/complexes/14?months=24          -> complexes/14/months=24.json
    /api/quotes/ranking?basis=market
        &days=7&months=12                -> quotes/ranking/basis=market~days=7~months=12.json

쿼리는 **이름순으로 정렬**해서 이어 붙인다. 프론트엔드는 파라미터를 넣는 순서가
화면마다 다를 수 있으므로, 정렬하지 않으면 같은 요청이 다른 파일을 가리킨다.

## 쓰기가 필요한 것은 내보내지 않는다

매물 붙여넣기(`parse-listing`, `evaluate`)와 삭제는 서버 계산과 DB 쓰기가 필요해
정적 사이트에서 성립하지 않는다. 그런 탭은 아예 숨긴다 — 눌리는데 실패하는 버튼을
두는 것보다 낫다.

## 사용

    python -m scripts.export_static                  # 기본 위치로
    python -m scripts.export_static --out <dir>
    python -m scripts.export_static --no-quotes      # 호가 관련 응답 제외
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = BASE_DIR.parent / "frontend" / "public" / "snapshot"

# 화면의 '분석 기간' 선택지. 여기 없는 기간은 정적 사이트에서 열리지 않는다.
MONTHS = (12, 24, 36)

# 매물 순위의 '확인일자' 선택지. None 은 '전체'(파라미터 없음).
RANK_DAYS = (None, 7, 14, 30)
RANK_BASIS = ("market", "factor")


def qkey(params: dict) -> str:
    """쿼리를 파일 이름 한 조각으로. 규칙은 모듈 주석 참조 — api.js 와 같아야 한다."""
    items = {k: v for k, v in params.items() if v is not None and v != ""}
    if not items:
        return "default"
    return "~".join(f"{k}={items[k]}" for k in sorted(items))


def target_of(out: Path, path: str, params: dict) -> Path:
    """`/api/model/factors`, {months:12} -> <out>/model/factors/months=12.json"""
    rel = path[len("/api/") :] if path.startswith("/api/") else path.lstrip("/")
    return out / rel / f"{qkey(params)}.json"


def quote_complex_ids() -> list[int]:
    """호가가 하나라도 있는 단지. 매물 순위에서 단지명을 누르면 상세로 가므로,
    그 단지들의 상세만 내보내면 된다 — 2,469곳을 전부 내보낼 이유가 없다."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Quote

    with SessionLocal() as db:
        ids = db.execute(select(Quote.complex_id).distinct()).scalars().all()
    return sorted(i for i in ids if i is not None)


class Req(NamedTuple):
    """내보낼 요청 하나.

    `allow_404` 는 **없는 것이 정상인** 응답을 위한 것이다. 도보 경로는 역 정보가
    없는 단지에서 404 가 나는데 그건 고장이 아니다. 프론트도 그때 null 로 받아
    점선 직선을 그린다. 이걸 실패로 세면 매 실행이 실패로 끝나고, 그러면
    **진짜 실패와 구분할 수 없게 된다.**
    """

    path: str
    params: dict
    allow_404: bool = False


def build_plan(with_quotes: bool) -> list[Req]:
    """내보낼 요청 목록. 화면이 부르는 것과 1:1 로 맞춘다."""
    plan: list[Req] = [
        # App 부팅 시
        Req("/api/health", {}),
        Req("/api/complexes/meta/filters", {}),
        # 지도 — 역 마커. 파라미터가 없어 한 개뿐이다.
        Req("/api/map/stations", {}),
    ]

    for m in MONTHS:
        # 시장 분석 — 요인별 보정계수
        plan.append(Req("/api/model/factors", {"months": m}))
        # FitLoading 이 문구를 고르려고 부른다. 정적에서는 곧바로 오지만,
        # 없으면 404 가 콘솔에 남는다.
        plan.append(Req("/api/model/status", {"months": m}))
        # 시장 분석의 도보거리 상세 창과 지도 탭이 같이 쓴다.
        plan.append(Req("/api/model/fit", {"months": m}))
        plan.append(Req("/api/map/complexes", {"months": m}))

    if with_quotes:
        for m in MONTHS:
            for basis in RANK_BASIS:
                for days in RANK_DAYS:
                    plan.append(Req(
                        "/api/quotes/ranking",
                        {"months": m, "basis": basis, "days": days},
                    ))
        for cid in quote_complex_ids():
            for m in MONTHS:
                plan.append(Req(f"/api/complexes/{cid}", {"months": m}))

    return plan


def walk_path_plan(out: Path) -> list[Req]:
    """지도 마커를 눌렀을 때 받는 도보 경로.

    **이 목록은 계획 단계에 알 수 없다.** 지도에 뜨는 단지 집합은
    `/api/map/complexes` 가 정하는데(거래가 있고 좌표가 있는 단지), 여기서 DB 를
    다시 질의하면 그 조건을 재구현하는 셈이라 어긋날 수 있다. 그래서 1단계에서
    내보낸 지도 응답을 **읽어서** 그 id 를 쓴다 — 이미 받아 둔 답이 있으면 다시
    묻지 않는다.

    기간이 달라도 마커 집합은 거의 같지만 완전히 같지는 않다(그 기간에 거래가
    없는 단지는 빠진다). 기간별 파일을 다 모아 합집합을 쓴다. 경로 자체는 기간과
    무관하므로 단지당 한 개면 된다.
    """
    ids: set[int] = set()
    for m in MONTHS:
        f = out / "map" / "complexes" / f"months={m}.json"
        if not f.exists():
            continue
        payload = json.loads(f.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            if item.get("id") is not None:
                ids.add(int(item["id"]))
    return [Req(f"/api/map/walk-path/{i}", {}, allow_404=True) for i in sorted(ids)]


def clear(out: Path) -> int:
    """이전 스냅샷을 지운다. 지난 실행에 있던 파일이 남아 있으면 **오래된 값이
    최신인 척** 보인다 — 화면에는 아무 표시도 나지 않는다.

    실수로 엉뚱한 디렉터리를 비우지 않도록 이름을 확인한다."""
    if not out.exists():
        return 0
    if out.name != "snapshot":
        raise SystemExit(f"안전장치: --out 의 마지막 경로가 'snapshot' 이어야 합니다 ({out})")
    n = sum(1 for _ in out.rglob("*.json"))
    shutil.rmtree(out)
    return n


def git_head() -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR.parent, capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def data_counts() -> dict:
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Complex, Quote, Trade

    with SessionLocal() as db:
        return {
            "trades": db.execute(select(func.count()).select_from(Trade)).scalar_one(),
            "complexes": db.execute(select(func.count()).select_from(Complex)).scalar_one(),
            "quotes": db.execute(select(func.count()).select_from(Quote)).scalar_one(),
            "latest_deal_date": db.execute(select(func.max(Trade.deal_date))).scalar_one(),
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="정적 사이트용 스냅샷 내보내기")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--no-quotes",
        action="store_true",
        help="호가 관련 응답(매물 순위·단지 상세)을 내보내지 않는다",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out: Path = args.out.resolve()
    with_quotes = not args.no_quotes

    say = (lambda *a: None) if args.quiet else print

    # 적합이 무거워서 워커를 띄운다. 스크립트에서는 단일 프로세스가 안전하다 —
    # TestClient 안에서 자식 프로세스를 띄우면 윈도우에서 재수입 문제가 생긴다.
    os.environ.setdefault("FIT_IN_PROCESS", "1")

    from starlette.testclient import TestClient

    from app.main import app

    removed = clear(out)
    if removed:
        say(f"이전 스냅샷 {removed}개 파일 삭제")

    ok = 0
    absent = 0
    failures: list[dict] = []
    total_bytes = 0
    t_all = time.perf_counter()

    def run(plan: list[Req], label: str) -> None:
        """계획 하나를 실행한다. 단계가 둘이라 함수로 뺐다 — 도보 경로 목록은
        1단계 결과(지도 응답)를 읽어야 정해지므로 처음부터 알 수 없다."""
        nonlocal ok, absent, total_bytes
        say(f"{label} — 요청 {len(plan)}건 -> {out}")
        # 도보 경로는 1,851건이라 한 줄씩 적으면 로그가 읽히지 않는다. 묶어서 적는다.
        verbose = len(plan) <= 120
        for i, req in enumerate(plan, 1):
            t0 = time.perf_counter()
            query = {k: v for k, v in req.params.items() if v is not None and v != ""}
            try:
                r = client.get(req.path, params=query, timeout=600)
            except Exception as exc:  # noqa: BLE001
                failures.append({"path": req.path, "params": query, "error": repr(exc)})
                say(f"  [{i}/{len(plan)}] X {req.path} {query} — {exc!r}")
                continue

            dt = time.perf_counter() - t0
            if r.status_code == 404 and req.allow_404:
                # 없는 것이 정상. 파일을 만들지 않고, 프론트는 404 를 받아 null 로 둔다.
                absent += 1
                continue
            if r.status_code != 200:
                failures.append({
                    "path": req.path, "params": query,
                    "status": r.status_code, "body": r.text[:200],
                })
                say(f"  [{i}/{len(plan)}] X {req.path} {query} — HTTP {r.status_code}")
                continue

            dest = target_of(out, req.path, req.params)
            dest.parent.mkdir(parents=True, exist_ok=True)
            # 파싱하지 않고 바이트 그대로 — 다시 만들지 않는 것이 가장 확실하다.
            dest.write_bytes(r.content)
            ok += 1
            total_bytes += len(r.content)
            if verbose:
                kb = len(r.content) / 1024
                say(f"  [{i}/{len(plan)}] {dest.relative_to(out)}  {kb:,.0f}KB  {dt:.2f}s")
        if not verbose:
            say(f"  {label} 완료 — 저장 {ok}건 · 경로 없음 {absent}건")

    with TestClient(app) as client:
        base = build_plan(with_quotes)
        run(base, "1단계: 화면 데이터")
        say("")
        # 2단계는 1단계가 내보낸 지도 응답에서 단지 id 를 읽어 만든다.
        walks = walk_path_plan(out)
        run(walks, "2단계: 도보 경로")

    elapsed = time.perf_counter() - t_all
    attempted = len(base) + len(walks)

    meta = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_head": git_head(),
        "months": list(MONTHS),
        # 지도 탭이 보이는지는 프론트의 VITE_STATIC_MAP 이 정한다. 데이터는 늘 있다.
        "tabs": ["market", "map"] + (["ranking"] if with_quotes else []),
        "includes_quotes": with_quotes,
        "data": data_counts(),
        "files": ok,
        "walk_paths_absent": absent,
        "bytes": total_bytes,
        "export_seconds": round(elapsed, 1),
        "failures": failures,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    say("")
    say(
        f"성공 {ok}/{attempted} · 경로 없음 {absent}건(정상) · "
        f"{total_bytes / 1024 / 1024:.1f}MB · {elapsed:.1f}s"
    )
    if failures:
        # 빈 결과는 조용하다. 실패를 종료 코드로 올려 스케줄러가 알 수 있게 한다.
        say("")
        say(f"실패 {len(failures)}건:")
        for f in failures:
            say(f"  {f['path']} {f.get('params')} — {f.get('status') or f.get('error')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
