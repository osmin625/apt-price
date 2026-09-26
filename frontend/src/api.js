const qs = (params = {}) => {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.append(k, v)
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || `요청 실패 (${res.status})`)
  }
  return res.json()
}

export const api = {
  health: () => request('/health'),
  filters: () => request('/complexes/meta/filters'),
  market: (params) => request(`/analysis/market${qs(params)}`),
  complexes: (params) => request(`/complexes${qs(params)}`),
  complex: (id, params) => request(`/complexes/${id}${qs(params)}`),
  areaTypes: (id) => request(`/complexes/${id}/area-types`),
  dongs: (id) => request(`/complexes/${id}/dongs`),
  quotes: (id, params) => request(`/complexes/${id}/quotes${qs(params)}`),
  evaluate: (body, params) =>
    request(`/listings/evaluate${qs(params)}`, { method: 'POST', body: JSON.stringify(body) }),
  saveListing: (body, params) =>
    request(`/listings${qs(params)}`, { method: 'POST', body: JSON.stringify(body) }),
  listings: (params) => request(`/listings${qs(params)}`),
  deleteListing: (id) => request(`/listings/${id}`, { method: 'DELETE' }),

  // 역거리 연속 모델 + 지도
  modelFit: (params) => request(`/model/fit${qs(params)}`),
  residuals: (params) => request(`/model/residuals${qs(params)}`),
  groups: (params) => request(`/model/groups${qs(params)}`),
  factors: (params) => request(`/model/factors${qs(params)}`),
  compare: (body) =>
    request('/model/compare', { method: 'POST', body: JSON.stringify(body) }),
  parseListing: (text, complexId) =>
    request('/model/parse-listing', {
      method: 'POST',
      body: JSON.stringify({ text, complex_id: complexId ?? null }),
    }),
  mapComplexes: (params) => request(`/map/complexes${qs(params)}`),
  stations: () => request('/map/stations'),
  rings: (params) => request(`/map/rings${qs(params)}`),
  walkPath: (id, params) => request(`/map/walk-path/${id}${qs(params)}`),
}
