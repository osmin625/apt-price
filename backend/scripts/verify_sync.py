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

**화면 문구에 얼린 수치는 잡는다**(`check_frozen_numbers`). 문서와 달리 화면 문구는
모양이 좁다 — 그때 잰 상관(0.352)이나 그때 센 건수(14,509호)다.

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
    "probe_ecos.py",     # ECOS 통계표 코드를 목록과 대조하는 일회성 도구
    "memo_report.py",    # 메모 사전을 늘릴 때 쓰는 측정 루프
    "verify_sync.py",    # 이 파일. 아래 검사가 자기 자신을 요구하지 않게 한다
}

# 바뀐 UI 이름. 변경 기록(ui-log.md)에는 당시 이름이 맞으므로 거기서는 안 본다.
#
# 이 목록을 손으로 유지하는 것이 모순처럼 보이지만, **실패 모양이 다르다** —
# 여기 안 적으면 그 이름 변경을 못 잡을 뿐이고(검사가 조용해짐), architecture.md
# 목록은 안 적으면 **문서가 거짓말을 한다.** 후자가 훨씬 나쁘다.
RETIRED_LABELS = {
    # '시장 분석' → '미시 분석' → '매물 분석' 으로 두 번 옮겼다. 중간 이름도
    # 남겨 둬야 그 단계에서 쓴 문서가 잡힌다.
    "시장 분석": "매물 분석",
    "미시 분석": "매물 분석",
    "매크로 탭": "가격 분석 탭",
    # **되살아난 이름이라 지금은 검사되지 않는다**(아래 `if old in live`). 거시 국면 탭이
    # '거시 분석' 이름을 다시 쓰면서, 옛 뜻(지금의 가격 분석)으로 남은 곳을 기계가 못
    # 가린다. reb.md·pipeline.md 가 공표 통계를 '거시 탭' 이라 부르던 것이 그렇게 남아
    # 있었다(2026-10-18 에 손으로 찾았다). 공표 통계 이야기에 '거시' 가 나오면 의심한다.
    "거시 분석": "가격 분석",
    # '매물 관리'/'매물 순위' 는 짝이라 같이 옮겼다. 붙여넣는 쪽과 보는 쪽이다.
    "매물 관리": "호가 입력",
    "매물 순위": "호가 분석",
}
LABEL_EXEMPT = {"ui-log.md"}

# 일부러 남겨 둔 죽은 코드. **이유를 적어야 통과한다** — 그래야 '지우려다 만 것'
# 과 '뜻이 있어 남긴 것' 이 구분된다.
DEAD_OK = {
    "/api/analysis/aspect":
        "향 카드는 뺐지만 측정이 자산이다(칸 안 비교·부트스트랩 퇴화·검출 한계 "
        "±0.78~0.85%p). 호가를 더 모아 다시 볼 때 처음부터 하지 않으려고 남긴다.",
    "/api/quotes":
        "화면 없이 손으로 부르는 되돌리기(DELETE)다. 잘못 붙여넣은 목록을 통째로 지울 "
        "때 쓴다 — 버튼으로 두기에는 되돌릴 수 없는 일이라 처음부터 화면에 없었다.",
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
    arch = (ROOT / "docs" / "engineering" / "architecture.md").read_text(encoding="utf-8")

    def listed(name: str) -> bool:
        # **부분 문자열로 찾지 않는다.** 예전에는 `n in arch` 였는데, 그러면
        # `clients/kapt.py` 가 빠져 있어도 `ingest_kapt.py` 가 있어서 통과했다.
        # `reb.py`(ingest_reb)·`macro.py`(ingest_macro) 도 같은 식으로 빠진 채였다.
        # 앞이 글자·`_`·`.` 이면 다른 파일 이름의 꼬리다.
        return re.search(r"(?<![\w.])" + re.escape(name) + r"(?!\w)", arch) is not None

    def sweep(label: str, names: list[str]) -> None:
        missing = [n for n in names if not listed(n)]
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

    app = BACKEND / "app"
    sweep("앱", sorted(p.name for p in app.glob("*.py") if p.name not in ARCH_SKIP))
    # 하위 패키지는 **경로째** 찾는다. `quotes.py` 가 routers 와 services 에 둘 다
    # 있어서, 이름만 보면 한쪽이 빠져도 다른 쪽이 대신 통과시킨다.
    for pkg, label in (("routers", "라우터"), ("services", "서비스"), ("clients", "클라이언트")):
        sweep(label, sorted(
            f"{pkg}/{p.name}" for p in (app / pkg).glob("*.py")
            if p.name not in ARCH_SKIP
        ))


# ──────────────────────────────────────────────────────────
# 2. 이름 변경의 파급 — 폐기된 UI 이름이 문서에 남아 있나
# ──────────────────────────────────────────────────────────
def check_labels(r: Result) -> None:
    header("이름 — 폐기된 UI 이름이 문서에 남아 있나")
    app = (FRONT / "App.jsx").read_text(encoding="utf-8")
    live = set(re.findall(r"label:\s*'([^']+)'", app))
    print(f"  지금 탭: {' · '.join(sorted(live))}")

    # **문서만 보면 모자란다.** 탭 이름을 바꾸고도 화면 안의 제목은 그대로여서
    # '호가 입력' 탭에 '매물 관리' 라고 적혀 있었다(아홉 곳). 보는 사람에게는
    # 문서보다 화면이 먼저다. JSX 도 같이 본다 — 주석은 뺀다. 거기 적힌 옛 이름은
    # '왜 바꿨나' 를 남긴 경위 기록이라 지우면 안 된다.
    docs = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md")),
            *sorted(FRONT.rglob("*.jsx"))]
    hits = 0
    for d in docs:
        if d.name in LABEL_EXEMPT:
            continue
        text = d.read_text(encoding="utf-8")
        if d.suffix == ".jsx":
            text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
            text = re.sub(r"(?m)^\s*//.*$", " ", text)
        for old, new in RETIRED_LABELS.items():
            if old in live:
                continue  # 되살아난 이름
            n = text.count(old)
            if n:
                hits += n
                r.bad(f"{d.relative_to(ROOT).as_posix()} 에 옛 이름 '{old}' {n}곳 "
                      f"(지금은 '{new}')")
    print(f"  폐기된 이름 {len(RETIRED_LABELS)}개 검사 · 남은 곳 {hits}")
    check_particles(r, live, docs)


