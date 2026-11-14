"""저장소 건강검진 — **한 명령으로** 뒤처진 곳과 군살을 본다.

사용법:
    python -m scripts.checkup              # 전부
    python -m scripts.checkup --fast       # 느린 검사(적합·전수 대조)는 건너뛴다
    python -m scripts.checkup --only 신선도
    python -m scripts.checkup --no-db      # DB 없이 되는 것만(CI). NEEDS_DB 선언으로 거른다

## 왜 이것이 따로 있나

검증 스크립트가 계속 는다. 하나씩 기억해서 돌리는 구조는 **반드시 뒤처진다** —
이 저장소가 '손으로 유지하는 목록' 에서 이미 당한 것과 같은 함정이다. 그래서 입구를
하나로 둔다.

그 입구가 **또 손으로 유지하는 목록**이었다. 돌릴 스크립트를 여섯 개만 적어 두어
`verify_absorb`·`verify_name_match`·`verify_sync_guard` 가 빠져 있었고, 그동안
`verify_sync_guard` 는 실패하고 있었다(죽은 API 시험이 '못 잡음'). CLAUDE.md 는
"`verify_*` 를 전부 돌린다" 고 적고 있었다. 지금은 `scripts/verify_*.py` 를 **찾아서**
돌린다. 새로 만든 검사는 아무 데도 적지 않아도 돈다.

그리고 기존 검사들이 못 보던 두 축을 더한다.

- **신선도**: 적재가 멈춰도 아무도 모른다. 실거래가 2주째 안 들어와도 화면은 멀쩡히
  뜬다 — 오래된 값으로. 빈 결과가 조용한 것과 같은 이치다.
- **군살**: 뺀 기능의 잔재가 쌓인다. 재 보니 CSS 클래스 300개 중 79개(26%)가 죽어
  있었다 — 향 나침반·A·B 비교처럼 화면에서 뺀 것들이다. 죽은 규칙은 이름이 겹쳐
  **멀쩡한 것을 망가뜨린다**(`.is-thin` 이 실제로 그랬다).

## 심각도

    [X]  고쳐야 한다. 종료 코드 1.
    [!]  살펴볼 것. 사람이 판단한다 — 종료 코드에 영향 없음.
    [OK] 통과.

군살은 **전부 [!]** 다. 지울지는 사람이 정한다 — `realestate/services/aspect.py` 처럼 측정이
자산이라 남기는 것이 있다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "backend"
FRONT = ROOT / "frontend" / "src"
PY = sys.executable

sys.path.insert(0, str(BACKEND))

from scripts.doc_index import agent_guides  # noqa: E402

# 며칠(개월) 지나면 경고할까. **근거를 함께 적는다** — 숫자만 있으면 다음 사람이
# 못 고친다.
STALE = {
    # 실거래 신고 기한이 계약 후 30일이라 1주일쯤 비는 것은 정상이다.
    # 2주가 넘으면 적재가 멈췄을 가능성이 높다.
    "trade_days": 14,
    # R-ONE 은 전월 통계를 다음 달 중순에 낸다. 두 달이 넘게 비면 이상하다.
    "reb_days": 75,
    # 소상공인 상가정보는 분기 갱신이다. 두 분기를 넘기지 않는다.
    "amenity_days": 180,
    # 손으로 받는 CSV(경기도기본통계 주택 현황). **연 단위 통계**라 1년에 한 번
    # 새 해가 붙는다. 400일을 넘겼으면 한 해를 통째로 놓쳤다는 뜻이다.
    # API 가 없어 자동 갱신이 안 된다 — 사람이 받아야 하므로 알려 주는 것이 전부다.
    "manual_csv_days": 400,
    # 멸실을 재는 전수 스냅샷(K-apt·건축물대장). **이것만은 안 뜨면 영영 못 센다.**
    # 다른 적재는 늦게 돌려도 과거 값이 그대로 오지만, 스냅샷은 '그때 무엇이
    # 있었나' 라서 지나가면 복구할 수 없다. 1년에 한 번 뜨면 되므로 400일로 두되,
    # 넘기면 그해 멸실은 **영구히 빈칸**이 된다는 뜻이다.
    "snapshot_days": 400,
    # 한국은행 ECOS 지표는 **지표마다 늦는 정도가 다르다.** 최신 공표통계 한 줄
    # (`reb_days`)은 가장 늦은 달 하나만 보므로, CPI 가 멈춰도 기준금리가 새로
    # 들어오면 지나간다. 그래서 지표별로 본다. 2026-10-13 에 받았을 때 cpi·기준금리는
    # 2026-09, M2 는 2026-07 까지 왔다 — M2 는 두 달 뒤 중순에 나오므로 정상이다.
    # 예금은행 신규취급액 금리(주담대·전세대출·정기예금)는 다음 달 말께 나온다 — 2026-10-19 에
    # 2026-08 까지였다(그 달 말일에서 50일). 75일이면 정상 지연과 겹치지 않는다.
    "ecos_days": {"cpi": 45, "base_rate": 45, "m2": 105,
                  "mortgage_rate": 75, "jeonse_loan_rate": 75, "deposit_rate": 75,
                  # 원/달러 말일자료는 다음 달 첫 영업일에 나온다. 기준금리와 같은 45일.
                  "krw_usd": 45,
                  # 장기 투자의 KOSPI 평가(2026-11-13). 시가총액·PER(901Y014)은 2026-11-13 에 2026-09 까지였다 —
                  # 그 달 말일에서 44일. 다음 달 치는 그 뒤에 나오므로 75일. 국고채 10년은 다음 달 초라 45일.
                  "kospi_mcap": 75, "kospi_per": 75, "kr_10y": 45,
                  # 명목 GDP 는 분기 끝에서 두 달 남짓 뒤 잠정치로 들어온다(속보치는 실질만). 다음 분기 치가 나오기
                  # 직전이면 분기 끝에서 92 + 70일 — 170일을 넘기면 한 분기를 놓쳤다.
                  "kr_gdp": 170},
    # 지수 일봉(stock.db). ECOS·FRED 모두 다음 영업일에 전날 종가가 들어온다. 설·추석 연휴
    # (최장 5거래일)에 주말이 붙으면 9일까지 빈다 — 10일을 넘기면 적재가 멈췄다.
    "stock_days": 10,
    # EDGAR 재무(기술주 가치 탭). 마지막 기간 끝에서 며칠인가로 본다. 3분기(9월 말) 뒤 다음 값은 연간 보고서(10-K)인데,
    # 기한이 연말에서 60일(대형)~90일(소형 — 디웨이브)이다. 9월 말 + 92일 + 90일 = 182일까지가 정상이라 190일.
    "edgar_days": 190,
    # FRED 미국 3개월 국채(월평균)는 다음 달 첫 영업일께 나온다. ECOS 기준금리와 같은 45일.
    "fred_days": {"us_tbill3m": 45,
                  # 금리 월평균·실업률은 다음 달 첫 주에 나온다 — 45일.
                  "us_fedfunds": 45, "us_10y": 45, "us_term_spread": 45, "us_unrate": 45,
                  # 물가는 다음 달 중순, M2 는 넷째 주께 나온다 — 그 달 말일에서 55일 남짓까지 정상이라 75일.
                  "us_cpi": 75, "us_m2": 75,
                  # 자금순환표(Z.1)는 분기 끝에서 10주쯤 뒤에 나온다 — 다음 분기 치 직전이면 92 + 72일. GDP 는 속보가
                  # 분기 끝 한 달 뒤라 92 + 30일. 정부 셧다운이면 늦을 수 있어 둘 다 여유를 둔다.
                  "us_mcap": 170, "us_gdp": 130},
    # 실러 자료(비공식, app/macro/clients/shiller.py). 주가·CAPE 는 달마다 갱신된다 — 2026-11-13 에 2026-10 까지였다.
    # 이익(E)은 발표가 늦어 표 끝 넉 달이 비어 있다(같은 날 2026-06 까지) — 그 달 말일에서 136일. 실러가 손으로
    # 갱신하므로 한두 달 거르는 일이 있어 주가 75일, 이익 200일.
    "shiller_days": {"shiller_p": 75, "shiller_e": 200},
}
def period_end(period: str | None) -> dt.date | None:
    """macro.db 시점의 마지막 날 — 월 'YYYYMM', 분기 'YYYYQn'. 월·분기 통계는 그 기간이 끝나야 셀 수 있다."""
    if not period:
        return None
    y = int(period[:4])
    m = int(period[5]) * 3 if period[4] == "Q" else int(period[4:6])
    return dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)


DEAD_CSS_WARN_PCT = 15.0

# 지침서가 길어지면 손볼 때가 됐다는 신호다. 300줄은 규칙이 아니라 **읽어 볼
# 때**를 알려 주는 선이다 — 세 번 다 '한 문서가 두 가지 일을 한다' 는 것을
# 길어진 뒤에 알아챘다(CLAUDE.md '300줄이 넘으면 손본다' 참조).
DOC_LINES_WARN = 300

# 길어도 되는 문서. **이유를 적어야** 여기 넣는다.
DOC_LONG_OK = {
    "ui-log.md": "시간순 기록이라 쌓이는 것이 정상이다. 나누면 '언제 무엇을 "
                 "시도했나' 가 끊긴다",
    "method.md": "수식과 그 형태를 고른 이유가 한 쌍이라 떼면 둘 다 반쪽이 된다. "
                 "지금 값이 없어 길이가 썩음의 신호가 아니다(문서 첫머리 참조)",
}

# 저장소에 남으면 안 되는 것(스크래치패드에 만들기로 한 것들).
#
# `nul` 을 넣었다가 **4,644개**가 잡혔다. 윈도우에서 `nul` 은 장치 이름이라 어느
# 디렉터리에서든 존재하는 것처럼 보인다. 검사가 거짓 양성을 쏟으면 사람이 안 믿는다.
JUNK = ["*.tmp", "*.orig", "*.rej", "*.bak"]
JUNK_SKIP = (".git", ".venv", "node_modules", "__pycache__", "dist", "build")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, level: str, section: str, msg: str) -> None:
        self.rows.append((level, section, msg))

    @property
    def failed(self) -> int:
        return sum(1 for lv, _, _ in self.rows if lv == "X")

    @property
    def notes(self) -> int:
        return sum(1 for lv, _, _ in self.rows if lv == "!")


# ──────────────────────────────────────────────────────────
# 1) 정합성 — 기존 검증 스크립트를 전부 돌린다
# ──────────────────────────────────────────────────────────
# 돌릴 목록은 **파일에서 찾는다**(`suites()`). 여기에는 보여 줄 이름과 느린지만
# 적는다 — 빠뜨려도 검사는 돌고, 이름이 독스트링 첫 줄로 나올 뿐이다.
# 느림의 근거는 2026-10-18 에 잰 값이다: 적합을 돌리는 것(sync·payloads·absorb 110초),
# DB 전수 대조(name_match 240초), 저장소를 깨뜨려 보며 sync 를 스무 번 남짓 도는 것
# (sync_guard 125초). 나머지는 몇 초다.
SUITE_META = {
    "verify_docs": ("문서 링크·앵커·라우팅 표", False),
    "verify_guard": ("실패 감지가 걸리는지", False),
    "verify_sync": ("코드↔문서↔데이터↔프론트", True),
    "verify_sync_guard": ("싱크 검사가 깨뜨렸을 때 걸리는지", True),
    "verify_spline": ("스플라인 기저", False),
    "verify_absorb": ("고정효과 흡수 vs 더미 회귀", True),
    "verify_listing_parse": ("매물 파서가 주석의 사례대로", False),
    "verify_name_match": ("단지명 매칭 전수 대조", True),
    "verify_payloads": ("페이로드가 JSON 이 되는지", True),
    "verify_supply_cum": ("누적 공급 — 공급 분석과 같은 값", False),
    "verify_reflect": ("반영 분해 — scipy nnls 와 같은 답", False),
    "verify_fit_orphan": ("부모가 죽으면 적합 워커도", False),
}

# 일부러 안 돌리는 검사. **이유를 적어야** 여기 넣는다(DEAD_OK 와 같은 생각).
SUITE_SKIP: dict[str, str] = {}


# 검사마다 DB 가 있어야 하는지 **그 파일이 선언한다** — `NEEDS_DB = True|False`.
# CI(GitHub Actions)에는 적재에 몇 시간 걸린 apt.db 가 없다. 여기에 '어느 것이 DB 를 쓰나'
# 목록을 두면 또 손으로 유지하는 목록이 되고, 새 검사를 더한 사람은 이 파일을 모른다.
# 그래서 선언을 검사 파일에 두고, **선언이 없으면 `[X]`** 로 막는다 — 빠뜨린 검사가 CI 에서
# 'DB 가 없어 죽음' 으로 실패하거나, 반대로 조용히 건너뛰어지지 않게.
NEEDS_DB_RE = re.compile(r"^NEEDS_DB\s*=\s*(True|False)\b", re.M)


def needs_db(name: str) -> bool | None:
    """선언한 값. 선언이 없으면 None."""
    m = NEEDS_DB_RE.search((BACKEND / "scripts" / f"{name}.py").read_text(encoding="utf-8"))
    return None if m is None else m.group(1) == "True"


def suites() -> list[tuple[str, str, bool]]:
    """(모듈, 설명, 느린가). `SUITE_META` 순서를 먼저, 거기 없는 것은 이름순으로 뒤에."""
    found = sorted(p.stem for p in (BACKEND / "scripts").glob("verify_*.py"))
    order = [n for n in SUITE_META if n in found] + [n for n in found if n not in SUITE_META]
    out = []
    for name in order:
        if name in SUITE_SKIP:
            continue
        what, slow = SUITE_META.get(name, (None, False))
        if what is None:
            doc = (BACKEND / "scripts" / f"{name}.py").read_text(encoding="utf-8")
            first = re.search(r'"""\s*(.+)', doc)
            what = (first.group(1).strip("*. ") if first else name)[:28]
        out.append((f"scripts.{name}", what, slow))
    return out


