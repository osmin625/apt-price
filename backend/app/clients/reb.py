"""한국부동산원 부동산통계 Open API (R-ONE) 클라이언트.

공공데이터포털 '한국부동산원_부동산통계 조회 서비스' (데이터 15134761)
https://www.data.go.kr/data/15134761/openapi.do

## 왜 KB 가 아니라 여기인가

KB부동산 데이터허브에도 같은 성격의 통계가 있고 화면도 좋다. 그런데 거기서 경기
남부 17개 시군구를 모아 보려면 매번 17번을 손으로 고르고(선택이 URL·공유링크에
남지 않는다) 차트는 5개까지만 그려진다. 데이터를 가져오려면 공개 문서가 없는
내부 API 를 써야 하는데, 이 저장소는 같은 이유로 네이버 호가 수집을 처음부터
배제했다. 기준을 상대에 따라 바꾸지 않는다.

한국부동산원은 **공표 통계를 Open API 로 직접 준다.** 무료이고 이용허락범위에
제한이 없다. 숫자는 KB 와 다르다(조사 주체·표본이 다르다) — 같은 것의 다른 추정치
이지 둘 중 하나가 틀린 것이 아니다.

## 인증키

data.go.kr 의 API 유형이 `LINK` 다. 즉 data.go.kr 이 중계하지 않고 R-ONE 이 직접
서비스하므로, **MOLIT_SERVICE_KEY 를 그대로 쓸 수 없고** R-ONE 에서 따로 발급받는다
(data.go.kr 활용신청 → 제공처 이동, 또는 R-ONE 로그인 후 '인증키 발급내역').

키가 없으면 샘플 모드로 동작한다. 샘플은 **5행 고정**이고 `pIndex`·`pSize` 가
무시된다(재서 확인했다). 그래서 파싱과 코드 대조는 키 없이도 검증할 수 있지만
실제 적재는 불가능하다.

## 쓰는 통계표

전부 월간·시군구 단위다. 코드는 R-ONE '통계코드 검색'에서 확인했다.

    A_2024_00045  (월) 매매가격지수_아파트
    A_2024_00050  (월) 전세가격지수_아파트
    A_2024_00060  (월) 평균매매가격_아파트
    A_2024_00061  (월) 평균단위매매가격_아파트      ← ㎡당. 우리 평당가와 직접 대조된다
    A_2024_00062  (월) 중위매매가격_아파트
    A_2024_00072  (월) 평균 매매가격 대비 전세가격_아파트  ← 전세가율

## 지역 코드는 표마다 다르다 — 박아 두면 틀린다

처음에는 지수표(`A_2024_00045`)의 분류코드 조회 화면에서 법정동코드로 대조해
`CLS_IDS` 를 박아 두고 모든 표에 썼다. **틀렸다.** 적재를 돌리자 검사가 잡았다.

    [X] 화성시 만세구  R-ONE 경로가 '경기>서해안권>부천시>원미구' 로 끝이 다릅니다.

같은 `530091` 이 지수표에서는 화성시 만세구인데 평균매매가격표(`A_2024_00060`)
에서는 부천시 원미구였다. 가격표에는 `(구)원미구` 같은 **옛 행정구역 항목이 더**
들어 있어 번호가 3칸씩 밀린다. 지수표 분류 236개, 가격표 245개다.

그래서 코드를 박지 않고 **표마다 `SttsApiTblItm.do` 로 받아 경로로 찾는다.**
`ITM_FULLNM` 이 `경기>서해안권>화성시>만세구` 처럼 시와 구를 다 담고 있어 모호하지
않다. 끝 조각이 우리 구 이름과 **정확히 같아야** 하므로 `(구)원미구` 같은 항목은
저절로 걸러진다. 후보가 둘 이상이면 고르지 않고 실패시킨다 — 잘못 붙이면 남의
지역 시세가 섞이고, 못 붙이면 줄 하나가 비는 것뿐이다.

받은 뒤에도 `CLS_FULLNM` 으로 한 번 더 검산한다(`check_region`). 찾을 때 쓴 것과
같은 경로지만, 응답이 요청한 지역과 다르게 올 가능성까지 닫아 둔다. **틀린 코드는
오류가 아니라 남의 지역 값으로 조용히 돌아오기** 때문이다 — 화성시 분구 때 실거래
0건으로 겪은 것과 같은 실패 방식이다.

## 화성시 분구는 시계열이 짧다

`probe_reb.py` 를 돌려 알아냈다. 다른 시군구는 2003년 11월부터 있는데 **화성시
만세·효행·병점·동탄구는 2026년 1월부터**다. 분구 시점에 통계가 새로 시작한 것이다.

화면에서 이걸 모르고 같은 축에 그리면 화성 4개 구만 선이 뚝 끊긴 것처럼 보이고,
장기 추이 비교에서는 분모가 달라진다. **없는 기간을 0 이나 결측 보간으로 메우지
말 것** — 분구 전 화성시 전체(`41590`, CLS_ID 520032)는 따로 있으므로, 긴 추이가
필요하면 그쪽을 쓰고 그렇게 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import settings
from .molit import DISTRICTS

BASE = "https://www.reb.or.kr/r-one/openapi"

# 통계표 코드 → 우리가 부르는 이름. 적재와 화면이 같은 키를 쓴다.
TABLES: dict[str, str] = {
    "A_2024_00045": "sale_index",       # 매매가격지수
    "A_2024_00050": "jeonse_index",     # 전세가격지수
    "A_2024_00060": "avg_sale_price",   # 평균매매가격(만원)
    "A_2024_00061": "avg_unit_price",   # 평균단위매매가격(㎡당)
    "A_2024_00062": "med_sale_price",   # 중위매매가격(만원)
    "A_2024_00072": "jeonse_ratio",     # 매매가격 대비 전세가격(%)
    # 거래량. 가격 표와 **다른 축**이라 넣었다 — 12개월 거래 배수와 12개월 가격
    # 변화의 Spearman 이 0.352 밖에 안 된다(모델 괴리 차트가 0.882 였다). 가격만
    # 봐서는 '거래가 받쳐 준 상승' 과 '호가만 오른 상승' 이 구분되지 않는다.
    # 과천은 거래가 5년 평균의 0.76배로 **줄었는데** 가격은 +7.8% 였다.
    #
    # 항목이 두 개다(100001 동(호)수 · 100002 면적). 기본 ITM_ID 가 100001 이라
    # 호수가 들어온다. 면적은 쓰지 않는다 — 평형 구성은 평균/중위 괴리로 본다.
    "A_2024_00554": "trade_volume",     # 아파트매매거래현황(호)
}

# 지수·금액 표는 항목이 하나뿐이라 ITM_ID 를 고정해도 된다. 분류코드 조회에서
# 확인했다(지수=100001). 표마다 다를 수 있으므로 None 이면 생략하고 전부 받는다.
DEFAULT_ITM_ID = "100001"

# 표별 지역코드 캐시. {통계표: {우리 시군구코드: CLS_ID}}
_CLS_CACHE: dict[str, dict[str, str]] = {}


class RebError(RuntimeError):
    pass


@dataclass
class RebPoint:
    """통계 한 점. 한 (표·지역·월)."""

    table_id: str
    metric: str
    sgg_cd: str          # 우리 기준 시군구 코드(법정동코드 앞 5자리)
    cls_id: str          # R-ONE 지역코드. 재조회할 때 쓴다
    region_name: str     # R-ONE 표기. 대조용으로 남긴다
    ym: str              # "YYYYMM"
    value: float
    unit: str = ""       # 공표 단위(UI_NM). '지수'/'%'/'천원'/'천원/㎡'


def available() -> bool:
    return bool(getattr(settings, "reb_service_key", "") or "")


def _get(path: str, params: dict) -> dict:
    q = {"Type": "json", **{k: v for k, v in params.items() if v is not None}}
    key = getattr(settings, "reb_service_key", "") or ""
    if key:
        q["KEY"] = key

    try:
        r = httpx.get(f"{BASE}/{path}", params=q, timeout=30.0)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as exc:
        raise RebError(f"R-ONE 요청 실패: {exc}") from exc
    except ValueError as exc:
        raise RebError(f"R-ONE 응답이 JSON 이 아닙니다: {exc}") from exc

    # 오류는 최상위 RESULT 로 온다. HTTP 는 200 이므로 여기서 안 보면 조용히 넘어간다.
    if "RESULT" in data:
        res = data["RESULT"]
        raise RebError(f"R-ONE 오류 {res.get('CODE')}: {res.get('MESSAGE')}")
    return data


def _unwrap(data: dict, root: str) -> tuple[int, list[dict]]:
    """R-ONE 응답은 [{head:[{list_total_count}, {RESULT}]}, {row:[...]}] 모양이다."""
    blocks = data.get(root)
    if not isinstance(blocks, list) or not blocks:
        raise RebError(f"{root} 블록이 없습니다.")

    total = 0
    rows: list[dict] = []
    for b in blocks:
        if "head" in b:
            for h in b["head"]:
                if "list_total_count" in h:
                    total = int(h["list_total_count"])
                if "RESULT" in h and h["RESULT"].get("CODE") not in (None, "INFO-000"):
                    raise RebError(
                        f"R-ONE 오류 {h['RESULT'].get('CODE')}: {h['RESULT'].get('MESSAGE')}"
                    )
        if "row" in b:
            rows.extend(b["row"])
    return total, rows


def table_meta() -> dict[str, dict]:
    """통계표 목록. 우리가 쓰는 표의 **기준시점**이 여기 있다.

    지수는 기준시점이 100 이고, 한국부동산원은 주기적으로 기준을 옮긴다(리베이스).
    그래서 "2026년 1월 = 100" 같은 문구를 코드에 박으면 언젠가 거짓이 된다.
    실제로 그렇게 적었다가 틀렸다 — 받아서 보니 2026년 **6월** 기준이었고,
    데이터로도 202606 의 값이 모든 시군구에서 정확히 100.000 이었다.

    그래서 적재할 때 `RPSTUI_NM` 을 같이 받아 행에 저장한다. 리베이스되면 다음
    적재에서 저절로 따라간다.
    """
    out: dict[str, dict] = {}
    page = 1
    while page <= 30:  # 738개 / 100 = 8페이지. 여유를 두되 무한루프는 막는다.
        data = _get("SttsApiTbl.do", {"pIndex": page, "pSize": 100})
        total, rows = _unwrap(data, "SttsApiTbl")
        if not rows:
            break
        for r in rows:
            tid = str(r.get("STATBL_ID") or "")
            if tid in TABLES:
                out[tid] = r
        if len(out) == len(TABLES) or len(rows) < 100:
            break
        page += 1
    return out


# ──────────────────────────────────────────────────────────
# 공급 통계 — 시도 단위
# ──────────────────────────────────────────────────────────
# 가격 표는 시군구까지 오지만 공급 표는 **대부분 시도까지만** 온다(미분양만 예외).
# 그래서 서울·경기 두 줄로 본다. 서울을 넣는 이유는 붙여 주신 대로 — 수도권 공급이
# 넘치면 서울 외곽부터 빠지므로 둘을 같이 봐야 한다.
SIDO: dict[str, str] = {"11": "서울", "41": "경기"}

# (통계표, 항목ID, 주기, 지표이름). 항목ID 는 `region_codes` 의 ITM_TAG=='항목'.
#
# 표를 고른 경위는 docs/analysis/supply.md 에 있다. 738개를 훑어 '입주/준공/착공/인허가/
# 분양/멸실/보급률' 로 걸렀고, **미래 입주 예정 물량은 R-ONE 에 없다**(민간 집계다).
SUPPLY_TABLES: dict[str, tuple[str, int, str]] = {
    # 공급 파이프라인. 인허가 → 착공 → 준공 순으로 2~3년씩 흐른다.
    #
    # **인허가만 연 누계로 온다.** 2024년 서울이
    # 2517 → 5055 → 6654 → ... → 51792 로 12월까지 계속 커진다. 착공·준공은 월별이다
    # (준공 2024: 3407, 1930, 1282, ... 로 오르내린다).
    #
    # 모르고 12개월을 더했다가 서울 인허가가 282,599호로 나왔다 — 준공이 4만인데
    # 7배다. 숫자가 들어오긴 하므로 **오류가 아니라 그럴듯한 거짓**이었다.
    # 적재할 때 월별로 되돌린다. 화면마다 기억할 일이 아니다.
    "T235263129553687": ("permit", 10001, "MM"),     # 주택건설인허가실적(연 누계)
    "T233033129823134": ("start", 10001, "MM"),      # 주택착공실적
    "T237273130004614": ("done", 10001, "MM"),       # 주택준공실적(사용검사)
    # 적정 공급량의 두 조각. 둘 다 연 단위다.
    "T234153129852136": ("households", 10001, "YY"),  # 주택보급률 > 가구수(등록센서스)
    "T246383134037612": ("demolish", 10001, "YY"),    # 주택멸실현황 > 계
    # 아파트만 따로. 멸실의 성격을 보려면 필요하다(단독 철거와 다르다).
    "T246383134037612#apt": ("demolish_apt", 10006, "YY"),
}

# 연 누계로 공표되는 지표. 적재할 때 차분해서 월별로 되돌린다.
CUMULATIVE_YTD = {"permit"}

# 표마다 지역 경로 모양이 다르다. **짐작하지 않고** 이 순서로 찾아 첫 번째를 쓴다.
#   준공·착공   서울>총계
#   인허가      서울>합계(가구수기준)
#   멸실·보급률  서울
#   분양        수도권>서울
_SIDO_PATH_PREFS = ("{s}", "{s}>총계", "{s}>계", "{s}>합계(가구수기준)", "수도권>{s}")


def sido_cls_id(table_id: str, sido: str) -> str:
    """이 표에서 시도의 `CLS_ID`.

    경로 모양이 표마다 달라서 선호 순서로 찾는다. **후보가 없으면 실패시킨다** —
    엉뚱한 지역을 집으면 남의 공급량이 섞이는데, 그건 빈 줄보다 나쁘다
    (`district_cls_ids` 와 같은 원칙).
    """
    rows = [r for r in region_codes(table_id.split("#")[0])
            if r.get("ITM_TAG") == "분류"]
    by_path = {str(r.get("ITM_FULLNM") or ""): str(r["ITM_ID"]) for r in rows}
    for pref in _SIDO_PATH_PREFS:
        want = pref.format(s=sido)
        if want in by_path:
            return by_path[want]
    raise RebError(
        f"{table_id} 에서 '{sido}' 경로를 찾지 못했습니다. "
        f"있는 경로 예: {sorted(by_path)[:6]}"
    )


def fetch_sido(table_id: str, sgg_cd: str, *, page_size: int = 1000) -> list[RebPoint]:
    """한 (공급표·시도)의 전체 시계열.

    연 단위 표는 `ym` 을 `YYYY00` 으로 둔다 — 6자리 자리수를 맞추면서 월과 섞이지
    않고, 문자열 정렬이 그대로 시간 순서가 된다.
    """
    metric, itm_id, cycle = SUPPLY_TABLES[table_id]
    sido = SIDO[sgg_cd]
    cls_id = sido_cls_id(table_id, sido)
    real_id = table_id.split("#")[0]

    data = _get("SttsApiTblData.do", {
        "STATBL_ID": real_id, "DTACYCLE_CD": cycle,
        "CLS_ID": cls_id, "ITM_ID": itm_id, "pSize": page_size,
    })
    _, rows = _unwrap(data, "SttsApiTblData")

    out: list[RebPoint] = []
    for r in rows:
        val = r.get("DTA_VAL")
        if val is None:
            continue
        t = str(r.get("WRTTIME_IDTFR_ID") or "")
        if cycle == "YY":
            if len(t) != 4:
                continue
            t = t + "00"
        elif len(t) != 6:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        out.append(RebPoint(
            table_id=real_id, metric=metric, sgg_cd=sgg_cd,
            cls_id=str(cls_id), region_name=sido, ym=t, value=v,
            unit=str(r.get("UI_NM") or ""),
        ))

    if metric in CUMULATIVE_YTD:
        out = _undo_ytd(out)
    return out


def _undo_ytd(points: list[RebPoint]) -> list[RebPoint]:
    """연 누계를 월별로 되돌린다. 1월은 그대로, 그 뒤는 전월과의 차.

    **그 해 1월이 없으면 그 해를 통째로 버린다.** 2월부터 시작하는 해에서 2월 값을
    그대로 쓰면 1~2월 두 달치가 한 달로 들어간다. 줄이 하나 비는 것이 낫다.
    """
    by_year: dict[str, list[RebPoint]] = {}
    for p in points:
        by_year.setdefault(p.ym[:4], []).append(p)

    out: list[RebPoint] = []
    for year, ps in by_year.items():
        ps.sort(key=lambda p: p.ym)
        if ps[0].ym[4:] != "01":
            continue
        prev = 0.0
        for p in ps:
            out.append(RebPoint(
                table_id=p.table_id, metric=p.metric, sgg_cd=p.sgg_cd,
                cls_id=p.cls_id, region_name=p.region_name, ym=p.ym,
                value=p.value - prev, unit=p.unit,
            ))
            prev = p.value
    return out


def region_codes(table_id: str) -> list[dict]:
    """표의 항목·분류 목록. 지역은 `ITM_TAG == "분류"` 로 온다.

    주의: 여기에는 **법정동코드가 없다.** 우리 시군구와 잇는 것은 `ITM_FULLNM`
    경로다 — `district_cls_ids` 참조.
    """
    data = _get("SttsApiTblItm.do", {"STATBL_ID": table_id, "pSize": 1000})
    _, rows = _unwrap(data, "SttsApiTblItm")
    return rows


def _path_matches(full_name: str, our_name: str) -> bool:
    """`경기>서해안권>화성시>만세구` 가 `화성시 만세구` 인가.

    끝 조각이 **정확히** 같아야 한다. 가격표에 섞여 있는 `(구)원미구` 같은 옛
    행정구역이 `원미구` 로 잡히면 안 되기 때문이다.
    """
    parts = [p.strip() for p in (full_name or "").split(">") if p.strip()]
    if not parts:
        return False
    want = our_name.split()  # ["화성시", "만세구"] 또는 ["오산시"]
    if parts[-1] != want[-1]:
        return False
    if len(want) == 2 and want[0] not in parts:
        return False
    return True


def district_cls_ids(table_id: str) -> dict[str, str]:
    """이 표에서 우리 17개 시군구의 `CLS_ID`. 표마다 다르므로 매번 조회한다.

    후보가 둘 이상이면 **고르지 않고 실패시킨다.** 잘못 붙이면 남의 지역 시세가
    섞이지만, 못 붙이면 줄 하나가 비는 것뿐이다.
    """
    if table_id in _CLS_CACHE:
        return _CLS_CACHE[table_id]

    rows = [r for r in region_codes(table_id) if r.get("ITM_TAG") == "분류"]
    out: dict[str, str] = {}
    for sgg, our_name in DISTRICTS.items():
        hits = [r for r in rows if _path_matches(str(r.get("ITM_FULLNM") or ""), our_name)]
        if len(hits) > 1:
            paths = [str(h.get("ITM_FULLNM")) for h in hits]
            raise RebError(f"{our_name}: {table_id} 에서 후보가 여럿입니다 — {paths}")
        if hits:
            out[sgg] = str(hits[0]["ITM_ID"])

    _CLS_CACHE[table_id] = out
    return out


def check_region(sgg_cd: str, full_name: str) -> str | None:
    """받은 값이 정말 그 지역 것인지 검산. 어긋나면 사유를 돌려준다.

    `full_name` 은 `CLS_FULLNM`(예: `경기>경부2권>수원시>영통구`)이다. 우리 이름
    (`수원시 영통구`)의 마지막 조각이 경로 끝과 같고, 시 이름도 경로 안에 있어야
    한다. 구가 없는 시(오산시 등)는 마지막 조각 하나만 본다.

    박아 둔 코드가 낡으면 **오류가 아니라 남의 지역 값**이 조용히 들어온다.
    화성시 분구 때 실거래 0건으로 겪은 것과 같은 실패 방식이라 검사를 코드에 넣는다.
    """
    ours = DISTRICTS.get(sgg_cd)
    if not ours:
        return f"{sgg_cd} 는 우리 대상 시군구가 아닙니다."
    if not full_name:
        return f"{ours}: CLS_FULLNM 이 비어 있어 검산할 수 없습니다."
    if not _path_matches(full_name, ours):
        return f"{ours}: R-ONE 경로가 '{full_name}' 입니다."
    return None


def fetch(
    table_id: str,
    cls_id: str,
    *,
    sgg_cd: str = "",
    start_ym: str | None = None,
    end_ym: str | None = None,
    itm_id: str | None = DEFAULT_ITM_ID,
    page_size: int = 1000,
) -> list[RebPoint]:
    """한 (표·지역)의 월별 값.

    키가 없으면 5행만 돌아온다. 그래도 **파싱과 코드 대조는 검증된다** — 적재가
    안 될 뿐이다. 빈 결과를 성공으로 넘기지 않도록 호출한 쪽에서 건수를 본다.
    """
    metric = TABLES.get(table_id, table_id)
    out: list[RebPoint] = []
    page = 1
    while True:
        data = _get(
            "SttsApiTblData.do",
            {
                "STATBL_ID": table_id,
                "DTACYCLE_CD": "MM",
                "CLS_ID": cls_id,
                "ITM_ID": itm_id,
                "START_WRTTIME": start_ym,
                "END_WRTTIME": end_ym,
                "pIndex": page,
                "pSize": page_size,
            },
        )
        total, rows = _unwrap(data, "SttsApiTblData")
        if not rows:
            break

        for r in rows:
            val = r.get("DTA_VAL")
            if val is None:
                continue
            out.append(
                RebPoint(
                    table_id=table_id,
                    metric=metric,
                    sgg_cd=sgg_cd,
                    cls_id=str(r.get("CLS_ID", cls_id)),
                    region_name=str(r.get("CLS_FULLNM") or r.get("CLS_NM") or ""),
                    ym=str(r.get("WRTTIME_IDTFR_ID") or ""),
                    value=float(val),
                    # 단위를 값과 함께 가져간다. 천원을 만원으로 잘못 읽으면
                    # 평당가가 10배로 튀는데, 그건 그래프에서 '비싼 동네'로만
                    # 보여서 조용히 지나간다.
                    unit=str(r.get("UI_NM") or ""),
                )
            )

        if len(out) >= total or len(rows) < page_size:
            break
        page += 1
        if page > 100:  # 안전장치. 월간 통계가 이보다 길 수 없다.
            break

    return out


def fetch_district(
    table_id: str,
    sgg_cd: str,
    *,
    start_ym: str | None = None,
    end_ym: str | None = None,
) -> list[RebPoint]:
    """우리 시군구 코드로 받는다. 받은 값이 그 지역 것인지 **검산까지** 한다."""
    cls_id = district_cls_ids(table_id).get(sgg_cd)
    if not cls_id:
        raise RebError(
            f"{DISTRICTS.get(sgg_cd, sgg_cd)}: {table_id} 에 이 지역이 없습니다."
        )

    points = fetch(table_id, cls_id, sgg_cd=sgg_cd, start_ym=start_ym, end_ym=end_ym)
    if points:
        why = check_region(sgg_cd, points[0].region_name)
        if why:
            raise RebError(f"지역 대조 실패 — {why}")
    return points


# ──────────────────────────────────────────────────────────
# 거시 요인 — 수요·통화·금리
# ──────────────────────────────────────────────────────────
# 공급 표를 찾느라 738개를 훑다가 **금리·대출·심리·미분양이 전부 R-ONE 안에**
# 있는 것을 봤다. 한국은행 ECOS 키를 따로 받아야 하는 줄 알았는데 아니었다
# (M2 와 기준금리만 ECOS 에 있다 — `clients/ecos.py`).
#
# 지역 경로를 여기 **직접 적는다.** `sido_cls_id` 의 선호 순서로는 못 고른다 —
# 미분양은 `경기>계`, 심리는 `수도권>경기`, 금리는 지역이 아니라 `대출평균>가계대출`
# 이라는 **대출 종류**다. 모양이 제각각이라 짐작할 수 있는 규칙이 없다.
# 적은 경로가 맞는지는 `scripts/probe_reb.py --macro` 가 매번 대조한다.
MACRO_TABLES: dict[str, tuple[str, int, dict[str, str]]] = {
    # 수요 — 안 팔린 집. 늘면 수요가 식었다는 뜻이다.
    "unsold": ("T237973129847263", 10001, {"11": "서울>계", "41": "경기>계"}),
    # 수요 — 국토연구원 부동산시장 소비자 심리조사. 100 이 중립이다.
    "sentiment": ("T232543129897499", 10001,
                  {"00": "전국>소계", "11": "수도권>서울", "41": "수도권>경기"}),
    # 통화 — 예금취급기관 가계대출 잔액(십억원). M2 보다 집값에 닿는 경로가 짧다.
    "loan_balance": ("T231283129942110", 10001, {"00": "예금취급기관"}),
    # 금리 — 예금은행 가계대출 금리(신규취급액 기준, %). 기준금리가 아니라 **실제로
    # 무는 금리**다. 기준금리는 ECOS 에서 받아 따로 둔다.
    "loan_rate": ("T233453129931506", 10001, {"00": "대출평균>가계대출"}),
}


# 우리가 보는 '경기 남부'. **코드가 아니라 이름으로 맞춘다** — 미분양 표는
# `경기>수원시` 처럼 시 단위 이름만 주고 법정동코드를 주지 않는다. 시 코드를
# 기억으로 적었다가 틀리면 남의 지역 미분양이 섞이는데, 그건 빈 줄보다 나쁘다.
#
# 목록은 `molit.DISTRICTS` 의 구 이름에서 **파생**한다('수원시 영통구' -> '수원시').
# 대상 지역을 넓히면 저절로 따라온다 — 손으로 유지하는 목록을 하나 더 만들지 않는다.
SOUTH_GG_CODE = "41S"  # 법정동코드가 아니다. 우리가 정의한 묶음이라는 표시다.


def south_gg_cities() -> list[str]:
    return sorted({name.split()[0] for name in DISTRICTS.values()})


def fetch_unsold_south(*, page_size: int = 1000) -> list[RebPoint]:
    """경기 남부 8개 시 미분양의 월별 합.

    **한 시라도 경로를 못 찾으면 실패시킨다.** 일곱 개만 더해 놓고 '경기 남부'
    라고 부르면 조용히 작은 값이 된다 — 빠진 줄은 오류를 내지 않는다.
    """
    table_id, itm_id, _ = MACRO_TABLES["unsold"]
    total: dict[str, float] = {}
    unit = ""
    for city in south_gg_cities():
        cls_id = macro_cls_id(table_id, f"경기>{city}")
        data = _get("SttsApiTblData.do", {
            "STATBL_ID": table_id, "DTACYCLE_CD": "MM",
            "CLS_ID": cls_id, "ITM_ID": itm_id, "pSize": page_size,
        })
        _, rows = _unwrap(data, "SttsApiTblData")
        got = 0
        for r in rows:
            v = r.get("DTA_VAL")
            t = str(r.get("WRTTIME_IDTFR_ID") or "")
            if v is None or len(t) != 6:
                continue
            total[t] = total.get(t, 0.0) + float(v)
            unit = unit or str(r.get("UI_NM") or "")
            got += 1
        if not got:
            raise RebError(f"미분양: '경기>{city}' 가 0행입니다.")

    name = "경기 남부 " + "·".join(c[:-1] for c in south_gg_cities())
    return [RebPoint(table_id=table_id, metric="unsold", sgg_cd=SOUTH_GG_CODE,
                     cls_id="", region_name=name[:60], ym=t, value=v, unit=unit)
            for t, v in sorted(total.items())]


def macro_cls_id(table_id: str, path: str) -> str:
    """경로 문자열 그대로 `CLS_ID` 를 찾는다. 없으면 실패시킨다.

    표가 갈아 치워지면 경로가 안 맞아 **빈 결과**가 돌아오는데, 그건 오류로 보이지
    않는다. 여기서 끊는 쪽이 낫다 — `sido_cls_id` 와 같은 원칙이다.
    """
    rows = [r for r in region_codes(table_id) if r.get("ITM_TAG") == "분류"]
    by_path = {str(r.get("ITM_FULLNM") or ""): str(r["ITM_ID"]) for r in rows}
    if path not in by_path:
        near = [p for p in by_path if path.split(">")[-1] in p][:5]
        raise RebError(
            f"{table_id} 에 '{path}' 경로가 없습니다. 비슷한 것: {near or '없음'}"
        )
    return by_path[path]


def fetch_macro(metric: str, sgg_cd: str, *, page_size: int = 1000) -> list[RebPoint]:
    """한 (거시지표·지역)의 월별 전체 시계열."""
    table_id, itm_id, paths = MACRO_TABLES[metric]
    path = paths[sgg_cd]
    data = _get("SttsApiTblData.do", {
        "STATBL_ID": table_id, "DTACYCLE_CD": "MM",
        "CLS_ID": macro_cls_id(table_id, path), "ITM_ID": itm_id,
        "pSize": page_size,
    })
    _, rows = _unwrap(data, "SttsApiTblData")

    out: list[RebPoint] = []
    for r in rows:
        v = r.get("DTA_VAL")
        t = str(r.get("WRTTIME_IDTFR_ID") or "")
        if v is None or len(t) != 6:
            continue
        out.append(RebPoint(
            table_id=table_id, metric=metric, sgg_cd=sgg_cd, cls_id="",
            region_name=path, ym=t, value=float(v), unit=str(r.get("UI_NM") or ""),
        ))
    return out
