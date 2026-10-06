"""경계를 넘는 싱크가 어긋났는지 검사한다 — 코드↔문서, 코드↔데이터, 프론트↔백엔드.

사용법:
    python -m scripts.verify_sync
    python -m scripts.verify_sync --no-model   # 적합을 돌리지 않는다(빠름)

## 왜 필요한가

이 저장소의 검사는 오랫동안 **코드 ↔ 코드**만 봤다. `verify_spline`·`verify_absorb`·
`verify_name_match` 는 전부 "같은 계산의 두 구현이 같은 답을 내나" 다.

그런데 프로젝트가 커지며 실제로 어긋난 자리는 전부 그 바깥이었다. 한 번 손으로 훑어
여덟 군데를 찾았는데, 메커니즘으로 묶으면 다섯이다.

  손으로 유지하는 목록    architecture.md 가 테이블 5/12·스크립트 9/23 만 적고 있었다
  이름 변경의 파급       탭 이름을 바꿨는데 design.md 19곳·README 3곳이 옛 이름이었다
  문서에 얼린 수치       factors.md 안에서 기준이 셋으로 갈렸다
  계약 한쪽만 변경       프론트가 `f.unresolved` 를 읽는데 백엔드가 안 보냈다
  파생이 원천보다 뒤처짐  신규 단지 3곳에 좌표·도보경로·입지가 없었다

손으로 찾았다는 것 자체가 증상이다. 다음 달에 또 손으로 해야 하기 때문이다.

다섯 중 **'문서에 얼린 수치' 만 기계로 못 잡는다.** 그건 `scripts/model_status.py` 와
규칙으로 간다 — 지금 값은 문서에 쓰지 않는다.

## 무엇을 하지 않나

- **죽은 코드를 지우지 않는다.** 보고만 한다. `services/aspect.py` 는 쓰이지 않지만
  측정이 자산이라 남겼다. 지울지는 사람이 정한다.
- **싱크 0 을 목표로 하지 않는다.** 변경과 파급 사이에는 늘 틈이 생긴다. 목표는
  **틈이 조용하지 않게** 하는 것이다.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "backend"
FRONT = ROOT / "frontend" / "src"

sys.path.insert(0, str(BACKEND))

# architecture.md 에 일부러 안 적는 것. 목록이 '전부' 를 뜻하지 않아도 되지만,
# **빠뜨린 것과 일부러 뺀 것은 구분되어야** 한다.
ARCH_SKIP = {
    "__init__.py",
    "probe_reb.py",      # R-ONE 응답을 들여다보는 일회성 도구
    "memo_report.py",    # 메모 사전을 늘릴 때 쓰는 측정 루프
    "verify_sync.py",    # 이 파일. 아래 검사가 자기 자신을 요구하지 않게 한다
}

# 바뀐 UI 이름. 변경 기록(ui-log.md)에는 당시 이름이 맞으므로 거기서는 안 본다.
#
# 이 목록을 손으로 유지하는 것이 모순처럼 보이지만, **실패 모양이 다르다** —
# 여기 안 적으면 그 이름 변경을 못 잡을 뿐이고(검사가 조용해짐), architecture.md
# 목록은 안 적으면 **문서가 거짓말을 한다.** 후자가 훨씬 나쁘다.
RETIRED_LABELS = {
    "시장 분석": "미시 분석",
    "매물 분석": "매물 관리",
    "매크로 탭": "거시 분석 탭",
}
LABEL_EXEMPT = {"ui-log.md"}

# 일부러 남겨 둔 죽은 코드. **이유를 적어야 통과한다** — 그래야 '지우려다 만 것'
# 과 '뜻이 있어 남긴 것' 이 구분된다.
DEAD_OK = {
    "/api/analysis/aspect":
        "향 카드는 뺐지만 측정이 자산이다(칸 안 비교·부트스트랩 퇴화·검출 한계 "
        "±0.78~0.85%p). 호가를 더 모아 다시 볼 때 처음부터 하지 않으려고 남긴다.",
}

# 엔드포인트를 부르는 곳. 프론트가 안 불러도 정적 내보내기가 쓰면 살아 있는 것이다.
CALLER_FILES = [
    FRONT / "api.js",
    BACKEND / "scripts" / "export_static.py",
]


class Result:
    def __init__(self) -> None:
        self.fail: list[str] = []
        self.warn: list[str] = []

    def bad(self, msg: str) -> None:
        self.fail.append(msg)

    def note(self, msg: str) -> None:
        self.warn.append(msg)


def header(title: str) -> None:
    print(f"\n== {title} ==")


# ──────────────────────────────────────────────────────────
# 1. 손으로 유지하는 목록 — architecture.md 가 실물을 다 적었나
# ──────────────────────────────────────────────────────────
def check_lists(r: Result) -> None:
    header("목록 — architecture.md 가 실물을 다 적었나")
    arch = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    def sweep(label: str, names: list[str]) -> None:
        missing = [n for n in names if n not in arch]
        print(f"  {label:<10} 실물 {len(names):>3}개 · 빠짐 {len(missing)}개")
        for n in missing:
            r.bad(f"architecture.md 에 {label} '{n}' 가 없습니다")

    # 테이블: models.py 의 Base 상속 클래스
    src = (BACKEND / "app" / "models.py").read_text(encoding="utf-8")
    tables = [
        n.name for n in ast.parse(src).body
        if isinstance(n, ast.ClassDef)
        and any(getattr(b, "id", "") == "Base" for b in n.bases)
    ]
    sweep("테이블", tables)

    scripts = sorted(
        p.name for p in (BACKEND / "scripts").glob("*.py")
        if p.name not in ARCH_SKIP
    )
    sweep("스크립트", scripts)

    clients = sorted(
        p.name for p in (BACKEND / "app" / "clients").glob("*.py")
        if p.name not in ARCH_SKIP
    )
    sweep("클라이언트", clients)


# ──────────────────────────────────────────────────────────
# 2. 이름 변경의 파급 — 폐기된 UI 이름이 문서에 남아 있나
# ──────────────────────────────────────────────────────────
def check_labels(r: Result) -> None:
    header("이름 — 폐기된 UI 이름이 문서에 남아 있나")
    app = (FRONT / "App.jsx").read_text(encoding="utf-8")
    live = set(re.findall(r"label:\s*'([^']+)'", app))
    print(f"  지금 탭: {' · '.join(sorted(live))}")

    docs = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").glob("*.md"))]
    hits = 0
    for d in docs:
        if d.name in LABEL_EXEMPT:
            continue
        text = d.read_text(encoding="utf-8")
        for old, new in RETIRED_LABELS.items():
            if old in live:
                continue  # 되살아난 이름
            n = text.count(old)
            if n:
                hits += n
                r.bad(f"{d.relative_to(ROOT).as_posix()} 에 옛 이름 '{old}' {n}곳 "
                      f"(지금은 '{new}')")
    print(f"  폐기된 이름 {len(RETIRED_LABELS)}개 검사 · 남은 곳 {hits}")


# ──────────────────────────────────────────────────────────
# 3. 죽은 API — 라우터에 있는데 아무도 안 부르는 엔드포인트
# ──────────────────────────────────────────────────────────
def check_endpoints(r: Result) -> None:
    header("API — 라우터에 있는데 아무도 안 부르나")
    callers = "\n".join(
        p.read_text(encoding="utf-8") for p in CALLER_FILES if p.exists()
    )
    found: list[tuple[str, str]] = []
    for p in sorted((BACKEND / "app" / "routers").glob("*.py")):
        src = p.read_text(encoding="utf-8")
        m = re.search(r'APIRouter\(prefix="([^"]+)"', src)
        if not m:
            continue
        prefix = m.group(1)
        for path in re.findall(r'@router\.(?:get|post|put|delete)\("([^"]*)"', src):
            full = (prefix + path).rstrip("/") or prefix
            found.append((p.name, full))

    dead = []
    for fname, full in found:
        # 경로 변수는 프론트가 문자열을 조립하므로 앞부분만 본다.
        probe = full.split("{")[0].rstrip("/")
        # `api.js` 의 `request()` 가 `/api` 를 붙이므로 프론트에는 `/model/...` 로
        # 적혀 있다. 전체 경로만 찾으면 **살아 있는 엔드포인트를 전부 죽었다고
        # 보고한다** — 처음에 14개를 그렇게 잡았다.
        short = probe[len("/api"):] if probe.startswith("/api") else probe
        # **부분 문자열로 찾으면 안 된다.** `/model/groups` 를 그렇게 찾으면
        # `/model/groups_DISABLED` 도 걸려서, 경로를 잘못 고쳐도 '살아 있다' 고
        # 보고한다. 일부러 깨뜨려 보고 알았다. 뒤에 단어 문자가 오면 다른 경로다
        # (`/` 는 경로 변수가 이어지는 것이므로 허용).
        def called(path: str) -> bool:
            return bool(re.search(re.escape(path) + r"(?![\w-])", callers))

        if probe and not called(probe) and not called(short):
            dead.append((fname, full))
    print(f"  엔드포인트 {len(found)}개 · 호출되지 않음 {len(dead)}개")
    for fname, full in dead:
        if full in DEAD_OK:
            print(f"    (일부러 남김) {full} — {DEAD_OK[full][:46]}...")
            continue
        r.bad(f"{fname}: {full} 를 부르는 곳이 없습니다. 지우거나, 남길 이유를 "
              f"verify_sync.py 의 DEAD_OK 에 적으세요")


# ──────────────────────────────────────────────────────────
# 4. 계약 — 프론트가 읽는 키를 백엔드가 보내나
# ──────────────────────────────────────────────────────────
# (프론트 파일, 접근자 변수, 페이로드를 만드는 함수 이름)
CONTRACTS = [
    ("views/MarketView.jsx", "f", "factor_payload.factors[]"),
    ("components/FactorHint.jsx", "parts", "ranking.factor_parts"),
]


def strip_comments(src: str) -> str:
    """주석을 지운다.

    **주석 안의 접근자를 세면 안 된다.** 죽은 분기를 지우면서 "`f.unresolved` 분기가
    있었다" 고 적어 두었더니, 검사가 그 주석을 읽고 없는 키라고 잡았다. 검사가 거짓
    양성을 내면 사람이 검사를 안 믿게 되고, 그러면 없는 것과 같아진다.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


