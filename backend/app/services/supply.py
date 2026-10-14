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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clients.reb import SIDO
from ..models import KaptUnit, RebStat

# 가구수는 '천' 단위로 공표된다(라벨이 뒤바뀌어 있다 — 위 주석 참조).
HH_SCALE = 1000.0

# 경기 남부 8개 시 묶음. 법정동코드가 아니라 **우리가 정의한 묶음**이다
# (`clients/reb.py` 의 SOUTH_GG_CODE 참조).
SOUTH_GG = "41S"

# 착공이 준공으로 나타나기까지. **재서 정했다**(상관 최대 지점).
# 서울은 선행성이 성립하지 않아 넣지 않는다.
LEAD_MONTHS: dict[str, int] = {"41": 27}
LEAD_CORR: dict[str, float] = {"41": 0.895}

# 단년 증가분이 집계 변경에 흔들려서 함께 낸다.
SMOOTH_YEARS = 3

# 중위 증가의 이 비율에 못 미치는 해는 '집계가 튄 해' 로 본다. 서울 2016 이
# 0.7%, 다음으로 낮은 해가 63.2% 라 0.25 는 어느 쪽에도 가깝지 않다.
ODD_GROWTH_RATIO = 0.25


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
    # 과부족 **누계**. 한 해씩 보면 들쭉날쭉해서 "모자란 상태가 쌓였나" 를 못 본다.
    # 경기는 2016~2018 에 +15만을 쌓았다가 2019~2021 에 −16만을 까먹는다 —
    # 단년만 보면 2022년이 거의 균형(-5,814)으로 보이지만 누계로는 여전히 깊다.
    # 시작점은 **데이터가 있는 첫 해**다. 절대 수준이 아니라 그 뒤의 기울기를
    # 보는 선이므로 화면에 "몇 년부터 누계" 를 적는다.
    # 단년 증가분이 **집계 기준이 바뀐 해에 튄다.** 서울 2016년이 +200 인데
    # 앞뒤가 +28,300·+28,600 이다 — 2015년 인구주택총조사가 등록센서스로 바뀐
    # 자국으로 보인다. 그해만 '공급 과잉 +45,764' 로 혼자 솟는다.
    #
    # **연도를 코드에 박지 않는다.** 중위 증가의 25% 에 못 미치는 해를 튄 해로
    # 본다. 재 보니 서울 2016 이 0.7% 이고 다음으로 낮은 해가 63.2% 라 사이가
    # 넉넉하다(경기는 걸리는 해가 없다). 지역을 넓혀도 규칙이 따라간다.
    _gs = sorted(grow.values())
    _med = _gs[len(_gs) // 2] if _gs else 0.0
    odd_years = {y for y, v in grow.items() if _med and v < _med * ODD_GROWTH_RATIO}

    cum = cum_s = 0.0
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
            "gap_cum": None,      # 아래에서 채운다
            "gap_cum_smooth": None,
            # 집계가 튄 해. 화면이 점을 찍고 까닭을 적는다.
            "growth_odd": y in odd_years,
            "gap_smooth": (round(got - need_s)
                           if got is not None and need_s is not None else None),
        })
        if got is not None:
            cum += got - need
            rows[-1]["gap_cum"] = round(cum)
            if need_s is not None:
                cum_s += got - need_s
                rows[-1]["gap_cum_smooth"] = round(cum_s)

    # **준공은 있는데 적정을 못 내는 해**도 행으로 낸다. 가구수·멸실은 연 단위로
    # 늦게 공표되고, 준공은 월별로 빨리 나온다. 행을 '둘 다 있는 해' 로만 만들면
    # 12개월이 다 찬 해의 준공이 통째로 버려지는데, 화면은 '올해라 빠진다' 고만
    # 말해 다른 까닭을 댄다(재 보니 준공은 다음 해 8월까지 있는데 가구수·멸실은
    # 그 전 해에서 끝났다). 적정·과부족·누계는 **None** — 0 으로 채우면 '적정
    # 공급이 0 이라 크게 더 지었다' 는 거짓이 된다. 누계도 여기서 멈춘다.
    #
    # 뒤쪽만 붙인다. 가구수가 시작되기 전의 준공은 적정 공급 계열의 '앞' 이 아니라
    # 이 비교의 범위 밖이다 — 붙이면 누계 시작점(`cum_from`)과 그림 폭이 바뀐다.
    adequate_to = max(grow) if grow else None
    for y in sorted(done):
        if adequate_to is None or y <= adequate_to:
            continue
        rows.append({
            "year": y,
            "households": None, "household_growth": None,
            "household_growth_smooth": None,
            "demolish": None, "demolish_apt": None,
            "adequate": None, "adequate_smooth": None,
            "done": round(done[y]),
            "gap": None, "gap_cum": None, "gap_cum_smooth": None,
            "growth_odd": False, "gap_smooth": None,
            # 적정이 빈 까닭. 화면이 '—' 를 찍고 끝 연도를 말한다.
            "need_missing": True,
        })
    for r in rows:
        r.setdefault("need_missing", False)
    # 화면이 그리는 누계는 **3년평균 기준**(`gap_cum_smooth`)이라 시작 해도 그것을
    # 따른다. 단년 누계(`gap_cum`)로 잡았더니 범례는 '2011년~' 인데 점선은 평균이
    # 처음 서는 2013년에서 시작했다 — 앞 두 해는 평균을 낼 재료가 모자란다.
    first = next((r["year"] for r in rows if r["gap_cum_smooth"] is not None), None)
    return {"sgg_cd": sgg_cd, "region": SIDO.get(sgg_cd, sgg_cd), "rows": rows,
            "cum_from": first,
            # 끝 연도를 **데이터에서** 준다. 화면 문구가 연도를 박지 않게.
            "adequate_to": adequate_to,
            "households_to": max(hh) if hh else None,
            "demolish_to": max(dem) if dem else None}