def run_suites(rep: Report, fast: bool, no_db: bool = False) -> None:
    print("\n== 정합성 ==")
    env = {**os.environ, "FIT_IN_PROCESS": "1", "PYTHONIOENCODING": "utf-8"}
    if no_db:
        env["CHECK_NO_DB"] = "1"  # 검사 안에서 DB 를 읽는 절만 건너뛰게(verify_sync 등)
    for mod, what, slow in suites():
        db = needs_db(mod.split(".")[-1])
        if db is None:
            print(f"  {what:<28} NEEDS_DB 선언 없음")
            rep.add("X", "정합성", f"{mod} 에 `NEEDS_DB = True|False` 가 없습니다 — "
                                   "DB 없이(CI) 돌 수 있는지 선언하세요")
            continue
        if no_db and db:
            print(f"  {what:<28} 건너뜀 (DB 필요)")
            continue
        if fast and slow:
            print(f"  {what:<28} 건너뜀 (--fast)")
            continue
        p = subprocess.run([PY, "-m", mod], cwd=BACKEND,
                           capture_output=True, env=env)
        out = p.stdout.decode("utf-8", "replace")
        if p.returncode == 0:
            print(f"  {what:<28} 통과")
            # 통과했어도 `[!]` 는 올린다. 알려진 결함처럼 '사람이 정할 것' 을
            # 스크립트가 말해도, 여기서 버리면 직접 돌려 본 사람만 안다.
            for t in (l for l in out.splitlines() if l.startswith("[!]")):
                rep.add("!", "정합성", f"{mod}: {t[4:]}")
        else:
            # 스크립트마다 실패를 찍는 모양이 다르다(`[X]`·`[FAIL]`·트레이스백). 예전에는
            # `[X]`/`[!]` 줄만 골라서, `verify_payloads` 가 지운 함수를 부르다 죽었을 때도
            # `verify_absorb` 가 `[FAIL]` 을 찍었을 때도 '실패 — 0건' 만 남았다. 고른 줄이
            # 없으면 stderr·stdout 의 끝을 보여 준다 — 왜 실패했는지가 검진에 남아야 한다.
            lines = out.splitlines()
            tail = [l for l in lines if l.lstrip().startswith(("[X]", "[!]", "[FAIL]"))]
            if not tail:
                err = p.stderr.decode("utf-8", "replace").strip().splitlines()
                tail = (err or lines)[-3:]
            print(f"  {what:<28} 실패")
            rep.add("X", "정합성", f"{mod} 실패 — {tail[-1].strip()[:90] if tail else '출력 없음'}")
            for t in tail[:4]:
                print(f"      {t}")


