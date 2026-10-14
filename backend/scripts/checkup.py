"""저장소 건강검진 — **한 명령으로** 뒤처진 곳과 군살을 본다.

사용법:
    python -m scripts.checkup              # 전부
    python -m scripts.checkup --fast       # 적합이 필요한 것은 건너뛴다
    python -m scripts.checkup --only 신선도

## 왜 이것이 따로 있나

검증 스크립트가 여덟 개가 됐다. 하나씩 기억해서 돌리는 구조는 **반드시 뒤처진다** —
이 저장소가 '손으로 유지하는 목록' 에서 이미 당한 것과 같은 함정이다. 그래서 입구를
하나로 둔다.

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

군살은 **전부 [!]** 다. 지울지는 사람이 정한다 — `services/aspect.py` 처럼 측정이
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
    "ecos_days": {"cpi": 45, "base_rate": 45, "m2": 105},
}
DEAD_CSS_WARN_PCT = 15.0

# 지침서가 길어지면 손볼 때가 됐다는 신호다. 300줄은 규칙이 아니라 **읽어 볼
# 때**를 알려 주는 선이다 — 세 번 다 '한 문서가 두 가지 일을 한다' 는 것을
# 길어진 뒤에 알아챘다(CLAUDE.md '300줄이 넘으면 손본다' 참조).
DOC_LINES_WARN = 300

# 길어도 되는 문서. **이유를 적어야** 여기 넣는다.
DOC_LONG_OK = {
    "ui-log.md": "시간순 기록이라 쌓이는 것이 정상이다. 나누면 '언제 무엇을 "
                 "시도했나' 가 끊긴다",
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
# (모듈, 설명, 적합이 필요한가)
SUITES = [
    ("scripts.verify_docs", "문서 링크·앵커·라우팅 표", False),
    ("scripts.verify_guard", "실패 감지가 걸리는지", False),
    ("scripts.verify_sync", "코드↔문서↔데이터↔프론트", True),
    ("scripts.verify_spline", "스플라인 기저", False),
    ("scripts.verify_listing_parse", "매물 파서가 주석의 사례대로", False),
    ("scripts.verify_payloads", "페이로드가 JSON 이 되는지", True),
]


def run_suites(rep: Report, fast: bool) -> None:
    print("\n== 정합성 ==")
    env = {**os.environ, "FIT_IN_PROCESS": "1", "PYTHONIOENCODING": "utf-8"}
    for mod, what, needs_fit in SUITES:
        if fast and needs_fit:
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
            tail = [l for l in out.splitlines() if l.startswith(("[X]", "[!]"))]
            print(f"  {what:<28} 실패")
            rep.add("X", "정합성", f"{mod} 실패 — {len(tail)}건")
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

    from app.db import SessionLocal
    from app.models import BldRun, ComplexAmenity, KaptRun, RebStat, Trade

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

    from app.clients import ecos

    with SessionLocal() as db:
        last_ecos = dict(db.execute(
            select(RebStat.metric, func.max(RebStat.ym))
            .where(RebStat.metric.in_(list(ecos.TABLES)))
            .group_by(RebStat.metric)).all())
    for metric in ecos.TABLES:
        # 한도가 없는 지표를 더했으면 여기서 멈춘다 — 조용히 빠지지 않게.
        limit = STALE["ecos_days"][metric]
        last = last_ecos.get(metric)
        d = None
        if last:
            y, m = int(last[:4]), int(last[4:6])
            d = dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)
        say(f"ECOS {metric}", days_since(d, today), limit,
            f"python -m scripts.ingest_macro --metric {metric}")

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
    docs = sorted((ROOT / "docs").glob("*.md"))
    long_docs = []
    for d in docs:
        n = len(d.read_text(encoding="utf-8").splitlines())
        if n > DOC_LINES_WARN and d.name not in DOC_LONG_OK:
            long_docs.append((d.name, n))
    print(f"  긴 지침서       {len(long_docs)}/{len(docs)} "
          f"({DOC_LINES_WARN}줄 넘음)")
    if long_docs:
        rep.add("!", "군살",
                "300줄 넘는 지침서 " + ", ".join(f"{n}({c}줄)" for n, c in long_docs)
                + " — CLAUDE.md 의 '300줄이 넘으면 손본다' 참조")
        for n, c in sorted(long_docs, key=lambda kv: -kv[1]):
            print(f"      {n:<16} {c}줄")

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


SECTIONS = {"정합성": None, "신선도": None, "군살": None}


def main() -> int:
    ap = argparse.ArgumentParser(description="저장소 건강검진")
    ap.add_argument("--fast", action="store_true", help="적합이 필요한 검사는 건너뛴다")
    ap.add_argument("--only", choices=list(SECTIONS), help="한 절만")
    ap.add_argument("--today", help="신선도 기준일 (YYYY-MM-DD) — 검사 시험용")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    rep = Report()
    want = {args.only} if args.only else set(SECTIONS)

    if "정합성" in want:
        run_suites(rep, args.fast)
    if "신선도" in want:
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
