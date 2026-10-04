import { useEffect, useState } from 'react'

import MacroView from './MacroView'
import MarketView from './MarketView'

/**
 * 분석 — **미시**와 **거시**를 한 탭에 둔다.
 *
 * ## 왜 합쳤나
 *
 * 둘은 같은 질문의 두 축이다. '무엇이 가격을 얼마나 움직이나'(요인별 보정계수)와
 * '지역이 서로 어떻게 다르게 움직이나'(공표 통계)는 따로 보면 반쪽이다. 실제로
 * 모델 괴리 차트는 **두 탭의 값을 겹쳐야** 뜻이 생기는데, 그걸 보려면 탭을 오가며
 * 머릿속에서 이어 붙여야 했다.
 *
 * 탭을 나눈 이유는 화면이 좁아서였다. 그런데 가로 공간은 남아 돌았다 — 1240px 로
 * 묶어 두고 격자는 300px 짜리 카드를 쓰니, 넓은 화면에서 양옆이 통째로 비었다.
 * 폭을 넓히면 두 섹션이 한 탭에 들어간다.
 *
 * ## 숨기지 않고 나눈다
 *
 * 섹션을 탭처럼 만들어 한쪽만 보여 줄 수도 있었다. 그러면 탭이 두 개였던 것과
 * 같아진다 — 이름만 바뀐다. 둘 다 그려 두고 **건너뛸 길만** 준다. 위쪽 링크는
 * 고르는 것이 아니라 이동이고, 지금 보고 있는 섹션이 표시된다.
 */
export default function AnalysisView({ filters, setFilters, meta }) {
  const here = useActiveSection(['micro', 'macro'])

  const jump = (id) => {
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="analysis">
      <nav className="section-nav" aria-label="섹션 건너뛰기">
        {[
          ['micro', '미시 분석', '무엇이 가격을 얼마나 움직이나'],
          ['macro', '거시 분석', '시군구가 서로 어떻게 다른가'],
        ].map(([id, label, sub]) => (
          <button
            key={id}
            className={here === id ? 'on' : ''}
            aria-current={here === id ? 'true' : undefined}
            onClick={() => jump(id)}
          >
            <b>{label}</b>
            <span>{sub}</span>
          </button>
        ))}
      </nav>

      <section id="micro" className="analysis-section">
        <h2 className="section-title">
          미시 분석 <span>단지와 매물 — 우리 모델이 낸 값</span>
        </h2>
        <MarketView filters={filters} setFilters={setFilters} meta={meta} />
      </section>

      <section id="macro" className="analysis-section">
        <h2 className="section-title">
          거시 분석 <span>시군구 — 한국부동산원 공표 통계</span>
        </h2>
        <MacroView />
      </section>
    </div>
  )
}

/* 지금 보고 있는 섹션. 스크롤 위치로 정한다.
 *
 * IntersectionObserver 의 기본 동작(화면에 보이면 켬)으로는 둘 다 걸쳐 있을 때
 * 어느 쪽인지 못 고른다. 그래서 **화면 위쪽 1/3 선을 지난 마지막 섹션**을 본다 —
 * 읽고 있는 자리가 보통 거기다. */
function useActiveSection(ids) {
  const [here, setHere] = useState(ids[0])
  useEffect(() => {
    const onScroll = () => {
      const line = window.innerHeight / 3
      let cur = ids[0]
      for (const id of ids) {
        const el = document.getElementById(id)
        if (el && el.getBoundingClientRect().top <= line) cur = id
      }
      setHere(cur)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
    // ids 는 호출부에서 리터럴이라 매 렌더 새 배열이다. 길이로만 의존한다.
  }, [ids.length])
  return here
}
