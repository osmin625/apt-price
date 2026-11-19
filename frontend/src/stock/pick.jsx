import { useEffect, useState } from 'react'

import { api } from '../api'

/**
 * 종목 고르기 — 주식 탭 위에서 종목 하나를 고르면 탭마다 같은 종목을 그 탭의 방식으로 본다(2026-11-20 요청,
 * docs/stock/picks.md). 고른 것은 주소에 싣는다(`#long-term?sym=tsla`) — 공유하거나 새로 고쳐도 남고, 탭을 옮겨도
 * App.jsx 의 `goTab` 이 `?` 뒤를 그대로 넘긴다. 기본은 고르지 않음(지수만)이다.
 *
 * 고를 수 있는 것은 미리 내보낸 종목뿐이다 — 정적 사이트에는 서버가 없어 아무 티커나 받을 수 없다.
 * 목록과 재료는 한 응답(`/api/stock/picks`)이라 한 번만 받아 둔다.
 */
let cache = null
export function loadPicks() {
  if (!cache) {
    cache = api.stockPicks().catch((e) => {
      cache = null
      throw e
    })
  }
  return cache
}

const EVENT = 'stockpick'

export function readSym() {
  const q = window.location.hash.split('?')[1]
  return q ? new URLSearchParams(q).get('sym') : null
}

function writeSym(id) {
  const path = window.location.hash.replace(/^#/, '').split('?')[0]
  const next = `#${path}${id ? `?sym=${encodeURIComponent(id)}` : ''}`
  // 고르는 것은 탭을 옮기는 것이 아니라 보는 대상을 바꾸는 것이라 뒤로 가기 기록을 쌓지 않는다.
  window.history.replaceState(null, '', next)
  window.dispatchEvent(new Event(EVENT))
}

/** 고른 종목의 id 와 고르는 함수. 주소가 바뀌면 따라간다. */
export function useSym() {
  const [sym, setSym] = useState(readSym)
  useEffect(() => {
    const on = () => setSym(readSym())
    window.addEventListener('hashchange', on)
    window.addEventListener('popstate', on)
    window.addEventListener(EVENT, on)
    return () => {
      window.removeEventListener('hashchange', on)
      window.removeEventListener('popstate', on)
      window.removeEventListener(EVENT, on)
    }
  }, [])
  return [sym, writeSym]
}

/** 고른 종목의 재료 — 고르지 않았으면 pick 이 null. */
export function usePicked() {
  const [sym] = useSym()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (!sym) return undefined
    let alive = true
    loadPicks().then((d) => alive && setData(d)).catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [sym])
  const pick = sym && data ? data.companies.find((c) => c.id === sym) || null : null
  return { sym, pick, data, error, loading: Boolean(sym) && !data && !error }
}

export function StockPicker() {
  const [sym, setSym] = useSym()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let alive = true
    loadPicks().then((d) => alive && setData(d)).catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [])
  return (
    <div className="stock-pick">
      <span className="muted small">종목</span>
      <div className="seg" role="tablist" aria-label="종목">
        <button role="tab" aria-selected={!sym} onClick={() => setSym(null)}>지수만</button>
        {(data?.companies || []).map((c) => (
          <button key={c.id} role="tab" aria-selected={sym === c.id} onClick={() => setSym(c.id)}>
            {c.label}
          </button>
        ))}
      </div>
      {!data && <span className="muted small">{error ? '종목을 못 불러왔습니다' : '불러오는 중…'}</span>}
    </div>
  )
}
