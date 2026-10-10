"""지금 모델이 어떤 상태인지 한 화면에 찍는다.

사용법:
    python -m scripts.model_status
    python -m scripts.model_status --months 24

## 왜 필요한가

문서에 숫자를 박아 두면 **반드시 어긋난다.** 실제로 그랬다 — `docs/factors.md` 안에서
기준 숫자가 셋으로 갈렸다.

    최고층·브랜드 절   거래 68,050 · 단지 1,846 · adj 0.8477
    입지 절                              adj 0.8622 · tau 0.17551
    직거래 절                                        tau 0.17390
    (지금)            거래 68,780 · 단지 1,822 · adj 0.8653 · tau 0.17078

각각은 **그때의 실험 기록**이라 틀린 게 아니다. 문제는 읽는 사람이 어느 것이 '지금'
인지 알 수 없다는 것이다. 그래서 실험 기록은 조건을 적어 문서에 남기고, **'지금' 은
문서에 적지 않고 여기서 찍는다.**

같은 이유로 데이터 구멍도 같이 센다. 실거래 적재로 새 단지가 생기면 좌표·도보경로·
입지가 비는데, 단지 수를 세어 보기 전에는 보이지 않는다(실제로 3곳을 그렇게 찾았다).
"""

from __future__ import annotations

import argparse
import sys
import warnings
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Complex, ComplexAmenity, Quote, RebStat, Trade,
)
from app.services import hedonic  # noqa: E402


def data_section(db) -> list[str]:
    n_cx = db.scalar(select(func.count()).select_from(Complex)) or 0
    out = [
        "## 데이터",
        f"  거래        {db.scalar(select(func.count()).select_from(Trade)):>8,}",
        f"  단지        {n_cx:>8,}",
        f"  호가        {db.scalar(select(func.count()).select_from(Quote)):>8,}",
        f"  공표 통계    {db.scalar(select(func.count()).select_from(RebStat)):>8,}",
    ]
    ym = db.execute(select(func.min(Trade.deal_ym), func.max(Trade.deal_ym))).one()
    out.append(f"  거래 기간    {ym[0]} ~ {ym[1]}")

    rows = db.execute(
        select(func.coalesce(Trade.deal_type, ""), func.count())
        .group_by(func.coalesce(Trade.deal_type, ""))
    ).all()
    tot = sum(n for _, n in rows) or 1
    for t, n in sorted(rows, key=lambda kv: -kv[1]):
        out.append(f"    {t or '(빈값)':<10} {n:>8,} ({n / tot * 100:4.1f}%)")

    # 구멍 — 적재 순서가 어긋나면 여기서 보인다
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
    out.append("")
    if bad:
        out.append("  [!] 비어 있는 것:")
        for w, n, c in bad:
            out.append(f"      {w} 없는 단지 {n}곳 → python -m {c}")
    else:
        out.append("  구멍 없음 (좌표·도보경로·입지 전부 채워짐)")
    return out


def model_section(rows, months: int) -> list[str]:
    tot: dict[int, int] = defaultdict(int)
    mkt: dict[int, int] = defaultdict(int)
    for r in rows:
        c = r["complex_id"]
        tot[c] += 1
        if r.get("deal_type") != "직거래":
            mkt[c] += 1
    MIN = hedonic.MIN_TRADES_PER_COMPLEX

    out = [
        "",
        f"## 모델 (최근 {months}개월)",
        f"  적합 입력    거래 {len(rows):>7,} · 단지 {len(tot):>6,}",
        f"  중개거래 {MIN}건 이상 단지 {sum(1 for c in tot if mkt[c] >= MIN):,}곳 "
        f"(전체 거래로 세면 {sum(1 for c in tot if tot[c] >= MIN):,}곳)",
        "",
        f"  {'스펙':<6}{'거래':>9}{'단지':>7}{'R2':>9}{'adj':>9}{'tau':>9}",
    ]
    fits = {}
    for key in hedonic.SPECS:
        try:
            f = hedonic.fit(rows, spec=key)
        except Exception as exc:  # noqa: BLE001
            out.append(f"  {key:<6} 적합 실패: {type(exc).__name__}")
            continue
        fits[key] = f
        out.append(f"  {key:<6}{f['n_obs']:>9,}{f['n_complexes']:>7,}"
                   f"{f['r2']:>9.4f}{f['adj_r2']:>9.4f}{f['tau']:>9.5f}")

    f = fits.get(hedonic.DEFAULT_SPEC) or next(iter(fits.values()), None)
    if f is None:
        return out

    dt = (f.get("stage1") or {}).get("deal_type")
    if dt:
        out += ["", f"  직거래 {dt['pct']:+.2f}% (SE {dt['se'] * 100:.2f}%p, "
                    f"p={dt['p']}) · {dt['n_direct']:,}건 ({dt['share_pct']}%)"]

    out += ["", "  요인별 유의성 (전체가 0 인가)", ]
    lin = f.get("linearity") or {}
    for var in f.get("spline_terms", {}):
        t = lin.get(var) or {}
        jp, sig = t.get("joint_p"), t.get("significant")
        mark = "유의" if sig else ("검출 안 됨" if sig is False else "—")
        nl = t.get("p")
        out.append(f"    {var:<16} 전체 p={str(jp):<10} {mark:<8}"
                   f" 비선형 p={nl if nl is not None else '—'}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="지금 모델 상태")
    ap.add_argument("--months", type=int, default=12)
    args = ap.parse_args()
    warnings.filterwarnings("ignore")

    with SessionLocal() as db:
        lines = data_section(db)
        if hedonic.available():
            rows = hedonic.load_rows(db, months=args.months)
            lines += model_section(rows, args.months)
        else:
            lines += ["", "## 모델", "  의존성이 없어 건너뜀"]

    print("\n".join(lines))
    print("\n이 값들은 **문서에 적지 않는다.** 적으면 반드시 어긋난다 —"
          "\n실험 기록은 조건과 함께 docs/factors.md 에, '지금' 은 여기서 찍는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
