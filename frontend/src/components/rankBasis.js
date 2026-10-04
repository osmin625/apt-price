import { eok, fmt } from './Charts'

/**
 * 순위 기준(실거래/요인)에 따라 값을 고르는 규칙.
 *
 * 표(`RankTable`)와 좁은 화면 카드(`RankCards`)가 **같은 규칙**을 써야 한다. 각자
 * 고르게 두면 같은 매물이 창 폭에 따라 다른 판정을 달게 된다 — 화면을 줄였더니
 * '적정' 이 '저평가' 로 바뀌는 식이다.
 *
 * 둘 중 한쪽에 두고 다른 쪽에서 가져오면 순환 import 가 된다(RankTable 이 RankCards
 * 를 쓴다). 그래서 따로 둔다.
 */

export const toneOf = (pct) => (pct == null ? null : pct < -3 ? 'good' : pct > 3 ? 'bad' : 'mid')

export const gapText = (pct) => (pct == null ? '—' : `${pct > 0 ? '+' : ''}${fmt(pct, 1)}%`)

/**
 * 판정은 기준을 따라간다.
 *
 * 서버가 `verdict`(실거래)와 `verdict_factor`(요인)를 따로 준다. 안 그러면 요인
 * 기준 화면에서 대비는 -12% 인데 판정은 '적정' 으로 적힌다 — 다른 기준의 답이다.
 *
 * 요인 적정가가 없는 줄(모델이 값을 못 낸 경우)은 **빈 칸**이다. 실거래 판정을 대신
 * 보여 주면 보고 있는 숫자와 다른 것을 말하게 된다.
 */
export const verdictOf = (i, isFactor) =>
  isFactor ? (i.gap_factor_pct == null ? null : i.verdict_factor) : i.verdict

/**
 * 안 보이는 쪽 기준의 값. 호버(표)와 한 줄(카드)로 내린다.
 *
 * 열을 숨겼다고 값까지 버리지는 않는다. 두 기준이 어긋나는 것 **자체가 정보**다 —
 * 광교 84㎡ 가 실거래 기준 1위인데 요인 기준 4위로 내려간 적이 있다. 자기 단지
 * 최근 거래보다는 많이 싸지만 펀더멘털 대비로는 아니라는 뜻이었다.
 */
export const otherOf = (i, isFactor) => {
  if (isFactor) {
    return `실거래 기준 ${i.fair_price ? eok(i.fair_price) : '—'} · 대비 ${gapText(i.gap_pct)}`
  }
  return i.factor_price
    ? `요인 기준 ${eok(i.factor_price)} · 대비 ${gapText(i.gap_factor_pct)}`
    : '요인 기준 값이 없습니다 (모델 적합 필요)'
}