def payload_keys(months: int = 12):
    """실제 페이로드에서 키를 뽑는다. 적합이 필요하므로 실패하면 None."""
    from app.db import SessionLocal
    from app.services import hedonic, model_view as mv

    if not hedonic.available():
        return None
    with SessionLocal() as db:
        fit = mv.get_fit(db, months=months)
        p = mv.factor_payload(fit)
        factor_keys = set()
        for f in p["factors"]:
            factor_keys |= set(f.keys())
        cid = int(fit["alpha"]["complex_id"].iloc[0])
        area = 84.0
        m = mv.model_price(db, fit, {"complex_id": cid, "exclusive_area": area,
                                     "floor": 10}) or {}
    # 순위표가 호버로 띄우는 분해. `ranking.py` 가 model_price 결과를 추려
    # 담으므로 **model_price 의 키와 다르다** — 그 차이를 모르고 비교하면
    # 멀쩡한 필드를 없다고 잡는다.
    parts = {
        "complex": None, "unit": None, "premium_pct": None,
        "market_count": m.get("market_count"), "trade_count": m.get("trade_count"),
    }
    return {
        "factor_payload.factors[]": factor_keys,
        "model_price": set(m.keys()),
        "ranking.factor_parts": set(parts),
    }


def check_contract(r: Result, months: int) -> None:
    header("계약 — 프론트가 읽는 키를 백엔드가 보내나")
    try:
        keys = payload_keys(months)
    except Exception as exc:  # noqa: BLE001
        print(f"  건너뜀 — 페이로드를 못 만들었습니다 ({type(exc).__name__}: {exc})")
        return
    if keys is None:
        print("  건너뜀 — 모델 의존성이 없습니다")
        return

    for rel, var, payload in CONTRACTS:
        src = strip_comments((FRONT / rel).read_text(encoding="utf-8"))
        used = set(re.findall(rf"\b{var}\.(\w+)", src))
        have = keys[payload]
        missing = sorted(used - have)
        print(f"  {rel:<32} 읽는 키 {len(used):>2} · 없는 키 {len(missing)}")
        for k in missing:
            r.bad(f"{rel} 가 `{var}.{k}` 를 읽는데 {payload} 에 없습니다")


