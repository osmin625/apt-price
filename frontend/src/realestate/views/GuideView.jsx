import { useEffect, useMemo, useState } from 'react'

import ChartLink from '../../shared/ChartLink'
import Hint from '../../shared/Hint'
import { ALL_ITEM_IDS, PHASES } from '../lib/buyGuide'

/**
 * 집 구하기 — 사기 전 준비부터 입주 후까지 단계별 할 일 목록(2026-11-14 요청).
 *
 * 다른 탭은 데이터를 보여 주지만 이 탭은 **할 일**을 보여 준다. 그래서 서버를 부르지 않고, 목록은
 * `lib/buyGuide.js` 한 곳에 있다(무엇을 바탕으로 했고 무엇을 일부러 안 적었는지도 거기). 서버가 없으니
 * 정적 사이트에도 그대로 실린다.
 *
 * ## 체크는 이 브라우저에만 남긴다
 *
 * 체크 표시는 localStorage 에 둔다 — 한 사람이 자기 진척을 보는 용도라 서버에 쓸 까닭이 없고, 정적
 * 사이트에는 쓸 서버도 없다. 사생활 창·저장 차단에서는 읽기·쓰기가 예외를 던지므로 전부 try 로 감싸고,
 * 실패하면 체크가 새로고침까지만 살아 있을 뿐 화면은 그대로 돈다.
 *
 * ## 카드는 단계 하나에 하나
 *
 * 처음에는 시기(사기 전·계약·잔금·이사·입주 후) 하나를 카드 하나로 두려 했는데, '사기 전' 만 항목이
 * 마흔 개 가까워 한 칸이 화면 몇 장 길이가 됐다(conventions.md '내용이 칸보다 크면 창으로'). 단계마다
 * 카드를 두고 시기는 카드 묶음의 머리로만 둔다. 카드마다 링크(`#buy-guide/<단계>`)가 있어 '잔금일' 처럼
 * 지금 필요한 단계를 바로 열 수 있다.
 *
 * ## 설명은 항목 옆 ⓘ
 *
 * 항목 하나는 한 줄이다. 왜·어디서·무엇을 조심하나는 그 항목의 ⓘ 에 접는다 — 펼쳐 두면 할 일 목록이
 * 설명서가 되어 '다음에 뭘 하지' 가 안 보인다.
 */

const STORE_KEY = 'buy-guide-checked-v1'

function loadChecked() {
  try {
    const raw = window.localStorage.getItem(STORE_KEY)
    const ids = raw ? JSON.parse(raw) : []
    // 목록에서 빠진 항목의 체크는 버린다 — 남겨 두면 진척 수가 항목 수를 넘는다.
    const live = new Set(ALL_ITEM_IDS)
    return new Set(Array.isArray(ids) ? ids.filter((id) => live.has(id)) : [])
  } catch {
    return new Set()
  }
}

function saveChecked(set) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify([...set]))
  } catch {
    // 저장이 막힌 브라우저 — 이번 방문 동안만 기억한다.
  }
}

const count = (items, checked) => items.filter((i) => checked.has(i.id)).length

export default function GuideView() {
  const [checked, setChecked] = useState(loadChecked)
  const [hideDone, setHideDone] = useState(false)

  useEffect(() => saveChecked(checked), [checked])

  const toggle = (id) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const reset = () => {
    if (checked.size && window.confirm('체크한 항목을 모두 지울까요?')) setChecked(new Set())
  }

  const phaseItems = useMemo(
    () => Object.fromEntries(PHASES.map((p) => [p.id, p.steps.flatMap((s) => s.items)])),
    [],
  )
  const total = ALL_ITEM_IDS.length
  const done = checked.size
  // 단계 번호는 시기를 건너 이어 센다 — '7. 계약 전 확인' 처럼 전체에서 몇 번째인지 보이게.
  let stepNo = 0

  const jump = (phaseId) =>
    document.getElementById(`buy-phase-${phaseId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <>
      <div className="card buy-head">
        <h2>
          집 구하기
          <Hint
            notes={[
              '아파트를 사기 전 준비부터 계약·잔금·이사·입주 후까지 할 일을 순서대로 모았습니다.',
              '체크는 이 브라우저에만 저장됩니다. 다른 기기나 사생활 창에서는 보이지 않습니다.',
              '대출 한도·세율·규제 지역처럼 정책으로 바뀌는 숫자는 적지 않았습니다. 기한(30일·60일·14일)도 법이 바뀌면 달라지니 은행·관할 관청·법무사에게 확인하세요.',
              '해당할 때만 할 일은 이름 옆에 조건을 붙였습니다.',
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
        <ol className="buy-phases">
          {PHASES.map((p, i) => {
            const items = phaseItems[p.id]
            const n = count(items, checked)
            return (
              <li key={p.id}>
                <button
                  type="button"
                  className={`buy-phase${n === items.length ? ' is-done' : ''}`}
                  onClick={() => jump(p.id)}
                >
                  <span className="buy-phase-no">{i + 1}</span>
                  {p.title}
                  <span className="buy-phase-count">
                    {n}/{items.length}
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
        <div className="buy-tools">
          <label className="buy-toggle">
            <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
            끝낸 항목 숨기기
          </label>
          <button type="button" className="ghost" onClick={reset} disabled={!done}>
            체크 지우기
          </button>
        </div>
      </div>

      {PHASES.map((p, pi) => (
        <section key={p.id} className="buy-section" id={`buy-phase-${p.id}`}>
          <h3 className="buy-section-title">
            <span className="buy-phase-no">{pi + 1}</span>
            {p.title}
          </h3>
          <div className="buy-grid">
            {p.steps.map((s) => {
              stepNo += 1
              const n = count(s.items, checked)
              const shown = hideDone ? s.items.filter((it) => !checked.has(it.id)) : s.items
              return (
                <div key={s.id} className={`card buy-step${n === s.items.length ? ' is-done' : ''}`}>
                  <h2>
                    <span className="buy-step-no">{stepNo}.</span> {s.title}
                    {s.tag && <span className="badge buy-tag">{s.tag}</span>}
                    {s.hint && <Hint notes={s.hint} />}
                    <ChartLink id={s.id} />
                    <span className="buy-step-count">
                      {n}/{s.items.length}
                    </span>
                  </h2>
                  {shown.length === 0 ? (
                    <p className="muted small buy-all-done">이 단계는 모두 끝냈습니다.</p>
                  ) : (
                    <ul className="buy-items">
                      {shown.map((it) => (
                        // 배지·ⓘ·탭 링크는 label 밖에 둔다 — 안에 두면 ⓘ 를 누를 때 체크까지 바뀐다.
                        // 그렇다고 줄 끝에 따로 두면 글이 길 때 ⓘ 만 다음 줄로 떨어져서, 글과 같은
                        // 흐름(inline)에 잇고 체크 칸만 왼쪽 열로 뺐다.
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
                            {it.tag && <span className="badge buy-tag">{it.tag}</span>}
                            {it.d && <Hint wide notes={it.d} />}
                            {it.go && (
                              <a className="buy-go" href={`#${it.go[0]}`}>
                                {it.go[1]} <span aria-hidden="true">→</span>
                              </a>
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      ))}
    </>
  )
}
