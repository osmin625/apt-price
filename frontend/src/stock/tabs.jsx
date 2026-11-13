import { api } from '../api'
import * as LONG from './techniques/long'
import * as SHORT from './techniques/short'
import IndexView from './views/IndexView'
import TechniqueView from './views/TechniqueView'

/**
 * 주식의 탭 — 모양은 `realestate/tabs.jsx` 와 같다(id·label·static·render). 탭 id 는 자산을 건너
 * 겹치지 않아야 한다 — 주소 `#탭` 만으로 자산이 정해진다(App.jsx `assetOfTab`).
 *
 * 첫 조각은 지수 둘이다. 맨 위는 경제지표의 영향(docs/stock/effects.md), 아래는 구간 예측(docs/stock/indices.md).
 * 2026-11 에 id 를 'indices'(지수 예측)에서 바꿨다 — 옛 주소는 App.jsx 의 `TAB_ALIAS` 가 이리로 보낸다.
 *
 * 순서는 부동산과 같은 원칙(큰 틀에서 상세로) — 시장 전체(지수 분석) → 몇 년을 보는 기법(장기 투자) → 며칠~몇 주를
 * 보는 기법(단기 매매). 뒤의 둘은 기법 저장소다(2026-11-12 합의, docs/stock/valuation.md · trading.md).
 * '단타' 대신 '단기 매매' 인 것은 받는 자료가 일봉이라 며칠~몇 주 매매가 중심이어서다.
 */
const LONG_NOTES = [
  '버핏·그레이엄 같은 장기 투자자의 가치평가 기법을 모았습니다. 카드를 누르면 원리·쓰는 법·예시·함정·원전이 나옵니다.',
  '지수 평가 넷은 실제 S&P 500·KOSPI 에 돌렸습니다. 카드의 한 줄은 지금 값과 역사 백분위(그달까지의 값 가운데 아래인 비율)이고, 창에는 백분위 칸마다 그 뒤 5·10년 수익률과 실제 계열 그림이 있습니다.',
  '나머지는 한 회사의 재무에 쓰는 기법이라 가상 회사 숫자로 계산 과정을 보여 줍니다. 창에 그렇게 적었습니다.',
  '기법 설명이지 투자 권유가 아닙니다. 어느 기법도 언제 사고팔지를 보장하지 않습니다.',
]
const SHORT_NOTES = [
  '차트 모양과 지표로 며칠~몇 주를 보고 사고파는 기법을 모았습니다. 카드를 누르면 원리·규칙·예시·함정·원전이 나옵니다.',
  '종가로 잼 카드는 규칙을 실제 S&P 500·KOSPI 종가에 그대로 돌렸습니다. 카드의 한 줄은 지금 상태 — 진입·청산이 있는 규칙은 규칙대로라면 지금 들고 있는 구간인지, 패턴은 형성 중이거나 최근에 난 신호입니다. 창에는 과거 성적(아무 날이나 산 것·사서 들고 있기와 견준 것, 거래 비용 뺌)과 실제 사례가 있습니다.',
  '고가·저가, 거래량, 분봉이 필요한 기법은 지금 받는 자료(지수 일봉 종가)로는 실제 지수에 돌릴 수 없어, 모양을 정해 만든 합성 가격으로 설명합니다. 그 위의 진입·청산 표시도 규칙을 돌려 얻었습니다.',
  '기법 설명이지 투자 권유가 아닙니다. 거래 비용을 빼면 잦은 매매일수록 남는 것이 줄어듭니다.',
]

export const TABS = [
  { id: 'index-analysis', label: '지수 분석', static: true, render: () => <IndexView /> },
  {
    id: 'long-term', label: '장기 투자', static: true,
    render: () => <TechniqueView title="장기 투자 — 가치평가 기법" notes={LONG_NOTES} catalog={LONG} load={api.stockLongTerm} />,
  },
  {
    id: 'short-term', label: '단기 매매', static: true,
    render: () => <TechniqueView title="단기 매매 — 차트 기법" notes={SHORT_NOTES} catalog={SHORT} load={api.stockShortTerm} />,
  },
]
