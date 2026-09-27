import { useEffect, useState } from 'react'

import { api } from './api'
import MarketView from './views/MarketView'
import ComplexesView from './views/ComplexesView'
import ComplexDetail from './views/ComplexDetail'
import MapView from './views/MapView'
import ModelView from './views/ModelView'
import CompareView from './views/CompareView'
import RankingView from './views/RankingView'

const TABS = [
  { id: 'market', label: '시장 분석' },
  { id: 'complexes', label: '단지 비교' },
  { id: 'map', label: '지도' },
  { id: 'model', label: '거리 모델' },
  { id: 'compare', label: '매물 분석' },
  { id: 'ranking', label: '매물 순위' },
]

const DEFAULT_FILTERS = {
  months: 12,
  sgg_cd: '',
  area_band: '',
  station_band: '',
  age_band: '',
  line: '',
  station: '',
  household_band: '',
}

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
      ) : tab === 'complexes' ? (
        <ComplexesView
          filters={filters}
          setFilters={setFilters}
          meta={meta}
          onSelect={openDetail}
        />
      ) : tab === 'map' ? (
        <MapView months={Math.max(filters.months, 12)} onSelect={openDetail} />
      ) : tab === 'model' ? (
        <ModelView months={Math.max(filters.months, 12)} onSelect={openDetail} />
      ) : tab === 'ranking' ? (
        <RankingView
          months={Math.max(filters.months, 12)}
          setMonths={(m) => setFilters({ ...filters, months: m })}
        />
      ) : (
        <CompareView months={Math.max(filters.months, 12)} meta={meta} onSelect={openDetail} />
      )}
    </div>
  )
}

export function FilterBar({ filters, setFilters, meta, extra }) {
  const set = (key) => (e) => setFilters({ ...filters, [key]: e.target.value })

  return (
    <div className="filters">
      <div className="field">
        <label htmlFor="f-months">분석 기간</label>
        <select
          id="f-months"
          value={filters.months}
          onChange={(e) => setFilters({ ...filters, months: Number(e.target.value) })}
        >
          <option value={6}>최근 6개월</option>
          <option value={12}>최근 12개월</option>
          <option value={24}>최근 24개월</option>
          <option value={36}>최근 36개월</option>
        </select>
      </div>

      <div className="field">
        <label htmlFor="f-sgg">자치구</label>
        <select id="f-sgg" value={filters.sgg_cd} onChange={set('sgg_cd')}>
          <option value="">전체</option>
          {meta?.districts.map((d) => (
            <option key={d.code} value={d.code}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="f-area">전용 면적대</label>
        <select id="f-area" value={filters.area_band} onChange={set('area_band')}>
          <option value="">전체</option>
          {meta?.area_bands.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="f-station">입지 (역까지 거리)</label>
        <select id="f-station" value={filters.station_band} onChange={set('station_band')}>
          <option value="">전체</option>
          {meta?.station_bands.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="f-age">컨디션 (준공 연식)</label>
        <select id="f-age" value={filters.age_band} onChange={set('age_band')}>
          <option value="">전체</option>
          {meta?.age_bands.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="f-line">지하철 노선</label>
        <select
          id="f-line"
          value={filters.line}
          onChange={(e) =>
            // 노선을 바꾸면 이전 역 선택은 버린다. 다른 노선의 역이 남아 있으면
            // 교집합이 비어 화면이 빈 채로 이유를 알 수 없게 된다.
            setFilters({ ...filters, line: e.target.value, station: '' })
          }
        >
          <option value="">전체</option>
          {meta?.lines?.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        {/* id 는 f-zone — 기존 '입지(역까지 거리)' 필터가 이미 f-station 을 쓴다.
            겹치면 label 이 엉뚱한 select 를 가리킨다. */}
        <label htmlFor="f-zone">생활권 (최근접역)</label>
        <select id="f-zone" value={filters.station} onChange={set('station')}>
          <option value="">전체</option>
          {(meta?.stations ?? [])
            .filter((s) => !filters.line || s.line === filters.line)
            .map((s) => (
              <option key={`${s.line}-${s.name}`} value={s.name}>
                {s.name}
                {filters.line ? '' : ` (${s.line})`}
                {s.minutes_to_gangnam ? ` · 강남 ${s.minutes_to_gangnam}분` : ''}
              </option>
            ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="f-households">단지 규모 (세대수)</label>
        <select id="f-households" value={filters.household_band} onChange={set('household_band')}>
          <option value="">전체</option>
          {meta?.household_bands?.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      {extra}

      <button
        className="ghost"
        onClick={() =>
          setFilters({
            ...filters,
            sgg_cd: '',
            area_band: '',
            station_band: '',
            age_band: '',
            line: '',
            station: '',
            household_band: '',
          })
        }
      >
        필터 초기화
      </button>
    </div>
  )
}
