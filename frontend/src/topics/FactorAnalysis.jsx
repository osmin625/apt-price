/**
 * 거시 분석의 요인 하나 — 지금 위치 · 지금과 비슷했던 때 그 뒤 · 시차별 상관.
 *
 * 원래 `views/RegimeView.jsx` 의 요인 창이었다. 이제 어느 탭에서 열든 주제 창
 * (`TopicModal`)의 '가격과의 관계' 절로 들어간다.
 */
import { fmt } from '../components/Charts'
import { zText } from '../components/heat'
import Hint from '../components/Hint'

const ymText = (ym) => `${ym.slice(0, 4)}.${ym.slice(4)}`

const sgn = (v) => (v > 0 ? '+' : '')
const pct = (v) => (v == null ? '—' : `${sgn(v)}${fmt(v, 1)}%`)
const tone = (v) => (v == null ? 'muted' : v >= 0 ? 'tone-pos' : 'tone-neg')
const period = (e) => (e.from === e.to ? ymText(e.from) : `${ymText(e.from)}~${ymText(e.to)}`)

/**
 * 그 요인이 **지금과 비슷한 자리**였던 시기와 그 뒤 — 시기로 세고 기저율과 나란히.
 * 요인 하나만 맞춘 것이라 그때 다른 요인은 전혀 달랐을 수 있다(요인 전부로 본 것은 거시
 * 분석의 '비슷했던 시기').
 */
function FactorThen({ t }) {
  if (!t) return null
  const b = t.base
  return (
    <>
      <h4>
        지금과 비슷한 자리였던 때{' '}
        <span className="muted small">
          {t.summary.episodes}번 · 그 뒤 1년 오름 {t.summary.up}/{t.summary.episodes} · 기저 {b.up_pct}%
        </span>
        <Hint
          wide
          notes={[
            `지금 위치(${zText(t.z_now)})에서 평소 폭의 ±${t.band}배 안에 있던 달을 모아, 12개월 안에 이어지는 달을 한 시기로 묶었습니다. 지금과 이어진 최근은 뺐습니다.`,
            `기저: ${ymText(b.from)}~${ymText(b.to)} 의 모든 달 가운데 그 뒤 1년이 오른 비율 ${b.up_pct}%, 중위 ${pct(b.median)}. 비슷했던 때의 결과는 이것과 견줘 읽습니다.`,
            '시기마다의 값은 그 시기 달들의 중위입니다. 한두 번 있었던 일은 경향이 아니라 일화입니다.',
          ]}
        />
      </h4>
      {t.episodes.length === 0 ? (
        <p className="empty">지금처럼 이 자리였던 시기가 없습니다.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>시기</th>
                <th className="num">개월</th>
                <th>그때 위치</th>
                <th className="num">6개월 뒤</th>
                <th className="num">1년 뒤</th>
                <th className="num">2년 뒤</th>
              </tr>
            </thead>
            <tbody>
              {t.episodes.map((e) => (
                <tr key={e.from}>
                  <td>{period(e)}</td>
                  <td className="num">{e.months}</td>
                  <td className="muted">{zText(e.z)}</td>
                  {['6', '12', '24'].map((h) => (
                    <td key={h} className={`num ${tone(e.fwd[h])}`}>{pct(e.fwd[h])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export function FactorDetail({ f }) {
  const m = f.measured
  return (
    <>
      <p className="sub">
        {f.up_means}는 뜻입니다. 지금 {ymText(f.latest.ym)} 값은 {f.latest.value}
        {f.unit} 로 {zText(f.z)}입니다.{' '}
        <b>{f.region}</b> 기준입니다.
      </p>
      <FactorThen t={f.then} />
      <h4>시차별 상관</h4>
      <p className="muted small"><Hint pill wide label="설명">
        그림의 두 선이 같이 움직였는지입니다. <b>시차 N개월</b>은 요인 값을 본 달에서
        N개월 지나 시작하는 1년의 가격 변화와 견준 것이고, 0개월은 보고 나서 바로 다음
        1년 — 그림에서 같은 달에 겹친 두 값입니다. 겹치지 않는 표본과 부호가 같아야 믿습니다.
        시차가 길어지며 부호가 뒤집히는 것은 그 요인이 가격을
        거꾸로 민다는 뜻이 아니라, 1~2년이면 시장 국면이 바뀌어 다음 국면과 겹쳐 보이는
        것에 가깝습니다. 가장 센 시차 하나만 고르지 않습니다 — 여럿 중 최대를 고르면 고른
        값 자체가 우연을 탑니다.
      </Hint></p>
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
      <p className="muted small"><Hint pill wide label="설명">
        월별 상관의 n 은 {m.n} 이지만 12개월 창이 겹쳐 있어 <b>독립 표본은 해마다 하나,{' '}
        {m.nonoverlap_n}개 남짓</b>입니다. 그래서 매년 12월만 쓴 값을 같이 냅니다.
        {m.agree ? ' 두 값의 부호가 같습니다.' : ' 두 값의 부호가 달라 약하게 봅니다.'}
      </Hint></p>
    </>
  )
}
