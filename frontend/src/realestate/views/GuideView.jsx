import { useEffect, useState } from 'react'

import ChartLink from '../../shared/ChartLink'
import Hint from '../../shared/Hint'
import { ALL_ITEM_IDS, DECISION_VALUES, DECISIONS, PHASES, applies } from '../lib/buyGuide'

/**
 * 집 구하기 — 사기 전 준비부터 입주 후까지 단계별 할 일 목록(2026-11-14 요청)과 그 안의 갈림길(11-15).
 *
 * 다른 탭은 데이터를 보여 주지만 이 탭은 **할 일**을 보여 준다. 그래서 서버를 부르지 않고, 목록은
 * `lib/buyGuide.js` 한 곳에 있다(무엇을 바탕으로 했고 무엇을 일부러 안 적었는지, 갈림길이 어떻게 흐름을
 * 바꾸는지도 거기). 서버가 없으니 정적 사이트에도 그대로 실린다.
 *
 * ## 갈림길 — 고른 답이 흐름을 바꾼다
 *
 * 정해야 하는 것(목적·지금 집·대출·매물 유형·세입자 …)은 목록 안에서 답을 고르는 칸이다. 고르면 그 답의
 * '알아 둘 것' 이 그 자리에 펼쳐지고, 그 답에 매인 항목·단계가 뒤에 나타난다. 고르지 않은 갈림길에 매인
 * 것은 감추고, 감춘 단계 자리에는 '무엇을 정하면 나타나는지' 를 남긴다 — 통째로 지우면 흐름에 무엇이
 * 빠졌는지 모른다. 머리의 '내 선택' 줄은 흐름 순서대로 갈림길을 늘어놓아 남은 결정으로 바로 간다.
 *
 * 진척은 **지금 답에 해당하는 것만** 센다. 해당 없는 항목까지 세면 끝까지 해도 100% 가 안 된다.
 * 갈림길도 할 일 하나로 센다 — 고르는 것이 그 단계의 일이다.
 *
 * ## 체크와 답은 이 브라우저에만 남긴다
 *
 * localStorage 에 둔다 — 한 사람이 자기 진척을 보는 용도라 서버에 쓸 까닭이 없고, 정적 사이트에는 쓸
 * 서버도 없다. 사생활 창·저장 차단에서는 읽기·쓰기가 예외를 던지므로 전부 try 로 감싸고, 실패하면
 * 새로고침까지만 살아 있을 뿐 화면은 그대로 돈다. 답을 바꿔 감춰진 항목의 체크는 지우지 않는다 — 답을
 * 되돌리면 그대로 돌아온다.
 *
 * ## 카드는 단계 하나에 하나
 *
 * 시기 하나를 카드 하나로 두면 '사기 전' 이 마흔 줄 가까워 한 칸이 화면 몇 장이 된다(conventions.md
 * '내용이 칸보다 크면 창으로'). 단계마다 카드를 두고 시기는 카드 묶음의 머리로만 둔다.
 *
 * CSS 는 `buy-*` 다. `guide-*` 는 가격 분석의 '읽는 법' 이 먼저 쓰고 있다.
 */

const STORE_KEY = 'buy-guide-checked-v1'
const CHOICE_KEY = 'buy-guide-choices-v1'

function load(key, fallback, clean) {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? clean(JSON.parse(raw)) : fallback
  } catch {
    return fallback
  }
}

function save(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 저장이 막힌 브라우저 — 이번 방문 동안만 기억한다.
  }
}

// 목록에서 빠진 항목·답은 버린다 — 남겨 두면 진척 수가 항목 수를 넘는다.
const cleanChecked = (ids) => {
  const live = new Set(ALL_ITEM_IDS)
  return new Set(Array.isArray(ids) ? ids.filter((id) => live.has(id)) : [])
}
const cleanChoices = (obj) => {
  const out = {}
  for (const [k, vs] of Object.entries(obj || {})) {
    const ok = DECISION_VALUES[k]
    const keep = ok && Array.isArray(vs) ? vs.filter((v) => ok.has(v)) : []
    if (keep.length) out[k] = keep
  }
  return out
}