# ──────────────────────────────────────────────────────────
# 2) 신선도 — 적재가 멈춰도 화면은 멀쩡하다
# ──────────────────────────────────────────────────────────
def days_since(d: dt.date | None, today: dt.date) -> int | None:
    return None if d is None else (today - d).days


def check_fresh(rep: Report, today: dt.date) -> None:
    print("\n== 신선도 ==")
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.realestate.models import BldRun, ComplexAmenity, KaptRun, RebStat, Trade

    with SessionLocal() as db:
        last_trade = db.scalar(select(func.max(Trade.deal_date)))
        last_reb = db.scalar(select(func.max(RebStat.ym)))
        oldest_amen = db.scalar(select(func.min(ComplexAmenity.collected_at)))

    def say(label: str, age: int | None, limit: int, fix: str) -> None:
        if age is None:
            print(f"  {label:<16} 비어 있음")
            rep.add("X", "신선도", f"{label} 데이터가 없습니다 → {fix}")
            return
        over = age > limit
        print(f"  {label:<16} {age:>4}일 전 (한계 {limit}일)"
              + ("  뒤처짐" if over else ""))
        if over:
            rep.add("X", "신선도", f"{label} 가 {age}일 전입니다 → {fix}")

    say("최신 실거래", days_since(last_trade, today), STALE["trade_days"],
        "python -m scripts.ingest_trades --months 3")

    reb_date = None
    if last_reb:
        y, m = int(last_reb[:4]), int(last_reb[4:6])
        # 그 달의 말일로 본다 — 월 단위 통계라 하루까지 따질 것이 없다.
        reb_date = (dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1))
    say("최신 공표통계", days_since(reb_date, today), STALE["reb_days"],
        "python -m scripts.ingest_reb")

    from app.macro import store as macro_store
    from app.macro.clients import ecos

    try:
        # 분기 계열(명목 GDP)은 freq 'Q' 로 들어 있다 — 월만 보면 '받은 적 없음' 으로 보인다.
        last_ecos = {**macro_store.last_period(ecos.TABLES), **macro_store.last_period(ecos.TABLES, "Q")}
    except macro_store.MacroMissing as exc:
        rep.add("X", "신선도", str(exc))
        last_ecos = {}
    for metric in ecos.TABLES:
        # 한도가 없는 지표를 더했으면 여기서 멈춘다 — 조용히 빠지지 않게.
        limit = STALE["ecos_days"][metric]
        say(f"ECOS {metric}", days_since(period_end(last_ecos.get(metric)), today), limit,
            f"python -m scripts.ingest_macro --metric {metric}")

    from app.macro.clients import fred
    from app.stock import store as stock_store
    from app.stock.indices import INDICES

    try:
        last_fred = {**macro_store.last_period(fred.SERIES), **macro_store.last_period(fred.SERIES, "Q")}
        last_shiller = macro_store.last_period(STALE["shiller_days"])
    except macro_store.MacroMissing:
        last_fred, last_shiller = {}, {}  # 위 ECOS 에서 이미 [X] 로 알렸다
    for name in fred.SERIES:
        say(f"FRED {name}", days_since(period_end(last_fred.get(name)), today), STALE["fred_days"][name],
            "python -m scripts.ingest_stock")
    for name, limit in STALE["shiller_days"].items():
        say(f"실러 {name}", days_since(period_end(last_shiller.get(name)), today), limit,
            "python -m scripts.ingest_stock")

    try:
        last_bar = stock_store.last_dates()
    except stock_store.StockMissing as exc:
        rep.add("X", "신선도", str(exc))
        last_bar = {}
    for ix in INDICES:
        last = last_bar.get((ix.market, ix.symbol))
        d = dt.date(int(last[:4]), int(last[4:6]), int(last[6:8])) if last else None
        say(f"지수 {ix.label}", days_since(d, today), STALE["stock_days"],
            "python -m scripts.ingest_stock")

    from app.stock.companies import COMPANIES

    try:
        filed = stock_store.last_filed()
    except stock_store.StockMissing:
        filed = {}
    for co in COMPANIES:
        last = last_bar.get((co.market, co.symbol))
        d = dt.date(int(last[:4]), int(last[4:6]), int(last[6:8])) if last else None
        say(f"종목 {co.label}", days_since(d, today), STALE["stock_days"], "python -m scripts.ingest_stock")
        end = filed.get(co.symbol, (None, None))[1]
        d = dt.date(int(end[:4]), int(end[4:6]), int(end[6:8])) if end else None
        say(f"재무 {co.label}", days_since(d, today), STALE["edgar_days"], "python -m scripts.ingest_stock")

    amen_age = days_since(oldest_amen.date() if oldest_amen else None, today)
    say("입지 수집", amen_age, STALE["amenity_days"],
        f"python -m scripts.ingest_amenity --older-than {STALE['amenity_days']}")

    # 손으로 받은 자료. 파일 이름의 날짜를 본다 — 파일 수정 시각은 복사할 때마다
    # 바뀌어서 '언제 받은 자료인가' 를 말해 주지 않는다.
    manual = sorted((ROOT / "backend" / "data" / "manual").glob("gg_housing_*.csv"))
    if not manual:
        rep.add("!", "신선도", "손으로 받은 주택 현황 CSV 가 없습니다 "
                             "(backend/data/manual/README.md 참조)")
        print("  손으로 받은 CSV        없음")
    else:
        stamp = manual[-1].stem.split("_")[-1]
        try:
            got = dt.date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        except ValueError:
            got = None
        say("주택 현황 CSV", days_since(got, today), STALE["manual_csv_days"],
            "backend/data/manual/README.md 의 주소에서 다시 받는다")

    # 전수 스냅샷. 두 번째를 떠야 비로소 멸실이 나온다.
    for label, model, cmd in (
        ("K-apt 스냅샷", KaptRun, "python -m scripts.ingest_kapt_all"),
        ("건축물대장 스냅샷", BldRun, "python -m scripts.ingest_bldrgst"),
    ):
        last = db.scalar(select(func.max(model.taken_on)))
        got = None
        if last and len(last) == 8:
            try:
                got = dt.date(int(last[:4]), int(last[4:6]), int(last[6:8]))
            except ValueError:
                got = None
        if got is None:
            rep.add("!", "신선도", f"{label} 이 아직 없습니다 — {cmd}")
            print(f"  {label:<18} 없음")
            continue
        say(label, days_since(got, today), STALE["snapshot_days"], cmd)
        # 스냅샷이 하나뿐이면 멸실을 아직 못 센다. 고쳐야 할 것은 아니지만
        # **왜 숫자가 없는지**는 보여야 한다.
        runs = db.scalar(select(func.count(func.distinct(model.taken_on)))) or 0
        if runs < 2:
            print(f"      스냅샷이 {runs}개뿐이라 멸실은 아직 셀 수 없습니다 "
                  f"(두 번째부터 나옵니다)")


