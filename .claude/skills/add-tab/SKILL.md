---
name: add-tab
description: 대시보드에 새 탭이나 카드·그림을 더한다. 새 화면을 만들 때, 탭을 정적 사이트에 실을 때, 탭 이름·순서를 바꿀 때 쓴다.
---

# 새 탭·카드 더하기

순서와 끝난 기준만 적는다. 화면 규칙은 [conventions.md](../../../docs/screens/conventions.md),
부동산 화면 설계는 [design.md](../../../docs/screens/design.md) 에 있다.

## 순서

1. **자리를 정한다.** 탭은 자산의 `frontend/src/<자산>/tabs.jsx` 의 `TABS` 한 곳이 이름·순서·
   정적 여부·화면을 다 든다. 순서 원칙(큰 틀에서 상세로)은 그 파일 머리 주석에 있다.
   **id 는 자산을 건너 겹치지 않게** 짓는다 — 주소 `#탭` 만으로 자산이 정해진다. id 는
   나중에 화면 이름이 바뀌어도 그대로 둔다(링크·정적 경로가 묶인다).
2. **백엔드** — 라우터는 얇게, 규칙·집계는 services 에([architecture.md](../../../docs/engineering/architecture.md)
   '라우터는 얇게'). 새 라우터는 `main.py` 에 등록한다.
3. **프론트** — `api.js` 에 호출 하나, 화면은 `src/<자산>/views/`. 카드·로딩·창·색은
   `src/shared/` 의 부품을 쓴다.
4. **문구** — 화면에는 제목·값·한 줄 상태만, 설명은 `Hint`(ⓘ)로 접는다. 그때 잰 값·그날의
   판정·통제한 요인 나열은 넣지 않는다(루트 CLAUDE.md '화면 문구에는 시간이 지나도 맞는 것만').
5. **정적 사이트** — `static: true` 로 실을 탭은 그 탭이 부르는 응답을 `export_static.py` 의
   `build_plan` 에도 넣는다. 안 넣으면 그 탭만 '불러오는 중' 으로 조용히 멈춘다.
6. **문서** — 화면 설계 문서에 절 하나, 이름이 헷갈릴 만하면 [용어집](../../../docs/engineering/glossary.md)
   에 id ↔ 화면 이름 한 줄. 이름을 바꿨으면 옛 이름을 `verify_sync.py` 의 `RETIRED_LABELS` 에.

## 끝난 기준

- `backend/` 에서 `python -m scripts.checkup --fast` 통과 — 이름·조사·엔드포인트·계약·긴 문구를
  `verify_sync` 가 본다
- 개발 서버(`.claude/launch.json` 의 `backend`·`frontend`)에서 `#<id>` 로 바로 열리고, 옛 탭
  링크도 그대로 열린다. 콘솔 오류가 없다
- 정적에 실었으면 내보낸 스냅샷에 그 응답 파일이 있다
