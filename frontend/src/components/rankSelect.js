/**
 * 순위표에서 단지명을 누를 때의 동작.
 *
 * 그냥 누르면 **단지 상세**로 가고, Ctrl(맥은 ⌘)을 누른 채 누르면 **그 단지만** 남긴다.
 *
 * ## 왜 한 버튼에 둘을 두나
 *
 * 순위표를 보다가 "이 단지 것만 모아 보자" 가 되는 순간은 거의 항상 **그 단지 이름을
 * 보고 있을 때**다. 필터를 따로 두면 이름을 기억해 다른 곳에 다시 입력해야 한다.
 * 브라우저에서 Ctrl+클릭이 '다르게 열기' 인 것과 같은 결이라 설명 없이도 손이 간다.
 *
 * ## 표와 카드가 같은 함수를 쓴다
 *
 * 각자 쓰면 한쪽만 고쳐져 창 폭에 따라 동작이 달라진다 — 기준별 열에서 이미 겪은
 * 함정이다(`rankBasis.js`). 한쪽에 두고 다른 쪽에서 가져오면 순환 import 가 되므로
 * (RankTable 이 RankCards 를 쓴다) 따로 둔다.
 */

export const ONLY_HINT = '클릭: 단지 상세 · Ctrl(⌘)+클릭: 이 단지만 보기'

export function nameClick(e, complexId, onSelect, onOnlyComplex) {
  if ((e.ctrlKey || e.metaKey) && onOnlyComplex) {
    // 버튼이라 기본 동작은 없지만, 브라우저나 확장이 Ctrl+클릭에 뭔가 붙이는 경우가 있다.
    e.preventDefault()
    e.stopPropagation()
    onOnlyComplex(complexId)
    return
  }
  onSelect(complexId)
}
