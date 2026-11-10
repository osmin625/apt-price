import IndexView from './views/IndexView'

/**
 * 주식의 탭 — 모양은 `realestate/tabs.jsx` 와 같다(id·label·static·render). 탭 id 는 자산을 건너
 * 겹치지 않아야 한다 — 주소 `#탭` 만으로 자산이 정해진다(App.jsx `assetOfTab`).
 *
 * 첫 조각은 지수 둘이다. 종목 예측은 같은 평가 장치에 얹는다(docs/stock/indices.md).
 */
export const TABS = [
  { id: 'indices', label: '지수 예측', static: true, render: () => <IndexView /> },
]
