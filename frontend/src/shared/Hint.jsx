import { useEffect, useRef, useState } from 'react'

/**
 * 값에 붙는 주석 — 호버(또는 포커스)했을 때만 펼친다.
 *
 * 경고 문구를 카드 안에 줄줄이 늘어놓으면 한 매물에 3~5줄이 깔려 화면의 절반을
 * 먹는다. 그런데 그 문구들은 대부분 **특정 값 하나**에 대한 주석이다 —
 * "39㎡를 40㎡로 맞췄다"는 전용면적 이야기고, "'고층'을 19층으로 봤다"는 층 이야기다.
 * 그러면 그 값 옆에 두고 필요할 때만 보게 하는 편이 맞다.
 *
 * ## 왜 position: fixed 인가
 *
 * 순위표는 `.table-wrap { overflow: auto }` 안에 있다. 그 안에서 팝업을
 * `position: absolute` 로 띄우면 **컨테이너에 잘린다** — 실제로 표 오른쪽 열의
 * 주석이 통째로 안 보였다. 스크롤 컨테이너 밖으로 나가려면 뷰포트 기준으로
 * 띄워야 하고, 그러면 위치를 CSS 로는 못 잡으므로 열릴 때 계산해 넣는다.
 *
 * 화면 오른쪽·아래 끝에서는 팝업이 잘리지 않도록 방향을 뒤집는다.
 *
 * `notes` 는 문장 목록, `children` 은 표 같은 구조를 그대로 넣을 때 쓴다.
 * `title` 속성은 쓰지 않는다 — 지연이 길고 줄바꿈과 서식을 못 준다.
 */
export default function Hint({ notes, children, tone = 'info', label, wide, pill }) {
  const dotRef = useRef(null)
  const [pos, setPos] = useState(null)

  const list = (notes || []).filter(Boolean)

  const openAt = () => {
    const r = dotRef.current?.getBoundingClientRect()
    if (!r) return
    const w = wide ? 360 : 290
    const margin = 10
    // 오른쪽으로 넘치면 왼쪽으로 붙인다.
    const left = Math.min(Math.max(margin, r.left), window.innerWidth - w - margin)
    // 아래로 넘치면 위로 띄운다. 높이는 열어 봐야 알 수 있으므로 넉넉히 가정한다.
    const below = window.innerHeight - r.bottom
    setPos(
      below < 180
        ? { left, bottom: window.innerHeight - r.top + 6, width: w }
        : { left, top: r.bottom + 6, width: w },
    )
  }

  const close = () => setPos(null)

  // 손가락에는 호버가 없다.
  //
  // 휴대폰에서 순위 카드의 ⓘ 를 눌러도 아무 일이 없었다. 열리는 경로가 `mouseenter`
  // 와 `focus` 뿐인데, 터치 브라우저는 앞의 것을 흉내만 내고(첫 탭에서 한 번, 그나마
  // 기기마다 다르다) 뒤의 것은 폼 요소가 아니면 잘 주지 않는다.
  //
  // 그래서 **탭으로 여닫게** 한다. 데스크톱에서도 클릭으로 고정할 수 있어 나쁘지 않다.
  const toggle = (e) => {
    e.stopPropagation()
    if (pos) close()
    else openAt()
  }

  // 열려 있는 동안 바깥을 누르면 닫는다. 터치에는 `mouseleave` 가 오지 않으므로
  // 이게 없으면 한 번 연 팝업이 계속 떠 있는다.
  useEffect(() => {
    if (!pos) return
    const onDocDown = () => close()
    document.addEventListener('pointerdown', onDocDown)
    return () => document.removeEventListener('pointerdown', onDocDown)
  }, [pos])

  // 훅을 다 부른 **뒤에** 판단한다. 조기 반환을 위에 두면 훅이 조건부로 호출돼
  // 리액트가 렌더마다 다른 훅 순서를 보게 된다.
  if (list.length === 0 && !children) return null

  return (
    <span
      className={`hint is-${tone}`}
      tabIndex={0}
      role="button"
      aria-expanded={!!pos}
      onMouseEnter={openAt}
      onFocus={openAt}
      onMouseLeave={close}
      onBlur={close}
      onPointerDown={toggle}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          toggle(e)
        } else if (e.key === 'Escape') {
          close()
        }
      }}
    >
      <span className={`hint-dot${pill ? ' is-pill' : ''}`} ref={dotRef} aria-hidden="true">
        {label ?? (tone === 'warn' ? '!' : 'i')}
      </span>
      {pos && (
        <span className={`hint-pop${wide ? ' is-wide' : ''}`} style={pos}>
          {children}
          {list.map((t, i) => (
            <span key={i} className="hint-line">
              {t}
            </span>
          ))}
        </span>
      )}
    </span>
  )
}
