import { useEffect, useState } from 'react'

import { api, snapshotMeta, STATIC_MODE } from './api'
import { scrollToChart, TabContext } from './shared/ChartLink'
import Hint from './shared/Hint'
import ComplexDetail from './realestate/views/ComplexDetail'
import { TABS as REALESTATE_TABS } from './realestate/tabs'

/**
 * 자산 — 제목 자리에서 고른다. 탭은 자산마다 따로 있다.
 *
 * 2026-10-27 요청으로 범위를 넓혔다: 이 사이트는 '경기 남부 아파트 적정 시세' 였고, 이제 그 전부가
 * '부동산' 한 자산이다. 탭과 그 화면은 자산마다 `src/<자산>/tabs.jsx` 가 정한다 — 이 파일은 조립만 한다.
 * 새 자산은 여기 한 줄과 그 자산의 tabs.jsx 를 더한다. 탭이 아직 없는 자산(주식)은 빈 목록이다.
 *
 * 탭이 없는 자산도 고를 수 있게 둔다. tabs.jsx 의 '눌리는데 실패하는 탭을 두지 않는다' 와 부딪히는 것 같지만,
 * 그 규칙이 막는 것은 **눌렀더니 틀린 답이나 오류가 나오는 것**이다. 탭이 없는 자산은 그렇다고 말하는
 * 빈 화면만 낸다 — 무엇을 넓히려는지가 제목에서 보이는 편이 낫다고 봤다.
 */
const ASSETS = [
  { id: 'realestate', label: '부동산', tabs: REALESTATE_TABS },
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
      ) : (
        cur.tabs.find((t) => t.id === tab)?.render({ filters, setFilters, meta, onSelect: openDetail, pasted })
      )}
      </TabContext.Provider>
    </div>
  )
}
