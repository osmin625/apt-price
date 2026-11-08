import { createContext, useContext, useEffect, useRef, useState } from 'react'

/**
 * 그림(카드)마다 붙는 링크 — `#탭/그림` 주소를 만들고 누르면 복사한다(2026-10-22 요청: 탭별·차트별로
 * 링크를 구분). 그 주소로 들어오면 `App` 이 탭을 열고 이 카드까지 내려 준다(`scrollToChart`).
 *
 * ## 왜 해시(#)인가
 *
 * 정적 사이트가 GitHub Pages 라 `/apt-price/regime` 같은 경로는 서버가 404 를 낸다. 해시는 서버에 가지
 * 않아 정적 사이트와 로컬이 같은 주소로 돈다.
 *
 * ## 카드에 id 를 직접 달지 않는다
 *
 * 카드가 마흔 장 가까이 되고 로딩·오류 판에도 같은 제목이 있다. 링크가 들어간 그 카드만 찾아가면 되므로,
 * 링크가 자기를 감싼 카드(`.card`, `.macro-card`)에 `chart-<id>` 를 붙인다. id 는 탭 안에서만 겹치지
 * 않으면 된다 — 한 번에 한 탭만 그려진다.
 */
export const TabContext = createContext('')

export const chartDomId = (id) => `chart-${id}`

export default function ChartLink({ id }) {
  const tab = useContext(TabContext)
  const ref = useRef(null)
  const [copied, setCopied] = useState(false)
  const href = `#${tab}/${id}`

  useEffect(() => {
    const card = ref.current?.closest('.card, .macro-card')
    if (card) card.id = chartDomId(id)
  }, [id])

  const onClick = (e) => {
    e.preventDefault()
    // 주소만 바꾸고 다시 스크롤하지 않는다 — 이미 보고 있는 카드다.
    window.history.replaceState(null, '', href)
    const done = () => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    }
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(window.location.href).then(done, () => {})
  }

  return (
    <a ref={ref} className={`chart-link${copied ? ' is-copied' : ''}`} href={href} onClick={onClick}
       aria-label="이 그림으로 가는 링크 복사">
      {copied ? '복사됨' : '#'}
    </a>
  )
}

/** 주소의 `#탭/그림` 에서 그림 카드가 그려질 때까지 기다렸다가 내려 준다. 데이터를 받은 뒤에 카드가 생기므로
 *  곧바로는 없다 — 잠깐씩 다시 찾고, 8초가 지나면 그만둔다(없는 그림 이름이면 탭만 열린다). */
export function scrollToChart(id) {
  if (!id) return () => {}
  let tries = 0
  const timer = setInterval(() => {
    const el = document.getElementById(chartDomId(id))
    if (el) {
      clearInterval(timer)
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      el.classList.add('is-target')
      setTimeout(() => el.classList.remove('is-target'), 2000)
    } else if (++tries > 53) {
      clearInterval(timer)
    }
  }, 150)
  return () => clearInterval(timer)
}
