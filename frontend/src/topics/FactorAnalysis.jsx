/**
 * 거시 분석의 요인 하나 — 지금 위치·방향의 근거·시차별 상관.
 *
 * 원래 `views/RegimeView.jsx` 의 요인 창이었다. 이제 어느 탭에서 열든 주제 창
 * (`TopicModal`)의 '가격과의 관계' 절로 들어간다.
 */
import { zText } from '../components/heat'

const ymText = (ym) => `${ym.slice(0, 4)}.${ym.slice(4)}`

export function FactorDetail({ f }) {
  const m = f.measured
  return (
    <>
      <p className="sub">
        {f.up_means}는 뜻입니다. 지금 {ymText(f.latest.ym)} 값은 {f.latest.value}
        {f.unit} 로 {zText(f.z)}입니다.{' '}
        <b>{f.region}</b> 기준입니다.
      </p>
      <p className="sub">{f.pressure.why}</p>
      <h4>시차별 상관</h4>
      <p className="muted small">
        그림의 두 선이 같이 움직였는지입니다. <b>시차 N개월</b>은 요인 값을 본 달에서
        N개월 지나 시작하는 1년의 가격 변화와 견준 것이고, 0개월은 보고 나서 바로 다음
        1년 — 그림에서 같은 달에 겹친 두 값입니다. 방향(위 판정)은 0개월 값으로 정하고 겹치지 않는 표본과
        부호가 같아야 믿습니다. 시차가 길어지며 부호가 뒤집히는 것은 그 요인이 가격을
        거꾸로 민다는 뜻이 아니라, 1~2년이면 시장 국면이 바뀌어 다음 국면과 겹쳐 보이는
        것에 가깝습니다. 가장 센 시차 하나만 고르지 않습니다 — 여럿 중 최대를 고르면 고른
        값 자체가 우연을 탑니다.
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
        월별 상관의 n 은 {m.n} 이지만 12개월 창이 겹쳐 있어 <b>독립 표본은 해마다 하나,{' '}
        {m.nonoverlap_n}개 남짓</b>입니다. 그래서 매년 12월만 쓴 값을 같이 냅니다.
        {m.agree ? ' 두 값의 부호가 같습니다.' : ' 두 값의 부호가 달라 약하게 봅니다.'}
      </p>
    </>
  )
}
