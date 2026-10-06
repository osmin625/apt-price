import { fmt } from './Charts'
import Hint from './Hint'

/**
 * 순위표 행에서 **왜 이 값인지**를 호버로 보여 준다.
 *
 * 순위만 보고는 납득할 수 없다 — "이 매물이 왜 요인 기준으로 30% 싼가" 에 답하려면
 * 요인별 기여가 보여야 한다. 그렇다고 표에 열을 아홉 개 더 붙일 수는 없으니
 * 호버로 펼친다.
 *
 * 단지 요인과 유닛 요인을 나눠 둔다. 앞은 "어디에 있는 아파트인가"(단지 사이 비교),
 * 뒤는 "그 안에서 어느 집인가"(단지 안 비교)로 성격이 다르다.
 */
export default function FactorHint({ parts }) {
  if (!parts) return null
  const rows = [
    ['단지 — 어디에 있는 아파트인가', parts.complex],
    ['유닛 — 그 안에서 어느 집인가', parts.unit],
  ].filter(([, v]) => v?.length)
  if (!rows.length) return null

  return (
    <Hint wide>
      <span className="fh">
        {rows.map(([title, list]) => (
          <span key={title} className="fh-group">
            <span className="fh-title">{title}</span>
            {list.map((p, i) => (
              <span key={i} className="fh-row">
                <span className="fh-label">{p.label}</span>
                {p.value && <span className="fh-value">{p.value}</span>}
                <span className={`fh-pct ${p.pct > 0 ? 'tone-pos' : 'tone-neg'}`}>
                  {p.pct > 0 ? '+' : ''}
                  {fmt(p.pct, 1)}%
                </span>
              </span>
            ))}
          </span>
        ))}
        {/* 이 시세가 몇 건에 얹혀 있나. 직거래가 섞인 단지는 중개거래가 더 적다 —
            '적정' 판정이 2건 위에 서 있는지 아닌지는 보여야 한다. */}
        {parts.market_count != null && (
          <span className={`fh-foot${parts.market_count < 5 ? ' fh-thin' : ''}`}>
            중개거래 <b>{parts.market_count}건</b> 기준
            {parts.trade_count > parts.market_count &&
              ` · 직거래 ${parts.trade_count - parts.market_count}건은 할인을 걷어낸 뒤 씀`}
            {parts.market_count < 5 && ' · 표본이 적어 흔들릴 수 있음'}
          </span>
        )}
        {parts.premium_pct != null && (
          <span className="fh-foot">
            단지 고유 프리미엄{' '}
            <b>
              {parts.premium_pct > 0 ? '+' : ''}
              {fmt(parts.premium_pct, 1)}%
            </b>{' '}
            — 요인으로 설명되지 않고 이 단지에 붙어 있는 값입니다.
          </span>
        )}
      </span>
    </Hint>
  )
}
