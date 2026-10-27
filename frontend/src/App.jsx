import { useEffect, useState } from 'react'

import { api, snapshotMeta, STATIC_MAP, STATIC_MODE } from './api'
import { scrollToChart, TabContext } from './components/ChartLink'
import Hint from './components/Hint'
import MacroView from './views/MacroView'
import MarketView from './views/MarketView'
import ComplexDetail from './views/ComplexDetail'
import MapView from './views/MapView'
import ModelView from './views/ModelView'
import CompareView from './views/CompareView'
import RankingView from './views/RankingView'
import RegimeView from './views/RegimeView'
import SupplyView from './views/SupplyView'
import TenureView from './views/TenureView'

/**
 * `static: true` 인 탭만 정적 사이트에 실린다.
 *
 * 나머지는 서버가 필요해서 빼는 것이 아니라, **서버 없이는 틀린 답을 내기 때문에**
 * 뺀다. 매물 분석은 붙여넣은 텍스트를 파싱하고 그 자리에서 평가하므로 미리 파일로
 * 만들어 둘 수가 없다. 분해 모델은 만들 수는 있지만 아직 안 넣었다 —
 * export_static.py 의 목록에 넣고 여기 `static: true` 만 켜면 된다.
 *
 * 지도는 데이터가 아니라 **키 때문에** 조건부다. 응답은 늘 내보내지만, 카카오 JS
 * 키가 공개 번들에 들어가야 하므로 켜는 것을 의도적인 행위로 만들었다
 * (`VITE_STATIC_MAP=1`). 자세한 것은 api.js 의 STATIC_MAP 주석과 docs/engineering/deploy.md.
 *
 * 눌리는데 실패하는 탭을 두지 않는다. 없는 기능은 아예 안 보이는 쪽이 낫다.
 *
 * ## 순서 — 큰 틀에서 상세로
 *
 * 2026-10-22 요청으로 다시 줄 세웠다: 거시 분석이 첫째, 탭을 넘길수록 범위가 좁아져 호가 분석이 마지막.
 * 전국·경기의 거시 요인 → 공급 → 경기 남부 평균의 매매·전세·월세 → 시군구별 공표 가격 → 단지 가격을 움직이는
 * 요인(매물 분석·분해 모델) → 단지 하나하나(지도) → 매물 하나하나(호가 입력·분석). 예전에는 매물 분석이
 * 첫 탭이라, 무엇을 보는 사이트인지 알기 전에 단지 요인부터 나왔다. 첫 화면은 이 목록의 첫 탭이다.
 */
const TABS = [
  // 공급은 여섯 요인 중 하나다. 나머지(수요·통화량·금리·정책·세금)까지 한 화면에
  // 놓고 **어느 쪽으로 미는지**를 본다. 공급 탭과 겹치는 것은 준공·미분양뿐이고,
  // 거기서는 '얼마나 모자라나', 여기서는 '그래서 어느 쪽인가' 를 묻는다.
  { id: 'regime', label: '거시 분석', static: true },
  // 공급은 2~3년 전에 정해져 지금 나타난다. 가격 추이와 같은 축에 놓으면
  // 둘 다 안 읽혀서 탭을 따로 뒀다.
  { id: 'supply', label: '공급 분석', static: true },
  // 거시 탭이 '가격을 어느 쪽으로 미나' 라면, 여기는 '수요가 어느 점유 형태로 옮겨 가나' 다.
  // 같은 금리가 매매·전세·월세에 다르게 닿는 것을 보려면 세 가격이 한 화면에 있어야 한다.
  { id: 'tenure', label: '매매·전세·월세', static: true },
  // 한 탭 안에 섹션으로 합쳐 봤다가 **되돌렸다.** 둘(가격 분석·매물 분석)은 같은 질문의 두 축이지만,
  // 각자 카드가 예닐곱 장이라 한 화면에 올리면 좌우 2단으로 쪼개도 빽빽했다.
  // 겹쳐 봐야 하는 것은 '모델과 어긋나는 곳' 한 장뿐이고, 그건 가격 분석 쪽에 이미 있다.
  // 이름을 두 번 바꿨다. '시장 분석' → '미시 분석' → '매물 분석' 이고,
  // '매크로' → '거시 분석' → '가격 분석' 이다. 바꾼 이유는 같다 — '미시/거시' 가
  // 무엇을 보는 탭인지 말해 주지 않았다. 지금 이름은 **대상**을 가리킨다.
  { id: 'macro', label: '가격 분석', static: true },
  { id: 'micro', label: '매물 분석', static: true },
  // 정적 사이트에도 싣는다. 적합 결과(`/model/fit`)는 이미 내보내고 있었고, 묶어 보기
  // (`/model/groups`)만 더하면 됐다. 맨 위 수식(`ModelFormula`)이 탭의 입구다.
  { id: 'model', label: '분해 모델', static: true },
  { id: 'map', label: '지도', static: STATIC_MAP },
  // '매물 분석' 이었다. 붙여넣어 읽는 것만 하던 탭에 **메모 사전 관리**가
  // 들어오면서, 하는 일이 분석보다 관리에 가까워졌다.
  // 둘은 짝이다 — 한쪽에 붙여넣고 다른 쪽에서 본다. 이름도 짝으로 맞췄다.
  { id: 'compare', label: '호가 입력' },
  { id: 'ranking', label: '호가 분석', static: true },
]