# 받침에 따라 갈리는 조사. 바꾼 이름의 끝 글자가 달라지면 **조사도 틀린다.**
# '매물 순위' → '호가 분석' 으로 바꿨더니 "순위는" 자리에 "분석는" 이 남았고
# ('위' 는 받침이 없고 '석' 은 있다), 문서 넷과 CLAUDE.md 에서 다섯 곳이 그랬다.
# 눈으로는 잘 안 보인다 — 뜻은 통하니까.
_WRONG_AFTER_JONG = {"는": "은", "와": "과", "가": "이", "나": "이나"}
_WRONG_AFTER_VOWEL = {"은": "는", "과": "와", "이": "가", "으로": "로"}


def check_particles(r: Result, live: set[str], docs: list) -> None:
    """바뀐 탭 이름 뒤의 조사가 받침과 맞나.

    `로`/`으로` 는 ㄹ 받침이 예외다('모델로' 가 맞다). 그래서 받침 있는 이름 뒤의
    `로` 는 **ㄹ 받침일 때만** 통과시킨다.
    """
    hits = 0
    targets = [*docs, *sorted(FRONT.rglob("*.jsx"))]
    for d in targets:
        text = d.read_text(encoding="utf-8")
        for label in live:
            jong = (ord(label[-1]) - 0xAC00) % 28 if "가" <= label[-1] <= "힣" else 0
            wrong = dict(_WRONG_AFTER_JONG) if jong else dict(_WRONG_AFTER_VOWEL)
            if jong and jong != 8:
                wrong["로"] = "으로"
            for bad_p, good in wrong.items():
                # `**호가 분석**는` 처럼 강조가 끼어도 잡는다.
                for mid in ("", "**"):
                    needle = label + mid + bad_p
                    n = text.count(needle)
                    if n:
                        hits += n
                        r.bad(f"{d.relative_to(ROOT).as_posix()} 의 "
                              f"'{needle}' {n}곳 — '{label}{mid}{good}' 가 맞습니다")
    print(f"  조사 — 탭 이름 {len(live)}개 뒤를 검사 · 어긋난 곳 {hits}")


# ──────────────────────────────────────────────────────────
# 3. 죽은 API — 라우터에 있는데 아무도 안 부르는 엔드포인트
# ──────────────────────────────────────────────────────────
def _api_wrappers(src: str) -> list[tuple[str, str]]:
    """`api.js` 의 `export const api = { ... }` 를 (이름, 그 항목의 원문) 으로 나눈다."""
    m = re.search(r"export const api = \{\n(.*?)\n\}", src, flags=re.S)
    if not m:
        return []
    out = []
    for chunk in re.split(r"\n(?=  \w+:)", m.group(1)):
        name = re.match(r"\s*(\w+):", chunk)
        if name:
            out.append((name.group(1), chunk))
    return out


def _path_re(path: str) -> str:
    """라우터 경로를 호출 쪽 문자열에서 찾을 정규식으로.

    경로 변수(`{complex_id}`)는 호출 쪽에서 `${id}`(JS)·`{cid}`(f-string)·글자 그대로
    중 하나로 온다. 예전에는 첫 `{` 앞까지만 잘라 찾았는데, 그러면
    `/complexes/{complex_id}/area-types` 가 `/complexes` 로 줄어 **목록 엔드포인트가
    대신 살려 줬다** — 프론트에서 호출을 지운 뒤에도(512bd50) 라우터가 남아 있었다.

    **앞뒤에 단어 문자·`-`·`/` 가 붙으면 다른 경로다.** `/model/groups` 를 부분
    문자열로 찾으면 `/model/groups_DISABLED` 도 걸리고, `/quotes` 는 `/quotes/ranking`
    에, `/complexes` 는 `/map/complexes` 에 걸린다 — 마지막 것이 실제로 단지 목록
    엔드포인트를 살려 두고 있었다.
    """
    var = r"(?:\$\{[^}]+\}|\{[^}]+\}|[^/'\"`?$\s]+)"
    parts = re.split(r"\{[^}]+\}", path)
    return (r"(?<![\w/-])" + var.join(re.escape(x) for x in parts)
            + r"(?![\w/-])")


