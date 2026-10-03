import { eok, fmt } from './Charts'

/**
 * 요인별 적정가 — 매물 **하나**를 요인으로 분해한다.
 *
 * 기존 '요인별 기여' 표는 A−B 상대 차이만 보여 줘서 두 가지가 안 됐다.
 * 같은 단지 두 매물을 넣으면 단지 요인이 전부 0% 라 표가 텅 비고, 한쪽만
 * 넣으면 아예 나오지 않았다. 여기서는 **절대값**으로 낸다 — 각 요인이 이
 * 매물의 값을 어디로 끌고 가는지, 그래서 얼마인지.
 *
 * 세 값이 다른 질문에 답한다.
 *
 * - **실거래 기준**: 그 단지 같은 평형이 실제로 얼마에 팔리나. 학군·브랜드·
 *   재건축 기대가 이미 값에 들어 있다.
 * - **요인 기준**: 역거리·강남접근성·연식·세대수·노선·자치구만으로 얼마여야 하나.
 *   측정하지 않은 것은 빠져 있다.
 * - 둘의 차이가 그 단지에 붙어 있는 **고유 프리미엄**이다.
 */
export default function FactorPrice({ fair, model, gap, gapFactor }) {
  if (!model) return null
  const adj = model.factor_price_adj ?? model.factor_price
  const cal = model.calibration

  return (
    <div className="factor-price">
      {/* 금액 세 개는 카드 위에 이미 있다. 여기서는 **왜 갈리는지**만 본다. */}
      <p className="fp-lead">
        요인 기준 <b>{eok(adj)}</b> — 실거래 기준과의 차이{' '}
        <b>
          {model.complex_premium_pct > 0 ? '+' : ''}
          {fmt(model.complex_premium_pct, 1)}%
        </b>
        <span className="muted small"> 가 이 단지에 붙어 있는 고유 프리미엄입니다.</span>
      </p>

      <table className="fp-table">
        <thead>
          <tr>
            <th>요인</th>
            <th>이 매물</th>
            <th className="num">기준 대비</th>
          </tr>
        </thead>
        <tbody>
          <tr className="fp-group">
            <td colSpan={3}>단지 — 어디에 있는 아파트인가</td>
          </tr>
          {model.complex_parts.map((f) => (
            <tr key={f.key}>
              <td>{f.label}</td>
              <td>{f.value}</td>
              <td className={`num ${f.pct > 0 ? 'tone-pos' : 'tone-neg'}`}>
                {f.pct > 0 ? '+' : ''}
                {fmt(f.pct, 1)}%
              </td>
            </tr>
          ))}
          <tr className="fp-group">
            <td colSpan={3}>유닛 — 그 안에서 어느 집인가</td>
          </tr>
          {model.unit_parts.map((f) => (
            <tr key={f.key}>
              <td colSpan={2}>{f.label}</td>
              <td className={`num ${f.pct > 0 ? 'tone-pos' : 'tone-neg'}`}>
                {f.pct > 0 ? '+' : ''}
                {fmt(f.pct, 1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="muted small">
        기준은 <b>{model.reference}</b>. 단지 요인은 그 기준 단지 대비, 유닛 요인은 전용
        84㎡·중층 대비입니다.
      </p>
      {cal?.applied && (
        <p className="muted small">
          면적 곡선 교정 <b>{cal.pct > 0 ? '+' : ''}{cal.pct}%</b> 적용 (원값{' '}
          {eok(model.factor_price)}). {cal.note}
        </p>
      )}
      {cal && !cal.applied && <p className="paste-warn">{cal.reason}</p>}
    </div>
  )
}