/**
 * 자산 — 제목 자리에서 고른다. 탭은 자산마다 따로 있다.
 *
 * 2026-10-27 요청으로 범위를 넓혔다: 이 사이트는 '경기 남부 아파트 적정 시세' 였고, 이제 그 전부가
 * '부동산' 한 자산이다. 위 TABS 가 그대로 부동산의 탭이다. 새 자산은 여기 한 줄과 그 탭 목록을 더한다.
 *
 * 탭이 없는 자산도 고를 수 있게 둔다. 위의 '눌리는데 실패하는 탭을 두지 않는다' 와 부딪히는 것 같지만,
 * 그 규칙이 막는 것은 **눌렀더니 틀린 답이나 오류가 나오는 것**이다. 탭이 없는 자산은 그렇다고 말하는
 * 빈 화면만 낸다 — 무엇을 넓히려는지가 제목에서 보이는 편이 낫다고 봤다.
 */
const ASSETS = [
  { id: 'realestate', label: '부동산', tabs: TABS },
  { id: 'stock', label: '주식', tabs: [] },
].map((a) => ({ ...a, tabs: STATIC_MODE ? a.tabs.filter((t) => t.static) : a.tabs }))

/** 탭 id 는 자산을 건너 겹치지 않는다 — 그래서 주소에 자산을 따로 적지 않아도 탭에서 자산이 나온다. */
const assetOfTab = (id) => ASSETS.find((a) => a.tabs.some((t) => t.id === id))

/**
 * 주소 `#탭/그림` → { asset, tab, chart }. 탭이 없는 자산은 `#자산`(`#stock`).
 * 모르는 이름이면 첫 자산의 첫 탭(링크가 옛 탭 이름이어도 빈 화면이 아니게). 예전 링크(`#regime/overlay`)는
 * 그대로 부동산으로 열린다.
 */
