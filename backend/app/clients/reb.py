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