# ──────────────────────────────────────────────────────────
# 3) 군살 — 뺀 기능의 잔재는 쌓이고, 이름이 겹치면 멀쩡한 것을 망가뜨린다
# ──────────────────────────────────────────────────────────
def dead_css() -> tuple[int, int, list[str]]:
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    # **주석을 먼저 벗긴다.** 안 그러면 규칙은 이미 지웠는데 설명 주석에만 남은
    # 이름이 '죽은 클래스' 로 영영 잡힌다. z-index 사다리 주석이 `.map-dock`·
    # `.chart-tooltip` 을 언급하는데, 그중 `.map-dock` 은 규칙이 없다.
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    # 상태 접두사(is-/has-)는 템플릿 문자열로 붙이는 일이 많아 뺀다.
    names = {c for c in re.findall(r"\.([a-zA-Z][\w-]*)", css)
             if not c.startswith(("hover", "focus", "active", "is-", "has-"))}
    body = "\n".join(p.read_text(encoding="utf-8")
                     for p in list(FRONT.rglob("*.jsx")) + list(FRONT.rglob("*.js")))
    dead = sorted(c for c in names if c not in body)
    return len(names), len(dead), dead


def check_cruft(rep: Report) -> None:
    print("\n== 군살 ==")

    total, n_dead, dead = dead_css()
    pct = n_dead / max(total, 1) * 100
    print(f"  죽은 CSS 클래스    {n_dead}/{total} ({pct:.0f}%)")
    if pct >= DEAD_CSS_WARN_PCT:
        # 접두사로 묶어 보여 준다 — 어느 기능의 잔재인지가 바로 보인다.
        groups: dict[str, int] = {}
        for c in dead:
            groups[c.split("-")[0]] = groups.get(c.split("-")[0], 0) + 1
        top = sorted(groups.items(), key=lambda kv: -kv[1])[:5]
        rep.add("!", "군살", f"죽은 CSS {n_dead}개 ({pct:.0f}%) — 많은 순: "
                             + ", ".join(f"{k}-* {v}개" for k, v in top))
        print("      " + ", ".join(f"{k}-* {v}개" for k, v in top))
        print("      (템플릿 문자열로 붙이는 클래스는 거짓 양성일 수 있다)")

    # 지침서 길이. 넘었다고 틀린 것은 아니라 `[!]` 다 — 사람이 읽어 보고
    # 줄일지·나눌지·그대로 둘지 고른다.
    # docs/ 는 묶음 폴더 아래에 둔다(verify_docs 가 지킨다). 그래서 rglob 이고,
    # 찍을 때는 묶음까지 보이게 docs/ 아래 경로를 쓴다.
    #
    # **CLAUDE.md 도 잰다.** 매 세션이 통째로 읽는 유일한 문서라 길어지는 비용이 가장
    # 크다 — 라우팅 표로 '필요한 것만 읽게' 해 놓고 입구가 뚱뚱해지면 소용이 없다.
    # 2026-10-18 에 규칙이 쌓여 280줄이 되도록 이 검사 밖에 있었다.
    # 자산 폴더의 지침서도 잰다 — 그 폴더를 열면 루트와 함께 통째로 읽힌다.
    docs = [*agent_guides(ROOT), *sorted((ROOT / "docs").rglob("*.md"))]
    long_docs = []
    for d in docs:
        n = len(d.read_text(encoding="utf-8").splitlines())
        if n > DOC_LINES_WARN and d.name not in DOC_LONG_OK:
            long_docs.append((d.relative_to(ROOT / "docs").as_posix()
                              if (ROOT / "docs") in d.parents
                              else d.relative_to(ROOT).as_posix(), n))
    print(f"  긴 지침서       {len(long_docs)}/{len(docs)} "
          f"({DOC_LINES_WARN}줄 넘음)")
    if long_docs:
        rep.add("!", "군살",
                "300줄 넘는 지침서 " + ", ".join(f"{n}({c}줄)" for n, c in long_docs)
                + " — CLAUDE.md 의 '300줄이 넘으면 손본다' 참조")
        for n, c in sorted(long_docs, key=lambda kv: -kv[1]):
            print(f"      {n:<26} {c}줄")

    # 정적 번들. 문서에 적어 두면 또 어긋나므로 **여기서 잰다**(deploy.md 참조).
    # 임계값 근거: GitHub Pages 소프트 한도가 1GB 라 용량 자체는 문제가 아니다.
    # 다만 순위 스냅샷 하나를 휴대폰에서 통째로 받으므로, 한 파일이 3MB 를 넘으면
    # 체감이 나빠진다. 전체는 자릿수가 바뀌는지 보려고 둔다.
    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        files = [p for p in dist.rglob("*") if p.is_file()]
        mb = sum(p.stat().st_size for p in files) / 1e6
        big = sorted((p for p in files if p.stat().st_size > 3e6),
                     key=lambda p: -p.stat().st_size)
        print(f"  정적 번들         {len(files)}개 · {mb:.1f}MB"
              + (f" · 3MB 넘는 파일 {len(big)}개" if big else ""))
        for p in big[:3]:
            rep.add("!", "군살", f"스냅샷 한 파일이 큽니다: "
                                 f"{p.relative_to(dist).as_posix()} "
                                 f"{p.stat().st_size/1e6:.1f}MB")
    else:
        print("  정적 번들         없음 (내보낸 적 없음)")

    fc = BACKEND / "data" / "fitcache"
    if fc.exists():
        files = list(fc.glob("*.pkl"))
        mb = sum(f.stat().st_size for f in files) / 1e6
        print(f"  적합 디스크 캐시   {len(files)}개 · {mb:.1f}MB")

    junk = [
        p for pat in JUNK for p in ROOT.rglob(pat)
        if p.is_file() and not any(x in p.parts for x in JUNK_SKIP)
    ]
    print(f"  저장소 임시 파일   {len(junk)}개")
    for p in junk[:5]:
        rep.add("!", "군살", f"임시 파일이 저장소에 있습니다: "
                             f"{p.relative_to(ROOT).as_posix()}")

    stray = leftover_work_dirs()
    print(f"  남은 작업 폴더    {len(stray)}개")
    for s in stray:
        rep.add("!", "군살", s)


