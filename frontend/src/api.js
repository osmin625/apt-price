const qs = (params = {}) => {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.append(k, v)
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

/**
 * 실패한 요청. `status` 를 붙여 두는 이유가 있다.
 *
 * 예전에는 `new Error(message)` 만 던졌다. 그래서 화면 쪽에서는 "왜 실패했는지"를
 * 알 수 없어, 시장 분석은 **모든** 실패를 의존성 누락으로 단정하고 "pip install
 * -r requirements.txt 후 다시 열어 보세요" 를 띄웠다. 실제로 사용자가 본 상황은
 * 의존성이 멀쩡한데(numpy·pandas·statsmodels 다 설치돼 있었다) start.bat 이
 * 백엔드보다 먼저 브라우저를 열어 첫 요청이 프록시에서 끊긴 것이었다.
 *
 * 틀린 원인을 단정하는 안내는 없는 안내보다 나쁘다. 의존성 누락은 백엔드가
 * 503 으로만 알려 주므로, 그 구분이 가능하도록 상태 코드를 같이 넘긴다.
 */
export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (e) {
    // 네트워크 단계에서 끊긴 것 — 백엔드가 아직 안 떴거나 죽었다. status 없음.
    throw new ApiError('백엔드에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.', 0)
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new ApiError(detail.detail || `요청 실패 (${res.status})`, res.status)
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
  modelStatus: (params) => request(`/model/status${qs(params)}`),
  compare: (body) =>
    request('/model/compare', { method: 'POST', body: JSON.stringify(body) }),
  quoteRanking: (params) => request(`/quotes/ranking${qs(params)}`),
  deleteQuote: (id) => request(`/quotes/${id}`, { method: 'DELETE' }),
  parseBulk: (text, params) =>
    request('/model/parse-bulk', {
      method: 'POST',
      body: JSON.stringify({ text, ...params }),
    }),
  parseListing: (text, complexId) =>
    request('/model/parse-listing', {
      method: 'POST',
      body: JSON.stringify({ text, complex_id: complexId ?? null }),
    }),
  mapComplexes: (params) => request(`/map/complexes${qs(params)}`),
  stations: () => request('/map/stations'),
  walkPath: (id, params) => request(`/map/walk-path/${id}${qs(params)}`),
}