function readHash() {
  const [t, c] = decodeURIComponent(window.location.hash.replace(/^#/, '')).split('/')
  const byTab = assetOfTab(t)
  if (byTab) return { asset: byTab.id, tab: t, chart: c || null }
  const a = ASSETS.find((x) => x.id === t) || ASSETS[0]
  return { asset: a.id, tab: a.tabs[0]?.id ?? null, chart: null }
}

// 단지 비교 탭을 없애면서 구·면적대·입지 같은 필터를 읽는 곳이 사라졌다.
// 남은 화면은 전부 분석 기간만 쓴다.
const DEFAULT_FILTERS = { months: 12 }

export default function App() {
  const [asset, setAsset] = useState(() => readHash().asset)
  const [tab, setTab] = useState(() => readHash().tab)
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [meta, setMeta] = useState(null)
  const [health, setHealth] = useState(null)
  const [detailId, setDetailId] = useState(null)
  const [snap, setSnap] = useState(null)
  // 전역 Ctrl+V 로 들어온 매물 텍스트. `at` 이 바뀔 때마다 다시 읽는다.
  const [pasted, setPasted] = useState(null)

  useEffect(() => {
    api.filters().then(setMeta).catch(() => setMeta(null))
    api.health().then(setHealth).catch(() => setHealth(null))
    if (STATIC_MODE) snapshotMeta().then(setSnap)
  }, [])

  /* 대시보드 **아무 곳에서나** Ctrl+V 하면 매물로 읽는다.
   *
   * 북마클릿으로 담은 뒤 '매물 분석 탭으로 가서 입력칸을 누르고 붙여넣기' 를 거쳐야
   * 했는데, 그 세 걸음이 전체 과정에서 제일 번거로웠다. 창을 바꾸고 Ctrl+V 하면 끝나게 한다.
   *
   * 입력칸 안에서 누른 붙여넣기는 건드리지 않는다 — 비고를 적다가 붙여넣는 것까지
   * 가로채면 못 쓴다. 매물처럼 생긴 글(가격 줄이 있는)만 받는다. */
  useEffect(() => {
    if (STATIC_MODE) return // 정적 사이트에서는 쓰기가 안 된다
    const onPaste = (e) => {
      const el = e.target
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
      const text = e.clipboardData?.getData('text') || ''
      if (!/^\s*(매매|전세|월세)\s*[\d억]/m.test(text)) return
      e.preventDefault()
      window.history.pushState(null, '', '#compare')
      setAsset('realestate')
      setTab('compare')
      setDetailId(null)
      setPasted({ text, at: Date.now() })
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  }, [])

  // 주소가 바뀌면(링크로 들어옴·뒤로 가기) 그 탭을 열고 그림까지 내려 준다. 탭을 누를 때는 주소에
  // 기록만 남긴다(pushState) — 뒤로 가기가 앞 탭으로 돌아가게.
  useEffect(() => {
    let stop = scrollToChart(readHash().chart)
    const onHash = () => {
      const h = readHash()
      setAsset(h.asset)
      setTab(h.tab)
      setDetailId(null)
      stop()
      stop = scrollToChart(h.chart)
    }
    window.addEventListener('hashchange', onHash)
    window.addEventListener('popstate', onHash)
    return () => {
      stop()
      window.removeEventListener('hashchange', onHash)
      window.removeEventListener('popstate', onHash)
    }
  }, [])
  const goTab = (id) => {
    if (readHash().tab !== id || window.location.hash !== `#${id}`) window.history.pushState(null, '', `#${id}`)
    setTab(id)
    setDetailId(null)
  }
  // 자산을 바꾸면 그 자산의 첫 탭으로 간다. 탭이 없으면 주소에 자산 이름만 남긴다.
  const goAsset = (id) => {
    if (id === asset) return
    const first = ASSETS.find((x) => x.id === id).tabs[0]?.id
    setAsset(id)
    if (first) return goTab(first)
    window.history.pushState(null, '', `#${id}`)
    setTab(null)
    setDetailId(null)
  }
  const cur = ASSETS.find((a) => a.id === asset)

  const openDetail = (id) => {
    setDetailId(id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="app">
      <header className="top">
        <div className="top-main">
          <div className="top-title">
            <h1>자산 분석</h1>
            <div className="seg asset-pick" role="tablist" aria-label="자산">
              {ASSETS.map((a) => (
                <button key={a.id} role="tab" aria-selected={asset === a.id} onClick={() => goAsset(a.id)}>
                  {a.label}
                </button>
              ))}
            </div>
          </div>
          {asset === 'realestate' && (
            <p>
              경기 남부 아파트 · 국토교통부 실거래가 기반 · <strong>전용면적</strong> 평당가로 비교 (공급면적 아님)
            </p>
          )}
        </div>
        {/* 매물을 찾아오는 곳. 이 앱은 붙여넣은 텍스트만 읽으므로, 실제 매물은
            여기서 보고 복사해 온다. rel 에 noopener 를 넣어 새 탭이 이 페이지의
            window 를 건드리지 못하게 한다. 부동산에서만 뜻이 있다. */}
        {asset === 'realestate' && (
        <a
          className="ext-link"
          href="https://fin.land.naver.com/map?center=3zicav-2Azj62&zoom=14.2696839630405&tradeTypes=A1&realEstateTypes=A01&dealPrice=0-510000000&activeDevelopments=RAIL&layer=NobwRAlgJmBcYAsD2BbApmANGAzmghgE4DGCACkfijnCAL50C6QA"
          target="_blank"
          rel="noopener noreferrer"
        >
          네이버페이 부동산 <span aria-hidden="true">↗</span>
        </a>
        )}
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
          )}
          <Hint notes={['매물을 새로 넣거나 모델을 다시 돌리는 것은 로컬 대시보드에서 합니다.']} />
        </div>
      )}

      {asset === 'realestate' && health && !health.molit_key_set && (
        <div className="notice">
          국토교통부 API 키가 설정되지 않아 <strong>합성 데모 데이터</strong>로 동작 중입니다.
          실제 실거래가를 보려면 <code>backend/.env</code> 에 키를 넣고{' '}
          <code>python -m scripts.ingest_trades</code> 를 실행하세요.
        </div>
      )}

      {cur.tabs.length > 0 && (
      <nav className="tabs">
        {cur.tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => goTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      )}

      <TabContext.Provider value={tab}>
      {!tab ? (
        <div className="card empty asset-empty">{cur.label} 분석은 준비 중입니다.</div>
      ) : detailId ? (
        <ComplexDetail
          complexId={detailId}
          months={filters.months}
          onClose={() => setDetailId(null)}
        />
      ) : tab === 'micro' ? (
        <MarketView filters={filters} setFilters={setFilters} meta={meta} />
      ) : tab === 'macro' ? (
        <MacroView />
      ) : tab === 'supply' ? (
        <SupplyView />
      ) : tab === 'regime' ? (
        <RegimeView />
      ) : tab === 'tenure' ? (
        <TenureView />
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
        <CompareView months={Math.max(filters.months, 12)} incoming={pasted} />
      )}
      </TabContext.Provider>
    </div>
  )
}
