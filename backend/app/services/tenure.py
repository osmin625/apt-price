"""매매 · 전세 · 월세 — 같은 집을 세 방법으로 살 때의 비용과, 금리에 따라 수요가 옮겨 가는 흐름.

## 무엇을 보려는가 (2026-10-19 요청)

실수요자는 매매(주담대 이자)·전세(전세대출 이자)·월세(차임) 중 매달 덜 드는 쪽으로 옮긴다.
금리가 오르면 매매·전세 이자가 무거워져 그쪽 수요가 빠지고(매매·전세 하락 압력), 그 수요가 월세로
몰려 월세와 전월세 전환율이 오른다. 월세 지출이 이자 비용과 맞붙는 데까지 오르면 다시 매매·전세로
돌아가 시차를 두고 가격을 밀어 올린다 — 이 연쇄가 **실제로 나타났는지 지켜보는** 탭이다. 증명하는
도구가 아니다: 월세 통계가 2015년부터라 금리 인상 국면이 사실상 한 번(2021~2023)이고, 그 뒤
금리 인하와 겹친다.

## 같은 집의 월 비용 — 무엇을 세고 무엇을 안 세나

    매매 = 매매가 × (대출 비율 × 주담대 금리 + 나머지 × 예금 금리) ÷ 12
    전세 = 전세가 × (대출 비율 × 전세대출 금리 + 나머지 × 예금 금리) ÷ 12
    월세 = 전세가 × 전월세 전환율 ÷ 12         (같은 집의 전세 보증금을 전부 월세로 바꾼 값)

'계산기로 두들기는' 이자 비교에 맞춘다 — 기대 시세차익·세금·관리비·감가는 세지 않는다. 대출
비율은 화면에서 바꾼다(계산은 화면이 한다 — 정적 사이트에서도 돌게). 여기서는 재료만 보낸다.
월세를 실제 '평균 월세' 가 아니라 **전환율로 바꾼 같은 집**으로 내는 까닭: 평균 월세가 붙은 집은
평균 매매가가 붙은 집보다 작아(월세 아파트가 소형에 몰린다) 세 값을 견주면 집 크기를 견주게 된다.

## 가격 수준은 지수로 이어 붙인다 — 2021-07 표본 개편

R-ONE 의 평균 매매가격·평균 월세보증금은 2021-07 에 한 달 새 18%·55% 뛴다(13개 구 평균,
2021-06 → 07). 집값이 그만큼 오른 것이 아니라 그 달 표본을 크게 늘린 개편 때문이고, 지수는 개편
앞뒤를 이어 붙여 둬 끊기지 않는다. 처음에 평균가를 그대로 써서 '같은 집 월 비용' 이 그 달 한꺼번에
뛰었다. 그래서 수준은 **마지막 달의 평균가 한 점**만 쓰고, 그 앞은 지수 비율로 거슬러 낸다.

    매매가(t) = 매매가(마지막) × 매매지수(t) ÷ 매매지수(마지막)
    전세가(t) = 매매가(마지막) × 전세가율(마지막) × 전세지수(t) ÷ 전세지수(마지막)

전환율은 비율이라 개편에 끊기지 않았다(4.28 → 4.24%). 평균 월세·보증금은 같은 개편으로 끊기고
소형 위주라 받지 않는다. `scripts/verify_tenure.py` 가 이어 붙인 값에 한 달 새 튐이 없는지,
그리고 원래 평균가를 넣으면 2021-07 을 잡는지를 본다.

## 지역 — 모든 달에 값이 있는 구만

경기 남부 17개 구를 평균 내되 **분석 기간의 모든 달에 값이 있는 구만** 쓴다. 화성시는 2026-02 에
네 구로 나뉘어 그 앞이 비어 있다 — 섞으면 그 달에 평균의 구성이 바뀌어 값이 튄다(그 달 집값이
변한 것처럼 보인다). 빠진 구는 응답에 이름과 까닭을 싣는다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clients.molit import DISTRICTS
from ..models import RebStat

# 구마다 오는 표(R-ONE). 평균가·전세가율은 마지막 달 한 점만 쓴다(위 '지수로 이어 붙인다').
LEVELS = ("avg_sale_price", "jeonse_ratio", "conv_rate")
INDICES = ("sale_index", "jeonse_index", "rent_index")
# 전국 한 줄(ECOS·R-ONE). 구와 무관하다.
RATES = ("mortgage_rate", "jeonse_loan_rate", "deposit_rate", "base_rate")

# 화면이 처음 띄우는 대출 비율. 매매는 LTV 규제 상한 언저리, 전세는 전세대출 보증 한도(보증금의
# 80%)에서 잡았다 — 바꿔 보라고 둔 기본값이지 '평균적인 사람' 의 값이 아니다.
DEFAULT_LTV = {"buy": 0.5, "jeonse": 0.8}

# 삼성전자 임직원 사내 주거지원 대출(2026-10-22 요청 — 임직원이면 사내대출 기준으로 견주게). 조건은
# 사용자가 정리한 페이지(사내 주거지원제도, 2026-10 확인)를 옮겼다 — 공표 통계가 아니라 사내 제도라
# 대조할 공개 출처가 없다. 바뀌면 여기만 고친다(화면 문구는 이 값에서 그 자리에서 만든다).
#
# - 주택 **구입**만이다. 정리에 전세 지원은 없다 — 그래서 전세·월세 비용은 임직원이어도 같다.
# - 한도는 매매가의 70% 와 5억 중 작은 쪽(KB 시세 70% 도 걸리지만 시세가 없어 매매가로 본다).
# - 본인 부담 연 1.5%, 회사 지원 연 3.1% 는 근로소득으로 과세된다. 실효 금리 = 1.5 + 3.1 × 세율.
#   세율은 과세표준 구간마다 달라 화면에서 고른다(소득세 15·24·35% + 지방소득세 10%).
# - 3년 거치 10년 상환이지만 이 탭은 이자만 견준다(원금 상환은 저축이라 비용이 아니다).
# - **금리 이력이 없다.** 지금 조건을 과거 모든 달에 적용한 가정이고, 화면에 그렇게 적는다.
EMPLOYEE_LOAN = {
    "label": "삼성전자 임직원",
    "loan": "사내 주거지원 대출",
    "rate": 1.5,
    "support": 3.1,
    "ltv": 0.7,
    "cap": 50000,                    # 만원(5억)
    "tax": [0.165, 0.264, 0.385],    # 15·24·35% 구간 + 지방소득세
}

# 금리 인상기 — 기준금리가 오른 달끼리 이만큼 안에 이어지면 한 국면이다. 인상은 몇 달 걸러
# 한 번씩 오므로(2021-08 → 11 → 2022-01 …) 12개월이면 한 사이클이 끊기지 않는다.
HIKE_GAP = 12
# 순서 확인 그림 — 인상 시작 달 앞뒤로 이만큼.
EVENT_SPAN = (-12, 48)


def _gap(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[4:]) - int(a[4:])


def _load(db: Session, metrics: tuple[str, ...], by_sgg: bool) -> dict[str, dict]:
    """{metric: {sgg: {ym: v}}} (by_sgg) 또는 {metric: {ym: v}}(전국)."""
    q = select(RebStat.metric, RebStat.sgg_cd, RebStat.ym, RebStat.value).where(RebStat.metric.in_(metrics))
    out: dict[str, dict] = {m: {} for m in metrics}
    for m, sgg, ym, v in db.execute(q):
        if by_sgg:
            if sgg in DISTRICTS:
                out[m].setdefault(sgg, {})[ym] = float(v)
        else:
            out[m][ym] = float(v)
    return out


def _panel(data: dict[str, dict]) -> tuple[list[str], list[str]]:
    """모든 지표·모든 달에 값이 있는 (구, 달). 달은 지표들이 함께 있는 구간이다."""
    months = None
    for m, by in data.items():
        ms = set().union(*[set(s) for s in by.values()]) if by else set()
        months = ms if months is None else months & ms
    months = sorted(months or [])
    sggs = [s for s in DISTRICTS
            if all(s in data[m] and all(ym in data[m][s] for ym in months) for m in data)]
    return sggs, months


def _avg(by: dict[str, dict[str, float]], sggs: list[str], ym: str) -> float:
    return sum(by[s][ym] for s in sggs) / len(sggs)


def chained(lv: dict, ix: dict, sggs: list[str], months: list[str]) -> list[tuple[str, float, float]]:
    """[(ym, 매매가, 전세가)] 만원, 구 평균. 마지막 달 평균가에서 지수 비율로 거슬러 낸다.

    구마다 이어 붙인 뒤 평균한다 — 평균가를 먼저 평균하고 평균 지수로 거스르면 비싼 구와 싼 구의
    오른 폭이 섞인다. 전세가도 구마다 (매매가 × 전세가율) 을 낸 뒤 평균한다.
    """
    if not months:
        return []
    T = months[-1]
    out = []
    for ym in months:
        sale = jeonse = 0.0
        for s in sggs:
            p = lv["avg_sale_price"][s][T] / 10                                # 천원 → 만원
            sale += p * ix["sale_index"][s][ym] / ix["sale_index"][s][T]
            jeonse += p * lv["jeonse_ratio"][s][T] / 100 * ix["jeonse_index"][s][ym] / ix["jeonse_index"][s][T]
        out.append((ym, sale / len(sggs), jeonse / len(sggs)))
    return out


def hikes(base: dict[str, float]) -> list[dict]:
    """기준금리 인상기 — 오른 달을 `HIKE_GAP` 안에 이어지는 것끼리 묶어 첫 인상~마지막 인상."""
    ks = sorted(base)
    ups = [ks[i] for i in range(1, len(ks)) if base[ks[i]] > base[ks[i - 1]] + 1e-9]
    out: list[dict] = []
    for ym in ups:
        if out and _gap(out[-1]["to"], ym) <= HIKE_GAP:
            out[-1]["to"] = ym
        else:
            out.append({"from": ym, "to": ym})
    for h in out:
        h["rise"] = round(base[h["to"]] - base[ks[ks.index(h["from"]) - 1]], 2)
    return out


def _yoy(s: dict[str, float]) -> list[dict]:
    ks = sorted(s)
    return [{"ym": ks[i], "v": round((s[ks[i]] / s[ks[i - 12]] - 1) * 100, 2)}
            for i in range(12, len(ks)) if _gap(ks[i - 12], ks[i]) == 12]


def overview(db: Session) -> dict:
    lv = _load(db, LEVELS, by_sgg=True)
    ix = _load(db, INDICES, by_sgg=True)
    rt = _load(db, RATES, by_sgg=False)
    if not ix["rent_index"] or not rt["mortgage_rate"]:
        return {"available": False,
                "note": "월세·금리가 아직 적재되지 않았습니다 — ingest_reb, ingest_macro 를 돌리세요."}

    sggs, months = _panel(lv)
    isggs, imonths = _panel(ix)
    use = [s for s in sggs if s in isggs]
    dropped = [{"name": DISTRICTS[s], "why": "분석 기간 중 빈 달이 있다(분구 등)"}
               for s in DISTRICTS if s not in use]

    levels = chained(lv, ix, use, [m for m in months if m in imonths])
    rows = []
    for ym, sale, jeonse in levels:
        if not all(ym in rt[r] for r in ("mortgage_rate", "jeonse_loan_rate", "deposit_rate")):
            continue
        rows.append({
            "ym": ym, "sale": round(sale), "jeonse": round(jeonse),
            "conv": round(_avg(lv["conv_rate"], use, ym), 2),
            "mortgage": rt["mortgage_rate"][ym], "jeonse_loan": rt["jeonse_loan_rate"][ym],
            "deposit": rt["deposit_rate"][ym], "base": rt["base_rate"].get(ym),
        })

    idx = {m: {ym: _avg(ix[m], use, ym) for ym in imonths} for m in INDICES}
    hk = [h for h in hikes(rt["base_rate"]) if h["to"] >= imonths[0]]
    events = []
    for h in hk:
        s0 = h["from"]
        if s0 not in idx["rent_index"]:
            continue
        paths = {}
        for m in INDICES:
            ks = sorted(idx[m])
            i0 = ks.index(s0)
            paths[m] = [{"k": k, "v": round(idx[m][ks[i0 + k]] / idx[m][s0] * 100, 2)}
                        for k in range(EVENT_SPAN[0], EVENT_SPAN[1] + 1) if 0 <= i0 + k < len(ks)]
        events.append({"start": s0, "end": h["to"], "rise": h["rise"], "paths": paths})

    return {
        "available": True,
        "region": f"경기 남부 {len(use)}개 구",
        "used": [DISTRICTS[s] for s in use],
        "dropped": dropped,
        "rows": rows,
        "yoy": {m: _yoy(idx[m]) for m in INDICES},
        "rates": {r: [{"ym": k, "v": v} for k, v in sorted(rt[r].items()) if k >= (imonths[0] if imonths else k)]
                  for r in RATES},
        "hikes": hk,
        "events": events,
        "ltv": DEFAULT_LTV,
        "employee": EMPLOYEE_LOAN,
        "event_span": list(EVENT_SPAN),
    }
