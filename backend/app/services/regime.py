"""거시 국면 — 요인들이 지금 어느 쪽으로 미는가, 과거에는 어땠나.

## 화살표 하나로 못 박지 않는다

"공급 부족이니 상승" 같은 말은 쉽지만 **재 보면 그렇게 깔끔하지 않다.** 각 요인과
'그 뒤 12개월 경기 남부 가격 변화' 의 상관을 전부 재 봤다(시차 0~24개월).

    주택 소비심리   0m +0.42 ·  6m -0.03 · 12m -0.34 · 18m -0.51
    거래량 전년비   0m +0.25 ·  6m +0.32 · 12m +0.26 · 18m -0.02
    미분양 전년비   0m -0.31 ·  6m -0.12 · 12m -0.00 · 18m -0.06

(처음 잰 표다. 2026-10-16 건수 계열을 로그 변화율로 바꾼 뒤에는 미분양 0m −0.49,
준공 −0.36, 거래량 +0.50 — 부호와 판정은 같고 세기만 바뀌었다. docs/analysis/macro.md.
지금 값은 화면과 `scripts/model_status.py` 가 그 자리에서 잰다.)
    대출금리 전년차  0m -0.27 ·  6m -0.31 · 12m -0.30 · 18m -0.16
    가계대출 전년비  0m +0.29 ·  6m +0.04 · 12m -0.13 · 18m -0.20
    M2 전년비      0m -0.07 ·  6m -0.17 · 12m -0.34 · 18m -0.44
    기준금리 수준    0m -0.09 ·  6m -0.00 · 12m +0.06 · 18m +0.10

**가장 센 것도 0.42 고, 심리는 18개월 뒤에 부호가 뒤집힌다**(과열의 끝). 통화량과
기준금리는 0에 가깝다. 그래서 방향만 큼직하게 띄우면 없는 확신을 파는 셈이 된다.
화면에는 방향과 **세기·시차 프로파일을 같이** 낸다.

## 겹치는 창을 조심한다

12개월 변화율을 매달 계산하면 이웃한 관측이 11개월을 공유한다. n=219 처럼 보여도
독립 표본은 20개 남짓이다. 그래서 **매년 12월만 쓴 겹치지 않는 상관**을 같이 낸다.
둘의 부호가 다르면 그 요인은 방향을 말하지 않는다.

## 지금 값이 아니라 '자기 평균에서 얼마나 벗어났나' 를 쓴다

요인마다 단위가 다르고(호, 지수, %, 십억원) 추세도 다르다. 수준을 그대로 비교할
수 없으니 **자기 역사 평균에서 평소 오르내림 폭(표준편차)의 몇 배 벗어났나**(z)로 바꾼다.
미분양이 많은 것인지는 경기도 미분양의 긴 역사에 비춰 봐야 안다. 예전에는 백분위였다 —
`hist_z` 주석.

## 지역이 섞인다

가격은 경기 남부 17개 구인데 미분양·심리는 경기 전체, 통화·금리는 전국이다.
공급 표가 시도까지만 오기 때문이고(`docs/analysis/supply.md`), 좁힐 방법이 없다.
**섞어 쓰는 것을 화면에 적는다** — 경기 전체를 경기 남부처럼 부르지 않는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clients.molit import DISTRICTS
from ..models import RebStat
from .policy import COVERS_FROM, GOV_SOURCE, GOVERNMENTS, POLICY, government_at

# '그때는' 의 '지금과 비슷한 자리'(±0.5, `SIMILAR_BAND`). 예전에는 과거 국면 표의 다섯 단계
# (보통 ±0.5 · 매우 ±1.5) 경계이기도 했는데, 그 표가 글자를 빼고 배수만 적게 되며(2026-10-19)
# 이것 하나만 남았다.
#
# 예전에는 여기에 방향을 말하는 최소 상관(`MIN_R` 0.15)과 방향 판정(`_pressure`)이 있었다.
# 이 탭이 예측을 그만두며(2026-10-18) 걷었다. 실험 틀은 scripts/cv_macro.py 가 자기 값으로 지닌다.
Z_MID = 0.5



@dataclass(frozen=True)
class Factor:
    key: str
    group: str
    label: str
    metric: str
    sgg_cd: str
    region: str
    transform: str  # level | yoy | diff12 | roll12_yoy | log12 | roll12_log | vs_adequate | cum_adequate
    unit: str
    up_means: str   # 이 값이 커지면 어떤 뜻인가(화면 설명)
    # 이론 방향 — 평균보다 높으면 가격을 올리는 쪽(+1)인가 내리는 쪽(−1)인가. **데이터로 고르지
    # 않는다**(2026-10-19 요청 — 상관이 약하다고 빼던 방식을 버렸다). 반영 분해(`reflect`)가 쓴다.
    sign: int = 0
    # 이론 시차(개월) — 그 요인이 가격에 닿기까지. 이것도 **측정 전에** 정했다. 수급 재고(누적 공급)
    # 12, 금융 여건(M2·대출·금리) 6, 시장 동행 지표(거래량·심리·전세가율·미분양) 0.
    lag: int = 0


# 지역·변환을 한 곳에 모은다. 화면과 측정이 **같은 정의**를 봐야 한다.
FACTORS: tuple[Factor, ...] = (
    # 건수 계열(준공·미분양·거래량)은 로그 변화율이다(`_log12`). 전년비(%)는 1년 전
    # 값이 작으면 수천 %로 터져 그림과 상관을 그 몇 달이 덮었다. 단위는 비운다 —
    # 로그 변화율은 %가 아니다. 읽는 법은 `TRANSFORM_LABEL` 이 화면에 붙인다.
    # '누적 공급' — 적정 공급(가구 증가 + 멸실) 대비 준공의 **누적 차이**(`_cum_adequate`).
    # 공급 분석의 '누적 차이' 점선과 같은 값을 달마다 쌓은 것이다. 바뀐 경위(2026-10-18~19):
    #   준공 물량(준공 12개월 합의 로그 변화율) — 작년보다 더 지었나만 말했다
    #   공급(12개월 준공 ÷ 적정) — 그 1년이 필요한 만큼이었나. 한 해 덜 지어도 앞서 많이
    #     지었으면 모자라지 않은데, 그것을 못 본다
    #   누적 공급 — 그동안 쌓인 과부족. 요청. (12개월 비율은 `_vs_adequate` 로 남아
    #     scripts/cv_macro.py 의 기록 재현에 쓴다.)
    Factor("supply", "공급", "누적 공급", "done", "41", "경기", "cum_adequate", "호",
           "적정보다 더 지은 것이 쌓였다(0 이면 그동안 적정만큼)", sign=-1, lag=12),
    Factor("unsold", "공급", "미분양", "unsold", "41", "경기", "log12", "",
           "안 팔린 집이 늘었다", sign=-1),
    Factor("trade", "수요", "거래량", "trade_volume", "", "경기 남부", "roll12_log", "",
           "사려는 사람이 늘었다", sign=+1),
    Factor("sentiment", "수요", "주택시장 소비심리", "sentiment", "41", "경기", "level", "지수",
           "사겠다는 쪽이 늘었다(100 이 중립)", sign=+1),
    Factor("jeonse_ratio", "수요", "전세가율", "jeonse_ratio", "", "경기 남부", "level", "%",
           "전세가 매매에 가까워졌다", sign=+1),
    Factor("m2", "통화량", "M2(광의통화)", "m2", "00", "전국", "yoy", "%",
           "시중에 도는 돈이 빨리 늘었다", sign=+1, lag=6),
    Factor("loan_balance", "통화량", "가계대출 잔액", "loan_balance", "00", "전국", "yoy", "%",
           "가계가 빚을 빨리 늘렸다", sign=+1, lag=6),
    Factor("base_rate", "금리", "한국은행 기준금리", "base_rate", "00", "전국", "diff12", "%p",
           "1년 전보다 금리가 올랐다", sign=-1, lag=6),
    Factor("loan_rate", "금리", "가계대출 금리", "loan_rate", "00", "전국", "diff12", "%p",
           "실제로 무는 금리가 올랐다", sign=-1, lag=6),
)

GROUP_ORDER = ("공급", "수요", "통화량", "금리", "정책", "세금")


# ──────────────────────────────────────────────────────────
# 계열 만들기
# ──────────────────────────────────────────────────────────
def _raw(db: Session, metric: str, sgg_cd: str) -> dict[str, float]:
    """월별 원계열. `sgg_cd` 가 비면 우리 17개 구의 평균(또는 합)을 쓴다."""
    q = select(RebStat.ym, RebStat.value).where(RebStat.metric == metric)
    if sgg_cd:
        q = q.where(RebStat.sgg_cd == sgg_cd)
    rows = db.execute(q).all()
    if sgg_cd:
        return {ym: float(v) for ym, v in rows}

    # 17개 구를 합친다. 거래량은 합, 지수·비율은 평균이다 — 거래량을 평균 내면
    # 지역을 넓힐 때 값이 작아져 추세가 꺾인 것처럼 보인다.
    agg: dict[str, list[float]] = {}
    for ym, v in rows:
        agg.setdefault(ym, []).append(float(v))
    if metric == "trade_volume":
        return {ym: sum(vs) for ym, vs in agg.items()}
    return {ym: sum(vs) / len(vs) for ym, vs in agg.items()}


def _roll12(s: dict[str, float]) -> dict[str, float]:
    ks = sorted(s)
    return {ks[i]: sum(s[k] for k in ks[i - 11:i + 1]) for i in range(11, len(ks))}


def _yoy(s: dict[str, float]) -> dict[str, float]:
    ks = sorted(s)
    return {ks[i]: (s[ks[i]] / s[ks[i - 12]] - 1) * 100
            for i in range(12, len(ks)) if s[ks[i - 12]]}


def _log12(s: dict[str, float]) -> dict[str, float]:
    """1년 전 대비 **로그 변화율**(×100). 두 배면 +69, 절반이면 −69.

    건수 계열(미분양·준공·거래량)에 쓴다. 전년비(%)는 1년 전 값이 작으면 터진다 —
    경기 미분양이 819호에서 20,691호가 되자 +2,426% 가 나왔다. 그 몇 달이 그림을
    덮어 나머지가 0 근처에 납작해지고, 상관도 그 몇 점에 끌려 **실제보다 약하게**
    나왔다(미분양 0개월 −0.31, 같은 비율을 로그로 재면 −0.50).

    로그는 전년비와 **순서가 같다**(같은 비율 x/y 를 다른 눈금으로 잴 뿐). 그래서 그때
    (자가 백분위이던 때) 과거 국면·비슷했던 달은 바뀌지 않고 상관의 크기와 그림만 바뀌었다.
    0 이하가 낀 달은 로그를 낼 수 없어 뺀다(전년비도 1년 전 0 은 뺐다).
    """
    ks = sorted(s)
    return {ks[i]: math.log(s[ks[i]] / s[ks[i - 12]]) * 100
            for i in range(12, len(ks)) if s[ks[i - 12]] > 0 and s[ks[i]] > 0}


def _diff12(s: dict[str, float]) -> dict[str, float]:
    ks = sorted(s)
    return {ks[i]: s[ks[i]] - s[ks[i - 12]] for i in range(12, len(ks))}


def _vs_adequate(db: Session, sgg_cd: str) -> dict[str, float]:
    """12개월 준공 ÷ 적정 공급 × 100. 100 이면 그 1년 동안 적정만큼 지었다.

    적정 공급은 공급 분석과 **같은 값**을 쓴다(`supply.balance` 의 3년평균 기준
    `adequate_smooth`) — 두 탭이 '적정' 을 다르게 셈하면 같은 해가 한쪽에서는 모자라고
    다른 쪽에서는 넘친다. 3년평균인 까닭은 가구수 집계가 바뀐 해에 단년 증가가 튀기
    때문이다(supply 모듈 주석).

    적정은 **연** 값이고 준공 창은 달마다 민다. m월에 끝나는 12개월은 그 해 m개월과 앞 해
    12−m개월이라, 적정도 그 비율로 두 해를 섞는다.

    적정은 준공보다 **늦게** 공표된다(가구수·멸실이 한 해쯤 늦다). 그 뒤 달에는 마지막으로
    공표된 해의 적정을 이어 쓴다 — 빼면 이 요인이 한 해 넘게 멈춰 국면 표·한 그림의 '지금' 까지
    끌고 내려간다. 이어 쓴 달은 `adequate_carried` 로 알려 화면이 그렇게 적는다.
    """
    from . import supply as sp

    need = {r["year"]: r["adequate_smooth"] for r in sp.balance(db, sgg_cd)["rows"]
            if r.get("adequate_smooth")}
    if not need:
        return {}
    last_year = max(need)
    first_year = min(need)

    def need_of(y: str) -> float | None:
        if y in need:
            return need[y]
        return need[last_year] if y > last_year else None

    done12 = _roll12(_raw(db, "done", sgg_cd))
    out: dict[str, float] = {}
    for ym, v in done12.items():
        y, m = ym[:4], int(ym[4:6])
        if y < first_year or (m < 12 and str(int(y) - 1) < first_year):
            continue
        cur, prev = need_of(y), need_of(str(int(y) - 1))
        if cur is None or (m < 12 and prev is None):
            continue
        n = (m * cur + (12 - m) * (prev or 0)) / 12
        if n > 0:
            out[ym] = v / n * 100
    return out


def _cum_adequate(db: Session, sgg_cd: str) -> dict[str, float]:
    """적정 공급 대비 준공의 **누적 차이**(호). 0 이면 그동안 적정만큼 지었다.

    공급 분석의 `gap_cum_smooth`(연 단위, 3년평균 적정 기준)와 **같은 계산을 달마다** 한다 —
    달마다 (그 달 준공 − 그 해 적정 ÷ 12)를 더한다. 그래서 12월 값이 그 해 누계와 같아야
    하고, scripts/verify_supply_cum.py 가 전수로 대조한다. 시작은 공급 분석의 누계 시작 해
    (`cum_from`) 1월이다 — 절대 수준이 아니라 그 뒤의 기울기를 보는 값이라 시작 해를 화면에
    적는다(`TRANSFORM_LABEL` 뒤에 붙인다).

    적정이 아직 공표되지 않은 해는 마지막 해 적정을 이어 쓴다(`_vs_adequate` 와 같은 까닭,
    화면이 `caveat` 로 적는다). 준공이 빠진 달이 있으면 거기서 멈춘다 — 빈 달을 0 으로
    더하면 '그달 하나도 안 지었다' 는 거짓 누적이 된다.
    """
    from . import supply as sp

    b = sp.balance(db, sgg_cd)
    need = {r["year"]: r["adequate_smooth"] for r in b["rows"] if r.get("adequate_smooth")}
    start = b.get("cum_from")
    if not need or not start:
        return {}
    last_year = max(need)
    done = _raw(db, "done", sgg_cd)
    out: dict[str, float] = {}
    cum = 0.0
    y, m = int(start), 1
    while f"{y}{m:02d}" in done:
        ym = f"{y}{m:02d}"
        n = need.get(str(y), need[last_year] if str(y) > last_year else None)
        if n is None:
            break
        cum += done[ym] - n / 12
        out[ym] = cum
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def adequate_carried(db: Session, sgg_cd: str = "41") -> str | None:
    """적정 공급이 공표된 마지막 해. 그 뒤 달의 '공급' 은 이 해 적정을 이어 쓴 값이다."""
    from . import supply as sp

    return sp.balance(db, sgg_cd).get("adequate_to")


def series_of(db: Session, f: Factor) -> dict[str, float]:
    if f.transform == "vs_adequate":
        return _vs_adequate(db, f.sgg_cd)
    if f.transform == "cum_adequate":
        return _cum_adequate(db, f.sgg_cd)
    raw = _raw(db, f.metric, f.sgg_cd)
    if f.transform == "level":
        return raw
    if f.transform == "yoy":
        return _yoy(raw)
    if f.transform == "diff12":
        return _diff12(raw)
    if f.transform == "roll12_yoy":
        return _yoy(_roll12(raw))
    if f.transform == "log12":
        return _log12(raw)
    if f.transform == "roll12_log":
        return _log12(_roll12(raw))
    raise ValueError(f"모르는 변환: {f.transform}")


def price_series(db: Session) -> dict[str, float]:
    """경기 남부 17개 구 매매가격지수 평균."""
    return _raw(db, "sale_index", "")


# ──────────────────────────────────────────────────────────
# 재기
# ──────────────────────────────────────────────────────────
def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else 0.0


def hist_z(values: list[float], v: float) -> float:
    """`v` 가 자기 역사(`values`) **평균에서 표준편차 몇 배** 떨어져 있나 — **탭 공통의 자**.

    + 면 평균보다 높고 − 면 낮다. 거시 분석의 요인 카드·그때는·과거 국면 표·한 그림에,
    가격 분석의 국면 점, 공급 분석의 미분양 카드가 모두 이 값으로 칠하고 판정한다. 화면의
    `heat.js` 의 `histZ` 가 같은 공식이다.

    예전에는 백분위(지금보다 낮았던 달의 몫)였다. 그 전에는 '역대 최저~최고 사이' 였고, 둘이
    섞여 같은 미분양이 두 숫자로 나와 백분위로 맞췄다. 그런데 백분위는 사실상 **중위**가
    기준이라, 맨 위 요인 합산 카드(평균 기준 z)와 같은 요인이 다른 말을 했다 — 거래량이
    한 카드는 '평균의 1.0배 위', 다른 카드는 '자기 역사 90%' 였다. 평균이 아니라 중위로 가르면
    '평균보다 높은데 아래 절반' 인 달도 생긴다. 2026-10-18 평균으로 통일했다.
    모집단 표준편차다(표본 수가 수백이라 n−1 과 차이가 없다). 흔들림이 없는 계열은 0 이다.
    """
    n = len(values)
    if not n:
        return 0.0
    mu = sum(values) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in values) / n)
    return (v - mu) / sd if sd else 0.0


def _z(s: dict[str, float], ym: str) -> float:
    return hist_z(list(s.values()), s[ym])


def _fwd12(price: dict[str, float], yms: list[str], i: int) -> float | None:
    return None if i + 12 >= len(yms) else (price[yms[i + 12]] / price[yms[i]] - 1) * 100


# 요인 창의 '그 뒤 가격과의 관계'(요인 × 그 뒤 12개월 겹친 그림, 시차별 상관, 매년 12월만 쓴
# 상관)를 2026-10-19 걷었다(요청). 상관을 재는 `lag_profile`·`nonoverlap`·`fwd12_series` 도
# 같이 걷었다 — 처음 잰 표는 docs/analysis/macro.md '먼저 알아야 할 것' 에 기록으로 있다.


# 요인 값이 무엇을 바꾼 것인지 사람이 읽는 이름. 같은 준공이라도 공급 탭은 '호'
# 단위 12개월 누적이고 여기는 그 누적의 전년비라, 말해 주지 않으면 두 그림의
# 숫자가 서로 다른 데이터처럼 보인다.
# 명사로 끝낸다 — 화면이 '위는 ○○ — {이것}입니다' 로 잇는다.
TRANSFORM_LABEL = {
    "level": "그 달의 값",
    "yoy": "1년 전 대비 증감률",
    "diff12": "1년 전과의 차이",
    "roll12_yoy": "12개월 합의 1년 전 대비 증감률",
    # 로그 변화율은 낯선 눈금이라 읽는 법을 이름에 붙인다. 69 는 ln 2 × 100 — 잰 값이
    # 아니라 정의라서 데이터가 바뀌어도 틀리지 않는다.
    "log12": "1년 전 대비 로그 변화율(두 배면 +69)",
    "roll12_log": "12개월 합의 1년 전 대비 로그 변화율(두 배면 +69)",
    "vs_adequate": "12개월 준공 ÷ 적정 공급(100 이 적정)",
    "cum_adequate": "적정 공급 대비 준공의 누적 차이",
}

# 높다·낮다로 읽는 변환. 증감(늘었다·줄었다)이 아니라 수준이다 — 문장과 그림의 0 선이 갈린다.
LEVEL_LIKE = ("level", "vs_adequate", "cum_adequate")

# 수준값 요인의 기준선. 심리지수는 100 이 '사겠다 = 팔겠다', 누적 공급은 0 이 '그동안 적정만큼'
# 이다. 화면이 요인 키로 짐작하지 않게 여기서 준다.
REF_LINE = {"sentiment": 100, "supply": 0}


def _caveat(db: Session, f: Factor, last: str) -> str | None:
    """그 요인의 지금 값이 **추정을 낀** 것이면 그렇다고 말한다. 연도는 데이터에서 읽는다."""
    if f.transform not in ("vs_adequate", "cum_adequate"):
        return None
    to = adequate_carried(db, f.sgg_cd)
    if to and last[:4] > to:
        return (f"적정 공급은 {to}년까지 공표돼, 그 뒤 달은 {to}년 적정을 이어 써서 "
                "셈한 값입니다(준공은 실적).")
    return None


def factor_rows(db: Session) -> list[dict]:
    price = price_series(db)
    out = []
    for f in FACTORS:
        s = series_of(db, f)
        if not s:
            continue
        last = max(s)
        vals = list(s.values())
        z = hist_z(vals, s[last])
        out.append({
            "key": f.key, "group": f.group, "label": f.label, "region": f.region,
            "unit": f.unit, "transform": f.transform, "up_means": f.up_means,
            # 누적은 시작 해가 뜻의 일부다 — 데이터에서 읽어 붙인다(박으면 어긋난다).
            "transform_label": (f"{TRANSFORM_LABEL[f.transform]}({min(s)[:4]}년~, 호)"
                                if f.transform == "cum_adequate" else TRANSFORM_LABEL[f.transform]),
            # 0 이 기준인 계열(증감·차이)인가. 수준값은 0 선을 맞추지 않는다.
            "level_like": f.transform in LEVEL_LIKE,
            "ref_line": REF_LINE.get(f.key),
            "caveat": _caveat(db, f, last),
            # 그 요인이 지금과 비슷한 자리였던 시기와 그 뒤, 그리고 기저율.
            "then": factor_then(s, price),
            "latest": {"ym": last, "value": round(s[last], 2)},
            "z": round(z, 2),
            # 값과 그 달의 z(전체 기간 평균에서 평소 폭의 몇 배). 겹친 그림이 z 로 그린다 —
            # 단위가 호·%·%p·지수로 제각각이라 한 축에 놓으려면 자를 맞춰야 한다. 화면이
            # 다시 계산하지 않게 여기서 준다(카드·국면 표와 같은 `hist_z`).
            "series": [{"ym": k, "v": round(v, 2), "z": round(hist_z(vals, v), 2)}
                       for k, v in sorted(s.items())],
        })
    return out


# ──────────────────────────────────────────────────────────
# 과거 추적 — 그때 각 요인은 어땠고, 집값은 어떻게 됐나
# ──────────────────────────────────────────────────────────
def history(db: Session) -> dict:
    """**달마다** 각 요인의 위치(z)와 **그 뒤 12개월 가격 변화**를 함께 적는다.

    예전에는 반년마다였고 칸에 '낮음·매우 낮음' 같은 글자를 적었다. 2026-10-19 요청으로 달마다
    내고(화면이 분기·월을 고른다) 글자 없이 배수만 적는다 — 글자는 ±0.5·±1.5 에서 끊겨 0.49 와
    0.51 이 다른 말이 됐다.

    인과를 말하지 않는다. "그때 이랬고 그 뒤 이랬다" 만 적는다 — 요인은 서로
    얽혀 있고(금리가 낮으면 대출이 늘고 심리가 산다) 표본은 스무 해뿐이다.
    """
    price = price_series(db)
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    cols = [(f, series_of(db, f)) for f in FACTORS]
    # 각 계열의 평균·표준편차는 **그 시점까지가 아니라 전체 기간** 기준이다. 보는 사람이
    # '지금 높음' 과 '그때 높음' 을 같은 자로 견주려면 자가 하나여야 한다.
    rows = []
    for i, ym in enumerate(yms):
        states = {}
        for f, s in cols:
            if ym in s:
                z = _z(s, ym)
                states[f.key] = {"z": round(z, 2), "v": round(s[ym], 2)}
        if not states:
            continue
        rows.append({
            "ym": ym,
            "states": states,
            "fwd12": (round(_fwd12(price, yms, i), 2)
                      if _fwd12(price, yms, i) is not None else None),
        })
    return {"rows": rows,
            # 표본 길이를 문구에 얼리지 않는다('스무 해') — 해마다 하나씩 는다.
            "note": ("그때의 요인 상태와 그 뒤 12개월 가격 변화를 나란히 둔 것입니다. "
                     "요인이 가격을 움직였다는 뜻이 아닙니다 — 요인들은 서로 얽혀 "
                     f"있고 표본은 {len(yms) // 12}년치뿐입니다.")}


# ──────────────────────────────────────────────────────────
# 과거 사례 — 지금과 비슷했던 때 그 뒤에 무슨 일이 있었나
# ──────────────────────────────────────────────────────────
# 이 탭은 예측하지 않는다(2026-10-18 요청 — 합산 모델을 걷었다, docs/analysis/macro-model.md).
# 대신 '지금과 비슷했던 때' 를 찾아 그 뒤를 **사례로** 보인다. 세 가지를 지킨다.
#
# 1. **달이 아니라 시기로 센다.** 이웃한 달은 거의 같은 상황이다. 예전 '비슷했던 달 12개' 는
#    재 보니 두 시기(2013-12~2014-06, 2024-05~2025-06)였다 — 12번이 아니라 2번 본 것이다.
# 2. **기저율과 나란히 둔다.** 아무 달이나 골라도 그 뒤 1년이 오른 달이 71%(2013년 이후 85%)다.
#    '비슷했던 때 다 올랐다' 는 기저율과 견주기 전에는 아무것도 말하지 않는다.
# 3. **지금과 이어진 최근은 뺀다.** 요인은 천천히 움직여 지난 1~2년이 늘 가장 비슷하게 나온다.
#    그것은 다른 시기가 아니라 '지금' 의 연장이다.
#
# z 는 **전체 기간** 평균·표준편차로 낸다(카드·과거 국면 표와 같은 자). 예측이 아니라 서술이라
# 미래 값이 자에 섞여도 된다 — '그때 높았다' 와 '지금 높다' 를 같은 자로 견주는 것이 목적이다.
SIMILAR_BAND = Z_MID          # 요인 하나가 '지금과 비슷한 자리' — 카드의 '보통' 경계와 같은 선
EPISODE_GAP = 12              # 이만큼 안에 이어지는 달은 한 시기다(12개월 창이 11개월을 겹친다)
RECENT_EXCLUDE = 24           # 지금과 이어진 최근은 뺀다
HORIZONS = (6, 12, 24)        # 그 뒤 몇 개월


def _gap(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[4:]) - int(a[4:])


def _episodes(yms: list[str]) -> list[list[str]]:
    """`EPISODE_GAP` 안에 이어지는 달을 한 시기로 묶는다."""
    eps: list[list[str]] = []
    for ym in sorted(yms):
        if eps and _gap(eps[-1][-1], ym) <= EPISODE_GAP:
            eps[-1].append(ym)
        else:
            eps.append([ym])
    return eps


def _fwd(price: dict[str, float], yms: list[str], i: int, k: int) -> float | None:
    return None if i + k >= len(yms) else (price[yms[i + k]] / price[yms[i]] - 1) * 100


def _median(vs: list[float]) -> float | None:
    if not vs:
        return None
    vs = sorted(vs)
    n = len(vs)
    return vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2


def base_rate(price: dict[str, float], months: list[str]) -> dict:
    """그 달들 **전부**의 그 뒤 12개월 — 조건 없이 골랐을 때의 기준선."""
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    vs = [v for v in (_fwd(price, yms, idx[m], 12) for m in months if m in idx) if v is not None]
    if not vs:
        return {"months": 0, "median": None, "up_pct": None}
    return {"months": len(vs), "median": round(_median(vs), 2),
            "up_pct": round(sum(1 for v in vs if v > 0) / len(vs) * 100),
            "from": min(months), "to": max(months)}


def _eligible(s: dict[str, float], price: dict[str, float], last: str) -> list[str]:
    """그 뒤 12개월이 알려지고, 지금과 이어진 최근이 아닌 달."""
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    return [ym for ym in sorted(s) if ym in idx and _gap(ym, last) >= RECENT_EXCLUDE
            and _fwd(price, yms, idx[ym], 12) is not None]


def _episode_row(eps: list[str], price: dict[str, float], z: dict[str, float]) -> dict:
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    fwd = {k: _median([v for v in (_fwd(price, yms, idx[m], k) for m in eps) if v is not None])
           for k in HORIZONS}
    return {"from": eps[0], "to": eps[-1], "months": len(eps),
            "z": round(_median([z[m] for m in eps]), 2),
            "fwd": {str(k): (round(v, 2) if v is not None else None) for k, v in fwd.items()}}


def factor_then(s: dict[str, float], price: dict[str, float]) -> dict:
    """그 요인이 **지금과 비슷한 자리**(z ±`SIMILAR_BAND`)였던 시기와 그 뒤.

    요인 하나만 맞춘 것이라 다른 요인은 그때 전혀 달랐을 수 있다 — 시기마다 무엇이 겹쳤는지는
    거시 분석의 '한 그림에' 와 과거 국면 표가 요인을 함께 보인다.
    """
    last = max(s)
    vals = list(s.values())
    z = {ym: hist_z(vals, v) for ym, v in s.items()}
    pool = _eligible(s, price, last)
    near = [ym for ym in pool if abs(z[ym] - z[last]) <= SIMILAR_BAND]
    eps = [_episode_row(e, price, z) for e in _episodes(near)]
    up = sum(1 for e in eps if (e["fwd"]["12"] or 0) > 0)
    return {"z_now": round(z[last], 2), "band": SIMILAR_BAND,
            "episodes": sorted(eps, key=lambda e: e["from"], reverse=True),
            "summary": {"episodes": len(eps), "up": up, "months": len(near),
                        "median12": (round(_median([e["fwd"]["12"] for e in eps
                                                     if e["fwd"]["12"] is not None]), 2)
                                     if eps else None)},
            "base": base_rate(price, pool)}


# ──────────────────────────────────────────────────────────
# 반영 분해 — 방향은 이론, 크기는 데이터
# ──────────────────────────────────────────────────────────
# 매매지수 1년 변화(%)를 요인들로 나눈다. 예측이 아니라 '지금 변화에 무엇이 얼마나 실려 있나'.
#
#     yoy(t) = a + Σ_j b_j · s_j · z_j(t − lag_j),    b_j ≥ 0
#
# s_j·lag_j 는 `Factor.sign`·`lag` — 이론으로 정했다. 데이터가 정하는 것은 크기 b_j(%p / 1σ) 뿐이고,
# 데이터가 이론과 반대로 움직였으면 b_j 는 0 이 된다(그것도 측정 결과로 보인다). 예전에는 상관의
# 부호로 방향을 정하고 |r| < 0.15 면 뺐다(2026-10-19 요청으로 버렸다).
#
# numpy 를 쓰지 않는다 — hedonic 만 쓰는 규칙(CLAUDE.md '순수 모듈을 지킨다' 옆 규칙). 부호 제약
# 최소제곱은 활성 집합법(Lawson–Hanson)으로 푼다. scipy 의 nnls 와 같은 답인지 scripts/verify_reflect.py 가 대조한다.
REFLECT_BOOT = 400        # 12개월 블록 부트스트랩 횟수 — 흔들림 폭(10~90%)
REFLECT_BLOCK = 12        # 겹치는 12개월 창의 자기상관을 덩어리째 지킨다
REFLECT_SEED = 20261019   # 화면 숫자가 열 때마다 바뀌지 않게


def _shift(s: dict[str, float], months: int) -> dict[str, float]:
    """s'(t) = s(t − months). 그 달에 이미 알려진 과거 값만 쓴다."""
    out = {}
    for ym, v in s.items():
        n = int(ym[:4]) * 12 + int(ym[4:]) - 1 + months
        out[f"{n // 12}{n % 12 + 1:02d}"] = v
    return out