def south_supply(db: Session, since: int = 2005) -> dict:
    """경기 남부 아파트 입주 물량 — **공표 통계가 못 주는 것을 전수 집계로 메운다.**

    공급 표에는 시 단위 분류가 하나도 없다(준공·착공·인허가·가구수·멸실 전부 0개).
    그래서 R-ONE 으로는 경기 남부 공급을 낼 수 없다. 대신 K-apt 의 의무관리대상
    공동주택을 17개 구 전수로 받아(`scripts/ingest_kapt_all`) 사용승인 연도별
    세대수를 더한다.

    ## 이것은 '준공' 이 아니다

    이름을 똑바로 붙여야 한다. 나오는 값은 **'지금 남아 있는 의무관리대상 아파트를
    사용승인 연도로 모은 것'** 이다.

    - 의무관리대상만 — 소규모 단지·빌라·단독은 빠진다
    - **지금 존재하는 단지만** — 철거된 단지가 없어 과거일수록 과소집계된다
    - 아파트만 — R-ONE 의 주택 준공(주택 전체)과 **직접 뺄 수 없다**

    그래서 적정 공급(가구 증가+멸실)에서 이 값을 빼지 않는다. 추세만 견준다.
    화면에도 그렇게 적는다 — 빼서 '경기 남부 부족분' 을 내면 그럴듯한 거짓이 된다.

    ## 최근 연도는 아직 덜 찼다

    사용승인이 안 난 단지는 K-apt 에 안 들어온다. 올해·내년 값이 작게 보이는 것은
    공급이 준 것이 아니라 **아직 안 들어온 것**이다. `partial_from` 으로 어느
    해부터 그런지 알려 준다.
    """
    rows = db.execute(
        select(KaptUnit.build_year,
               func.count(KaptUnit.id),
               func.sum(func.coalesce(KaptUnit.household_count, 0)))
        .where(KaptUnit.build_year.isnot(None), KaptUnit.build_year >= since)
        .group_by(KaptUnit.build_year)
        .order_by(KaptUnit.build_year)
    ).all()

    total = db.scalar(select(func.count()).select_from(KaptUnit)) or 0
    with_hh = db.scalar(select(func.count()).select_from(KaptUnit)
                        .where(KaptUnit.household_count.isnot(None))) or 0
    with_yr = db.scalar(select(func.count()).select_from(KaptUnit)
                        .where(KaptUnit.build_year.isnot(None))) or 0

    years = [{"year": str(y), "complexes": int(n), "households": int(hh or 0)}
             for y, n, hh in rows]

    # 가구 증가 — 공급의 짝이다. 경기도기본통계 CSV 에서 온다(시군구별 일반가구수).
    # **빼지 않는다.** 가구 증가는 모든 주택 유형의 수요이고 위 값은 아파트만이다.
    # 나란히 두고 사람이 견주게 한다.
    hh_series = _series(db, SOUTH_GG, "households_south")
    growth: dict[str, int] = {}
    ks = sorted(hh_series)
    for i in range(1, len(ks)):
        growth[ks[i][:4]] = int(hh_series[ks[i]] - hh_series[ks[i - 1]])
    for y in years:
        y["household_growth"] = growth.get(y["year"])
        y["households_total"] = (int(hh_series.get(y["year"] + "00"))
                                 if y["year"] + "00" in hh_series else None)

    # 교차검증 — 아파트 재고 증가와 K-apt 입주 합이 맞는가.
    # 기관도 방식도 다른 두 자료다(주택총조사 재고 vs 단지별 사용승인). 맞으면
    # 위의 입주 물량을 믿을 근거가 되고, 벌어지면 화면이 그렇게 말해야 한다.
    apt = _series(db, SOUTH_GG, "houses_apt_south")
    cross = None
    if len(apt) >= 2:
        aks = sorted(apt)
        first, last = aks[0][:4], aks[-1][:4]
        stock = int(apt[aks[-1]] - apt[aks[0]])
        moved = sum(y["households"] for y in years
                    if first < y["year"] <= last)
        cross = {
            "from": first, "to": last,
            "stock_delta": stock, "kapt_sum": moved,
            "gap_pct": round((moved / stock - 1) * 100, 1) if stock else None,
        }

    # 마지막 두 해는 아직 들어오는 중이라 따로 표시한다. '0' 이 아니라 '덜 찼다'.
    partial_from = years[-2]["year"] if len(years) >= 2 else None

    return {
        "region": "경기 남부 17개 구",
        "years": years,
        "coverage": {"units": total, "with_households": with_hh,
                     "with_year": with_yr},
        "partial_from": partial_from,
        "cross_check": cross,
        "note": ("K-apt 의무관리대상 공동주택을 17개 구 전수로 받아 사용승인 연도별로 "
                 "모은 값입니다. 공급 통계의 '준공' 과 다릅니다 — 소규모 단지와 "
                 "비아파트가 빠지고, 철거된 단지가 없어 과거일수록 적게 잡힙니다. "
                 "적정 공급에서 이 값을 빼지 않고 추세만 견줍니다. "
                 "최근 두 해는 사용승인이 아직 안 난 단지가 있어 덜 찬 값입니다. "
                 "가구 증가는 경기도기본통계의 시군구별 일반가구수에서 왔고, "
                 "모든 주택 유형의 수요라 아파트 입주와 빼서 쓰지 않습니다."),
    }


