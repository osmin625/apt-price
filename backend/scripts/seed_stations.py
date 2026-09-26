"""수원권 지하철역 + 강남 접근성 테이블을 채운다.

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
STATIONS: list[tuple[str, str, int, int]] = [
    # 신분당선 — 강남 직결. 수원 남동부 프리미엄의 원인.
    ("상현역", "신분당선", 30, 0),
    ("광교중앙역", "신분당선", 35, 0),
    ("광교역", "신분당선", 37, 0),
    # 수인분당선 — 정자/죽전에서 신분당 환승
    ("청명역", "수인분당선", 48, 1),
    ("영통역", "수인분당선", 50, 1),
    ("망포역", "수인분당선", 52, 1),
    ("매탄권선역", "수인분당선", 57, 1),
    ("수원시청역", "수인분당선", 58, 1),
    ("매교역", "수인분당선", 60, 1),
    ("고색역", "수인분당선", 62, 1),
    ("오목천역", "수인분당선", 65, 1),
    # 1호선(경부선) — 사당 또는 금정 환승
    ("세류역", "1호선", 58, 1),
    ("수원역", "1호선", 55, 1),
    ("화서역", "1호선", 58, 1),
    ("성균관대역", "1호선", 62, 1),
    # 수원 경계 밖이지만 생활권이 겹쳐 최근접역이 될 수 있는 역
    ("기흥역", "수인분당선", 45, 1),
    ("신갈역", "수인분당선", 47, 1),
    ("영덕역", "수인분당선", 43, 1),
    ("병점역", "1호선", 62, 1),
    ("의왕역", "1호선", 52, 1),
    ("금정역", "1호선", 45, 1),
]


def run(force: bool, do_geocode: bool, sleep: float) -> None:
    with SessionLocal() as db:
        existing = {
            (s.name, s.line): s for s in db.execute(select(Station)).scalars().all()
        }
        created = updated = geocoded = 0

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
