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
// title 속성의 줄바꿈. JSX 템플릿 리터럴에 실제 줄바꿈을 넣으면 들여쓰기까지
// 같이 들어가 툴팁이 어긋난다. 상수로 둔다.
const NL = '\n'
const NLNL = NL + NL

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

  /* 중개사 메모에서 뽑은 키워드.
   *
   * 민간임대 배지와 **다른 모양**으로 둔다. 저쪽은 사용자가 단지 상세에서 직접
   * 표시한 사실이고, 이쪽은 **올린 사람이 그렇게 적었다**는 뜻이다. '올수리' 는
   * 우리가 확인한 것이 아니다. 같은 모양으로 두면 둘이 같은 무게로 읽힌다.
   *
   * 셋까지만 배지로 내고 나머지는 '+N' 으로 접는다. 재 봤다 — **줄당** 태그는
   * 중위 4개·최대 10개다(메모 하나당은 중위 2개인데, 한 줄이 같은 층대 매물 여럿을
   * 접으므로 합집합이 커진다). 그래서 절반쯤 되는 줄이 '+N' 을 단다.
   *
   * 그래도 셋인 이유: 서버가 **가격에 걸리는 순서**로 돌려준다(급매·세안고·분양권P·
   * 조정가능이 앞, 전망·에어컨·채광이 뒤). 실제로 10개가 붙은 줄의 앞 셋은
   * 세안고·분양권P·조정가능이었고 접힌 일곱은 설비·전망 얘기였다. 늘려 봐야 중요한
   * 것이 더 보이지 않고 비고 입력칸만 밀려난다 — 이 칸의 주인은 사람이 쓰는 글이다. */
  const tags = item.note_tags || []
  const memos = item.memos || []
  const MAX = 3
  const shown = tags.slice(0, MAX)
  const rest = tags.length - shown.length
  // 호버에 원문을 같이 띄운다. 키워드가 왜 붙었는지는 원문을 봐야 안다.
  //
  // 건수를 먼저 적는다. 한 줄은 같은 층대 매물 여럿을 접은 것이라 태그도 **합집합**이고,
  // 그래서 한 줄에 '즉시입주' 와 '입주협의' 가 같이 붙을 수 있다 — 서로 다른 매물의
  // 말이다. 몇 건을 합친 것인지 모르면 그게 모순으로 보인다.
  const memoTitle = memos.length
    ? `중개사 메모 ${memos.length}건 (올린 사람의 말입니다)` + NLNL + memos.join(NL)
    : '중개사 메모에서 뽑은 키워드입니다'

  const Tags = () =>
    tags.length > 0 && (
      <>
        {shown.map((t) => (
          <b className="note-tag is-memo" key={t} title={memoTitle}>
            {t}
          </b>
        ))}
        {rest > 0 && (
          <b className="note-tag is-memo is-more" title={tags.join(' · ') + NLNL + memoTitle}>
            +{rest}
          </b>
        )}
      </>
    )

  if (STATIC_MODE) {
    // 정적 사이트에서는 쓸 수 없다. 눌리는데 실패하는 칸을 두지 않는다.
    if (!auto.length && !tags.length && !item.note) return <span className="muted">—</span>
    return (
      <span className="note-ro">
        {auto.map((t) => (
          <b className="note-tag" key={t}>
            {t}
          </b>
        ))}
        <Tags />
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
      <Tags />
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
