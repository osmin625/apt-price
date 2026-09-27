import { useEffect, useState } from 'react'

import { api } from '../api'
import FactorPrice from './FactorPrice'

import { eok, fmt } from './Charts'
import Hint from './Hint'

const TONE = {
  저평가: 'good',
  '다소 저렴': 'good',
  적정: 'mid',
  '다소 비쌈': 'bad',
  고평가: 'bad',
}

/**
 * 매물 하나의 적정가 진단 — 같은 단지·같은 평형의 실거래 기준.
 *
 * 비교 화면 안에서 A·B 두 장이 나란히 서므로 **접힌 상태가 기본**이다. 예전 전용
 * 탭에서는 타일 4개 + 산출 근거 + 실거래 표를 한꺼번에 펼쳐 뒀는데, 그걸 두 벌
 * 늘어놓으면 정작 아래에 있는 A·B 비교까지 스크롤이 닿지 않는다.
 *
 * 이 진단과 아래 요인별 비교는 **다른 질문에 답한다**. 여기는 "그 단지 같은 평형
 * 시세 대비 이 호가가 적정한가", 아래는 "A와 B 중 요인을 감안하면 어느 쪽이 싼가"다.
 */
export default function FairCard({ tag, name, result, busy, onSelect }) {
  const [open, setOpen] = useState(false)
  // 누적 호가. 실거래가 뜸한 동은 이쪽에만 신호가 남는다 — 값을 못 받는 매도자는
  // 싸게 파는 대신 물건을 거둬들이므로, 내려간 가격은 거래가 아니라 호가에 있다.
  const [quotes, setQuotes] = useState(null)
  const cid = result?.fair?.complex?.id
  const akey = result?.fair?.exclusive_area ? Math.round(result.fair.exclusive_area) : null
  useEffect(() => {
    if (!cid || !akey) return setQuotes(null)
    let alive = true
    api
      .quotes(cid, { area_key: akey })
      .then((d) => alive && setQuotes(d))
      .catch(() => alive && setQuotes(null))
    return () => {
      alive = false
    }
  }, [cid, akey, result?.input?.asking_price])

  // 계산 중에는 **이전 결과를 그대로 두고** 흐리게만 한다. 비우면 값이 사라졌다
  // 돌아오면서 화면이 튀고, 무엇이 바뀌었는지도 보이지 않는다.
  if (!result) {
    return busy ? (
      <div className={`fair-card is-${tag.toLowerCase()} is-busy`}>
        <div className="fair-head">
          <span className="fair-tag">{tag}</span>
          <b>{name || '계산 중…'}</b>
        </div>
        <p className="sub live" style={{ margin: 0 }}>
          실거래를 훑는 중입니다.
        </p>
      </div>
    ) : null
  }

  const { input, fair, gap } = result

  if (!fair?.fair_price) {
    return (
      <div className={`fair-card is-${tag.toLowerCase()}`}>
        <div className="fair-head">
          <span className="fair-tag">{tag}</span>
          <b>{name}</b>
        </div>
        <p className="empty" style={{ margin: 0 }}>
          {fair?.message ?? '비교 가능한 실거래가 없습니다.'}
        </p>
      </div>
    )
  }

  return (
    <div className={`fair-card is-${tag.toLowerCase()}${busy ? ' is-busy' : ''}`}>
      {/* 접힌 상태에서는 **판정에 필요한 것만** 둔다. 예전에는 큰 숫자 6개(적정시세·
          호가·괴리율·실거래기준·요인기준·단지프리미엄)에 표 2개가 한꺼번에 펼쳐져
          있었는데, '적정 시세'와 '실거래 기준'은 같은 값을 두 번 쓴 것이었다. */}
      {/* 위계: 이 카드가 답해야 할 것은 "싸냐 비싸냐" 하나다. 그래서 괴리율과
          판정이 가장 크고, 근거가 되는 금액은 그다음, 표본·신뢰도는 가장 작다.
          예전에는 호가가 제일 컸는데 호가는 **사용자가 이미 아는 값**이다. */}
      <div className="fair-head">
        <span className="fair-tag">{tag}</span>
        <b>{name}</b>
        <span className="muted small fair-spec">
          {fair.dong ? `${fair.dong}동 · ` : ''}
          {input.exclusive_area}㎡
          {input.floor ? ` · ${input.floor}층` : ''}
        </span>
        <Hint notes={fair.confidence_note ? [fair.confidence_note] : null} tone="warn" />
      </div>

      <div className="fair-answer" data-tone={TONE[gap.verdict]}>
        <span className="fair-gap">
          {gap.pct > 0 ? '+' : ''}
          {gap.pct}%
        </span>
        <span className="fair-verdict">{gap.verdict}</span>
      </div>

      <table className="fair-basis">
        <tbody>
          <tr>
            <td>호가</td>
            <td className="num">{eok(input.asking_price)}</td>
            <td className="num muted">{fmt(input.asking_ppp)}/평</td>
          </tr>
          <tr>
            <td>
              실거래 기준
              <Hint notes={[`${fair.basis} ${fair.sample_count}건 · 신뢰도 ${fair.confidence}`]} />
            </td>
            <td className="num">{eok(fair.fair_price)}</td>
            <td className="num muted">
              {eok(fair.fair_price_low)}~{eok(fair.fair_price_high)}
            </td>
          </tr>
          {result.model && (
            <tr>
              <td>
                요인 기준
                <Hint
                  notes={[
                    '역거리·강남접근성·연식·세대수·노선·자치구만으로 세운 값입니다. 학군·브랜드·재건축 기대는 빠져 있습니다.',
                    result.model.calibration?.applied
                      ? `면적 곡선 교정 ${result.model.calibration.pct}% 적용 (원값 ${eok(result.model.factor_price)}).`
                      : null,
                  ]}
                />
              </td>
              <td className="num">
                {eok(result.model.factor_price_adj ?? result.model.factor_price)}
              </td>
              <td
                className="num"
                data-tone={
                  !result.gap_factor
                    ? 'mid'
                    : result.gap_factor.pct > 3
                      ? 'bad'
                      : result.gap_factor.pct < -3
                        ? 'good'
                        : 'mid'
                }
              >
                {result.gap_factor
                  ? `${result.gap_factor.pct > 0 ? '+' : ''}${result.gap_factor.pct}%`
                  : '—'}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <button className="cmp-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className={`caret${open ? ' open' : ''}`} aria-hidden="true">
          ›
        </span>
        자세히
      </button>

      {open && (
        <div className="fair-detail">
          {/* 요인 분해 — 두 기준이 왜 갈리는지는 여기서 본다. */}
          <FactorPrice
            fair={fair}
            model={result.model}
            gap={gap}
            gapFactor={result.gap_factor}
          />

          {/* 그 동 자체 거래. 단지 전체 기준값과 벌어지면 "이 평형 실거래가 사실상
              다른 동 것 아니냐" 가 눈에 보인다. */}
          {fair.own_dong && (
            <p className="own-dong">
              <b>{fair.dong}동 자체 {fair.own_dong.n}건</b> 기준{' '}
              <b>{eok(fair.own_dong.fair_price)}</b>
              <span className="muted small">
                {' '}({fair.own_dong.oldest_date}~{fair.own_dong.latest_date}) · 위 값은 같은
                평형 {fair.sample_count}건 전체 기준
              </span>
            </p>
          )}

          {/* 누적 호가 — 실거래가 못 잡는 것을 보완한다. */}
          {quotes?.by_dong && Object.keys(quotes.by_dong).length > 0 && (
            <div className="quote-box">
              <div className="quote-head">
                같은 평형 누적 호가{' '}
                <span className="muted small">
                  최근 {quotes.active_days}일 · {quotes.total}건
                </span>
              </div>
              <table className="quote-table">
                <tbody>
                  {Object.entries(quotes.by_dong)
                    .sort((a, b) => a[1].median_ppp - b[1].median_ppp)
                    .map(([dong, v]) => (
                      <tr key={dong} className={dong === fair.dong ? 'is-same-dong' : ''}>
                        <td>{dong === '미상' ? '동 미상' : `${dong}동`}</td>
                        <td className="num">{v.n}건</td>
                        <td className="num">{eok(v.median_price)}</td>
                        <td className="num muted">
                          {v.min_price === v.max_price
                            ? ''
                            : `${eok(v.min_price)}~${eok(v.max_price)}`}
                        </td>
                        <td className="num">{fmt(v.median_ppp)}만원/평</td>
                      </tr>
                    ))}
                </tbody>
              </table>
              <p className="muted small" style={{ margin: '6px 0 0' }}>
                호가는 희망가와 급매가가 섞여 있고 성사 여부를 모릅니다. 실거래를 대체하지
                않고, 거래가 뜸한 동의 선행지표로 견줘 보세요.
              </p>
            </div>
          )}

          <div className="formula">
            <div>
              · 비교 표본 <strong>{fair.basis}</strong> {fair.sample_count}건 · 신뢰도{' '}
              {fair.confidence}
            </div>
            {fair.dong_coverage && (
              <div>
                · 그중 동 공개 {fair.dong_coverage.known}건
                {fair.dong_coverage.same_dong != null && (
                  <>
                    {' '}· <strong>{fair.dong}동 {fair.dong_coverage.same_dong}건</strong>
                  </>
                )}
                {fair.dong_coverage.known < fair.dong_coverage.total && (
                  <span className="muted">
                    {' '}— 국토부는 소유권이전등기 완료분만 동을 공개해 최근 거래일수록 비어 있습니다.
                  </span>
                )}
              </div>
            )}
            <div>
              · 층·동 중립 평당가 <code>{fmt(fair.base_ppp)}만원/평</code> × 층 보정{' '}
              <code>
                {fair.floor_factor.toFixed(3)} ({fair.floor_band},{' '}
                {fair.floor_premium_pct > 0 ? '+' : ''}
                {fair.floor_premium_pct}%)
              </code>
              {fair.dong_known && (
                <>
                  {' '}
                  × 동 보정{' '}
                  <code>
                    {fair.dong_factor.toFixed(3)} ({fair.dong}동,{' '}
                    {fair.dong_premium_pct > 0 ? '+' : ''}
                    {fair.dong_premium_pct}%)
                  </code>
                </>
              )}{' '}
              = <code>{fmt(fair.fair_ppp)}만원/평</code>
            </div>
            {!fair.dong_known && (
              <div className="muted">
                · 동 보정 없음 —{' '}
                {fair.dong
                  ? `${fair.dong}동은 거래가 적어 추정하지 않았습니다.`
                  : '동 정보가 없어 단지 평균 기준입니다. 동을 지정하면 조망·향·소음까지 반영합니다.'}
              </div>
            )}
            <div>
              · {fmt(fair.fair_ppp)}만원/평 × {input.pyeong}평 (전용 {input.exclusive_area}㎡) ={' '}
              <strong>{fmt(fair.fair_price)}만원</strong>
            </div>
            {input.exclusive_ratio && (
              <div>
                · 공급 {input.supply_area}㎡ 기준 전용률 <strong>{input.exclusive_ratio}%</strong>{' '}
                — 공급 평당가로 환산하면{' '}
                {fmt(input.asking_price / (input.supply_area / 3.305785))}만원/평
              </div>
            )}
          </div>

          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th>계약일</th>
                  <th>동</th>
                  <th className="num">전용</th>
                  <th className="num">층</th>
                  <th className="num">거래금액</th>
                  <th className="num">평당가</th>
                  <th className="num">시점 보정</th>
                </tr>
              </thead>
              <tbody>
                {fair.comparables.map((c, i) => (
                  <tr key={i} className={c.dong && c.dong === fair.dong ? 'is-same-dong' : ''}>
                    <td>{c.deal_date}</td>
                    {/* 국토부는 소유권이전등기가 끝난 거래만 동을 공개한다.
                        최근 거래일수록 비어 있는데, 가격을 좌우하는 건 그 최근 거래다. */}
                    <td>{c.dong ? `${c.dong}동` : <span className="muted">미공개</span>}</td>
                    <td className="num">{c.exclusive_area}㎡</td>
                    <td className="num">
                      {c.floor} <span className="badge">{c.floor_band}</span>
                    </td>
                    <td className="num">{fmt(c.deal_amount)}</td>
                    <td className="num">{fmt(c.ppp)}</td>
                    <td className="num" style={{ color: 'var(--text-secondary)' }}>
                      {fmt(c.adjusted_ppp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {onSelect && (
            <button className="ghost" style={{ marginTop: 10 }} onClick={() => onSelect(fair.complex.id)}>
              {fair.complex.name} 단지 상세 보기
            </button>
          )}
        </div>
      )}
    </div>
  )
}
