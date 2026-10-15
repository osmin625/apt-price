/**
 * 거시 분석의 요인 하나 — 지금 위치·방향의 근거·시차별 상관.
 *
 * 원래 `views/RegimeView.jsx` 의 요인 창이었다. 이제 어느 탭에서 열든 주제 창
 * (`TopicModal`)의 '가격과의 관계' 절로 들어간다.
 */

const ymText = (ym) => `${ym.slice(0, 4)}.${ym.slice(4)}`

export function FactorDetail({ f }) {
  const m = f.measured
  return (
    <>
      <p className="sub">
        {f.up_means}는 뜻입니다. 지금 {ymText(f.latest.ym)} 값은 {f.latest.value}
        {f.unit} 로 자기 역사의 {Math.round(f.percentile * 100)}% 지점입니다.{' '}
        <b>{f.region}</b> 기준입니다.
      </p>
      <p className="sub">{f.pressure.why}</p>
      <h4>시차별 상관</h4>
      <p className="muted small">
        x 를 한 시점에 놓고, 그 뒤 12개월 가격 변화와의 상관입니다. 가장 센 시차 하나만
        고르지 않습니다 — 25개 중 최대를 고르면 고른 값 자체가 우연을 탑니다.
      </p>
      <table>
        <thead>
          <tr>
            {m.profile.map((p) => (
              <th key={p.lag}>{p.lag}개월</th>
            ))}
            <th>겹치지 않는 표본</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            {m.profile.map((p) => (
              <td key={p.lag}>{p.r == null ? '—' : p.r > 0 ? `+${p.r}` : p.r}</td>
            ))}
            <td>
              {m.nonoverlap_r == null
                ? '—'
                : `${m.nonoverlap_r > 0 ? '+' : ''}${m.nonoverlap_r} (n=${m.nonoverlap_n})`}
            </td>
          </tr>
        </tbody>
      </table>
      <p className="muted small">
        월별 상관의 n 은 {m.n} 이지만 12개월 창이 겹쳐 있어 <b>독립 표본은 스무 개
        남짓</b>입니다. 그래서 매년 12월만 쓴 값을 같이 냅니다.
        {m.agree ? ' 두 값의 부호가 같습니다.' : ' 두 값의 부호가 달라 약하게 봅니다.'}
      </p>
    </>
  )
}
