"""붙여넣은 매물 텍스트에서 단지·면적·층·호가를 뽑아낸다.

## 왜 링크가 아니라 텍스트인가

네이버 부동산 링크는 두 가지 이유로 쓸 수 없다.

1. **링크에 매물 정보가 없는 경우가 많다.** `naver.me` 단축 링크를 펼치면
   `fin.land.naver.com/map?center=...&zoom=...&dealPrice=0-510000000` 처럼
   지도 좌표와 가격 필터만 들어 있다. 단지명도 면적도 층도 없다.
2. **있다 해도 긁어와야 한다.** 네이버 부동산은 공개 API가 없고 페이지는
   자바스크립트로 렌더링된다. 자동 수집은 이용약관 위반 소지가 있어 이 프로젝트가
   처음부터 제외한 방식이다(README '알려진 한계' 참조).

반면 사용자가 **보고 있는 화면의 텍스트를 복사해 붙여넣는 것**은 자동 수집이 아니다.
네이버든 다른 곳이든 출처를 가리지 않고, 사이트 구조가 바뀌어도 사람이 읽을 수 있는
형태면 계속 동작한다. 실패해도 조용히 틀리지 않고 '못 찾았다'고 말한다.

## 파싱 대상 예시

네이버 부동산 매물 화면을 그대로 긁어 오면 버튼 문구까지 섞여 들어온다.
쓸 줄만 골라 읽고 나머지는 무시한다.

    힐스테이트푸르지오수원 103동
    매매 9억
    3,360만원/3.3㎡평당가 도움말
    알림관심매물
    공유하기
    아파트88B㎡ (전용59B)8/15층남향

    래미안영통마크원 105동
    매매 8억 5,000
    아파트 · 84.97/59.94㎡, 중층, 남향

    광교자연앤힐스테이트
    12억 3000 / 전용 84.9㎡ / 15층

## 평당가 기준이 다르다

위 예시에서 네이버가 적은 평당가는 3,360만원/평인데 이 서비스는 5,043만원/평로
계산한다. 틀린 것이 아니라 **분모가 다르다** — 네이버는 공급 88㎡, 이 서비스는
전용 59㎡ 기준이다. 말해 주지 않으면 어느 한쪽이 틀린 줄 알기 때문에,
적힌 평당가와 호가로 분모를 역산해 공급 기준이면 경고로 짚어 준다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .. import pricing

# 면적 표기는 출처마다 다르다. 실제로 들어오는 형태:
#   112.9/84.97㎡        공급/전용 한 쌍
#   아파트88B㎡ (전용59B)  타입 문자(B)가 붙고 전용 쪽엔 단위가 없다
#   전용 84.9㎡ / 34평
# 타입 문자(A·B·84A·59B…)는 같은 평형의 평면 변형이라 면적 자체와는 무관하다.
_TYPE_SUFFIX = r"[A-Za-z]?"
_UNIT = r"(?:㎡|m2|m²)"

# '전용' 이라고 **명시된** 숫자가 가장 믿을 만하다. 단위는 있어도 없어도 받는다.
# 뒤가 `[\d.]` 면 매치를 막아야 한다. 안 그러면 '전용 112.40㎡' 같은 값에서
# 백트래킹으로 '112' 만 떼어 내고 '.40㎡' 를 남긴 채 매치에 성공한다.
_AREA_EXCL = re.compile(
    rf"전용\s*(\d{{2,3}}(?:\.\d+)?)\s*{_TYPE_SUFFIX}\s*{_UNIT}?(?![\d.])"
)
# '84.97/59.94㎡' 처럼 한 쌍이면 **뒤쪽이 전용**이다. 앞 숫자에도 단위가 붙을 수 있다 —
# `normalize_pyeong` 이 '34평/25.7평' 을 '112.40㎡/84.96㎡' 로 바꿔 놓기 때문이다.
_AREA_PAIR = re.compile(
    rf"(\d{{2,3}}(?:\.\d+)?)\s*{_TYPE_SUFFIX}\s*{_UNIT}?\s*/\s*"
    rf"(\d{{2,3}}(?:\.\d+)?)\s*{_TYPE_SUFFIX}\s*{_UNIT}"
)
_AREA_ONE = re.compile(rf"(\d{{2,3}}(?:\.\d+)?)\s*{_TYPE_SUFFIX}\s*{_UNIT}")
# '25평형' 도 평이다. '30평대' 는 크기가 아니라 범위라 건드리지 않는다.
# 숫자와 '평' 사이는 **같은 줄**에서만 잇는다. `\s*` 로 두면 '매매 3억 9,000' 다음 줄의
# '평당가' 와 붙어 '000평' → 0평 이 된다. '평대'(범위)·'평당'(단가)도 면적이 아니다.
_PYEONG = re.compile(r"(\d{1,3}(?:\.\d+)?)[ 	]*평(?:형)?(?![대당])")

# '아파트17평 (전용12)' — 괄호 안 전용에는 단위가 없다. 네이버는 공급 쪽에 쓴 단위를
# 전용 쪽에서 생략하므로, **앞의 공급이 평이면 전용도 평**이다. 단위 없는 숫자를
# 일괄로 ㎡ 취급하면 여기서 전용 12평(39.7㎡)이 12㎡ 가 되어 맞는 평형이 사라진다.
# (`88B㎡ (전용59B)` 는 공급이 ㎡ 라 이 패턴에 걸리지 않고 그대로 ㎡ 로 읽힌다.)
_PAIR_PYEONG = re.compile(
    r"(\d{1,3}(?:\.\d+)?)[ 	]*평(?:형)?(?![대당])(\s*[(（]?\s*전용\s*)(\d{1,3}(?:\.\d+)?)"
    r"(?![\d.]|\s*(?:㎡|m2|m²|평))"
)

# '3,360만원/3.3㎡' — 네이버가 표시하는 평당가. 3.3㎡ 가 곧 1평이다.
_STATED_PPP = re.compile(r"([\d,]{3,7})\s*만원\s*/\s*(?:3\.3\s*(?:㎡|m2|m²)|평)")

# '129동' '가동' 'A동' — 단지 안의 개별 동. 법정동('인계동')과 헷갈리면 안 되므로
# **숫자 또는 한 글자 한글/영문**만 받는다. 첫 줄(단지명 줄)에서만 찾는 이유는
# 본문에 '남동향' 같은 말이 섞이기 때문이다.
_DONG = re.compile(r"(?<![가-힣A-Za-z])(\d{1,4}|[가-하]|[A-Za-z])\s*동(?![향호])")

_FLOOR_NUM = re.compile(r"(?<![\d.])(\d{1,2})\s*/\s*(\d{1,2})\s*층")   # 15/25층, 8/15층
_FLOOR_ONE = re.compile(r"(?<![\d./])(\d{1,2})\s*층")
# '고/23층' — 네이버는 층을 감출 때 구간 글자만 쓰고 총 층수는 그대로 준다.
_FLOOR_BAND_TOTAL = re.compile(r"(저|중|고|탑)\s*/\s*(\d{1,2})\s*층")
_FLOOR_WORD = {"저층": "저층", "중층": "중층", "고층": "고층", "탑층": "최상층"}

# 8억 5,000 / 8억5000 / 12억 / 9,500
# 억 뒤의 만원 자리는 **같은 줄**에서만 찾는다. 줄바꿈을 넘게 두면
# '매매 13억' 다음 줄의 '112.9/84.9㎡' 에서 112 를 만원으로 먹어 130,112 이 된다.
# 뒤에 소수점·㎡·/ 가 붙으면 면적이지 가격이 아니므로 제외한다.
# 공백 없는 `/숫자` 만 면적 쌍으로 본다. `/` 를 통째로 막으면
# '12억 3000 / 전용 84.9㎡' 의 3000 까지 잃는다 — 거기서 `/` 는 항목 구분자다.
_PRICE_EOK = re.compile(
    r"(\d{1,2})\s*억(?:[ 	]*([\d,]{3,6})(?![\d.]|[ 	]*(?:㎡|m2|m²|평)|/\d))?"
)
_PRICE_MAN = re.compile(r"(?<![\d억,])([\d]{1,3}(?:,\d{3})+)\s*(?:만원|만)?")


@dataclass
class ParsedListing:
    complex_id: int | None = None
    complex_name: str | None = None
    exclusive_area: float | None = None
    supply_area: float | None = None      # 공급면적 — 평당가 기준 차이를 짚어 주는 데만 쓴다
    area_is_explicit: bool = False        # '전용' 이라고 적혀 있었는가
    # 전용면적이 **정수 평**에서 왔다면 그 값. 네이버는 평을 버림해서 쓰므로
    # (49.58㎡ = 14.998평 → '전용14'), 점이 아니라 [N, N+1)평 구간으로 봐야 한다.
    area_pyeong: int | None = None
    floor: int | None = None
    total_floor: int | None = None        # '8/15층' 의 15. DB 의 관측 최고층보다 정확하다
    dong: str | None = None               # '129동' — 있으면 역거리를 그 동 기준으로 잡는다
    floor_band: str | None = None
    asking_price: int | None = None       # 만원
    stated_ppp: int | None = None         # 매물에 적힌 평당가 (만원/평)
    # '3억 2,500 ~ 3억 8,000' 처럼 범위로 올라온 경우. 낮은 쪽을 쓰되 사실을 남긴다.
    price_is_range: bool = False
    candidates: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def warn(self, field: str | None, text: str) -> None:
        """경고를 **어느 값에 대한 것인지**와 함께 쌓는다.

        화면에서 경고 문구를 줄줄이 늘어놓으면 카드가 금방 길어진다. 대신 해당
        값(전용면적·층·호가…)에 호버했을 때 뜨게 하려면 그 대응을 여기서 정해 줘야
        한다. 프런트에서 문구를 키워드로 분류하는 방식은 문구를 고칠 때마다 조용히
        깨진다.

        field: complex | area | floor | dong | price | None(일반)
        """
        self.warnings.append({"field": field, "text": text})

    def as_dict(self) -> dict:
        return {
            "complex_id": self.complex_id,
            "complex_name": self.complex_name,
            "exclusive_area": self.exclusive_area,
            "supply_area": self.supply_area,
            "area_is_explicit": self.area_is_explicit,
            "area_pyeong": self.area_pyeong,
            "floor": self.floor,
            "total_floor": self.total_floor,
            "dong": self.dong,
            "floor_band": self.floor_band,
            "asking_price": self.asking_price,
            "stated_ppp": self.stated_ppp,
            "price_is_range": self.price_is_range,
            "candidates": self.candidates,
            "warnings": self.warnings,
        }


def parse_price(text: str) -> int | None:
    """한국식 가격 표기를 만원 단위 정수로. '8억 5,000' -> 85000."""
    m = _PRICE_EOK.search(text)
    if m:
        eok = int(m.group(1)) * 10000
        rest = m.group(2)
        man = int(rest.replace(",", "")) if rest else 0
        # '8억 5,000' 의 5,000 은 만원 단위다. 5자리 이상이면 원 단위로 잘못 쓴 것.
        if man >= 10000:
            man = 0
        return eok + man
    m = _PRICE_MAN.search(text)
    if m:
        v = int(m.group(1).replace(",", ""))
        return v if v >= 1000 else None
    return None


def normalize_pyeong(text: str) -> tuple[str, list[tuple[float, float]]]:
    """'34평' 을 '112.40㎡' 로 바꿔 **단위를 ㎡ 하나로 통일**한다.

    평용 경로를 따로 두면 ㎡ 쪽에 있는 기능(공급/전용 쌍, 공급면적 추출, '전용' 명시
    우선)이 평 쪽엔 없어서 `34평/25.7평` 이 34평을 전용으로 잡는 식으로 어긋난다.
    파싱 전에 한 번 환산해 두면 그런 분기 자체가 사라진다.

    평으로 적혀 있으면 평으로, ㎡ 로 적혀 있으면 ㎡ 로 읽는다 — 숫자 크기로 추측하지
    않는다. '30평대' 는 크기가 아니라 범위 표현이라 건드리지 않는다.
    """
    done: list[tuple[float, float]] = []

    def conv(py: float) -> str:
        m2 = py * pricing.PYEONG_M2
        done.append((py, m2))
        return f"{m2:.2f}㎡"

    def pair_sub(m: re.Match) -> str:
        # 공급·전용 둘 다 평이다. 전용 쪽 단위 생략을 앞에서 물려받는다.
        return conv(float(m.group(1))) + m.group(2) + conv(float(m.group(3)))

    text = _PAIR_PYEONG.sub(pair_sub, text)
    return _PYEONG.sub(lambda m: conv(float(m.group(1))), text), done


def parse_area(text: str) -> tuple[float | None, float | None, bool, list[str]]:
    """(전용면적㎡, 공급면적㎡, 전용이 명시됐는가, 경고).

    세 번째 값이 중요하다. 광고의 면적은 **표기가 없으면 공급**이라, 뒤에서 그 단지의
    실제 평형과 대조해 공급으로 재해석할지 정해야 한다(`routers/model._resolve_area`).
    '전용' 이라고 적혔거나 공급/전용 쌍의 뒤쪽이면 재해석할 이유가 없다.

    평 표기는 먼저 ㎡ 로 환산해(`normalize_pyeong`) 단위를 통일한 뒤, 아래 우선순위로
    읽는다. **표기의 확실성 순**이다.

    1. `전용59B` `전용 84.9㎡` `전용 25.7평` — '전용' 이라고 적힌 숫자. 단위가 없어도 받는다.
       네이버는 `아파트88B㎡ (전용59B)` 처럼 전용 쪽 단위를 생략한다.
    2. `112.9/84.97㎡` `34평/25.7평` — 한 쌍이면 뒤쪽이 전용.
    3. `84.97㎡` 단독 — 전용인지 공급인지 알 수 없으므로 경고를 단다.

    공급면적은 **평당가 기준이 다르다는 것을 짚어 주는 용도**로만 쓴다. 이 서비스의
    평당가는 전용 기준이고, 네이버가 보여 주는 평당가는 공급 기준이라 30% 넘게 벌어진다.
    """
    warns: list[str] = []
    text, converted = normalize_pyeong(text)
    if converted:
        # 환산한 값이 전용인지 공급인지는 여기서 알 수 없다. 그 판정은 단지의 실제
        # 평형과 대조한 뒤(`routers/model._resolve_area`)에나 나오므로, 여기서는
        # **환산 사실만** 적는다. '전용 112.4㎡' 라고 써 두면 바로 다음 줄에서
        # '공급으로 보인다' 고 뒤집히게 된다.
        warns.append({"field": "area", "text":
            "평 → ㎡ 환산(1평 = 3.305785㎡): "
            + ", ".join(f"{py:g}평 → {m2:.2f}㎡" for py, m2 in converted)})

    exclusive: float | None = None
    excl_span: tuple[int, int] | None = None

    m = _AREA_EXCL.search(text)
    if m:
        exclusive, excl_span = float(m.group(1)), m.span()

    if exclusive is None:
        m = _AREA_PAIR.search(text)
        if m:
            supply, exclusive = float(m.group(1)), float(m.group(2))
            if exclusive > supply:
                supply, exclusive = exclusive, supply
                warns.append({"field": "area",
                              "text": "공급/전용 순서가 뒤바뀐 것 같아 작은 쪽을 전용으로 봤습니다."})
            return exclusive, supply, True, warns

        m = _AREA_ONE.search(text)
        if m:
            v = float(m.group(1))
            return v, None, False, warns
        return None, None, False, warns

    # 전용을 찾았으면, 그와 겹치지 않으면서 더 큰 ㎡ 숫자가 공급면적이다.
    supply = None
    for m in _AREA_ONE.finditer(text):
        if excl_span and not (m.end() <= excl_span[0] or m.start() >= excl_span[1]):
            continue  # 전용 매치와 겹치는 숫자는 같은 값이다
        v = float(m.group(1))
        if v > exclusive and (supply is None or v < supply):
            supply = v
    return exclusive, supply, True, warns


def parse_floor(text: str) -> tuple[int | None, int | None, str | None]:
    """(해당 층, 건물 총 층수, 층 구간).

    `8/15층` 의 15는 **건물 실제 최고층**이다. DB 의 `max_floor` 는 거래에서 관측된
    최고층이라 거래가 적은 단지에서는 실제보다 낮게 잡힌다(README '알려진 한계').
    매물에 적혀 있으면 그쪽이 정확하므로 층 구간 판정에 쓴다.
    """
    m = _FLOOR_NUM.search(text)
    if m:
        return int(m.group(1)), int(m.group(2)), None
    m = _FLOOR_BAND_TOTAL.search(text)
    if m:
        return None, int(m.group(2)), _FLOOR_WORD.get(m.group(1) + "층", m.group(1) + "층")
    m = _FLOOR_ONE.search(text)
    if m:
        return int(m.group(1)), None, None
    for word, band in _FLOOR_WORD.items():
        if word in text:
            return None, None, band
    return None, None, None


def parse_dong(text: str) -> str | None:
    """'수원센트럴아이파크자이 129동' → '129'.

    **첫 줄에서만** 찾는다. 본문에는 '남동향'·'101호' 처럼 '동' 이 들어간 말이 섞이고,
    법정동('인계동')과도 구분해야 한다. 그래서 숫자나 한 글자(가·나·A) 만 받고,
    앞에 한글/영문이 더 붙어 있으면(인계'동') 버린다.
    """
    head = text.strip().splitlines()[0] if text.strip() else ""
    m = _DONG.search(head)
    return m.group(1) if m else None


def parse_stated_ppp(text: str) -> int | None:
    """매물에 적힌 평당가(만원/평). '3,360만원/3.3㎡' → 3360."""
    m = _STATED_PPP.search(text)
    return int(m.group(1).replace(",", "")) if m else None


_HEAD_DONG = re.compile(r"\s*(?:\d{1,4}|[가-힣])\s*동\s*$")


def _head_name(text: str) -> str:
    """첫 줄에서 동 표기를 뗀 **단지명 부분**의 정규화 키.

    '임광 8동' → '임광', '주공그린빌5 505동' → '주공그린빌5'.
    동이 없으면 첫 줄 전체를 쓴다.
    """
    line = next((ln for ln in text.splitlines() if ln.strip()), "")
    return pricing.name_key(_HEAD_DONG.sub("", line.strip()))


def name_fragments(text: str) -> list[str]:
    """첫 줄의 단지명을 **조각으로** 나눈다. '신성,신안,쌍용,진흥' → [신성, 신안, 쌍용, 진흥]

    시공사 여러 곳이 함께 지은 단지를 네이버는 한 줄로 묶어 쓰는데, 국토부는 시공사마다
    따로 기록한다. 수원 영통동 '신성,신안,쌍용,진흥' 은 국토부에 '신나무실신성'·
    '신나무실신안'·'신나무실쌍용'·'신나무실진흥' 네 단지로 들어 있다(각 60여 건).
    이름만으로는 1:N 이라 고를 수 없고, 그래서 조각을 따로 내어 준다.

    조각 하나로는 못 고른다 — '쌍용' 은 전국에 흔하다. 어느 단지인지는 **동 번호**가
    가른다(`routers/model._resolve_by_dong`).
    """
    line = next((ln for ln in text.splitlines() if ln.strip()), "")
    line = _HEAD_DONG.sub("", line.strip())
    parts = re.split(r"[,/·∙・]+", line)
    return [p for p in (x.strip() for x in parts) if len(p) >= 2]


def _name_candidates(text: str, complexes: list) -> list[dict]:
    """텍스트 안에서 우리 DB 의 단지명을 찾는다.

    정규화 키(`pricing.name_key`)로 비교하므로 공백·'아파트' 접미 차이를 흡수한다.
    **가장 긴 이름을 우선**한다 — '자연앤자이2단지' 가 있는데 '자연앤자이' 로
    끊어 버리면 엉뚱한 단지가 된다.
    """
    key = pricing.name_key(text)
    hits = []
    for cx in complexes:
        nk = cx.name_key or pricing.name_key(cx.name)
        if len(nk) >= 3 and nk in key:
            hits.append((len(nk), cx, True))

    if not hits:
        # **두 글자 단지**는 위 규칙으로 영원히 못 찾는다. `임광`(수원 매탄동, 1,320세대)
        # 처럼 실재하는 단지가 2,469곳 중 346곳(14%)이나 된다.
        #
        # 길이 제한이 있던 이유는 오탐이다. `현대`·`대우` 같은 두 글자를 본문 전체에서
        # 찾으면 '현대건설 시공' 같은 홍보문구에 걸린다. 그래서 **찾는 자리를 좁힌다** —
        # 단지명은 목록의 첫 줄에 있고, 그 줄은 '임광 8동' 처럼 이름과 동뿐이다.
        # 거기서 동을 떼고 남은 것과 **정확히 같을 때만** 인정한다.
        head = _head_name(text)
        if head:
            same = [
                cx for cx in complexes
                if (cx.name_key or pricing.name_key(cx.name)) == head
            ]
            # 같은 이름이 여러 곳이면(`현대` 는 장안구에만 네 곳) 찍지 않는다.
            # 후보로만 올려 사용자가 고르게 한다.
            exact = len(same) == 1
            for cx in same:
                hits.append((len(head), cx, exact))

    if not hits:
        # 완전 포함이 없으면 **앞부분이 겹치는** 단지를 후보로 올린다.
        # 텍스트에 '래미안영통마크원 105동' 이 있는데 DB 에는 '래미안영통마크원1단지'·
        # '2단지' 만 있는 경우가 실제로 있다. 자동 선택하면 둘 중 하나를 찍는
        # 셈이라 위험하지만, 후보조차 안 보여 주면 사용자가 처음부터 찾아야 한다.
        head = pricing.name_key(text.strip().splitlines()[0]) if text.strip() else ""
        for cx in complexes:
            nk = cx.name_key or pricing.name_key(cx.name)
            if len(nk) < 4 or len(head) < 4:
                continue
            common = 0
            for x, y in zip(nk, head):
                if x != y:
                    break
                common += 1
            if common >= 4:
                hits.append((common, cx, False))

    hits.sort(key=lambda p: -p[0])
    return [
        {
            "id": cx.id,
            "name": cx.name,
            "umd_nm": cx.umd_nm,
            "sgg_name": cx.sgg_name,
            "matched_len": n,
            "exact": exact,
        }
        for n, cx, exact in hits[:6]
    ]


# 목록에서 매물이 시작되는 지점. 네이버 목록은 **단지명 → 가격 → 아파트…** 3줄이
# 반복되고 나머지(중개사명·홍보문구·날짜·'관심매물')는 전부 노이즈다.
_PRICE_LINE = re.compile(r"^\s*(매매|전세|월세)\s*[\d억]")
# '3억 2,500 ~ 3억 8,000' — 중개사 여러 곳이 다른 값을 올린 경우 범위로 나온다.
_PRICE_RANGE = re.compile(r"[~〜]\s*\d")

# '집주인확인매물 2026.09.23' / '확인매물 2026.09.23' — 매물마다 붙는 **확인일자**다.
#
# 이 줄을 지금까지 노이즈로 버렸는데, 그러면 안 된다. 붙여넣은 시각은 한 번에 넣은
# 매물이 전부 같으므로 목록 안에서 시점을 가를 수 없다. 매물이 **언제 시점의 것인지**를
# 말해 주는 단서는 이 날짜뿐이다.
_CONFIRMED = re.compile(
    r"확인[^\n\d]{0,8}(20\d\d|\d\d)\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})"
)
_DATE_ANY = re.compile(r"(20\d\d)\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")
_REL_AGO = re.compile(r"(\d{1,3})\s*(일|주|개월)\s*전")


def parse_confirmed_on(text: str, today: date | None = None) -> date | None:
    """매물의 확인일자. '확인' 이 붙은 날짜를 먼저 보고, 없으면 아무 날짜나 본다.

    네이버는 **현재 올라와 있는 매물만** 보여 주므로 이 날짜는 '언제 올라왔나' 가
    아니라 '마지막으로 확인된 날' 이다. 그러니 이 날짜가 다르다고 해서 두 매물이
    다른 시기에 존재했다는 뜻은 아니다 — 둘 다 지금 올라와 있다. 그래도 매물마다
    다르므로 목록 안에서 시점을 구분하고 거를 수 있는 유일한 값이다.
    """
    today = today or date.today()
    m = _CONFIRMED.search(text) or _DATE_ANY.search(text)
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        y = int(y) if len(y) == 4 else 2000 + int(y)
        try:
            got = date(y, mo, d)
        except ValueError:
            return None
        # 미래 날짜는 잘못 읽은 것이다. 없는 것으로 친다.
        return got if got <= today else None
    m = _REL_AGO.search(text)
    if m:
        unit = m.group(2)
        days = int(m.group(1)) * (1 if unit == "일" else 7 if unit == "주" else 30)
        return today - timedelta(days=days)
    return None



def split_listings(text: str) -> list[dict]:
    """붙여넣은 목록을 매물 단위로 쪼갠다.

    **덩어리 전체를 넘기지 않고 3줄만 떼어낸다.** 홍보문구에 '임대분양가27,000'
    같은 숫자가 섞여 있어 통째로 넘기면 가격·면적 파서가 엉뚱한 값을 집는다.
    필요한 것은 단지명 줄, 가격 줄, 그리고 면적·층이 든 줄뿐이다.

    매물의 시작은 '**다음 줄이 가격 줄인 줄**'로 잡는다. 단지명을 DB와 대조해
    찾는 방법도 있지만, 그러면 DB에 없는 단지가 통째로 사라져 몇 건이 빠졌는지도
    알 수 없게 된다.
    """
    lines = text.splitlines()
    n = len(lines)

    def next_nonblank(i: int) -> int:
        while i < n and not lines[i].strip():
            i += 1
        return i

    starts: list[tuple[int, int]] = []  # (단지명 줄, 가격 줄)
    for i in range(n - 1):
        if not lines[i].strip():
            continue
        j = next_nonblank(i + 1)
        if j < n and _PRICE_LINE.match(lines[j]):
            starts.append((i, j))

    out: list[str] = []
    for k, (head, price) in enumerate(starts):
        limit = starts[k + 1][0] if k + 1 < len(starts) else n
        spec = next_nonblank(price + 1)
        block = [lines[head], lines[price]]
        # 면적·층이 든 줄. 보통 가격 바로 다음이지만 한두 줄 밀릴 때가 있다.
        for idx in range(spec, min(spec + 3, limit)):
            t = lines[idx]
            if "㎡" in t or "평" in t or "층" in t:
                block.append(t)
                break
        # 확인일자는 **버리지 않는다**. 다만 3줄 블록에 섞으면 '2026.09.23' 을
        # 가격·면적 파서가 집을 수 있으므로, 텍스트가 아니라 따로 실어 보낸다.
        out.append({
            "text": "\n".join(block),
            "confirmed_on": parse_confirmed_on("\n".join(lines[head:limit])),
        })
    return out


def parse_listing(text: str, complexes: list) -> ParsedListing:
    """붙여넣은 텍스트 한 덩이에서 매물 정보를 뽑는다."""
    out = ParsedListing()
    if not text or not text.strip():
        out.warn(None, "붙여넣은 내용이 비어 있습니다.")
        return out

    # 링크만 붙여넣은 경우를 먼저 잡아 준다 — 왜 안 되는지 알려줘야 한다.
    stripped = text.strip()
    if re.fullmatch(r"https?://\S+", stripped):
        out.warn(
            None,
            "링크만으로는 매물 정보를 알 수 없습니다. 네이버 부동산 링크에는 "
            "지도 좌표와 검색 조건만 들어 있는 경우가 많고, 매물 페이지를 자동으로 "
            "읽어오는 것은 이용약관 문제가 있습니다. 매물 화면의 **텍스트**를 "
            "복사해 붙여넣어 주세요."
        )
        return out

    out.stated_ppp = parse_stated_ppp(text)
    # 평당가 줄은 가격·면적 파싱에서 **빼고** 본다. '3,360만원/3.3㎡' 를 남겨 두면
    # 3,360 이 호가로, 3.3 이 면적으로 잡힐 수 있다.
    body = _STATED_PPP.sub(" ", text)

    out.exclusive_area, out.supply_area, out.area_is_explicit, warns = parse_area(body)
    # '전용14' 처럼 **정수 평**으로 적힌 전용면적인가. 네이버가 버림해서 쓰므로
    # 그런 값은 점이 아니라 구간으로 다뤄야 한다(`_resolve_area`).
    m_py = re.search(r"전용\s*(\d{1,3})\s*(?:평)?(?![\d.])", body)
    if m_py and out.area_is_explicit:
        out.area_pyeong = int(m_py.group(1))
    out.warnings.extend(warns)
    out.floor, out.total_floor, out.floor_band = parse_floor(body)
    out.dong = parse_dong(text)
    out.asking_price = parse_price(body)
    out.price_is_range = bool(_PRICE_RANGE.search(body))

    # 매물에 적힌 평당가가 공급 기준인지 전용 기준인지는 **계산해 보면 안다**.
    # 이 서비스의 평당가는 전용 기준이라 숫자가 다르게 나오는데, 이유를 말해 주지
    # 않으면 어느 한쪽이 틀린 줄 안다.
    if out.stated_ppp and out.asking_price and out.exclusive_area:
        implied_m2 = out.asking_price / out.stated_ppp * pricing.PYEONG_M2
        ours = pricing.price_per_pyeong(out.asking_price, out.exclusive_area)
        if abs(implied_m2 - out.exclusive_area) > 2.0:
            out.warn(
                "price",
                f"매물에 적힌 평당가 {out.stated_ppp:,}만원/평은 "
                f"공급면적({implied_m2:.0f}㎡) 기준입니다. 이 서비스는 전용"
                f"{out.exclusive_area:g}㎡ 기준으로 {ours:,.0f}만원/평으로 계산합니다."
            )

    cands = _name_candidates(text, complexes)
    out.candidates = cands
    exact = [c for c in cands if c.get("exact")]
    if exact:
        out.complex_id = exact[0]["id"]
        out.complex_name = exact[0]["name"]
        if len(exact) > 1 and exact[1]["matched_len"] == exact[0]["matched_len"]:
            out.warn("complex", "이름이 같은 단지가 여러 곳입니다. 아래 후보에서 직접 골라 주세요.")
    elif cands:
        # 부분 일치뿐이면 **자동 선택하지 않는다.** 1단지/2단지 중 하나를 찍는 꼴이 된다.
        out.warn("complex", "단지명이 정확히 일치하지 않습니다. 아래 후보 중에서 골라 주세요.")
    else:
        out.warn('complex', "텍스트에서 단지명을 찾지 못했습니다. 직접 선택해 주세요.")

    if out.exclusive_area is None:
        out.warn('area', "전용면적을 찾지 못했습니다.")
    if out.asking_price is None:
        out.warn('price', "가격을 찾지 못했습니다. 비워 두면 요인 분해만 계산됩니다.")
    return out
