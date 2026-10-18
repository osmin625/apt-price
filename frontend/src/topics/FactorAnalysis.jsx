/**
 * 거시 분석의 요인 하나 — 지금과 비슷한 자리였던 때와 그 뒤.
 *
 * 시차별 상관 표와 '그 뒤 가격과의 관계' 겹친 그림이 여기 있었다. 2026-10-19 요청으로 걷었다
 * — 요인과 매매지수를 견주는 것은 거시 분석의 '한 그림에' 가 모든 요인을 한 번에 한다.
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
 * 요인 하나만 맞춘 것이라 그때 다른 요인은 전혀 달랐을 수 있다(요인들이 함께 어땠는지는 거시
 * 분석의 '한 그림에' 와 과거 국면 표).
 */
export function FactorThen({ t }) {
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