def stray_dirs(claude_dir_children: list[str], worktrees: dict[str, str | None],
               merged: set[str]) -> list[str]:
    """`.claude/` 아래 남은 작업 폴더. 순수 함수라 자체 시험이 쉽다.

    `claude_dir_children` 은 `.claude/` 바로 아래 폴더의 절대 경로(정규화),
    `worktrees` 는 git 이 아는 워크트리 경로 → 브랜치, `merged` 는 main 에 머지된 브랜치.
    """
    out = []
    known = set(worktrees)
    for d in claude_dir_children:
        # worktrees 는 git 이 관리하고, skills 는 저장소에 커밋한 스킬이다(.gitignore 예외).
        if d.endswith(("/worktrees", "/skills")) or d in known:
            continue
        out.append(f"git 이 모르는 작업 폴더 {d.rsplit('/', 1)[-1]} — 옛 CLAUDE.md·코드 "
                   f"사본이 검색에 섞입니다. 쓰는 세션이 없으면 지우세요")
    for path, branch in worktrees.items():
        if branch and branch in merged and "/.claude/" in path:
            out.append(f"워크트리 {path.rsplit('/', 1)[-1]} 의 브랜치 {branch} 는 이미 main 에 "
                       f"머지됐습니다 — 쓰는 세션이 없으면 `git worktree remove`")
    return out