# ──────────────────────────────────────────────────────────
# 5. 파생이 원천보다 뒤처졌나
# ──────────────────────────────────────────────────────────
def check_data(r: Result) -> None:
    header("데이터 — 파생이 원천보다 뒤처졌나")
    try:
        from sqlalchemy import func, select

        from app.db import SessionLocal
        from app.models import Complex, ComplexAmenity
    except Exception as exc:  # noqa: BLE001
        print(f"  건너뜀 ({type(exc).__name__})")
        return

    with SessionLocal() as db:
        holes = [
            ("좌표", db.scalar(select(func.count()).select_from(Complex)
                              .where(Complex.lat.is_(None))) or 0, "scripts.geocode"),
            ("도보경로", db.scalar(select(func.count()).select_from(Complex)
                                .where(Complex.lat.isnot(None),
                                       Complex.walk_seconds.is_(None))) or 0,
             "scripts.route_walk"),
            ("주변 입지", db.scalar(select(func.count()).select_from(Complex)
                                 .where(Complex.lat.isnot(None))
                                 .where(~Complex.id.in_(
                                     select(ComplexAmenity.complex_id)))) or 0,
             "scripts.ingest_amenity"),
        ]
    bad = [(w, n, c) for w, n, c in holes if n]
    print(f"  파생 {len(holes)}가지 · 빈 곳 {len(bad)}가지")
    for w, n, c in bad:
        r.bad(f"{w} 없는 단지 {n}곳 → python -m {c}")


