import { eok, fmt } from './Charts'
import Hint from './Hint'

/**
 * 같은 집이 값을 바꿔 다시 올라온 경우의 **변동 표시**.
 *
 * 순위표에는 최신 호가 한 줄만 둔다. 그런데 "3.55억" 만 보면 이 집이 원래 3.8억을
 * 부르다 내린 것인지 처음부터 3.55억이었는지 알 수 없다 — 그 둘은 전혀 다른 정보다.
 * 값이 내려가고 있는 집은 매도자가 급하다는 뜻이고, 호가를 쌓는 이유가 바로 그것이다.
 *
 * 그래서 최신 호가 옆에 `▼ 6.6%` 만 붙이고, 전체 경로는 호버에 둔다. 표에 열을
 * 더 붙이면 대부분의 행이 빈칸이 된다 — 변동이 있는 매물은 소수다.
 *
 * 기준은 **직전 호가**다(사용자 요청). 최초 호가 대비는 아래 각주에 함께 적는다.
 */
export default function PriceTrail({ item }) {
  if (!(item?.revisions > 1) || item.price_change_pct == null) return null

  const hist = item.price_history || []
  const down = item.price_change_pct < 0
  const total = item.total_change_pct
  // 이어붙일 후보가 여럿이었으면 '어느 호가의 다음인지' 는 추측이다. 값 자체는
  // 맞지만 경로는 확정이 아니므로, 사실처럼 보여 주지 않는다.
  const guess = !!item.ambiguous

  return (
    <Hint
      pill
      wide
      tone={guess ? 'warn' : down ? 'good' : 'bad'}
      label={`${down ? '▼' : '▲'} ${fmt(Math.abs(item.price_change_pct), 1)}%${guess ? '?' : ''}`}
    >
      <span className="fh">
        <span className="fh-group">
          <span className="fh-title">
            호가 {hist.length}번 올라옴 · 최신 기준{guess ? ' · 경로는 추정' : ''}
          </span>
          {hist.map((h, n) => {
            const prev = n > 0 ? hist[n - 1].asking_price : null
            const step = prev ? ((h.asking_price - prev) / prev) * 100 : null
            const last = n === hist.length - 1
            return (
              <span key={n} className="fh-row">
                <span className="fh-label">
                  {h.first_seen}
                  {h.last_seen && h.last_seen !== h.first_seen ? ` ~ ${h.last_seen}` : ''}
                </span>
                <span className="fh-value" style={last ? { fontWeight: 700 } : null}>
                  {eok(h.asking_price)}
                </span>
                <span className={`fh-pct ${step == null ? '' : step > 0 ? 'tone-pos' : 'tone-neg'}`}>
                  {step == null ? '최초' : `${step > 0 ? '+' : ''}${fmt(step, 1)}%`}
                </span>
              </span>
            )
          })}
        </span>
        <span className="fh-foot">
          최초 {eok(item.first_price)} → 최신 <b>{eok(item.asking_price)}</b>
          {total != null && ` (${total > 0 ? '+' : ''}${fmt(total, 1)}%)`}. 옛 호가와 올라와 있던
          기간이 겹치지 않아 같은 집이 값을 바꾼 것으로 보고, 최신 호가만 순위에 넣었습니다.
          {guess &&
            ' 다만 같은 층·평형에 비어 있던 호가가 여럿이라 어느 호가의 다음인지는 확정할 수 없습니다 — 목록에 호가 나오지 않기 때문입니다.'}
        </span>
      </span>
    </Hint>
  )
}
