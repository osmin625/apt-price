import { useState } from 'react'

import ChartLink from '../../shared/ChartLink'
import Hint from '../../shared/Hint'
import TechniqueModal from '../components/TechniqueModal'

/**
 * 기법 저장소 — 장기 투자·단기 매매 두 탭이 같은 화면을 쓴다(2026-11-12 합의 — 같은 꼴이라 읽기 쉽다).
 * 목록은 `techniques/long.js`·`short.js` 가 든다. 묶음마다 카드 하나, 그 안에 기법마다 작은 카드.
 *
 * 화면에는 이름·한 줄·필요한 데이터만 두고, 설명은 누르면 열리는 창에 둔다(docs/screens/conventions.md
 * '내용이 칸보다 크면 창으로'). 한 줄(`summary`)은 정의라 시간이 지나도 맞는다.
 *
 * 매매 신호처럼 읽히지 않게, 카드에는 '사라·팔아라' 를 적지 않는다. 지금 상태·과거 성적은 재서 붙인다
 * (docs/stock/trading.md · valuation.md).
 */
export default function TechniqueView({ title, notes, catalog }) {
  const { GROUPS, TECHNIQUES, NEED } = catalog
  const [pick, setPick] = useState(null)
  const t = pick && TECHNIQUES.find((x) => x.id === pick)

  return (
    <>
      <section className="card">
        <h2>
          {title}
          <Hint wide notes={notes} />
        </h2>
        <p className="muted small">
          기법 {TECHNIQUES.length}개 · 묶음 {GROUPS.length}개 · 카드를 누르면 설명
        </p>
        <div className="tq-jump">
          {GROUPS.map((g) => (
            <a key={g.id} className="chip" href={`#chart-${g.id}`}
               onClick={(e) => {
                 e.preventDefault()
                 document.getElementById(`chart-${g.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
               }}>
              {g.label}
            </a>
          ))}
        </div>
      </section>
      {GROUPS.map((g) => (
        <section className="card" key={g.id}>
          <h2>
            {g.label}
            <ChartLink id={g.id} />
          </h2>
          <div className="rg-tiles tq-tiles">
            {TECHNIQUES.filter((x) => x.group === g.id).map((x) => (
              <div
                key={x.id}
                className="rg-tile tq-tile"
                role="button"
                tabIndex={0}
                onClick={() => setPick(x.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setPick(x.id)
                  }
                }}
              >
                <div className="rg-tile-head">
                  <strong>{x.name}</strong>
                </div>
                <div className="muted small">{x.en}</div>
                <p className="tq-one">{x.summary}</p>
                <div className="tq-badges">
                  <span className={`badge is-${x.need}`}>{NEED[x.need]}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      {t && <TechniqueModal t={t} needLabel={NEED[t.need]} onClose={() => setPick(null)} />}
    </>
  )
}
