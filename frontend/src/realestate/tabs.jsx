import { STATIC_MAP } from '../api'
import CompareView from './views/CompareView'
import MacroView from './views/MacroView'
import MapView from './views/MapView'
import MarketView from './views/MarketView'
import ModelView from './views/ModelView'
import RankingView from './views/RankingView'
import RegimeView from './views/RegimeView'
import SupplyView from './views/SupplyView'
import TenureView from './views/TenureView'

/**
 * 부동산의 탭 — 이 자산에 무슨 탭이 있고, 각 탭이 어떤 화면인지는 **여기 한 곳**이 정한다.
 *
 * 예전에는 탭 목록은 App.jsx 의 `TABS` 에, 화면 연결은 같은 파일의 삼항 체인(`tab === 'micro' ? …`)에
 * 따로 있었다. 탭을 더하면 두 곳을 고쳐야 했고, 자산이 늘면 자산 수만큼 불어날 자리였다. 이제 탭 하나가
 * `render` 까지 들고 있고, App.jsx 는 자산을 조립만 한다. 새 자산은 `src/<자산>/tabs.jsx` 를 같은 모양으로 둔다.
 *
 * `render(ctx)` 의 ctx — App 이 들고 있는 공용 상태: `filters`·`setFilters`(분석 기간), `meta`(필터 선택지),
 * `onSelect`(단지 상세 열기), `pasted`(전역 Ctrl+V 로 들어온 매물 텍스트).
 *
 * ## 정적 사이트 — `static`
 *
 * `static: true` 인 탭만 정적 사이트에 실린다. 나머지는 서버가 필요해서 빼는 것이 아니라, **서버 없이는
 * 틀린 답을 내기 때문에** 뺀다. 호가 입력은 붙여넣은 텍스트를 그 자리에서 읽고 평가하므로 미리 파일로
 * 만들어 둘 수가 없다. 눌리는데 실패하는 탭을 두지 않는다 — 없는 기능은 아예 안 보이는 쪽이 낫다.
 *
 * 탭을 정적에 실으려면 그 탭이 부르는 응답을 `backend/scripts/export_static.py` 의 `build_plan` 에도
 * 넣는다. 안 넣으면 그 탭만 404 로 비고, 화면에는 '불러오는 중' 으로 멈춰 조용하다.
 *
 * 지도는 데이터가 아니라 **키 때문에** 조건부다. 응답은 늘 내보내지만, 카카오 JS 키가 공개 번들에
 * 들어가야 하므로 켜는 것을 의도적인 행위로 만들었다(`VITE_STATIC_MAP=1`). 자세한 것은 api.js 의
 * STATIC_MAP 주석과 docs/engineering/deploy.md.
 *
 * ## 순서 — 큰 틀에서 상세로
 *
 * 2026-10-22 요청으로 다시 줄 세웠다: 거시 분석이 첫째, 탭을 넘길수록 범위가 좁아져 호가 분석이 마지막.
 * 전국·경기의 거시 요인 → 공급 → 경기 남부 평균의 매매·전세·월세 → 시군구별 공표 가격 → 단지 가격을 움직이는
 * 요인(매물 분석·분해 모델) → 단지 하나하나(지도) → 매물 하나하나(호가 입력·분석). 예전에는 매물 분석이
 * 첫 탭이라, 무엇을 보는 사이트인지 알기 전에 단지 요인부터 나왔다. 첫 화면은 이 목록의 첫 탭이다.
 */

// 분해 모델·지도·호가는 기간이 12개월보다 짧으면 적합 표본이 너무 얇다.
const atLeast12 = (ctx) => Math.max(ctx.filters.months, 12)

export const TABS = [
  // 공급은 여섯 요인 중 하나다. 나머지(수요·통화량·금리·정책·세금)까지 한 화면에
  // 놓고 **어느 쪽으로 미는지**를 본다. 공급 탭과 겹치는 것은 준공·미분양뿐이고,
  // 거기서는 '얼마나 모자라나', 여기서는 '그래서 어느 쪽인가' 를 묻는다.
  { id: 'regime', label: '거시 분석', static: true, render: () => <RegimeView /> },
  // 공급은 2~3년 전에 정해져 지금 나타난다. 가격 추이와 같은 축에 놓으면
  // 둘 다 안 읽혀서 탭을 따로 뒀다.
  { id: 'supply', label: '공급 분석', static: true, render: () => <SupplyView /> },
  // 거시 탭이 '가격을 어느 쪽으로 미나' 라면, 여기는 '수요가 어느 점유 형태로 옮겨 가나' 다.
  // 같은 금리가 매매·전세·월세에 다르게 닿는 것을 보려면 세 가격이 한 화면에 있어야 한다.
  { id: 'tenure', label: '매매·전세·월세', static: true, render: () => <TenureView /> },
  // 한 탭 안에 섹션으로 합쳐 봤다가 **되돌렸다.** 둘(가격 분석·매물 분석)은 같은 질문의 두 축이지만,
  // 각자 카드가 예닐곱 장이라 한 화면에 올리면 좌우 2단으로 쪼개도 빽빽했다.
  // 겹쳐 봐야 하는 것은 '모델과 어긋나는 곳' 한 장뿐이고, 그건 가격 분석 쪽에 이미 있다.
  // 이름을 두 번 바꿨다. '시장 분석' → '미시 분석' → '매물 분석' 이고,
  // '매크로' → '거시 분석' → '가격 분석' 이다. 바꾼 이유는 같다 — '미시/거시' 가
  // 무엇을 보는 탭인지 말해 주지 않았다. 지금 이름은 **대상**을 가리킨다.
  { id: 'macro', label: '가격 분석', static: true, render: () => <MacroView /> },
  {
    id: 'micro', label: '매물 분석', static: true,
    render: (ctx) => <MarketView filters={ctx.filters} setFilters={ctx.setFilters} meta={ctx.meta} />,
  },
  // 적합 결과(`/model/fit`)와 묶어 보기(`/model/groups`)를 정적으로도 내보낸다.
  // 맨 위 수식(`ModelFormula`)이 탭의 입구다.
  {
    id: 'model', label: '분해 모델', static: true,
    render: (ctx) => <ModelView months={atLeast12(ctx)} onSelect={ctx.onSelect} />,
  },
  {
    id: 'map', label: '지도', static: STATIC_MAP,
    render: (ctx) => <MapView months={atLeast12(ctx)} onSelect={ctx.onSelect} />,
  },
  // '매물 분석' 이었다. 붙여넣어 읽는 것만 하던 탭에 **메모 사전 관리**가
  // 들어오면서, 하는 일이 분석보다 관리에 가까워졌다.
  // 둘은 짝이다 — 한쪽에 붙여넣고 다른 쪽에서 본다. 이름도 짝으로 맞췄다.
  {
    id: 'compare', label: '호가 입력',
    render: (ctx) => <CompareView months={atLeast12(ctx)} incoming={ctx.pasted} />,
  },
  {
    id: 'ranking', label: '호가 분석', static: true,
    render: (ctx) => (
      <RankingView
        months={atLeast12(ctx)}
        setMonths={(m) => ctx.setFilters({ ...ctx.filters, months: m })}
        onSelect={ctx.onSelect}
      />
    ),
  },
]