const isDecision = (it) => it.kind === 'decision'
const decisionOf = Object.fromEntries(DECISIONS.map((d) => [d.id, d]))

/** `when` 가운데 아직 안 고른 갈림길 — 감춘 자리에 '무엇을 정하면 나타나나' 를 적는 데 쓴다. */
const pending = (when, choices) => Object.keys(when || {}).filter((k) => !(choices[k] || []).length)

function DecisionBlock({ d, chosen, onPick, compact }) {
  const picked = chosen || []
  if (compact && picked.length) {
    return (
      <li className="buy-decision is-compact" id={`buy-dec-${d.id}`}>
        <span className="buy-q-mark" aria-hidden="true">◆</span>
        <span className="buy-body">
          <span className="buy-q">{d.q}</span>{' '}
          <strong>{d.options.filter((o) => picked.includes(o.v)).map((o) => o.label).join(' · ')}</strong>
        </span>
      </li>
    )
  }
  const shown = d.options.filter((o) => picked.includes(o.v) && o.info?.length)
  return (
    <li className={`buy-decision${picked.length ? ' is-answered' : ''}`} id={`buy-dec-${d.id}`}>
      <span className="buy-q-mark" aria-hidden="true">◆</span>
      <div className="buy-body">
        <div className="buy-q">
          {d.q}
          {d.multi && <span className="buy-multi">여러 개</span>}
          {d.hint && <Hint wide notes={d.hint} />}
        </div>
        <div className="buy-options" role={d.multi ? 'group' : 'radiogroup'} aria-label={d.q}>
          {d.options.map((o) => {
            const on = picked.includes(o.v)
            return (
              <button
                key={o.v}
                type="button"
                role={d.multi ? 'checkbox' : 'radio'}
                aria-checked={on}
                className={`buy-option${on ? ' is-on' : ''}`}
                onClick={() => onPick(d, o.v)}
              >
                <span className="buy-option-label">{o.label}</span>
                {o.sub && <span className="buy-option-sub">{o.sub}</span>}
              </button>
            )
          })}
        </div>
        {shown.length > 0 && (
          <div className="buy-info">
            {shown.map((o) => (
              <div key={o.v}>
                <div className="buy-info-title">{shown.length > 1 ? `${o.label} — 알아 둘 것` : '알아 둘 것'}</div>
                <ul>
                  {o.info.map((x, i) => {
                    const line = typeof x === 'string' ? { t: x } : x
                    return (
                      <li key={i}>
                        {line.t}
                        {line.d && <Hint wide notes={line.d} />}
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </li>
  )
}

function Waiting({ keys, label }) {
  return (
    <p className="buy-waiting">
      먼저 정할 것:{' '}
      {keys.map((k, i) => (
        <span key={k}>
          {i > 0 && ', '}
          <a href={`#buy-dec-${k}`} onClick={(e) => { e.preventDefault(); jumpTo(`buy-dec-${k}`) }}>
            {decisionOf[k]?.short}
          </a>
        </span>
      ))}
      {' — '}
      {label}
    </p>
  )
}

const jumpTo = (domId) => document.getElementById(domId)?.scrollIntoView({ behavior: 'smooth', block: 'center' })

export default function GuideView() {
  const [checked, setChecked] = useState(() => load(STORE_KEY, new Set(), cleanChecked))
  const [choices, setChoices] = useState(() => load(CHOICE_KEY, {}, cleanChoices))
  const [hideDone, setHideDone] = useState(false)

  useEffect(() => save(STORE_KEY, [...checked]), [checked])
  useEffect(() => save(CHOICE_KEY, choices), [choices])

  const toggle = (id) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  // 하나만 고르는 갈림길은 같은 답을 다시 누르면 고르기를 취소한다 — 잘못 누른 것을 되돌릴 길.
  const pick = (d, v) =>
    setChoices((prev) => {
      const cur = prev[d.id] || []
      const only = new Set(d.options.filter((o) => o.only).map((o) => o.v))
      let next
      if (!d.multi) next = cur[0] === v ? [] : [v]
      else if (cur.includes(v)) next = cur.filter((x) => x !== v)
      else next = only.has(v) ? [v] : [...cur.filter((x) => !only.has(x)), v]
      const out = { ...prev }
      if (next.length) out[d.id] = next
      else delete out[d.id]
      return out
    })

  const reset = () => {
    if ((checked.size || Object.keys(choices).length) && window.confirm('체크와 고른 답을 모두 지울까요?')) {
      setChecked(new Set())
      setChoices({})
    }
  }

  // 지금 답에 해당하는 것만 — 시기·단계·항목의 when 을 모두 통과한 것.
  const live = (p, s, it) => applies(p.when, choices) && applies(s.when, choices) && applies(it.when, choices)
  const tally = (list) => {
    let n = 0
    let total = 0
    for (const [p, s, it] of list) {
      if (!live(p, s, it)) continue
      total += 1
      if (isDecision(it) ? (choices[it.id] || []).length : checked.has(it.id)) n += 1
    }
    return [n, total]
  }
  const triples = (p, steps = p.steps) => steps.flatMap((s) => s.items.map((it) => [p, s, it]))
  const [done, total] = tally(PHASES.flatMap((p) => triples(p)))

  const liveDecisions = DECISIONS.filter(
    (d) => applies(d.phaseWhen, choices) && applies(d.stepWhen, choices) && applies(d.when, choices),
  )
  const anything = checked.size > 0 || Object.keys(choices).length > 0
  let stepNo = 0

  return (
    <>
      <div className="card buy-head">
        <h2>
          집 구하기
          <Hint
            notes={[
              '아파트를 사기 전 준비부터 계약·잔금·이사·입주 후까지 할 일을 순서대로 모았습니다.',
              '◆ 는 정해야 하는 갈림길입니다. 답을 고르면 그 답에서 알아 둘 것이 펼쳐지고, 그 답에 맞는 할 일이 뒤 단계에 나타납니다.',
              '진척은 지금 고른 답에 해당하는 것만 셉니다.',
              '체크와 답은 이 브라우저에만 저장됩니다. 다른 기기나 사생활 창에서는 보이지 않습니다.',
              '대출 한도·세율·규제 지역처럼 정책으로 바뀌는 숫자는 적지 않았습니다. 기한(30일·60일·14일)도 법이 바뀌면 달라지니 은행·관할 관청·법무사에게 확인하세요.',
            ]}
          />
          <ChartLink id="overview" />
        </h2>
        <div className="buy-progress" aria-label="전체 진척">
          <div className="buy-bar">
            <i style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
          </div>
          <span className="buy-count">
            {done} / {total}
          </span>
        </div>
        <div className="buy-choices" aria-label="내 선택">
          <span className="buy-choices-label">내 선택</span>
          {liveDecisions.map((d) => {
            const picked = choices[d.id] || []
            const labels = d.options.filter((o) => picked.includes(o.v)).map((o) => o.label)
            return (
              <button
                key={d.id}
                type="button"
                className={`buy-chip${labels.length ? '' : ' is-open'}`}
                onClick={() => jumpTo(`buy-dec-${d.id}`)}
              >
                {d.short} <b>{labels.length ? labels.join('·') : '?'}</b>
              </button>
            )
          })}
        </div>
        <ol className="buy-phases">
          {PHASES.map((p, i) => {
            const [n, t] = tally(triples(p))
            const off = !applies(p.when, choices)
            return (
              <li key={p.id}>
                <button
                  type="button"
                  className={`buy-phase${t && n === t ? ' is-done' : ''}${off ? ' is-off' : ''}`}
                  onClick={() => jumpTo(`buy-phase-${p.id}`)}
                >
                  <span className="buy-phase-no">{i + 1}</span>
                  {p.title}
                  <span className="buy-phase-count">{off ? '—' : `${n}/${t}`}</span>
                </button>
              </li>
            )
          })}
        </ol>
        <div className="buy-tools">
          <label className="buy-toggle">
            <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
            끝낸 것 접기
          </label>
          <button type="button" className="ghost" onClick={reset} disabled={!anything}>
            모두 지우기
          </button>
        </div>
      </div>

      {PHASES.map((p, pi) => {
        const phaseOn = applies(p.when, choices)
        const phaseWait = pending(p.when, choices)
        return (
          <section key={p.id} className="buy-section" id={`buy-phase-${p.id}`}>
            <h3 className="buy-section-title">
              <span className="buy-phase-no">{pi + 1}</span>
              {p.title}
            </h3>
            {!phaseOn ? (
              phaseWait.length ? (
                <Waiting keys={phaseWait} label="정하면 이 시기의 할 일이 나타납니다." />
              ) : (
                <p className="buy-waiting">고른 답에서는 이 시기에 할 일이 없습니다.</p>
              )
            ) : (
              <div className="buy-grid">
                {p.steps.map((s) => {
                  if (!applies(s.when, choices)) {
                    const wait = pending(s.when, choices)
                    // 답이 정해졌는데 해당 없는 단계는 자리도 남기지 않는다. 아직 모를 때만 무엇을 정하면 되는지 적는다.
                    if (!wait.length) return null
                    return (
                      <div key={s.id} className="card buy-step is-waiting">
                        <h2>{s.title}</h2>
                        <Waiting keys={wait} label="정하면 나타납니다." />
                      </div>
                    )
                  }
                  stepNo += 1
                  const [n, t] = tally(triples(p, [s]))
                  const items = s.items.filter((it) => applies(it.when, choices))
                  const shown = hideDone ? items.filter((it) => isDecision(it) || !checked.has(it.id)) : items
                  return (
                    <div key={s.id} className={`card buy-step${n === t ? ' is-done' : ''}`}>
                      <h2>
                        <span className="buy-step-no">{stepNo}.</span> {s.title}
                        {s.hint && <Hint notes={s.hint} />}
                        <ChartLink id={s.id} />
                        <span className="buy-step-count">
                          {n}/{t}
                        </span>
                      </h2>
                      <ul className="buy-items">
                        {shown.map((it) =>
                          isDecision(it) ? (
                            <DecisionBlock
                              key={it.id}
                              d={it}
                              chosen={choices[it.id]}
                              onPick={pick}
                              compact={hideDone}
                            />
                          ) : (
                            // 배지·ⓘ·탭 링크는 label 밖에 둔다 — 안에 두면 ⓘ 를 누를 때 체크까지 바뀐다.
                            <li key={it.id} className={checked.has(it.id) ? 'is-checked' : ''}>
                              <input
                                id={`buy-${it.id}`}
                                type="checkbox"
                                checked={checked.has(it.id)}
                                onChange={() => toggle(it.id)}
                              />
                              <span className="buy-body">
                                <label htmlFor={`buy-${it.id}`} className="buy-text">
                                  {it.t}
                                </label>
                                {it.d && <Hint wide notes={it.d} />}
                                {it.go && (
                                  <a className="buy-go" href={`#${it.go[0]}`}>
                                    {it.go[1]} <span aria-hidden="true">→</span>
                                  </a>
                                )}
                              </span>
                            </li>
                          ),
                        )}
                      </ul>
                      {shown.length === 0 && <p className="muted small buy-all-done">이 단계는 모두 끝냈습니다.</p>}
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )
      })}
    </>
  )
}