def check_endpoints(r: Result) -> None:
    header("API — 라우터에 있는데 아무도 안 부르나")
    # **`api.js` 에 적혀 있는 것만으로는 부르는 것이 아니다.** 화면에서 기능을 빼면
    # 컴포넌트는 지워도 `api.js` 의 한 줄은 남기 쉽고, 그 한 줄이 엔드포인트를 살아
    # 있는 것처럼 보이게 했다. A·B 비교를 뺀 뒤(f56aadd) `/model/compare` 와 그 뒤의
    # `compare_listings` 300줄이 그렇게 2주를 남았고, 같은 식으로 엔드포인트 다섯이
    # 더 살아 있는 척했다(2026-10-18 에 지웠다). 그래서 `api.js` 는 **화면이 실제로
    # 부르는 항목만** 호출로 친다.
    api_src = (FRONT / "api.js").read_text(encoding="utf-8")
    users = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [*FRONT.rglob("*.jsx"), *FRONT.rglob("*.js")]
        if p.name != "api.js"
    )
    used_chunks, unused = [], []
    for name, chunk in _api_wrappers(api_src):
        # `api.groups(` 도, 줄을 넘긴 `api` ↵ `.groups(` 도 부르는 것이다.
        if re.search(r"(?<![\w.])api\s*\.\s*" + name + r"(?!\w)", users):
            used_chunks.append(chunk)
        else:
            unused.append(name)
    for name in unused:
        r.bad(f"api.js 의 `{name}` 를 부르는 화면이 없습니다. 지우세요 — 남아 있으면 "
              f"그 엔드포인트가 살아 있는 것처럼 보입니다")

    api_body = re.sub(r"export const api = \{\n.*?\n\}", "", api_src, flags=re.S)
    callers = "\n".join([
        api_body, *used_chunks,
        *(p.read_text(encoding="utf-8") for p in CALLER_FILES
          if p.exists() and p.name != "api.js"),
    ])
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
        # `api.js` 의 `request()` 가 `/api` 를 붙이므로 프론트에는 `/model/...` 로
        # 적혀 있다. 전체 경로만 찾으면 **살아 있는 엔드포인트를 전부 죽었다고
        # 보고한다** — 처음에 14개를 그렇게 잡았다.
        short = full[len("/api"):] if full.startswith("/api") else full
        if not any(re.search(_path_re(x), callers) for x in (full, short)):
            dead.append((fname, full))
    print(f"  엔드포인트 {len(found)}개 · 호출되지 않음 {len(dead)}개"
          f" · api.js 항목 중 부르는 화면이 없음 {len(unused)}개")
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
    # 변수는 `parts` 가 아니라 **합친 `p`** 다. 순위 payload 를 단지/유닛 두 조각으로
    # 나누면서 컴포넌트가 `parts.xxx` 를 더는 읽지 않게 됐고, 그래서 이 검사가
    # **읽는 키 0개**로 조용히 비어 있었다. 계약 검사가 아무것도 안 보고 통과하는
    # 것이 제일 나쁘다 — verify_sync_guard 가 "못 잡음" 을 내서 알았다.
    ("components/FactorHint.jsx", "p", "ranking.factor_parts"),
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
    # `FactorHint` 는 행의 유닛 몫과 단지 몫을 **합쳐서** 읽는다. 둘을 합친 키가
    # 그 컴포넌트가 기대하는 모양이다.
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


# 화면에 **평문으로** 나가는 문자열 필드. 여기에 마크다운을 쓰면 `**` 가 글자
# 그대로 보인다. React 가 문자열을 그대로 렌더하기 때문이고, 툴팁(title 속성)은
# 더 말할 것도 없다.
PLAIN_TEXT_KEYS = ("note", "joint_note", "reason", "note:", "label")