def check_dead_components(r: Result) -> None:
    """아무 데서도 import 하지 않는 컴포넌트.

    이것 때문에 실제로 당했다 — `FactorPrice.jsx` 가 죽은 줄 모르고 거기에 '이 단지
    시세는 중개거래 N건에 기반합니다' 안내를 넣었다. **한 번도 렌더링되지 않았다.**
    """
    header("프론트 — 아무 데서도 import 하지 않는 컴포넌트")
    comps = sorted((FRONT / "components").glob("*.jsx")) + \
        sorted((FRONT / "views").glob("*.jsx"))
    body = "\n".join(
        p.read_text(encoding="utf-8")
        for p in FRONT.rglob("*.jsx")
    ) + "\n".join(p.read_text(encoding="utf-8") for p in FRONT.rglob("*.js"))
    dead = []
    for c in comps:
        name = c.stem
        if name == "App":
            continue
        # 자기 자신의 export 는 빼고 센다
        hits = len(re.findall(rf"from '[^']*{re.escape(name)}'", body))
        if hits == 0:
            dead.append(c.relative_to(FRONT).as_posix())
    print(f"  컴포넌트 {len(comps)}개 · 아무도 안 씀 {len(dead)}개")
    for d in dead:
        if d in DEAD_OK:
            print(f"    (일부러 남김) {d} — {DEAD_OK[d][:46]}...")
            continue
        r.bad(f"{d} 를 import 하는 곳이 없습니다 — 거기 넣은 변경은 화면에 "
              f"나오지 않습니다. 지우거나 DEAD_OK 에 이유를 적으세요")


def main() -> int:
    ap = argparse.ArgumentParser(description="경계를 넘는 싱크 검사")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--no-model", action="store_true",
                    help="적합이 필요한 검사를 건너뛴다")
    args = ap.parse_args()

    r = Result()
    check_lists(r)
    check_labels(r)
    check_endpoints(r)
    check_dead_components(r)
    check_data(r)
    if args.no_model:
        header("계약 — 프론트가 읽는 키를 백엔드가 보내나")
        print("  --no-model 로 건너뜀")
    else:
        check_contract(r, args.months)

    print()
    for w in r.warn:
        print(f"[!] {w}")
    for f in r.fail:
        print(f"[X] {f}")
    if not r.fail:
        print("\n싱크 어긋남 없음"
              + (f" (살펴볼 것 {len(r.warn)}건)" if r.warn else ""))
        return 0
    print(f"\n어긋난 곳 {len(r.fail)}군데")
    return 1


if __name__ == "__main__":
    sys.exit(main())
