import { useEffect, useRef, useState } from 'react'

import { api, STATIC_MODE } from '../api'

/**
 * 매물 줄의 비고. "130동 민간임대" 처럼 사람이 적어 두는 메모.
 *
 * ## 유닛에 붙는다
 *
 * 키는 `quotes.unit_key()` 와 같은 (단지·동·평형·층)이다. 호가 하나(`quote_id`)에
 * 붙이면 **그 집이 값을 바꿔 다시 올라오는 순간 메모가 사라진다** — 적어 둔 사람은
 * 아무 경고도 못 받는다. 값은 바뀌어도 '130동이 민간임대' 라는 사실은 그대로다.
 *
 * ## 저장은 포커스를 뗄 때만
 *
 * 글자마다 보내면 순위표가 수십 줄이라 요청이 쏟아진다. 디바운스로 줄일 수도 있지만,
 * 그러면 "저장됐나?" 를 알 수 없는 구간이 생긴다. 다 쓰고 벗어날 때 한 번 보내고
 * 그때 상태를 보여 주는 쪽이 분명하다. Enter 로도 저장하고 Esc 로 되돌린다.
 *
 * 실패하면 **입력한 글자를 지우지 않는다.** 되돌려 버리면 쓴 사람이 쓴 것을 잃는다.
 */
export default function NoteCell({ item, onSaved }) {
  const [text, setText] = useState(item.note || '')
  const [state, setState] = useState('idle') // idle | saving | saved | error
  const saved = useRef(item.note || '')
  const timer = useRef(null)

  const unitId = JSON.stringify(item.note_key)

  // 기간·기준을 바꾸면 목록이 새로 오므로 서버 값에 맞춘다. 단, 사용자가 고쳐
  // 둔 것이 있으면 덮지 않는다 — 입력 중인 글자를 지우는 것만큼 나쁜 것이 없다.
  //
  // 다만 **줄이 바뀌었으면 무조건 맞춘다.** React 가 같은 자리의 컴포넌트를 다른
  // 행에 재사용할 수 있는데, 그때까지 입력 중이던 글자를 지키면 남의 줄에 남의
  // 메모가 떠 있게 된다. 못 지키는 것보다 엉뚱한 줄에 붙는 쪽이 훨씬 나쁘다.
  const lastUnit = useRef(unitId)
  useEffect(() => {
    const incoming = item.note || ''
    const moved = lastUnit.current !== unitId
    if (moved || (incoming !== saved.current && text === saved.current)) {
      setText(incoming)
      saved.current = incoming
      lastUnit.current = unitId
      setState('idle')
    }
  }, [item.note, unitId])

  useEffect(() => () => clearTimeout(timer.current), [])

  /* 민간임대 같은 표시는 **단지 상세에서 동에 붙인 것**이 파생돼 온다. 비고에
     글자로 써 넣지 않는 이유: 써 넣으면 표시를 끈 뒤에도 남고, 사용자가 직접 쓴
     메모와 구분되지 않는다. 배지로 두면 표시를 끄는 순간 같이 사라진다. */
  const auto = item.note_auto || []

  if (STATIC_MODE) {
    // 정적 사이트에서는 쓸 수 없다. 눌리는데 실패하는 칸을 두지 않는다.
    if (!auto.length && !item.note) return <span className="muted">—</span>
    return (
      <span className="note-ro">
        {auto.map((t) => (
          <b className="note-tag" key={t}>
            {t}
          </b>
        ))}
        {item.note}
      </span>
    )
  }

  const commit = async () => {
    const next = text.trim()
    if (next === saved.current) return
    setState('saving')
    try {
      await api.putQuoteNote({ ...item.note_key, text: next })
      saved.current = next
      setText(next)
      setState('saved')
      onSaved?.(item.note_key, next)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setState('idle'), 1500)
    } catch (e) {
      setState('error')
    }
  }

  return (
    <span className={`note-cell is-${state}`}>
      {auto.map((t) => (
        <b className="note-tag" key={t} title="단지 상세에서 이 동을 민간임대로 표시했습니다">
          {t}
        </b>
      ))}
      <input
        value={text}
        placeholder="비고"
        maxLength={300}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            setText(saved.current)
            e.currentTarget.blur()
          }
        }}
        aria-label="비고"
      />
      {state === 'saving' && <i className="note-mark" aria-hidden="true">…</i>}
      {state === 'saved' && <i className="note-mark ok" aria-hidden="true">✓</i>}
      {state === 'error' && (
        <i className="note-mark bad" title="저장하지 못했습니다. 다시 눌러 보세요.">!</i>
      )}
    </span>
  )
}