def check_markdown(r: Result) -> None:
    """사용자에게 평문으로 나가는 문구에 마크다운이 섞였나.

    **세 번 같은 실수를 했다** — 학원 요인 노트, `joint_note`, 공급 탭 note. 매번
    브라우저에서 별표를 눈으로 보고서야 알았다. 사람이 발견하기를 기다리는 구조다.

    찾는 방법: 백엔드 소스에서 `"note": "..."` 처럼 평문으로 나가는 키에 붙은
    문자열 리터럴을 모아 `**` 가 있는지 본다. 주석과 독스트링은 화면에 안 나가므로
    제외한다 — 거기서는 강조를 쓰는 것이 이 저장소의 방식이다.
    """
    header("문구 — 평문으로 나가는 곳에 마크다운이 있나")
    import ast

    hits = 0
    files = 0
    for p in sorted((BACKEND / "app").rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        files += 1
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # {"note": "...**...**..."} 형태
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if not (isinstance(k, ast.Constant) and k.value in PLAIN_TEXT_KEYS):
                        continue
                    text = _str_of(v)
                    if text and "**" in text:
                        hits += 1
                        r.bad(f"{p.relative_to(ROOT).as_posix()}:{getattr(v, 'lineno', '?')} "
                              f"— '{k.value}' 에 마크다운(**)이 있습니다. "
                              f"이 문구는 평문으로 렌더됩니다")
    print(f"  파일 {files}개 검사 · 마크다운 섞인 문구 {hits}개")


# 화면 문구에 **그때 잰 값**이 얼어 있나. 이 모양이면 데이터가 바뀌는 순간 문구만
# 그날에 멈춘다. 숫자가 꼭 필요하면 응답에서 그 자리에서 계산해 넣는다.
#
#   0.352 · +0.693     상관·비율처럼 소수 둘째 자리 이상
#   14,509호 · 1,137건  천 단위 쉼표가 붙은 건수
#   실측 1.1616         '실측' 바로 뒤의 숫자
#
# 잡지 못하는 것: 숫자 없이 '과천이 여기다' 처럼 지금 상태를 말하는 문장. 그건
# 사람이 쓸 때 지킨다(CLAUDE.md '추정을 사실처럼 보여 주지 않는다' 옆의 규칙).
FROZEN_RE = re.compile(
    r"(?<![\d.\w])[+\-−]?0\.\d{2,}"
    r"|\d{1,3}(?:,\d{3})+\s*(?:호|건|곳)"
    r"|실측\s*[\d.]+"
)
# 사용자 문구가 담기는 백엔드 키
USER_TEXT_KEYS = ("note", "joint_note", "reason", "read", "what", "why", "caveat", "hint")
# 일부러 둔 것. **이유를 적어야 통과한다**(DEAD_OK 와 같은 생각). 키는 '파일:값'.
FROZEN_OK: dict[str, str] = {}


def _jsx_text(src: str) -> list[tuple[int, str]]:
    """주석과 `{...}` 식을 걷어 낸 줄. 템플릿 리터럴의 `${...}` 도 걷는다 —
    그 자리는 데이터에서 계산되는 값이라 얼린 것이 아니다."""
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    src = re.sub(r"(^|[^:'\"`])//[^\n]*", r"\1", src)
    out = []
    for i, line in enumerate(src.split("\n"), 1):
        line = re.sub(r"\$\{[^}]*\}", "", line)
        line = re.sub(r"\{[^{}]*\}", "", line)
        if re.search(r"[가-힣]", line):
            out.append((i, line))
    return out


def check_frozen_numbers(r: Result) -> None:
    """화면 문구(백엔드 note·read 등, 프론트 JSX)에 그때 잰 값이 얼어 있나.

    한 번 손으로 훑었더니 열 곳이 넘었다. 화면 머리말은 '가장 센 상관 0.45' 라고
    하는데 같은 탭의 백엔드 note 는 0.42 라고 하고 있었다 — 둘 다 그날 잰 값을
    적어 둔 것이고, 하나만 고쳐졌다.
    """
    header("문구 — 화면 문구에 그때 잰 값이 얼어 있나")
    import ast

    hits = 0

    def hit(where: str, text: str) -> None:
        nonlocal hits
        for m in FROZEN_RE.finditer(text):
            if f"{where.split(':')[0]}:{m.group(0)}" in FROZEN_OK:
                continue
            hits += 1
            r.bad(f"{where} — 화면 문구에 얼린 값 '{m.group(0)}'. 데이터가 바뀌면 "
                  f"문구만 그날에 멈춥니다 — 빼거나 응답에서 계산해 넣으세요")

    for p in sorted((BACKEND / "app").rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value in USER_TEXT_KEYS:
                        text = _str_of(v)
                        if text:
                            hit(f"{p.relative_to(ROOT).as_posix()}:{getattr(v, 'lineno', '?')}", text)

    for p in sorted(FRONT.rglob("*.jsx")):
        for i, line in _jsx_text(p.read_text(encoding="utf-8")):
            hit(f"{p.relative_to(ROOT).as_posix()}:{i}", line)
    print(f"  얼린 값 {hits}개")


def _str_of(node) -> str:
    """상수 문자열과 이어 붙인 리터럴만 본다. f-string·변수는 건너뛴다."""
    import ast

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _str_of(node.left) + _str_of(node.right)
    return ""


# 화면에 펼쳐 둔 설명의 길이. **설명은 호버(`Hint`)로 접는다** — 2026-10-18 에 탭마다
# 카드 아래 두세 줄짜리 `p.sub`·`muted small` 이 깔려 그림보다 글이 먼저 보였다(문단
# 서른 곳 남짓). 화면에 남는 것은 제목과 값, 한 줄짜리 상태뿐이다.
#
# 60자는 '한 줄' 의 선이다 — 카드 폭 300px 남짓에서 작은 글씨 두 줄이 넘으면 설명이다.
# 세는 것은 **고정 글자**뿐이다. `{...}` 로 그 자리에서 계산해 넣는 값과 `<Hint>` 안은
# 세지 않는다 — 앞은 데이터이고 뒤는 이미 접혀 있다.
LONG_COPY_LIMIT = 60

# 일부러 펼쳐 둔 긴 문단. **이유를 적어야 통과한다.** 키는 '파일:첫 20자'.
LONG_COPY_OK: dict[str, str] = {}

_COPY_TAG = re.compile(r'<(p|div|span)\s+className="([^"]*)"[^>]*>(.*?)</\1>', re.S)


def _static_copy(inner: str) -> str:
    inner = re.sub(r"<Hint[\s>].*?</Hint>", " ", inner, flags=re.S)
    prev = None
    while prev != inner:
        prev = inner
        inner = re.sub(r"\{[^{}]*\}", " ", inner)
    inner = re.sub(r"<[^>]+>", " ", inner)
    return re.sub(r"\s+", " ", inner).strip()


def check_long_copy(r: Result) -> None:
    """설명 문단(`sub`·`muted`)이 화면에 길게 펼쳐져 있나 — 있으면 `Hint` 로 접는다."""
    header("문구 — 화면에 펼쳐 둔 긴 설명")
    hits = 0
    for p in sorted(FRONT.rglob("*.jsx")):
        src = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), p.read_text(encoding="utf-8"),
                     flags=re.S)
        for m in _COPY_TAG.finditer(src):
            if not ({"sub", "muted"} & set(m.group(2).split())):
                continue
            text = _static_copy(m.group(3))
            if len(text) <= LONG_COPY_LIMIT:
                continue
            rel = p.relative_to(FRONT).as_posix()
            if f"{rel}:{text[:20]}" in LONG_COPY_OK:
                continue
            hits += 1
            line = src[: m.start()].count("\n") + 1
            r.bad(f"{rel}:{line} 화면에 펼쳐 둔 설명 {len(text)}자 — '{text[:30]}…'. "
                  f"제목 옆 <Hint> 로 접으세요(긴 설명은 호버로)")
    print(f"  {LONG_COPY_LIMIT}자 넘게 펼쳐 둔 설명 {hits}곳")


