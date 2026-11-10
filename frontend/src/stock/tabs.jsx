import IndexView from './views/IndexView'

/**
 * 주식의 탭 — 모양은 `realestate/tabs.jsx` 와 같다(id·label·static·render). 탭 id 는 자산을 건너
 * 겹치지 않아야 한다 — 주소 `#탭` 만으로 자산이 정해진다(App.jsx `assetOfTab`).
 *
 * 첫 조각은 지수 둘이다. 맨 위는 경제지표의 영향(docs/stock/effects.md), 아래는 구간 예측(docs/stock/indices.md).
 * 2026-11 에 id 를 'indices'(지수 예측)에서 바꿨다 — 옛 주소는 App.jsx 의 `TAB_ALIAS` 가 이리로 보낸다.
 */
export const TABS = [
  { id: 'index-analysis', label: '지수 분석', static: true, render: () => <IndexView /> },
]
