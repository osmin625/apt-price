"""경기 남부(수원 생활권) 지하철역 + 강남 접근성 테이블을 채운다.

사용법:
    python -m scripts.seed_stations              # 좌표는 카카오로 조회(키 필요)
    python -m scripts.seed_stations --no-geocode # 좌표 없이 표만 넣기
    python -m scripts.seed_stations --force      # 기존 값 덮어쓰기

## 왜 API가 아니라 수기 테이블인가

카카오에는 공개된 대중교통 길찾기 REST API가 없다(자동차 길찾기만 제공).
ODsay를 쓰면 되지만 4번째 API 키가 되고, 더 중요하게는 **시드의 참값이
이 숫자에 의존**한다. 시드 실행과 검증 실행 사이에 값이 흔들리면 자기검증
테스트가 아무 이유 없이 불안정해진다. 노선이 새로 뚫릴 때만 바뀌는 숫자라
수기 관리가 맞다.

좌표만 카카오로 채운다 — 35쌍을 손으로 타이핑하면 하나는 반드시 틀린다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.kakao import KakaoError, find_station  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Station  # noqa: E402

# (역명, 노선, 강남역까지 전철 소요시간(분), 환승 횟수)
#
# ⚠️ 소요시간은 **현재 추정치**다. 실제 카카오맵/네이버지도 길찾기(평일 08:00 출발)로
#    검증한 뒤 이 표를 갱신할 것. 모델의 강남접근성 계수는 이 표만큼만 정확하다.
#
#    합성 데이터 단계에서는 정확도가 중요하지 않다 — 시드가 이 표를 참값으로 쓰고
#    회귀가 같은 표를 읽으므로 복원 검증은 값이 무엇이든 성립한다. 실거래가로
#    전환할 때 반드시 실측으로 교체해야 한다.
#
# 신분당선과 1호선의 2배 격차(광교중앙 35분 vs 성균관대 62분)가 이 항을 식별
# 가능하게 만드는 거의 유일한 변동이다. 신분당선 표본이 빠지면 계수는 무의미해진다.
# 노선별 역 순서. 강남 소요시간이 **노선을 따라 단조**여야 한다는 것을 검사하기 위한
# 것이지, 경로 계산을 위한 것이 아니다. 급행 정차역은 앞뒤보다 빠를 수 있으므로
# 예외로 표시한다.
#
# 이 검사를 넣은 이유: 수기 표가 커지면 반드시 어긋난다. 실제로 기존 21개 표에도
# 신갈(47)이 기흥(45)보다 느린데, 기흥이 급행 정차역이라 **맞는 값**이었다.
# 어떤 어긋남이 의도된 것이고 어떤 것이 실수인지는 적어 두지 않으면 구별할 수 없다.
LINE_ORDER: dict[str, list[str]] = {
    # 강남에서 먼 순서로 적는다 — 뒤로 갈수록 소요시간이 커져야 한다.
    "신분당선": ["동천역", "수지구청역", "성복역", "상현역", "광교중앙역", "광교역"],
    "수인분당선": [
        "오리역", "죽전역", "보정역", "구성역", "신갈역", "기흥역", "상갈역",
        "청명역", "영통역", "망포역", "매탄권선역", "수원시청역", "매교역",
        "고색역", "오목천역", "어천역", "야목역",
    ],
    # 1호선은 강남이 금정(4호선)·구로 양방향이라 한 줄로 세우기 어렵다.
    # 수원 기준 남쪽으로만 단조를 본다.
    "1호선": [
        "금정역", "군포역", "당정역", "의왕역", "성균관대역", "화서역",
        "수원역", "세류역", "병점역", "세마역", "오산대역", "오산역",
    ],
    "4호선": [
        "선바위역", "경마공원역", "대공원역", "과천역", "정부과천청사역",
        "인덕원역", "평촌역", "범계역", "금정역", "산본역", "수리산역", "대야미역",
    ],
    "에버라인": [
        "기흥역", "강남대역", "지석역", "어정역", "동백역", "초당역", "삼가역",
        "시청·용인대역", "명지대역", "김량장역", "용인중앙시장역", "고진역",
        "보평역", "둔전역", "전대·에버랜드역",
    ],
}

# 노선 순서를 어겨도 되는 역과 그 이유. 여기 없는 역이 순서를 어기면 검사가 잡는다.
FASTER_THAN_NEIGHBOR: dict[str, str] = {
    "기흥역": "수인분당선 급행 정차 + 에버라인·GTX-A 환승",
    "죽전역": "수인분당선 급행 정차",
    "수원역": "1호선 급행 정차 + 광역버스 환승",
    "금정역": "1·4호선 환승역",
    "동탄역": "GTX-A·SRT — 일반 전철 노선과 별개",
}

# (역명, 노선, 강남역까지 전철 소요시간(분), 환승 횟수)
#
# ⚠️ 소요시간은 **추정치**다. 공개된 대중교통 길찾기 REST API 를 이 프로젝트가 쓰지
#    않기 때문에(README '알려진 한계' 참조) 실측으로 대체하지 못했다. 모델의
#    강남접근성 계수는 이 표만큼만 정확하다 — 다른 요인(면적·층·도보·연식·세대수·동)
#    은 실거래에서 직접 추정되므로 이 한계의 영향을 받지 않는다.
#
#    값은 평일 오전 강남역 도착 기준이며, 환승 대기를 환승 1회당 약 5분으로 본다.
#    노선별 단조성은 아래 `check_monotone()` 이 매 실행마다 검사한다.
STATIONS: list[tuple[str, str, int, int]] = [
    # ── 신분당선 — 강남 직결. 수원 남동부·용인 수지 프리미엄의 원인.
    ("동천역", "신분당선", 23, 0),
    ("수지구청역", "신분당선", 25, 0),
    ("성복역", "신분당선", 27, 0),
    ("상현역", "신분당선", 30, 0),
    ("광교중앙역", "신분당선", 35, 0),
    ("광교역", "신분당선", 37, 0),
    # ── 수인분당선 — 정자/미금에서 신분당 환승
    ("오리역", "수인분당선", 30, 1),
    ("죽전역", "수인분당선", 32, 1),
    ("보정역", "수인분당선", 37, 1),
    ("구성역", "수인분당선", 40, 1),
    ("신갈역", "수인분당선", 43, 1),
    ("기흥역", "수인분당선", 42, 1),
    ("상갈역", "수인분당선", 46, 1),
    ("청명역", "수인분당선", 48, 1),
    ("영통역", "수인분당선", 50, 1),
    ("망포역", "수인분당선", 52, 1),
    ("매탄권선역", "수인분당선", 57, 1),
    ("수원시청역", "수인분당선", 58, 1),
    ("매교역", "수인분당선", 60, 1),
    ("고색역", "수인분당선", 62, 1),
    ("오목천역", "수인분당선", 65, 1),
    ("어천역", "수인분당선", 70, 1),
    ("야목역", "수인분당선", 74, 1),
    # ── 1호선(경부선) — 금정에서 4호선, 또는 사당 환승
    ("금정역", "1호선", 45, 1),
    ("군포역", "1호선", 48, 1),
    ("당정역", "1호선", 50, 1),
    ("의왕역", "1호선", 52, 1),
    # 성균관대·화서는 기존 표에서 각각 62·58분이었는데, 둘 다 수원역(55분)보다
    # **금정 쪽에 가까운데도 더 느린** 값이었다. 노선 순서를 따라 다시 잡았다.
    # (단조성 검사가 이 어긋남을 잡아내 발견했다)
    ("성균관대역", "1호선", 54, 1),
    ("화서역", "1호선", 56, 1),
    ("수원역", "1호선", 55, 1),
    ("세류역", "1호선", 58, 1),
    ("병점역", "1호선", 62, 1),
    ("세마역", "1호선", 66, 1),
    ("오산대역", "1호선", 69, 1),
    ("오산역", "1호선", 72, 1),
    ("서동탄역", "1호선", 65, 1),
    # ── 4호선 — 사당에서 2호선 환승. 과천·안양·군포가 여기에 걸린다.
    ("선바위역", "4호선", 26, 1),
    ("경마공원역", "4호선", 28, 1),
    ("대공원역", "4호선", 30, 1),
    ("과천역", "4호선", 32, 1),
    ("정부과천청사역", "4호선", 34, 1),
    ("인덕원역", "4호선", 37, 1),
    ("평촌역", "4호선", 40, 1),
    ("범계역", "4호선", 42, 1),
    ("산본역", "4호선", 47, 1),
    ("수리산역", "4호선", 50, 1),
    ("대야미역", "4호선", 54, 1),
    # ── 1호선(안양) — 금정 북쪽
    ("명학역", "1호선", 43, 1),
    ("안양역", "1호선", 41, 1),
    ("관악역", "1호선", 39, 1),
    ("석수역", "1호선", 37, 1),
    # ── GTX-A — 동탄·용인의 강남 접근성을 통째로 바꾼 노선. 수서에서 환승.
    ("동탄역", "GTX-A", 32, 1),
    # GTX-A 의 용인 정차역은 이름이 "용인역" 이 아니라 **구성역**이다(카카오 확인).
    # 같은 자리에 수인분당선 구성역(40분)이 따로 있고, 둘 다 표에 두는 것이 맞다 —
    # route_walk 가 도보시간까지 더해 더 빠른 쪽을 best_access 로 고른다.
    ("구성역 GTX-A", "GTX-A", 28, 1),
    # ── 에버라인(용인경전철) — 기흥에서 수인분당 환승(총 2회)
    ("강남대역", "에버라인", 47, 2),
    ("지석역", "에버라인", 49, 2),
    ("어정역", "에버라인", 51, 2),
    ("동백역", "에버라인", 53, 2),
    ("초당역", "에버라인", 55, 2),
    ("삼가역", "에버라인", 60, 2),
    ("시청·용인대역", "에버라인", 62, 2),
    ("명지대역", "에버라인", 64, 2),
    ("김량장역", "에버라인", 66, 2),
    # 운동장·송담대역 → 용인중앙시장역 개명(카카오 확인).
    ("용인중앙시장역", "에버라인", 68, 2),
    ("고진역", "에버라인", 71, 2),
    ("보평역", "에버라인", 73, 2),
    ("둔전역", "에버라인", 75, 2),
    ("전대·에버랜드역", "에버라인", 78, 2),
]


def check_monotone(rows: list[tuple[str, str, int, int]]) -> list[str]:
    """노선을 따라 소요시간이 단조 증가하는지 본다. 어긋난 곳을 문장으로 돌려준다.

    수기 표는 커지면 반드시 어긋난다. 어긋남 자체가 오류는 아니다 — 급행 정차역은
    앞뒤보다 빠른 게 맞다. 그래서 `FASTER_THAN_NEIGHBOR` 에 이유를 적어 둔 역은
    넘어가고, 이유 없이 어긋난 곳만 보고한다.
    """
    by_name = {name: minutes for name, _line, minutes, _t in rows}
    problems: list[str] = []
    for line, order in LINE_ORDER.items():
        prev_name = None
        for name in order:
            cur = by_name.get(name)
            if cur is None:
                continue
            if prev_name is not None and cur < by_name[prev_name]:
                if name in FASTER_THAN_NEIGHBOR:
                    pass  # 이유가 적혀 있다
                elif prev_name in FASTER_THAN_NEIGHBOR:
                    pass  # 앞 역이 빨랐던 것이라 역전은 자연스럽다
                else:
                    problems.append(
                        f"{line}: {prev_name}({by_name[prev_name]}분) → "
                        f"{name}({cur}분) — 강남에서 더 먼데 더 빠르다"
                    )
            prev_name = name
    return problems


def station_name_matches(written: str, found_name: str) -> bool:
    """카카오가 돌려준 역 이름이 표에 적은 이름과 같은 역인가.

    카카오는 노선명을 뒤에 붙여 준다('동천역 신분당선'). 가운뎃점도 '.' 로 쓴다
    ('시청.용인대역'). 그 차이를 걷어내고 비교한다.
    """
    def norm(v: str) -> str:
        v = (v or "").replace("·", "").replace(".", "").replace(" ", "")
        for line in ("신분당선", "수인분당선", "수도권1호선", "수도권4호선",
                     "1호선", "4호선", "GTX-A", "용인에버라인", "에버라인"):
            v = v.replace(line, "")
        return v.removesuffix("역")

    return norm(written) == norm(found_name)


def run(force: bool, do_geocode: bool, sleep: float) -> None:
    issues = check_monotone(STATIONS)
    if issues:
        print(f"⚠️ 노선 순서와 맞지 않는 소요시간 {len(issues)}건:")
        for t in issues:
            print(f"   {t}")
        print("   (급행 정차 등 이유가 있으면 FASTER_THAN_NEIGHBOR 에 적으세요)")
    else:
        print(f"노선 단조성 검사 통과 — {len(STATIONS)}개역")

    with SessionLocal() as db:
        existing = {
            (s.name, s.line): s for s in db.execute(select(Station)).scalars().all()
        }
        created = updated = geocoded = 0
        renamed: list[tuple[str, str, str]] = []

        for name, line, minutes, transfers in STATIONS:
            st = existing.get((name, line))
            if st is None:
                st = Station(name=name, line=line, source="curated")
                db.add(st)
                created += 1
            else:
                updated += 1
            st.minutes_to_gangnam = minutes
            st.transfers_to_gangnam = transfers

            if do_geocode and (force or st.lat is None):
                try:
                    hit = find_station(name, line_hint=line)
                    # 이름이 낡았는지 함께 본다. '운동장·송담대역'은 '용인중앙시장역'
                    # 으로, GTX-A '용인역'은 '구성역'으로 바뀌어 있었다. 좌표가 붙었다고
                    # 이름이 맞는 것도 아니다 — 카카오가 비슷한 다른 역을 줄 수 있다.
                    if hit is not None and not station_name_matches(name, hit.name):
                        renamed.append((name, line, hit.name))
                except KakaoError as exc:
                    print(f"  {exc}")
                    print("  → 좌표 없이 표만 저장합니다. 키를 넣고 --force 로 재실행하세요.")
                    do_geocode = False
                    hit = None
                except Exception as exc:
                    print(f"  [{name}] 좌표 조회 실패: {exc}")
                    hit = None
                if hit:
                    st.lat, st.lng = hit.lat, hit.lng
                    geocoded += 1
                time.sleep(sleep)

        db.commit()

        total = db.execute(select(Station)).scalars().all()
        if renamed:
            print(f"⚠️ 이름이 다른 역 {len(renamed)}곳 — 개명됐는지 확인하세요:")
            for wrote, line, found in renamed:
                print(f"   {line} '{wrote}' → 카카오는 '{found}'")
        missing = [s.name for s in total if s.lat is None]
        print(f"역 {len(total)}곳 (신규 {created} / 갱신 {updated} / 좌표 {geocoded}건 조회)")
        if missing:
            print(f"좌표 없음 {len(missing)}곳: {', '.join(missing[:8])}"
                  f"{' …' if len(missing) > 8 else ''}")
            print("  KAKAO_REST_KEY 설정 후 `python -m scripts.seed_stations --force` 재실행")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="좌표가 있어도 다시 조회")
    parser.add_argument("--no-geocode", action="store_true", help="카카오 조회 없이 표만 저장")
    parser.add_argument("--sleep", type=float, default=0.1)
    args = parser.parse_args()
    run(args.force, not args.no_geocode, args.sleep)