def check_css(r: Result) -> None:
    """CSS 가 **구문으로** 성한가.

    죽은 규칙을 지우다 주석을 깨뜨린 적이 두 번 있다. 지운 범위가 주석 중간에서
    시작해 닫는 `*/` 를 같이 데려갔고, 남은 선택자가 주석 안으로 빨려 들어갔다.

        /* `:not(.is-empty)` 가 있어야 한다. ... 특이도가
           더 높아서 {              <- `*/` 와 `.cmp-summary` 가 함께 지워졌다
          display: flex; ...

    그 뒤 `.spec` `.caret` `.cmp-actions` `.chip` 까지 **열두 규칙이 주석 안에서**
    조용히 죽었다. 호가 분석 탭의 알약 버튼이 브라우저 기본 버튼으로 돌아갔는데
    오류는 하나도 나지 않았다 — 사용자가 "버튼이 못생겨졌다" 고 말해 줘서 알았다.

    죽은 CSS 검사는 이것을 못 잡는다. 주석을 벗기고 세므로 **주석에 먹힌 규칙은
    애초에 없는 것처럼 보인다.** 그래서 구문을 따로 본다.
    """
    header("CSS — 구문이 성한가")
    import re as _re

    css_files = sorted(FRONT.rglob("*.css"))
    hits = 0
    for p in css_files:
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(ROOT).as_posix()

        # 1) 닫히지 않은 주석. 여는 것과 닫는 것을 **순서대로** 따라간다 —
        #    개수만 세면 주석 본문에 적힌 `/*` 에 속는다(실제로 있다).
        pos, open_at = 0, None
        while True:
            o, c = text.find("/*", pos), text.find("*/", pos)
            if o == -1 and c == -1:
                break
            if o != -1 and (c == -1 or o < c):
                open_at = o if open_at is None else open_at
                pos = o + 2
            else:
                open_at, pos = None, c + 2
        if open_at is not None:
            hits += 1
            r.bad(f"{rel}:{text[:open_at].count(chr(10)) + 1} — 주석이 닫히지 "
                  f"않았습니다. 뒤따르는 규칙이 통째로 죽습니다")

        # 2) 주석이 **규칙을 통째로 먹은** 경우. 닫는 기호가 뒤쪽 주석의 것으로
        #    이어져 버리면 파일 끝까지 열려 있지는 않으므로 1)로는 안 잡힌다.
        #    주석 본문에 선언 블록(`{` 뒤 `prop: value;` 두 줄 이상)이 있으면
        #    설명이 아니라 먹힌 CSS 다. 지금 저장소의 주석 65개 중 걸리는 것은 0개다.
        for cm in _re.finditer(r"/\*.*?\*/", text, flags=_re.S):
            body = cm.group(0)
            if "{" not in body:
                continue
            tail = body[body.index("{"):]
            # 줄머리로 고정하면 안 된다 — 이 저장소 CSS 는 한 줄 규칙이 많아
            # `.live { animation: ...; }` 같은 것을 통째로 놓친다(시험에서 걸렸다).
            if len(_re.findall(r"[a-z-]+\s*:\s*[^;{}]{1,60};", tail)) >= 2:
                hits += 1
                r.bad(f"{rel}:{text[:cm.start()].count(chr(10)) + 1} — 주석이 "
                      f"규칙을 먹었습니다. 그 안의 CSS 는 적용되지 않습니다")

        clean = _re.sub(r"/\*.*?\*/", "", text, flags=_re.S)

        # 2) 중괄호 수지
        if clean.count("{") != clean.count("}"):
            hits += 1
            r.bad(f"{rel} — 중괄호가 맞지 않습니다 "
                  f"({clean.count('{')} 열고 {clean.count('}')} 닫음)")

        # 3) 선택자 자리에 한국어 산문. 잘린 주석이 선택자가 된 모양이다.
        for m in _re.finditer(r"([^{}]+)\{", clean):
            sel = m.group(1).strip()
            if not sel or sel.startswith("@") or sel.endswith(")"):
                continue
            if _re.search(r"[가-힣]", sel) or ";" in sel:
                hits += 1
                r.bad(f"{rel} — 선택자 자리에 '{sel[:40]}' 가 있습니다. "
                      f"지우다 만 주석으로 보입니다")
    print(f"  CSS {len(css_files)}개 검사 · 깨진 곳 {hits}")
    check_css_vars(r)


