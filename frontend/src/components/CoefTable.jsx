import { Fragment, useState } from 'react'

import { fmt } from './Charts'
import Hint from './Hint'

// 연속 요인의 단위. 요인이 늘면 여기에 적는다.
const UNIT = {
  walk_min: '1분당',
  gangnam_min: '1분당',
  age: '1년당',
  top_floor: '1층당',
}

/**
 * 계수표 — 44개를 평평하게 늘어놓지 않는다.
 *
 * ## 왜 정리가 필요했나
 *
 * 연속 요인은 제한 3차 스플라인으로 적합하므로 요인 하나가 열 여러 개로 흩어진다.
 * 강남 접근성만 해도 `gangnam_min` + `__nl1` ~ `__nl5` 로 여섯 줄이다. 그런데 그
 * 낱개 계수는 **단독으로 읽을 수 없다** — 기저가 서로 물려 있어 하나만 떼면 뜻이 없다.
 *
 * 그걸 그대로 쏟아 놓으니 표가 44줄이 되고, 정작 읽을 수 있는 값(1분당 몇 %)은
 * 그 안에 묻혔다. 그래서 **요인 하나에 한 줄**로 묶고, 기저는 접어 둔다.
 *
 * 한 줄에 담는 것은 셋이다.
 *   - 읽을 수 있는 해석(`interpretation`) — 계수 자체가 아니라 '1분당 -2.51%'
 *   - **선형성 판정** — 이 요인이 직선인지 아닌지는 형태를 가정하지 않고 검정한 결과다
 *   - 기저 몇 개를 썼는지 — 접힌 것이 몇 줄인지 밝힌다
 */
export default function CoefTable({ fit }) {
  const [openVar, setOpenVar] = useState(null)

  const terms = fit.terms.filter((t) => t.name !== 'const')
  const spline = fit.spline_terms || {}
  const lin = fit.linearity || {}
  const byName = Object.fromEntries(terms.map((t) => [t.name, t]))

  // 스플라인 기저에 속한 이름을 모아 두고, 나머지를 범주형으로 본다.
  const inSpline = new Set(Object.values(spline).flat())
  const groups = Object.entries(spline)
    .map(([varName, names]) => ({
      varName,
      head: byName[names[0]],
      basis: names.slice(1).map((n) => byName[n]).filter(Boolean),
      lin: lin[varName],
    }))
    .filter((g) => g.head)
  const others = terms.filter((t) => !inSpline.has(t.name))

  const verdictTone = (v) => (v === '비선형' ? 'bad' : v ? 'mid' : null)

  /** 범주형은 로그차라 exp(coef)-1 이 곧 '기준 대비 몇 %' 다. */
  const catPct = (c) =>
    c == null ? '—' : `기준 대비 ${(Math.exp(c) - 1) * 100 > 0 ? '+' : ''}${fmt((Math.exp(c) - 1) * 100, 1)}%`

  /** 읽을 수 있는 한 줄. 직선이면 계수에서 바로 환산하고, 굽었으면 곡선으로 넘긴다. */
  const readable = (g) => {
    if (g.head.interpretation && !g.head.interpretation.includes('단독 해석 불가')) {
      return g.head.interpretation
    }
    const c = g.lin?.linear_coef
    if (c == null) return '—'
    // log_households 는 로그 단위라 '1세대당' 이 뜻이 없다. 2배당으로 읽는다.
    if (g.varName === 'log_households') {
      return `세대수 2배당 ${fmt((Math.exp(c * Math.LN2) - 1) * 100, 2)}%`
    }
    // 'age 면 년, 아니면 분' 으로 두었다가 단지 최고층을 넣는 순간 "1분당 1.40%"
    // 가 됐다. 단위는 변수마다 적어 둔다 — 모르는 변수는 '1단위당' 으로 둔다.
    const unit = UNIT[g.varName] || '1단위당'
    return `${unit} ${fmt((Math.exp(c) - 1) * 100, 2)}%`
  }

  return (
    <div className="table-wrap">
      <table className="coef">
        <thead>
          <tr>
            <th>요인</th>
            <th>읽는 법</th>
            <th className="num">계수</th>
            <th className="num">p</th>
            <th>형태</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <Fragment key={g.varName}>
              <tr>
                <td>{g.head.label}</td>
                <td className="muted small">{readable(g)}</td>
                <td className="num">{fmt(g.head.coef, 5)}</td>
                <td className="num">
                  {g.head.p < 0.001 ? '<0.001' : fmt(g.head.p, 3)}
                </td>
                <td>
                  {g.lin?.verdict && (
                    <span className="verdict" data-tone={verdictTone(g.lin.verdict)}>
                      {g.lin.verdict}
                    </span>
                  )}
                  {g.basis.length > 0 && (
                    <button
                      className="linklike coef-more"
                      onClick={() =>
                        setOpenVar(openVar === g.varName ? null : g.varName)
                      }
                    >
                      기저 {g.basis.length}개 {openVar === g.varName ? '접기' : '펼치기'}
                    </button>
                  )}
                  <Hint
                    notes={[
                      '연속 요인은 형태를 미리 정하지 않고 제한 3차 스플라인으로 적합한 뒤, 비선형항을 함께 0으로 두는 Wald 검정으로 직선인지 물었습니다.',
                      '낱개 기저 계수는 단독으로 읽을 수 없습니다 — 서로 물려 있어 하나만 떼면 뜻이 없습니다. 읽을 수 있는 값은 왼쪽의 해석과 시장 분석 탭의 곡선입니다.',
                    ]}
                  />
                </td>
              </tr>
              {openVar === g.varName &&
                g.basis.map((b) => (
                  <tr key={b.name} className="coef-basis">
                    <td>{b.label}</td>
                    <td className="muted small">단독 해석 불가</td>
                    <td className="num">{fmt(b.coef, 5)}</td>
                    <td className="num">{b.p < 0.001 ? '<0.001' : fmt(b.p, 3)}</td>
                    <td />
                  </tr>
                ))}
            </Fragment>
          ))}

          {others.length > 0 && (
            <tr className="coef-sep">
              <td colSpan={5}>
                범주형 — 기준 대비 차이
                <Hint
                  notes={[
                    '노선·자치구처럼 값이 범주인 요인입니다. 기준 범주가 0이고 나머지는 그 대비 차이입니다.',
                  ]}
                />
              </td>
            </tr>
          )}
          {others.map((t) => (
            <tr key={t.name}>
              <td>{t.label}</td>
              <td className="muted small">{t.interpretation || catPct(t.coef)}</td>
              <td className="num">{fmt(t.coef, 5)}</td>
              <td className="num">{t.p < 0.001 ? '<0.001' : fmt(t.p, 3)}</td>
              <td />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
