import { useEffect, useRef } from 'react'

/**
 * 화면 위에 띄우는 창.
 *
 * ## 왜 카드 안에서 펼치지 않나
 *
 * 처음에는 요인 카드 안에서 아래로 펼쳤다. 그런데 그 카드는 격자의 한 칸이라 폭이
 * 300px 남짓인데, 산점도와 타일 여섯 개를 그 안에 우겨넣으니 읽을 수가 없었다.
 * 게다가 한 칸만 길어져서 격자 전체가 어그러졌다.
 *
 * 내용이 칸보다 크면 칸을 늘릴 게 아니라 **칸 밖으로 꺼내야** 한다.
 *
 * ## 지키는 것
 *
 * - `Esc`, 배경 클릭, 닫기 버튼 — 나가는 길을 셋 다 둔다.
 * - 열릴 때 창으로 포커스를 옮기고, 닫을 때 **누르던 자리로 돌려준다.**
 *   안 그러면 키보드 사용자가 문서 맨 위로 튕긴다.
 * - 열려 있는 동안 뒤 배경은 스크롤되지 않는다. 모바일에서 특히 거슬린다.
 */
export default function Modal({ title, onClose, children, wide }) {
  const panelRef = useRef(null)
  const returnTo = useRef(null)

  useEffect(() => {
    returnTo.current = document.activeElement
    panelRef.current?.focus()

    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)

    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
      // 포커스를 눌렀던 요소로 돌려준다. 사라진 요소면 그냥 둔다.
      if (returnTo.current?.isConnected) returnTo.current.focus()
    }
  }, [onClose])

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className={`modal${wide ? ' is-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={panelRef}
      >
        <div className="modal-head">
          <strong>{title}</strong>
          <button className="ghost" onClick={onClose} aria-label="닫기">
            닫기
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}
