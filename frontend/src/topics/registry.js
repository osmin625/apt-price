/**
 * 주제 레지스트리 — **같은 주제는 창 하나**.
 *
 * 전세가율은 가격 분석(시군구 17곳의 추이)에도, 거시 분석(그 뒤 12개월 가격과의
 * 관계)에도 카드가 있다. 카드는 각 탭의 질문에 맞게 따로 두지만, 눌러서 뜨는 창이
 * 탭마다 다르면 '전세가율의 전체 그림' 이 두 군데에 반씩 나뉜다. 한쪽 창에만 있는
 * 정보를 찾으려면 다른 탭으로 건너가 같은 카드를 또 눌러야 했다.
 *
 * 그래서 창은 **주제마다 하나**로 둔다. 어느 탭에서 열든 같은 `TopicModal` 이 같은
 * 절(공급 → 지역별 추이 → 가격과의 관계)을 같은 순서로 보여 준다. 각 절은 자기
 * 데이터를 직접 받으므로 여는 탭이 무엇을 들고 있는지와 무관하다.
 *
 * 한 주제를 이루는 원천은 셋이다.
 *   metric — 가격 분석의 시군구 지표 (`/macro/series?metric=`)
 *   factor — 거시 분석의 요인 (`/regime/overview` 의 factors[].key)
 *   supply — 공급 분석의 절 (`/supply/overview` 의 unsold · pipeline)
 *
 * 여기 없는 키는 그 원천 하나짜리 주제로 만들어 같은 창으로 연다 — 겹치지 않는
 * 주제도 같은 길을 지나야 나중에 겹치게 됐을 때 이 표에 한 줄 더하는 것으로 끝난다.
 *
 * **새로 겹치는 주제가 생기면 여기에 한 줄을 더한다.** 거래량은 원천의 키가 서로
 * 다르다(`trade_volume` / `trade`) — 이름으로 짐작해 묶지 않고 이 표가 정한다.
 */
export const TOPICS = [
  { id: 'jeonse_ratio', title: '전세가율', metric: 'jeonse_ratio', factor: 'jeonse_ratio' },
  { id: 'trade_volume', title: '매매 거래량', metric: 'trade_volume', factor: 'trade' },
  { id: 'unsold', title: '미분양', supply: 'unsold', factor: 'unsold' },
  { id: 'pipeline', title: '공급 파이프라인 — 인허가 · 착공 · 준공', supply: 'pipeline' },
  // 거시 분석의 '누적 공급' 은 경기의 적정 공급 대비 준공 누적 차이다 — 공급 분석의 '적정보다
  // 더 지었나' 카드의 누적 점선과 같은 값이라 창이 하나다(scripts/verify_supply_cum.py 가 대조).
  // 예전에는 '준공 물량'(12개월 합의 로그 변화율), 그다음 '공급'(12개월 준공 ÷ 적정)이었다.
  { id: 'balance', title: '적정 대비 공급', supply: 'balance', factor: 'supply' },
]

/**
 * 주제 창의 '시군구별 추이' 절에 쓰는 지표. 주제에 가격 분석 지표가 없으면(파이프라인·
 * 미분양·금리 같은 요인) **매매가격지수**를 보여 준다 — 거시 분석이 요인과 견주는 가격이
 * 그것이라, 같은 창에서 시군구마다 어떻게 갔는지까지 이어 볼 수 있다.
 */
export const PRICE_METRIC = 'sale_index'

/**
 * **데이터 하나에 카드 하나.** 이 주제의 카드가 어느 탭에 있나. 공급·가격 분석에 원천이
 * 있으면 그쪽이 카드의 집이고, 거시 분석은 같은 데이터를 카드로 한 번 더 그리지 않고
 * 위치만 한 줄로 보여 준다. 집이 없는(거시에만 있는) 요인은 null.
 */
export function homeOf(topic) {
  if (topic?.supply) return '공급 분석'
  if (topic?.metric) return '가격 분석'
  return null
}

/** (원천, 키) → 주제. `extra` 는 그 창의 초기값(기간 · 지역)이다. */
export function topicFor(kind, key, extra = {}) {
  const { title, ...init } = extra
  const t = TOPICS.find((x) => x[kind] === key)
  // 등록된 주제는 제목도 여기서 정한다 — 여는 탭의 카드 이름(지표명·요인명)이 서로
  // 달라도 창 제목은 하나다. 등록 안 된 것만 여는 쪽이 넘긴 이름을 쓴다.
  return { ...(t || { id: `${kind}:${key}`, [kind]: key, title }), ...init }
}
