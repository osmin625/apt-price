import { useEffect, useState } from 'react'

import { api } from './api'
import MarketView from './views/MarketView'
import ComplexDetail from './views/ComplexDetail'
import MapView from './views/MapView'
import ModelView from './views/ModelView'
import CompareView from './views/CompareView'
import RankingView from './views/RankingView'

const TABS = [
  { id: 'market', label: '시장 분석' },
  { id: 'map', label: '지도' },
  { id: 'model', label: '거리 모델' },
  { id: 'compare', label: '매물 분석' },
  { id: 'ranking', label: '매물 순위' },
]

// 단지 비교 탭을 없애면서 구·면적대·입지 같은 필터를 읽는 곳이 사라졌다.
// 남은 화면은 전부 분석 기간만 쓴다.
const DEFAULT_FILTERS = { months: 12 }

export default function App() {
  const [tab, setTab] = useState('market')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [meta, setMeta] = useState(null)
  const [health, setHealth] = useState(null)
  const [detailId, setDetailId] = useState(null)

  useEffect(() => {
    api.filters().then(setMeta).catch(() => setMeta(null))
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  const openDetail = (id) => {
    setDetailId(id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="app">
      <header className="top">
        <div className="top-main">
          <h1>경기 남부 아파트 적정 시세</h1>
          <p>
            국토교통부 실거래가 기반 · <strong>전용면적</strong> 평당가로 비교 (공급면적 아님)
          </p>
        </div>
        {/* 매물을 찾아오는 곳. 이 앱은 붙여넣은 텍스트만 읽으므로, 실제 매물은
            여기서 보고 복사해 온다. rel 에 noopener 를 넣어 새 탭이 이 페이지의
            window 를 건드리지 못하게 한다. */}
        <a
          className="ext-link"
          href="https://fin.land.naver.com/map?center=3zicav-2Azj62&zoom=14.2696839630405&tradeTypes=A1&realEstateTypes=A01&dealPrice=0-510000000&activeDevelopments=RAIL&layer=NobwRAlgJmBcYAsD2BbApmANGAzmghgE4DGCACkfijnCAL50C6QA"
          target="_blank"
          rel="noopener noreferrer"
        >
          네이버페이 부동산 <span aria-hidden="true">↗</span>
        </a>
      </header>

      {health && !health.molit_key_set && (
        <div className="notice">
          국토교통부 API 키가 설정되지 않아 <strong>합성 데모 데이터</strong>로 동작 중입니다.
          실제 실거래가를 보려면 <code>backend/.env</code> 에 키를 넣고{' '}
          <code>python -m scripts.ingest_trades</code> 를 실행하세요.
        </div>
      )}

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => {
              setTab(t.id)
              setDetailId(null)
            }}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {detailId ? (
        <ComplexDetail
          complexId={detailId}
          months={filters.months}
          onClose={() => setDetailId(null)}
        />
      ) : tab === 'market' ? (
        <MarketView filters={filters} setFilters={setFilters} meta={meta} />
      ) : tab === 'map' ? (
        <MapView months={Math.max(filters.months, 12)} onSelect={openDetail} />
      ) : tab === 'model' ? (
        <ModelView months={Math.max(filters.months, 12)} onSelect={openDetail} />
      ) : tab === 'ranking' ? (
        <RankingView
          months={Math.max(filters.months, 12)}
          setMonths={(m) => setFilters({ ...filters, months: m })}
          onSelect={openDetail}
        />
      ) : (
        <CompareView months={Math.max(filters.months, 12)} meta={meta} onSelect={openDetail} />
      )}
    </div>
  )
}
