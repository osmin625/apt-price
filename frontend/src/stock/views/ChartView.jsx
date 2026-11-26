import { useMemo, useState } from 'react'

import ChartLink from '../../shared/ChartLink'
import Hint from '../../shared/Hint'
import Modal from '../../shared/Modal'
import { GROUPS, ITEMS, SECTIONS, search } from '../charts/catalog.js'
import ExampleChart from '../components/ExampleChart'
import { useSym } from '../pick'

/**
 * 차트 탭 — 증권사 앱의 차트 유형·오버레이·보조지표를 보는 법(2026-11-27 요청, docs/stock/charts.md).
 *
 * 꼴은 기법 저장소(TechniqueView)를 따랐다 — 묶음마다 카드, 그 안에 항목마다 작은 카드, 누르면 창. 다른 점 둘:
 * 항목이 백 개 남짓이라 **이름으로 찾는 칸**을 두었고, 창에는 그 지표를 **모두 같은 합성 가격** 위에 그린 그림이
 * 나온다(`charts/sample.js`) — 지표를 바꿔 가며 같은 구간에서 어떻게 다르게 반응하는지 견줄 수 있다.
 *
 * 단기 매매 탭에 같은 기법이 있으면(`short`) 창에서 그리로 잇는다 — 실제 지수에 돌린 성적은 거기 있고, 설명을 두
 * 곳에 쓰지 않는다.
 */
const NOTES = [
  '증권사 앱(HTS·MTS)이 흔히 주는 차트 유형·오버레이·보조지표를 모은 일반 목록입니다. NH투자증권 앱의 공식 목록은 공개된 곳이 없어 맞춰 보지 못했습니다 — 앱마다 이름·묶음·기본값이 조금씩 다릅니다.',
  '앱에서는 보통 차트 화면의 지표(또는 설정) 버튼에서 이름으로 찾아 켭니다. 오버레이는 가격 위에, 보조지표는 가격 아래 칸에 붙습니다.',
  '창의 그림은 모두 같은 합성 가격(오름 → 옆걸음 → 급락 → 되오름) 위에 지표의 식을 그대로 돌린 것입니다. 실제 종목이 아니라 값에는 뜻이 없습니다.',
  '등락 종목 수·투자자별 매매처럼 가격만으로 만들 수 없는 지표는 지어내지 않고 설명만 둡니다.',
  '기법 설명이지 투자 권유가 아닙니다. 어느 지표도 혼자서 사고팔 때를 알려 주지 않습니다.',
]

function ItemModal({ x, onClose }) {
  const spec = x.plot ? x.plot() : null
  return (
    <Modal title={`${x.name} · ${x.en}`} onClose={onClose} wide>
      <p className="tq-summary">{x.one}</p>
      <h3>계산</h3>
      <p>{x.calc}</p>
      <h3>흔한 설정</h3>
      <p>{x.set}</p>
      <h3>읽는 법</h3>
      <ul className="tq-list">{x.read.map((r) => <li key={r}>{r}</li>)}</ul>
      {spec && (
        <>
          <h3>
            예시 <span className="badge">합성 가격</span>
            <Hint notes={['실제 종목이 아니라 모양을 정해 만든 가격입니다. 지표는 손으로 그리지 않고 위 계산을 이 가격에 그대로 돌렸습니다 — 늦게 반응하는 지표는 그림에서도 늦습니다.']} />
          </h3>
          <ExampleChart spec={spec} />
        </>
      )}
      <h3>함정</h3>
      <p>{x.trap}</p>
      {x.short && (
        <p className="muted small">
          <a href="#short-term">단기 매매 탭</a>에 같은 기법을 실제 지수에 돌린 성적이 있습니다.
        </p>
      )}
    </Modal>
  )
}

export default function ChartView() {
  const [q, setQ] = useState('')
  const [pick, setPick] = useState(null)
  // 종목 일봉이 최근 100일뿐이라 백여 개 지표의 창(52·60일)을 채우지 못한다 — 단기 매매와 같은 까닭(docs/stock/picks.md).
  const [sym] = useSym()
  const found = useMemo(() => search(q), [q])
  const ids = new Set(found.map((x) => x.id))
  const x = pick && ITEMS.find((i) => i.id === pick)
  const count = (s) => ITEMS.filter((i) => GROUPS.find((g) => g.id === i.group).section === s).length

  return (
    <>
      <section className="card">
        <h2>
          차트 — 유형·오버레이·보조지표
          <Hint wide notes={NOTES} />
        </h2>
        <p className="muted small">
          {SECTIONS.map((s) => `${s.label} ${count(s.id)}개`).join(' · ')} · 카드를 누르면 설명
        </p>
        <input
          className="ch-search"
          type="search"
          placeholder="이름으로 찾기 — RSI, 볼린저, 일목 …"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="지표 이름으로 찾기"
        />
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
        {q && <p className="muted small">찾은 것 {found.length}개</p>}
        {sym && <p className="muted small">고른 종목은 이 탭에 없습니다 · 합성 가격으로 봅니다</p>}
      </section>
      {GROUPS.filter((g) => found.some((i) => i.group === g.id)).map((g) => (
        <section className="card" key={g.id}>
          <h2>
            {g.section === 'sub' ? `보조지표 — ${g.label}` : g.label}
            <ChartLink id={g.id} />
          </h2>
          <div className="rg-tiles tq-tiles">
            {ITEMS.filter((i) => i.group === g.id && ids.has(i.id)).map((i) => (
              <div
                key={i.id}
                className="rg-tile tq-tile"
                role="button"
                tabIndex={0}
                onClick={() => setPick(i.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setPick(i.id)
                  }
                }}
              >
                <div className="rg-tile-head"><strong>{i.name}</strong></div>
                <div className="muted small">{i.en}</div>
                <p className="tq-one">{i.one}</p>
                <div className="tq-badges">
                  <span className={`badge${i.plot ? '' : ' is-muted'}`}>{i.plot ? '예시 그림' : '설명만'}</span>
                  {i.short && <span className="badge">단기 매매에 성적</span>}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      {!found.length && <section className="card"><p className="empty">'{q}' 에 맞는 항목이 없습니다</p></section>}
      {x && <ItemModal x={x} onClose={() => setPick(null)} />}
    </>
  )
}