def _solve(A: list[list[float]], v: list[float]) -> list[float]:
    """작은 선형계 A x = v — 부분 피벗 가우스 소거."""
    n = len(v)
    M = [row[:] + [v[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-300:
            continue
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        if abs(M[r][r]) < 1e-300:
            continue
        x[r] = (M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))) / M[r][r]
    return x


def nnls_cd(X: list[list[float]], y: list[float], iters: int = 500) -> tuple[float, list[float]]:
    """절편 + 부호 제약(b ≥ 0) 최소제곱. 중심화한 뒤 **Lawson–Hanson 활성 집합법**, 절편은 중심에서 복원.

    처음에는 좌표 하강이었다. 실데이터에서는 scipy 와 1e-12 까지 같았는데, 거의 같은 열 둘(금리 둘처럼,
    상관 0.999)이 섞인 문제에서 수렴이 느려 최대 0.004 어긋났다(scripts/verify_reflect.py 가 잡았다).
    활성 집합법은 유한 번에 정확한 해에 닿는다. 그람 행렬(p×p)만 쓰므로 순수 파이썬으로 충분하다.
    `iters` 는 바깥 반복의 상한이다 — 시험이 '덜 푼 풀이' 를 만들 때 쓴다.
    """
    n, p = len(X), len(X[0])
    xm = [sum(r[j] for r in X) / n for j in range(p)]
    ym = sum(y) / n
    Xc = [[r[j] - xm[j] for j in range(p)] for r in X]
    yc = [v - ym for v in y]
    G = [[sum(Xc[i][a] * Xc[i][c] for i in range(n)) for c in range(p)] for a in range(p)]
    g = [sum(Xc[i][a] * yc[i] for i in range(n)) for a in range(p)]
    tol = 1e-10 * max(1.0, max(abs(v) for v in g))
    b = [0.0] * p
    P: list[int] = []

    def grad() -> list[float]:
        return [g[j] - sum(G[j][k] * b[k] for k in range(p)) for j in range(p)]

    for _ in range(iters):
        w = grad()
        free = [j for j in range(p) if j not in P and w[j] > tol]
        if not free:
            break
        P.append(max(free, key=lambda j: w[j]))
        while True:
            sP = _solve([[G[a][c] for c in P] for a in P], [g[a] for a in P])
            if all(v > 0 for v in sP):
                for j, v in zip(P, sP):
                    b[j] = v
                break
            # 경계까지만 간다 — 0 아래로 내려가는 변수를 활성 집합에서 뺀다.
            alpha = min(b[j] / (b[j] - v) for j, v in zip(P, sP) if v <= 0)
            for j, v in zip(P, sP):
                b[j] += alpha * (v - b[j])
            P = [j for j in P if b[j] > tol]
            for j in range(p):
                if j not in P:
                    b[j] = 0.0
    a = ym - sum(xm[j] * b[j] for j in range(p))
    return a, b


def _reflect_frame(db: Session, factors=FACTORS) -> tuple[list, list[str], list, list, dict]:
    price = price_series(db)
    yoy = _yoy(price)
    zs = []
    for f in factors:
        s = series_of(db, f)
        vals = list(s.values())
        zs.append(_shift({ym: hist_z(vals, v) for ym, v in s.items()}, f.lag))
    common = sorted(set.intersection(*[set(z) for z in zs]) & set(yoy))
    X = [[f.sign * z[ym] for f, z in zip(factors, zs)] for ym in common]
    y = [yoy[ym] for ym in common]
    return list(factors), common, X, y, yoy


def _r2(a: float, b: list[float], X: list[list[float]], y: list[float]) -> float:
    ym = sum(y) / len(y)
    ss = sum((v - ym) ** 2 for v in y)
    res = sum((v - a - sum(bj * xj for bj, xj in zip(b, r))) ** 2 for v, r in zip(y, X))
    return 1 - res / ss if ss else 0.0


def _pct(vs: list[float], q: float) -> float:
    vs = sorted(vs)
    k = (len(vs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return vs[lo] + (vs[hi] - vs[lo]) * (k - lo)


def reflect(db: Session, factors=FACTORS, boot: int = REFLECT_BOOT) -> dict:
    """매매지수 1년 변화를 '평균일 때 + 요인별 %p + 설명 안 된 몫' 으로 나눈다(위 머리 주석)."""
    import random

    fs, common, X, y, yoy = _reflect_frame(db, factors)
    if len(common) < 60:
        return {"available": False, "note": "요인이 모두 갖춰진 달이 모자라 나누지 않습니다."}
    a, b = nnls_cd(X, y)
    n = len(common)
    rng = random.Random(REFLECT_SEED)
    B = []
    for _ in range(boot):
        idx: list[int] = []
        while len(idx) < n:
            st = rng.randrange(0, n - REFLECT_BLOCK + 1)
            idx.extend(range(st, st + REFLECT_BLOCK))
        idx = idx[:n]
        B.append(nnls_cd([X[i] for i in idx], [y[i] for i in idx])[1])
    half = n // 2
    halves = []
    for sl in (slice(0, half), slice(half, None)):
        ah, bh = nnls_cd(X[sl], y[sl])
        halves.append({"from": common[sl][0], "to": common[sl][-1],
                       "r2": round(_r2(ah, bh, X[sl], y[sl]), 2),
                       "b": {f.key: round(v, 2) for f, v in zip(fs, bh)}})
    now = common[-1]
    x_now = X[-1]
    fitted = a + sum(bj * xj for bj, xj in zip(b, x_now))
    rows = []
    for j, f in enumerate(fs):
        bs = [bb[j] for bb in B]
        lo, hi = _pct(bs, 0.1), _pct(bs, 0.9)
        c = b[j] * x_now[j]
        c_lo, c_hi = sorted((lo * x_now[j], hi * x_now[j]))
        rows.append({"key": f.key, "label": f.label, "group": f.group, "sign": f.sign, "lag": f.lag,
                     "b": round(b[j], 2), "b_lo": round(lo, 2), "b_hi": round(hi, 2),
                     "zero_pct": round(sum(1 for v in bs if v < 1e-9) / len(bs) * 100),
                     # 그 요인의 위치(z) — 시차를 둔 달의 값이다. 화면은 방향을 곱하기 전 값을 보인다.
                     "z": round(f.sign * x_now[j], 2) if f.sign else 0.0,
                     "contrib": round(c, 2), "lo": round(c_lo, 2), "hi": round(c_hi, 2)})
    return {
        "available": True, "now": now, "from": common[0], "to": now, "months": n,
        "target": "매매지수 1년 변화",
        "base": round(a, 2), "fitted": round(fitted, 2), "actual": round(yoy[now], 2),
        "residual": round(yoy[now] - fitted, 2), "r2": round(_r2(a, b, X, y), 2),
        "factors": rows, "halves": halves,
        "boot": {"n": boot, "block": REFLECT_BLOCK},
    }


# ──────────────────────────────────────────────────────────
# 정책·세금 — 재는 것이 아니라 적어 두는 것
# ──────────────────────────────────────────────────────────
def policy_rows(db: Session) -> list[dict]:
    """연표에 **그 뒤 12개월 가격 변화**를 붙인다.

    대책이 가격을 그렇게 만들었다는 뜻이 아니다. 오히려 거꾸로다 — 오르니까
    규제가 나왔다. 그래도 "규제가 나온 뒤 실제로 무슨 일이 있었나" 는 사람들이
    가장 궁금해하는 것이고, 숫자를 안 적으면 각자 기억으로 채운다.
    """
    price = price_series(db)
    yms = sorted(price)
    idx = {y: i for i, y in enumerate(yms)}
    out = []
    for p in POLICY:
        ym = p["date"][:4] + p["date"][5:7]
        i = idx.get(ym)
        g = government_at(p["date"])
        out.append({
            **p,
            "gov": g["label"] if g else None,
            "fwd12": (round(_fwd12(price, yms, i), 2)
                      if i is not None and _fwd12(price, yms, i) is not None else None),
        })
    return sorted(out, key=lambda r: r["date"], reverse=True)


def policy_summary(rows: list[dict]) -> list[dict]:
    """종류별로 **그 뒤 12개월에 실제로 무슨 일이 있었나.**

    재 보면 상식과 반대다 — 규제강화 뒤가 더 올랐고 완화 뒤가 떨어졌다
    (12·16 +15.3%, 6·17 +17.4%, 7·10 +19.0% / 2022-11 -9.2%, 1·3 -2.7%).
    **정책이 거꾸로 작동해서가 아니라 오르니까 규제가 나왔기 때문이다.** 이걸
    적지 않으면 보는 사람이 "규제하면 오른다" 로 읽는다. 그래서 숫자와 함께
    왜 그렇게 보이는지를 같이 낸다.
    """
    out = []
    for kind in ("규제강화", "규제완화", "공급확대", "세제강화", "세제완화"):
        vals = sorted(r["fwd12"] for r in rows
                      if r["kind"] == kind and r["fwd12"] is not None)
        if not vals:
            continue
        mid = (vals[len(vals) // 2] if len(vals) % 2
               else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2)
        out.append({"kind": kind, "n": len(vals), "median": round(mid, 2),
                    "min": vals[0], "max": vals[-1]})
    return out


def overview(db: Session) -> dict:
    factors = factor_rows(db)
    policy = policy_rows(db)
    price = price_series(db)
    yms = sorted(price)
    last = yms[-1]
    yoy = ((price[last] / price[yms[-13]] - 1) * 100) if len(yms) > 13 else None
    # 매매지수는 **1년 변화율**로 겹친다. 지수 수준은 추세로만 올라 z 가 '요즘이 높다' 만
    # 말한다 — 요인들(대개 증감)과 같은 결로 견주려면 변화율이다.
    py = _yoy(price)
    pv = list(py.values())
    return {
        "price": {
            "region": f"경기 남부 {len(DISTRICTS)}개 시군구",
            "ym": last,
            "index": round(price[last], 2),
            "yoy": round(yoy, 2) if yoy is not None else None,
            "series": [{"ym": k, "v": round(v, 2)} for k, v in sorted(price.items())],
            "yoy_series": [{"ym": k, "v": round(v, 2), "z": round(hist_z(pv, v), 2)}
                           for k, v in sorted(py.items())],
        },
        "groups": list(GROUP_ORDER),
        "factors": factors,
        "policy": policy,
        "policy_covers_from": COVERS_FROM,
        "policy_aftermath": policy_summary(policy),
        # 겹친 그림의 정권 띠와 연표의 묶음 머리. 달(YYYYMM)로 넘긴다 — 그림의 x 축이 달이다.
        # 시작 달이 같으면 늦게 시작한 쪽이 그 달을 갖는다(파면 달은 권한대행).
        "governments": [{"from": g["start"][:4] + g["start"][5:7],
                         "to": g["end"][:4] + g["end"][5:7] if g["end"] else None,
                         "name": g["name"], "label": g["label"],
                         "start": g["start"], "end": g["end"], "note": g["note"]}
                        for g in GOVERNMENTS],
        "governments_source": GOV_SOURCE,
        "history": history(db),
        "reflect": reflect(db),
        # '가장 센 것도 0.50 이라 어느 요인도 혼자서는 설명하지 못한다' 를 적었었다.
        # 값은 그 자리에서 쟀지만 **판정('못한다')은 그날의 값에 묶여** 있어, 센 요인이
        # 생기면 숫자만 바뀌고 문장은 틀린다. 판정은 빼고 방법과 지역만 남긴다.
        "note": ("가격은 경기 남부 구들의 평균이지만 미분양·심리는 경기 전체, "
                 "통화량·금리는 전국 값입니다."),
    }