def unsold(db: Session) -> dict:
    """미분양 — **공급 표 중 유일하게 시 단위가 있다.**

    적정 공급·준공·착공·인허가는 전부 시도까지만 와서 경기 남부로 좁힐 수 없다
    (738개 표를 훑어 확인했다). 미분양만 예외라, 우리가 보는 지역에 가장 가까운
    공급 지표다. 그래서 따로 카드를 둔다.

    세 줄을 같이 낸다 — 서울·경기 전체·경기 남부 8개 시. 남부만 보면 수도권 전체가
    어느 쪽인지 모르고, 경기 전체만 보면 북부가 섞인다.
    """
    out = []
    for cd, label in (("11", "서울"), ("41", "경기 전체"), (SOUTH_GG, "경기 남부 8개 시")):
        s = _series(db, cd, "unsold")
        if not s:
            continue
        ks = sorted(s)
        last = ks[-1]
        # 전년 같은 달 대비. 미분양은 계절성이 있어 전월 대비는 흔들린다.
        prev = f"{int(last[:4]) - 1}{last[4:]}"
        out.append({
            "sgg_cd": cd,
            "region": label,
            "latest": {"ym": last, "value": round(s[last])},
            "yoy": (round((s[last] / s[prev] - 1) * 100, 1)
                    if s.get(prev) else None),
            "peak": {"ym": max(s, key=lambda k: s[k]),
                     "value": round(max(s.values()))},
            "series": [{"ym": k, "value": round(s[k])} for k in ks],
        })
    return {
        "regions": out,
        "note": ("미분양은 지은 뒤 안 팔린 집입니다. 늘면 수요가 식었다는 뜻이고, "
                 "다음 공급을 줄이는 쪽으로도 작용합니다. "
                 "공급 지표 가운데 시 단위가 있는 것은 미분양뿐이라 "
                 "경기 남부를 따로 낼 수 있습니다."),
    }


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