def leftover_work_dirs() -> list[str]:
    """에이전트 세션이 남긴 작업 폴더를 찾는다 — **지우지 않고 알리기만 한다.**

    `.claude/` 는 gitignore 라 ripgrep(Grep 도구)은 건너뛰지만 `grep -r` 는 들어간다.
    2026-10-18 에 문서를 정리하며 `grep -rn` 을 쳤더니 결과의 절반이 `.claude/wt-*`
    여덟 곳과 머지된 워크트리 하나에 든 **옛 CLAUDE.md·옛 코드**였다. 다음 사람(에이전트)
    이 그 사본을 지금 것으로 읽으면 이미 고친 규칙을 따라 한다 — 컨텍스트가 썩는
    가장 조용한 길이다. 다른 세션이 쓰는 중일 수 있으므로 지울지는 사람이 정한다.

    **지우려 하면 '사용 중' 으로 안 지워질 수 있다.** 2026-10-18 에 `wt-*` 여덟 곳이
    전부 그랬는데, 부모 세션이 끝난 뒤에도 살아남은 적합 워커(`multiprocessing-fork`
    로 뜬 python.exe, 부모 pid 가 없다)가 그 폴더의 `backend/` 를 작업 디렉터리로
    쥐고 있었다 — 폴더마다 하나씩, 생성 시각이 폴더와 맞았다. 그 워커를 끝내야 지워진다.
    """
    try:
        lst = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8").stdout
        mg = subprocess.run(["git", "branch", "--merged", "main", "--format=%(refname:short)"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    except OSError:
        return []

    def norm(p: str) -> str:
        return Path(p).resolve().as_posix().lower()

    worktrees: dict[str, str | None] = {}
    cur = None
    for line in lst.splitlines():
        if line.startswith("worktree "):
            cur = norm(line[len("worktree "):])
            worktrees[cur] = None
        elif line.startswith("branch ") and cur:
            worktrees[cur] = line[len("branch refs/heads/"):]
    if not worktrees:
        return []
    main_root = Path(next(iter(worktrees)))  # 첫 줄이 주 체크아웃이다
    cdir = main_root / ".claude"
    # `worktrees/` 안도 본다. 처음엔 그 폴더를 통째로 건너뛰어, git 에서 떨어져 나간
    # 빈 워크트리 폴더 둘(세션이 끝나며 등록만 풀린 것)을 못 잡았다.
    children = [norm(str(p)) for d in (cdir, cdir / "worktrees") if d.exists()
                for p in d.iterdir() if p.is_dir()]
    merged = {b.strip() for b in mg.splitlines() if b.strip() and b.strip() != "main"}
    return stray_dirs(children, worktrees, merged)


SECTIONS = {"정합성": None, "신선도": None, "군살": None}


def main() -> int:
    ap = argparse.ArgumentParser(description="저장소 건강검진")
    ap.add_argument("--fast", action="store_true", help="느린 검사(적합·전수 대조)는 건너뛴다")
    ap.add_argument("--only", choices=list(SECTIONS), help="한 절만")
    ap.add_argument("--today", help="신선도 기준일 (YYYY-MM-DD) — 검사 시험용")
    ap.add_argument("--no-db", action="store_true",
                    help="DB 없이 되는 것만 — NEEDS_DB 인 검사와 신선도를 건너뛴다(CI)")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    rep = Report()
    want = {args.only} if args.only else set(SECTIONS)

    if "정합성" in want:
        run_suites(rep, args.fast, args.no_db)
    if "신선도" in want:
        if args.no_db:
            print("\n== 신선도 ==\n  건너뜀 (--no-db) — 적재일은 DB 에 있다")
        else:
            check_fresh(rep, today)
    if "군살" in want:
        check_cruft(rep)

    print()
    for lv, sec, msg in rep.rows:
        print(f"[{lv}] {sec} · {msg}")
    if rep.failed:
        print(f"\n고쳐야 할 것 {rep.failed}건"
              + (f" · 살펴볼 것 {rep.notes}건" if rep.notes else ""))
        return 1
    print(f"\n이상 없음" + (f" (살펴볼 것 {rep.notes}건)" if rep.notes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