def check_css_vars(r: Result) -> None:
    """화면이 `var(--무엇)` 을 쓰는데 그 변수가 정의되어 있나.

    **없는 변수를 쓰면 선이 통째로 사라진다.** 공급 파이프라인의 준공선이 그랬다 —
    `var(--series-3)` 으로 그렸는데 styles.css 에는 `--series-1`·`--series-2` 밖에
    없었다. 값이 없으면 그 속성이 무효가 되고, SVG `stroke` 의 기본값은 `none` 이라
    **오류 없이 안 그려진다.** 범례 색칠도 같이 비었다.

    눈으로는 "선이 둘뿐이네" 로 보일 뿐이라 사용자가 말해 주기 전에는 모른다.
    실제로 그렇게 알았다.

    템플릿 문자열로 만드는 이름(`var(--series-${i})`)은 접두사까지만 보고 넘어간다 —
    i 가 몇까지 갈지는 정적으로 알 수 없다. 대신 **고정된 이름**은 전부 본다.
    """
    header("CSS 변수 — 화면이 쓰는 것이 정의되어 있나")
    import re as _re

    css = "\n".join(p.read_text(encoding="utf-8") for p in sorted(FRONT.rglob("*.css")))
    defined = set(_re.findall(r"(--[\w-]+)\s*:", css))

    used: dict[str, list[str]] = {}
    for p in sorted(FRONT.rglob("*.jsx")):
        text = p.read_text(encoding="utf-8")
        for m in _re.finditer(r"var\(\s*(--[\w-]+)\s*\)", text):
            name = m.group(1)
            # `--series-${ki + 1}` 처럼 만들다 만 이름은 건너뛴다.
            if "$" in name or "{" in name:
                continue
            used.setdefault(name, []).append(
                f"{p.relative_to(ROOT).as_posix()}:{text[:m.start()].count(chr(10)) + 1}")

    missing = sorted(n for n in used if n not in defined)
    for n in missing:
        r.bad(f"{used[n][0]} 가 `var({n})` 를 쓰는데 CSS 에 없습니다 — "
              f"그 속성은 무효가 되고 선·색이 조용히 사라집니다")
    print(f"  정의 {len(defined)}개 · 화면이 쓰는 고정 이름 {len(used)}개 · "
          f"없는 것 {len(missing)}개")

    # 템플릿으로 만드는 이름은 접두사로 센다. `--series-` 를 쓰면서 3까지 가는데
    # 2까지만 정의된 것이 이번 사고였다.
    prefixes = {m.group(1) for p in sorted(FRONT.rglob("*.jsx"))
                for m in _re.finditer(r"var\(\s*(--[\w-]+?)\$\{", p.read_text(encoding="utf-8"))}
    for pre in sorted(prefixes):
        n = len([d for d in defined if d.startswith(pre) and d[len(pre):].isdigit()])
        print(f"  `{pre}*` 를 만들어 쓰는 곳이 있습니다 — 지금 정의된 번호 {n}개")


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


# ──────────────────────────────────────────────────────────
# 6. 문서가 적은 실행법·이름이 아직 실물과 맞나
# ──────────────────────────────────────────────────────────
# 에이전트도 사람도 **문서를 먼저 읽고 그대로 따라 한다.** 그래서 문서에 남은 옛
# 명령·옛 이름은 틀린 지시가 된다. 이름을 바꾼 쪽에서는 아무것도 깨지지 않으므로
# 아무도 모른다 — 문서가 썩는 가장 흔한 길이다.

# 그때 이름이 맞는 기록이라 지금 이름과 대조하지 않는 문서.
HISTORY_DOCS = {"ui-log.md"}

# 문서가 부르지만 **우리 코드에 없는 것이 정상인** 이름. 이유를 적어야 통과한다.
NAME_OK = {
    "A_2024_00156": "reb.md '살펴보고 버린 표' 의 R-ONE 표 코드 — 안 쓰기로 한 표다",
    "A_2024_00549": "reb.md '살펴보고 버린 표' 의 R-ONE 표 코드 — 안 쓰기로 한 표다",
    "ConsoleHost": "deploy.md 스케줄러 충돌 조사에 나온 윈도우 모듈 이름",
    "formId": "south-supply.md 의 국토교통 통계누리 주소 인자 — 남의 사이트다",
    "regime.macro_model": "macro-model.md 가 걷은 합산 모델(2026-10-18)의 옛 자리를 적은 것 — "
                   "그 방식은 scripts/cv_macro.py 에만 남아 있다",
}

# 이름을 찾을 곳. 키가 든 `backend/.env` 와 `*.local` 은 **읽지 않는다.**
_NAME_SOURCES = [
    ROOT / "backend" / ".env.example", ROOT / "frontend" / ".env.example",
    ROOT / "frontend" / ".env.static", ROOT / "frontend" / "package.json",
    ROOT / "frontend" / "vite.config.js", ROOT / "frontend" / "index.html",
]
_CODE_EXT = (".py", ".js", ".jsx", ".css", ".ps1")
_PATH_EXT = (*_CODE_EXT, ".md", ".json", ".tsv", ".csv")
_FILE_SUFFIX = {"dll", "exe", "log", "db", "env", "txt", "html", "local", "static", "sh",
                "bat", "md", "json", "py", "js", "jsx", "css", "ps1", "tsv", "csv", "pyc"}


def _doc_files() -> list[Path]:
    return [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md")),
            BACKEND / "data" / "manual" / "README.md"]


def _code_files() -> list[Path]:
    return [p for p in [*(BACKEND / "app").rglob("*.py"), *(BACKEND / "scripts").glob("*.py"),
                        *FRONT.rglob("*.js"), *FRONT.rglob("*.jsx"), *FRONT.rglob("*.css"),
                        *ROOT.glob("*.ps1"), *(ROOT / "tools").glob("*.js"),
                        *(ROOT / "tools").glob("*.py")]
            if "__pycache__" not in p.parts]


def _ps1_params(src: str) -> set[str]:
    return {m.lower() for m in re.findall(
        r"\[(?:switch|string|int|double|bool|datetime)(?:\[\])?\]\s*\$(\w+)", src, flags=re.I)}


