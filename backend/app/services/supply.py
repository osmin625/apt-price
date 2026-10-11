"""공급 분석 — 적정 공급량과 실제 공급을 견준다.

## 적정 공급량을 상수로 두지 않는다

"서울은 연 5만 호가 필요하다" 는 널리 쓰이는 어림이지만, 우리는 **데이터로 낸다.**

    적정 공급 = 가구 증가 + 멸실

둘 다 한국부동산원에 있다 — 가구수는 주택보급률 표의 `가구수(등록센서스)`, 멸실은
주택멸실현황이다. 재 보니 서울은 2011~2015 에 46,000~54,000 이었고 가구 증가가
빨라진 2019년 이후 올라갔다. **상수가 아니라 해마다 달라지는 값**이다.

## 알아낸 함정 셋

1. **가구수 단위가 '천' 이다.** 공표 단위 라벨이 `천호` 로 적혀 있는데 실제로는
   천 가구다(주택수 쪽은 거꾸로 `천가구` 로 적혀 있다). 1000 을 곱해 쓴다.

2. **가구수가 2015·2016 에 튄다.** 2015년 증가가 +28,300 인데 2016년은 +200 이다.
   등록센서스 집계가 바뀐 자국으로 보인다. 단년 증가분을 그대로 쓰면 그 해만
   '공급 과잉' 으로 보이므로 **3년 이동평균**을 같이 낸다.

3. **착공→준공 선행성이 서울에서는 성립하지 않는다.** 12개월 누적으로 상관을 재니
   경기는 27개월 시차에서 +0.895 인데 서울은 시차 0에서 +0.693 이고 시차가 늘수록
   떨어진다. 서울 공급이 재건축·재개발 위주라 착공–준공 간격이 들쭉날쭉하기
   때문으로 보인다. 그래서 **경기만** 앞을 내다보고, 서울은 그렇게 말한다.

## 못 하는 것

미래 입주 예정 물량(2027·2028)은 R-ONE 에 없다. 준공실적은 이미 지어진 것이고,
예정치는 민간 집계다. 경기는 착공으로 가늠하고 서울은 가늠하지 않는다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clients.reb import SIDO
from ..models import RebStat

# 가구수는 '천' 단위로 공표된다(라벨이 뒤바뀌어 있다 — 위 주석 참조).
HH_SCALE = 1000.0

# 착공이 준공으로 나타나기까지. **재서 정했다**(상관 최대 지점).
# 서울은 선행성이 성립하지 않아 넣지 않는다.
LEAD_MONTHS: dict[str, int] = {"41": 27}
LEAD_CORR: dict[str, float] = {"41": 0.895}

# 단년 증가분이 집계 변경에 흔들려서 함께 낸다.
SMOOTH_YEARS = 3


def _series(db: Session, sgg_cd: str, metric: str) -> dict[str, float]:
    rows = db.execute(
        select(RebStat.ym, RebStat.value)
        .where(RebStat.sgg_cd == sgg_cd, RebStat.metric == metric)
    ).all()
    return {ym: float(v) for ym, v in rows}


def _to_year(monthly: dict[str, float]) -> dict[str, float]:
    """월별을 연 합계로. **그 해 12개월이 다 있을 때만** 센다.

    올해는 아직 안 끝났다. 8월까지만 있는 해를 연 합계로 내면 '올해 공급이 급감했다'
    는 거짓이 된다 — 빈 결과만큼이나 조용한 거짓말이다.
    """
    by_year: dict[str, list[float]] = {}
    for ym, v in monthly.items():
        by_year.setdefault(ym[:4], []).append(v)
    return {y: sum(vs) for y, vs in by_year.items() if len(vs) == 12}


def _roll(series: dict[str, float], n: int) -> dict[str, float]:
    ks = sorted(series)
    out: dict[str, float] = {}
    for i in range(n - 1, len(ks)):
        out[ks[i]] = sum(series[k] for k in ks[i - n + 1:i + 1]) / n
    return out


def balance(db: Session, sgg_cd: str) -> dict:
    """연도별 적정 공급 vs 실제 준공."""
    hh = {k[:4]: v * HH_SCALE for k, v in _series(db, sgg_cd, "households").items()}
    dem = {k[:4]: v for k, v in _series(db, sgg_cd, "demolish").items()}
    dem_apt = {k[:4]: v for k, v in _series(db, sgg_cd, "demolish_apt").items()}
    done = _to_year(_series(db, sgg_cd, "done"))

    yrs = sorted(set(hh) & set(dem))
    grow: dict[str, float] = {}
    for i, y in enumerate(yrs):
        if i:
            grow[y] = hh[y] - hh[yrs[i - 1]]
    grow_s = _roll(grow, SMOOTH_YEARS)

    rows = []
    for y in sorted(grow):
        need = grow[y] + dem[y]
        need_s = (grow_s[y] + dem[y]) if y in grow_s else None
        got = done.get(y)
        rows.append({
            "year": y,
            "households": round(hh[y]),
            "household_growth": round(grow[y]),
            "household_growth_smooth": round(grow_s[y]) if y in grow_s else None,
            "demolish": round(dem[y]),
            "demolish_apt": round(dem_apt.get(y, 0)),
            "adequate": round(need),
            "adequate_smooth": round(need_s) if need_s is not None else None,
            "done": round(got) if got is not None else None,
            "gap": round(got - need) if got is not None else None,
            "gap_smooth": (round(got - need_s)
                           if got is not None and need_s is not None else None),
        })
    return {"sgg_cd": sgg_cd, "region": SIDO.get(sgg_cd, sgg_cd), "rows": rows}


def pipeline(db: Session, sgg_cd: str, months: int = 12) -> dict:
    """인허가 → 착공 → 준공. 12개월 누적으로 본다.

    월별은 들쭉날쭉하다 — 서울 착공이 7월 6,386호인데 8월 1,172호다. 누적으로 봐야
    추세가 읽힌다.
    """
    out: dict[str, list[dict]] = {}
    for metric in ("permit", "start", "done"):
        s = _series(db, sgg_cd, metric)
        ks = sorted(k for k in s if not k.endswith("00"))
        acc = []
        for i in range(months - 1, len(ks)):
            win = ks[i - months + 1:i + 1]
            acc.append({"ym": ks[i], "value": round(sum(s[k] for k in win))})
        out[metric] = acc
    return {"sgg_cd": sgg_cd, "region": SIDO.get(sgg_cd, sgg_cd),
            "months": months, "series": out}


def lead(db: Session, sgg_cd: str, months: int = 12) -> dict:
    """착공으로 본 2~3년 뒤 입주. **경기만** 낸다.

    서울은 착공이 준공을 선행하지 않는다(위 주석). 값을 내지 않고 왜 못 내는지를
    돌려준다 — 빈 카드보다 낫고, 억지로 낸 숫자보다는 훨씬 낫다.
    """
    lag = LEAD_MONTHS.get(sgg_cd)
    if lag is None:
        return {
            "sgg_cd": sgg_cd, "region": SIDO.get(sgg_cd, sgg_cd),
            "available": False,
            "note": "착공이 준공을 선행하지 않아 앞을 가늠하지 않습니다. "
                    "12개월 누적 상관이 시차 0에서 +0.693 으로 가장 높고 시차가 "
                    "늘수록 떨어집니다 — 재건축·재개발 위주라 착공과 준공 사이가 "
                    "들쭉날쭉하기 때문으로 보입니다.",
        }

    s = _series(db, sgg_cd, "start")
    ks = sorted(k for k in s if not k.endswith("00"))
    acc = []
    for i in range(months - 1, len(ks)):
        win = ks[i - months + 1:i + 1]
        ym = ks[i]
        y, m = int(ym[:4]), int(ym[4:])
        t = (y * 12 + m - 1) + lag
        acc.append({
            "ym": ym,
            "expect_ym": f"{t // 12:04d}{t % 12 + 1:02d}",
            "value": round(sum(s[k] for k in win)),
        })
    return {
        "sgg_cd": sgg_cd, "region": SIDO.get(sgg_cd, sgg_cd), "available": True,
        "lag_months": lag, "corr": LEAD_CORR.get(sgg_cd), "months": months,
        "series": acc,
        "note": f"착공 12개월 누적이 {lag}개월 뒤 준공과 가장 잘 맞습니다"
                f"(상관 {LEAD_CORR.get(sgg_cd):+.3f}). 착공한 집이 그만큼 뒤에 "
                f"입주한다는 뜻이라, 최근 착공이 앞으로의 입주를 가늠하게 해 줍니다.",
    }


def age_pressure(db: Session) -> dict:
    """노후 재고 압력 — 우리 DB 의 준공연도로 센다.

    붙여 주신 내용의 '썩다리' 압력이다. 철거되지 않아도 40~50년 된 단지가 많아질수록
    새집 수요가 생긴다.

    **경기 남부만** 낼 수 있다. 서울은 단지 데이터가 없다(우리 대상 지역이 아니다).
    """
    from datetime import date

    from ..models import Complex

    now = date.today().year
    rows = db.execute(
        select(Complex.build_year, Complex.household_count, Complex.sgg_name)
        .where(Complex.build_year.isnot(None))
    ).all()

    bands = [("5년 이하", 0, 5), ("6~10년", 6, 10), ("11~20년", 11, 20),
             ("21~30년", 21, 30), ("31~40년", 31, 40), ("40년 초과", 41, 999)]
    cnt = {b[0]: 0 for b in bands}
    hh = {b[0]: 0 for b in bands}
    for by, hc, _sgg in rows:
        age = now - int(by)
        for name, lo, hi in bands:
            if lo <= age <= hi:
                cnt[name] += 1
                hh[name] += int(hc or 0)
                break

    total = sum(cnt.values()) or 1
    old = sum(cnt[b[0]] for b in bands if b[1] >= 31)
    return {
        "region": "경기 남부",
        "as_of_year": now,
        "bands": [{"band": b[0], "complexes": cnt[b[0]], "households": hh[b[0]],
                   "pct": round(cnt[b[0]] / total * 100, 1)} for b in bands],
        "total_complexes": total,
        "old_pct": round(old / total * 100, 1),
        "note": "준공 30년이 넘으면 재건축 연한에 들어간다. 철거되지 않아도 "
                "새집 수요를 만드는 쪽이라 공급 압력으로 읽는다. 서울은 우리가 "
                "단지 데이터를 모으는 지역이 아니라 낼 수 없다.",
    }
