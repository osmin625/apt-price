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


def build_plan(with_quotes: bool) -> list[tuple[str, dict]]:
    """내보낼 요청 목록. 화면이 부르는 것과 1:1 로 맞춘다."""
    plan: list[tuple[str, dict]] = [
        # App 부팅 시
        ("/api/health", {}),
        ("/api/complexes/meta/filters", {}),
    ]

    for m in MONTHS:
        # 시장 분석 — 요인별 보정계수
        plan.append(("/api/model/factors", {"months": m}))
        # FitLoading 이 문구를 고르려고 부른다. 정적에서는 곧바로 오지만,
        # 없으면 404 가 콘솔에 남는다.
        plan.append(("/api/model/status", {"months": m}))
        # 시장 분석 — 도보거리 상세 창(산점도 + 같은 단지 안 비교)
        plan.append(("/api/model/fit", {"months": m}))
        plan.append(("/api/map/complexes", {"months": m}))

    if with_quotes:
        for m in MONTHS:
            for basis in RANK_BASIS:
                for days in RANK_DAYS:
                    plan.append((
                        "/api/quotes/ranking",
                        {"months": m, "basis": basis, "days": days},
                    ))
        for cid in quote_complex_ids():
            for m in MONTHS:
                plan.append((f"/api/complexes/{cid}", {"months": m}))

    return plan


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

    plan = build_plan(with_quotes)
    removed = clear(out)
    if removed:
        say(f"이전 스냅샷 {removed}개 파일 삭제")

    say(f"내보낼 요청 {len(plan)}건 -> {out}")
    say("")

    ok = 0
    failures: list[dict] = []
    total_bytes = 0
    t_all = time.perf_counter()

    with TestClient(app) as client:
        for i, (path, params) in enumerate(plan, 1):
            t0 = time.perf_counter()
            query = {k: v for k, v in params.items() if v is not None and v != ""}
            try:
                r = client.get(path, params=query, timeout=600)
            except Exception as exc:  # noqa: BLE001
                failures.append({"path": path, "params": query, "error": repr(exc)})
                say(f"  [{i}/{len(plan)}] X {path} {query} — {exc!r}")
                continue

            dt = time.perf_counter() - t0
            if r.status_code != 200:
                failures.append({
                    "path": path, "params": query,
                    "status": r.status_code, "body": r.text[:200],
                })
                say(f"  [{i}/{len(plan)}] X {path} {query} — HTTP {r.status_code}")
                continue

            dest = target_of(out, path, params)
            dest.parent.mkdir(parents=True, exist_ok=True)
            # 파싱하지 않고 바이트 그대로 — 다시 만들지 않는 것이 가장 확실하다.
            dest.write_bytes(r.content)
            ok += 1
            total_bytes += len(r.content)
            kb = len(r.content) / 1024
            say(f"  [{i}/{len(plan)}] {dest.relative_to(out)}  {kb:,.0f}KB  {dt:.2f}s")

    elapsed = time.perf_counter() - t_all

    meta = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_head": git_head(),
        "months": list(MONTHS),
        "tabs": ["market"] + (["ranking"] if with_quotes else []),
        "includes_quotes": with_quotes,
        "data": data_counts(),
        "files": ok,
        "bytes": total_bytes,
        "export_seconds": round(elapsed, 1),
        "failures": failures,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    say("")
    say(f"성공 {ok}/{len(plan)} · {total_bytes / 1024 / 1024:.1f}MB · {elapsed:.1f}s")
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