# `--months 24 --refetch-all` 처럼 값이 붙어도 다음 플래그를 값으로 삼키지 않게 한다.
_CMD_PY = re.compile(
    r"python -m scripts\.(\w+)((?:[ \t]+--[\w-]+(?:[ \t=](?!-)[^\s`'\"#|)]+)?)*)")
_CMD_NPM = re.compile(r"npm run ([\w:-]+)")
_CMD_PS = re.compile(r"\.\\(\w+)\.ps1((?:[ \t]+-\w+)*)")


def check_commands(r: Result) -> None:
    """문서·주석이 적은 실행법이 실제로 돌아가나 — 모듈·플래그·npm 스크립트·ps1 인자.

    `scripts.<이름> --플래그` 의 플래그는 그 스크립트 소스에 따옴표째로 있어야 한다
    (argparse 의 `"--flag"`). 플래그 이름을 바꾸면 그 스크립트는 멀쩡히 돌고 **문서만
    옛 이름을 가르친다** — 따라 친 사람만 `unrecognized arguments` 를 본다.
    """
    header("명령 — 문서·주석이 적은 실행법이 실물과 맞나")
    pkg = __import__("json").loads((ROOT / "frontend" / "package.json")
                                   .read_text(encoding="utf-8")).get("scripts", {})
    srcs: dict[Path, str] = {}

    def src_of(p: Path) -> str:
        if p not in srcs:
            srcs[p] = p.read_text(encoding="utf-8", errors="replace")
        return srcs[p]

    n = bad = 0
    for d in [*_doc_files(), *_code_files()]:
        text = src_of(d)
        rel = d.relative_to(ROOT).as_posix()
        for m in _CMD_PY.finditer(text):
            n += 1
            mod = BACKEND / "scripts" / f"{m.group(1)}.py"
            if not mod.exists():
                bad += 1
                r.bad(f"{rel} 가 `python -m scripts.{m.group(1)}` 를 적는데 그 스크립트가 없습니다")
                continue
            for fl in re.findall(r"(?<![\w-])--[\w-]+", m.group(2)):
                if f'"{fl}"' not in src_of(mod) and f"'{fl}'" not in src_of(mod):
                    bad += 1
                    r.bad(f"{rel} 가 `scripts.{m.group(1)} {fl}` 를 적는데 그 플래그가 없습니다")
        for m in _CMD_NPM.finditer(text):
            n += 1
            if m.group(1) not in pkg:
                bad += 1
                r.bad(f"{rel} 가 `npm run {m.group(1)}` 를 적는데 package.json 에 없습니다")
        for m in _CMD_PS.finditer(text):
            n += 1
            ps = ROOT / f"{m.group(1)}.ps1"
            if not ps.exists():
                bad += 1
                r.bad(f"{rel} 가 `{m.group(1)}.ps1` 를 적는데 그 스크립트가 없습니다")
                continue
            params = _ps1_params(src_of(ps))
            for fl in re.findall(r"-(\w+)", m.group(2)):
                if fl.lower() not in params:
                    bad += 1
                    r.bad(f"{rel} 가 `{m.group(1)}.ps1 -{fl}` 를 적는데 그 인자가 없습니다")
    print(f"  명령 {n}개 · 어긋남 {bad}")


def _looks_like_code(tok: str) -> bool:
    """백틱 안의 낱말 중 **코드 이름처럼 생긴 것**만 본다. `_` 가 들었거나, `()` 가
    붙었거나, 낙타 표기다. 그냥 영단어(`sample`, `basis`)까지 보면 거짓 양성이 쏟아진다."""
    name = tok[:-2] if tok.endswith("()") else tok
    return bool(re.fullmatch(r"[A-Za-z_]\w*", name)) and (
        "_" in name or tok.endswith("()") or re.search(r"[a-z][A-Z]", name) is not None)


