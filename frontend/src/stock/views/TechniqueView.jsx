import { useEffect, useState } from 'react'

import ChartLink from '../../shared/ChartLink'
import Hint from '../../shared/Hint'
import { nowShort } from '../components/LiveSection'
import { valShort } from '../components/ValuationSection'
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
 *
 * `load` 가 있으면 실제 지수에 돌린 결과를 받아, 카드에 지수마다 지금 상태 한 줄을 단다 — 단기 매매는 종가로 재는
 * 기법(backend/app/stock/trading.py, `live.rules`), 장기 투자는 지수 평가 넷(valuation.py, `live.measures`). 받는 동안에도 카드와 설명은 그대로 보인다 — 설명이 초점이라 기다리게 하지 않는다.
 */
export default function TechniqueView({ title, notes, catalog, load }) {
  const { GROUPS, TECHNIQUES, NEED } = catalog
  const [pick, setPick] = useState(null)
  const [live, setLive] = useState(load ? null : undefined)
  const [error, setError] = useState(null)
  const t = pick && TECHNIQUES.find((x) => x.id === pick)

  useEffect(() => {
    // 장기·단기 두 탭이 같은 자리의 이 화면을 나눠 써서, 탭을 옮겨도 상태가 남는다 — 단기 탭의 오류가 장기 탭
    // 창에 '요청 실패' 로 뜬 적이 있다. load 가 바뀌면 처음부터.
    setLive(load ? null : undefined)
    setError(null)
    setPick(null)
    if (!load) return undefined
    let alive = true
    load().then((d) => alive && setLive(d)).catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [load])

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
                {(live?.rules?.[x.id] || live?.measures?.[x.id]) && (
                  <ul className="tq-state">
                    {live.indices.map((ix) => (
                      <li key={ix.id}>
                        <span className="muted">{ix.label}</span>{' '}
                        {live.rules?.[x.id]
                          ? nowShort(live.rules[x.id], live.rules[x.id].by[ix.id])
                          : valShort(x.id, live.measures[x.id], live.measures[x.id].by[ix.id])}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="tq-badges">
                  <span className={`badge is-${x.need}`}>{NEED[x.need]}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      {t && (
        <TechniqueModal t={t} needLabel={NEED[t.need]} onClose={() => setPick(null)} live={live} liveError={error} />
      )}
    </>
  )
}
