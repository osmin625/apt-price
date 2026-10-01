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

## 지역 코드 — 왜 표를 박아 두고도 매번 검사하는가

R-ONE 은 자체 `CLS_ID`(지역코드)를 쓴다. 우리 `molit.DISTRICTS` 와 이어 붙이려면
법정동코드가 필요한데, **API 응답에는 그게 없다.** `SttsApiTblItm.do` 는
`ITM_ID`·`ITM_NM` 만 주고, 법정동코드는 포털의 '통계코드 검색 > 분류코드 조회'
화면에만 나온다. 그래서 아래 `CLS_IDS` 는 그 화면에서 받아 **법정동코드 앞 5자리로
우리 표와 대조한 결과**를 적어 둔 것이다. 17개가 전부 맞았고, 화성시
분구(41591·41593·41595·41597)까지 일치했다 — 우리가 실거래 0건을 겪고서야 찾아낸
그 코드를 한국부동산원도 똑같이 쓴다는 독립 확인이다.

박아 둔 표는 언젠가 낡는다. 화성시가 그랬듯 행정구역은 바뀌고, 그때 **틀린 코드는
오류가 아니라 빈 결과나 남의 지역 값으로 조용히 돌아온다.** 그래서 데이터를 받을
때마다 응답의 `CLS_FULLNM`(예: `경기>경부2권>수원시>영통구`)이 우리가 기대한
시·구 이름으로 끝나는지 검사한다(`check_region`). 이름으로 **맞추지는** 않고
**검산만** 한다 — 맞추는 데 이름을 쓰면 다른 시의 같은 이름 구에 붙을 수 있다.

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

# 우리 시군구 코드 → R-ONE 지역코드(CLS_ID).
#
# 출처는 R-ONE '통계코드 검색 > A_2024_00045 > 분류코드 조회' 다. 그 화면이 주는
# 법정동코드 앞 5자리로 molit.DISTRICTS 와 대조해 적었다 — 기억으로 적은 코드는
# 하나도 없다. 모듈 주석의 '지역 코드' 항목 참조.
CLS_IDS: dict[str, str] = {
    # 수원시
    "41111": "530060",  # 장안구
    "41113": "530061",  # 권선구
    "41115": "530062",  # 팔달구
    "41117": "530063",  # 영통구
    # 용인시
    "41461": "530056",  # 처인구
    "41463": "530057",  # 기흥구
    "41465": "530058",  # 수지구
    # 화성시 — 분구
    "41591": "530091",  # 만세구
    "41593": "530092",  # 효행구
    "41595": "530093",  # 병점구
    "41597": "530094",  # 동탄구
    # 안양시
    "41171": "530045",  # 만안구
    "41173": "530046",  # 동안구
    # 단일 코드 시
    "41370": "520033",  # 오산시
    "41430": "520022",  # 의왕시
    "41410": "520021",  # 군포시
    "41290": "520018",  # 과천시
}


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

    주의: 여기에는 **법정동코드가 없다.** 우리 코드와 잇는 것은 `CLS_IDS` 다.
    """
    data = _get("SttsApiTblItm.do", {"STATBL_ID": table_id, "pSize": 1000})
    _, rows = _unwrap(data, "SttsApiTblItm")
    return rows


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

    parts = [p.strip() for p in full_name.split(">") if p.strip()]
    tail = parts[-1] if parts else ""
    want = ours.split()  # ["수원시", "영통구"] 또는 ["오산시"]

    if tail != want[-1]:
        return f"{ours}: R-ONE 경로가 '{full_name}' 로 끝이 다릅니다."
    if len(want) == 2 and want[0] not in parts:
        return f"{ours}: R-ONE 경로 '{full_name}' 에 '{want[0]}' 가 없습니다."
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
    cls_id = CLS_IDS.get(sgg_cd)
    if not cls_id:
        raise RebError(f"{sgg_cd} 의 R-ONE 지역코드가 CLS_IDS 에 없습니다.")

    points = fetch(table_id, cls_id, sgg_cd=sgg_cd, start_ym=start_ym, end_ym=end_ym)
    if points:
        why = check_region(sgg_cd, points[0].region_name)
        if why:
            raise RebError(f"지역 대조 실패 — {why}")
    return points