def check_doc_names(r: Result) -> None:
    """문서가 백틱으로 부르는 코드 이름·파일 경로가 아직 있나.

    `_undo_ytd()`·`HH_SCALE`·`regime.hist_z`·`components/Modal.jsx` 같은 것이다. 함수나
    파일 이름을 바꾸면 코드는 전부 따라가는데 문서는 따라가지 않는다 — 그리고 다음에
    그 문서를 읽은 사람(에이전트)은 없는 이름을 찾아 헤매거나, 더 나쁘면 **옛 이름으로
    새것을 만든다.** 2026-10-18 에 재 보니 걸린 것 다섯이 전부 거짓 양성이었다
    (`NAME_OK` 셋, 설정 파일에만 있는 환경 변수 둘). 지금 깨끗할 때 막아 둔다.
    """
    header("이름 — 문서가 부르는 코드 이름·경로가 아직 있나")
    # verify_sync_guard 는 **없는 이름을 일부러 적은** 시험 파일이라 뺀다. 넣으면 그
    # 시험이 넣은 가짜 이름이 '코드에 있다' 로 통과해 검사가 안 걸린다(실제로 그랬다).
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in [*_code_files(), *(s for s in _NAME_SOURCES if s.exists())]
                       if p.name != "verify_sync_guard.py")
    have = {p.name for p in _code_files()}
    bases = [ROOT, BACKEND, BACKEND / "app", FRONT, ROOT / "frontend"]

    def exists(word: str) -> bool:
        # 환경 변수는 문서에 `DATABASE_URL`, 코드(pydantic Settings)에 `database_url` 로 있다.
        return any(re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", corpus)
                   for w in {word, word.lower()} if w)

    n = 0
    hits: list[str] = []
    for d in _doc_files():
        if d.name in HISTORY_DOCS:
            continue
        rel = d.relative_to(ROOT).as_posix()
        for tok in sorted(set(re.findall(r"`([^`\n]{2,80})`", d.read_text(encoding="utf-8")))):
            tok = tok.strip()
            if tok in NAME_OK:
                continue
            # 경로: `components/Modal.jsx`, `backend/scripts/ingest_supply.py`
            if "/" in tok and tok.endswith(_PATH_EXT) and not re.search(r"[*<>{}$ ]", tok):
                n += 1
                if not any((b / tok).exists() for b in [*bases, d.parent]):
                    hits.append(f"{rel} 의 경로 `{tok}` 가 없습니다")
                continue
            # 파일 이름만: `pricing.py` — 어딘가에 그 이름의 코드 파일이 있어야 한다
            if re.fullmatch(r"[\w-]+\.(py|jsx?|css|ps1)", tok):
                n += 1
                if tok not in have:
                    hits.append(f"{rel} 의 파일 `{tok}` 가 없습니다")
                continue
            # `regime.hist_z`, `Complex.lat`, `pricing.rcs_basis()` — 점 뒤 이름을 본다
            m = re.fullmatch(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)(\(\))?", tok)
            if m and m.group(2).lower() in _FILE_SUFFIX:
                continue  # `clr.dll`·`sync_static.log` — 파일 이름이지 '모듈.이름' 이 아니다
            if m:
                n += 1
                if not exists(m.group(2)):
                    hits.append(f"{rel} 의 `{tok}` — `{m.group(2)}` 가 코드에 없습니다")
                continue
            if _looks_like_code(tok):
                n += 1
                name = tok[:-2] if tok.endswith("()") else tok
                if not exists(name):
                    hits.append(f"{rel} 의 `{tok}` 가 코드에 없습니다")
    for h in hits:
        r.bad(h + " — 이름을 바꿨으면 문서도 따라 고치세요(일부러면 NAME_OK 에 이유를)")
    print(f"  문서가 부르는 이름·경로 {n}개 · 없는 것 {len(hits)}")


def check_exemptions(r: Result) -> None:
    """예외 목록이 **아직 있는 것**을 가리키나.

    예외는 '이것은 일부러다' 라는 기록이다. 가리키던 것이 사라지면 기록만 남아 다음
    사람이 '이 엔드포인트는 일부러 남겼다' 를 믿고 찾아 헤맨다. 그리고 같은 이름이 다시
    생기면 **검사 없이 통과한다** — 예외가 엉뚱한 것을 덮는다.
    """
    header("예외 — 예외 목록이 아직 있는 것을 가리키나")
    stale: list[str] = []
    routers = "\n".join(p.read_text(encoding="utf-8")
                        for p in (BACKEND / "app" / "routers").glob("*.py"))
    for key in DEAD_OK:
        if key.startswith("/api/"):
            tail = key[len("/api"):]
            # `/api/quotes` 처럼 prefix 만인 엔드포인트도 있다 — 경로 끝 조각으로 찾는다
            last = "/" + tail.rsplit("/", 1)[-1]
            if last not in routers:
                stale.append(f"DEAD_OK 의 `{key}` — 그런 엔드포인트가 없습니다")
        elif not (FRONT / key).exists():
            stale.append(f"DEAD_OK 의 `{key}` — 그런 컴포넌트가 없습니다")
    for name in ARCH_SKIP:
        if not any((BACKEND / sub / name).exists() for sub in ("scripts", "app")):
            stale.append(f"ARCH_SKIP 의 `{name}` — 그런 파일이 없습니다")
    docs = {p.name for p in (ROOT / "docs").rglob("*.md")}
    for name in {*LABEL_EXEMPT, *HISTORY_DOCS}:
        if name not in docs:
            stale.append(f"`{name}` 를 예외로 두는데 그런 문서가 없습니다")
    for key in FROZEN_OK:
        f, _, val = key.partition(":")
        p = ROOT / f
        if not p.exists() or val not in p.read_text(encoding="utf-8"):
            stale.append(f"FROZEN_OK 의 `{key}` — 그 파일이나 값이 없습니다")
    doc_text = "\n".join(p.read_text(encoding="utf-8") for p in _doc_files())
    for name in NAME_OK:
        if f"`{name}`" not in doc_text:
            stale.append(f"NAME_OK 의 `{name}` — 이제 어느 문서도 부르지 않습니다")
    # checkup 의 DOC_LONG_OK — 다른 파일에 있으므로 소스에서 키를 읽는다
    ck = (BACKEND / "scripts" / "checkup.py").read_text(encoding="utf-8")
    m = re.search(r"DOC_LONG_OK = \{(.*?)\n\}", ck, flags=re.S)
    for name in re.findall(r'^\s+"([\w.-]+\.md)":', m.group(1) if m else "", flags=re.M):
        if name not in docs:
            stale.append(f"checkup.DOC_LONG_OK 의 `{name}` — 그런 문서가 없습니다")
    n = (len(DEAD_OK) + len(ARCH_SKIP) + len(LABEL_EXEMPT) + len(FROZEN_OK)
         + len(NAME_OK))
    print(f"  예외 {n}개 · 사라진 것을 가리킴 {len(stale)}")
    for s in stale:
        r.bad(s + " — 예외를 지우세요")


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
    check_markdown(r)
    check_frozen_numbers(r)
    check_long_copy(r)
    check_css(r)
    check_commands(r)
    check_doc_names(r)
    check_exemptions(r)
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
