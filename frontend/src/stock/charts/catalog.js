import { TREND, MOMENTUM } from './trend.js'
import { OVERLAYS, TYPES } from './types.js'
import { BREADTH, FLOW, VOLATILITY, VOLUME } from './volume.js'

/**
 * 차트 탭의 목록 — 증권사 앱(HTS·MTS)이 흔히 주는 차트 유형·오버레이·보조지표를 모았다(2026-11-27 요청,
 * docs/stock/charts.md). NH투자증권 앱의 공식 목록은 공개된 곳이 없어 **일반 목록**이다 — 앱마다 이름·묶음·
 * 기본값이 조금씩 다르다. 화면 머리말 ⓘ 가 그렇게 적는다.
 *
 * 한 줄의 꼴:
 *   id · group · name · en     id 는 탭 전체에서 하나(주소 `#charts/<id>` 가 아니라 창을 여는 데만 쓴다)
 *   one                        카드 한 줄 — 정의라 시간이 지나도 맞는다
 *   calc · set                 계산(정의가 여럿이면 고른 쪽) · 흔한 설정값
 *   read · trap                읽는 법(줄 몇 개) · 함정
 *   plot                       예시 그림 스펙을 만드는 함수(`ExampleChart`), 그릴 수 없으면 null
 *   short                      단기 매매 탭에 같은 기법이 있으면 그 id — 실제 지수 성적은 거기서 본다
 *
 * 그림은 모두 같은 합성 가격(`sample.js`) 위에 지표의 식을 그대로 돌린 것이다(`calc.js`).
 */
export const SECTIONS = [
  { id: 'type', label: '차트 유형' },
  { id: 'overlay', label: '오버레이' },
  { id: 'sub', label: '보조지표' },
]

export const GROUPS = [
  { id: 'type', section: 'type', label: '차트 유형' },
  { id: 'overlay', section: 'overlay', label: '오버레이' },
  { id: 'trend', section: 'sub', label: '추세' },
  { id: 'momentum', section: 'sub', label: '모멘텀·과열' },
  { id: 'volatility', section: 'sub', label: '변동성' },
  { id: 'volume', section: 'sub', label: '거래량' },
  { id: 'breadth', section: 'sub', label: '시장 강도(지수)' },
  { id: 'flow', section: 'sub', label: '수급·심리' },
]

export const ITEMS = [...TYPES, ...OVERLAYS, ...TREND, ...MOMENTUM, ...VOLATILITY, ...VOLUME, ...BREADTH, ...FLOW]

/** 검색 — 이름·영문·한 줄에서 찾는다. 띄어쓰기·대소문자는 무시('볼린저밴드' 도 '볼린저 밴드' 를 찾는다). */
export function search(q) {
  const norm = (s) => s.toLowerCase().replace(/[\s·()%-]/g, '')
  const k = norm(q)
  if (!k) return ITEMS
  return ITEMS.filter((x) => norm(`${x.name}${x.en}${x.one}`).includes(k))
}
