import { useEffect, useState } from 'react'

import { api, snapshotMeta, STATIC_MODE } from './api'
import MarketView from './views/MarketView'
import ComplexDetail from './views/ComplexDetail'
import MapView from './views/MapView'
import ModelView from './views/ModelView'
import CompareView from './views/CompareView'
import RankingView from './views/RankingView'

/**
 * `static: true` 인 탭만 정적 사이트에 실린다.
 *
 * 나머지는 서버가 필요해서 빼는 것이 아니라, **서버 없이는 틀린 답을 내기 때문에**
 * 뺀다. 매물 분석은 붙여넣은 텍스트를 파싱하고 그 자리에서 평가하므로 미리 파일로
 * 만들어 둘 수가 없다. 지도·분해 모델은 만들 수는 있지만 스냅샷이 무거워져
 * (지도 응답이 기간당 1.2MB) 이번 범위에서 뺐다 — 필요해지면 export_static.py 의
 * 목록에 넣고 여기 `static: true` 만 켜면 된다.
 *
 * 눌리는데 실패하는 탭을 두지 않는다. 없는 기능은 아예 안 보이는 쪽이 낫다.
 */
const TABS = [
  { id: 'market', label: '시장 분석', static: true },
  { id: 'map', label: '지도' },
  { id: 'model', label: '분해 모델' },
  { id: 'compare', label: '매물 분석' },
  { id: 'ranking', label: '매물 순위', static: true },
]

const VISIBLE_TABS = STATIC_MODE ? TABS.filter((t) => t.static) : TABS

// 단지 비교 탭을 없애면서 구·면적대·입지 같은 필터를 읽는 곳이 사라졌다.
// 남은 화면은 전부 분석 기간만 쓴다.
const DEFAULT_FILTERS = { months: 12 }

export default function App() {
  const [tab, setTab] = useState('market')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [meta, setMeta] = useState(null)
  const [health, setHealth] = useState(null)
  const [detailId, setDetailId] = useState(null)
  const [snap, setSnap] = useState(null)

  useEffect(() => {
    api.filters().then(setMeta).catch(() => setMeta(null))
    api.health().then(setHealth).catch(() => setHealth(null))
    if (STATIC_MODE) snapshotMeta().then(setSnap)
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

      {/* 정적 사이트는 **보고 있는 값이 언제 것인지 알 수 없다.** 로컬은 부를 때마다
          최신이지만 여기는 마지막 내보내기 시점에 멈춰 있다. 적지 않으면 오래된
          값을 최신으로 읽게 된다. */}
      {STATIC_MODE && (
        <div className="notice snapshot-note">
          <strong>내보낸 스냅샷입니다.</strong>{' '}
          {snap ? (
            <>
              {new Date(snap.generated_at).toLocaleString('ko-KR')} 기준 ·{' '}
              실거래 {snap.data?.trades?.toLocaleString()}건
              {snap.data?.latest_deal_date ? ` (최신 거래 ${snap.data.latest_deal_date})` : ''}
              {snap.includes_quotes ? ` · 매물 ${snap.data?.quotes?.toLocaleString()}건` : ''}
            </>
          ) : (
            '생성 시점을 읽지 못했습니다.'
          )}{' '}
          매물을 새로 넣거나 모델을 다시 돌리는 것은 로컬 대시보드에서 합니다.
        </div>
      )}

      {health && !health.molit_key_set && (
        <div className="notice">
          국토교통부 API 키가 설정되지 않아 <strong>합성 데모 데이터</strong>로 동작 중입니다.
          실제 실거래가를 보려면 <code>backend/.env</code> 에 키를 넣고{' '}
          <code>python -m scripts.ingest_trades</code> 를 실행하세요.
        </div>
      )}

      <nav className="tabs">
        {VISIBLE_TABS.map((t) => (
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
