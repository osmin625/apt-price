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

/**
 * 정적 모드 — 백엔드 없이 스냅샷 파일만 읽는다.
 *
 * 모델을 돌리는 것과 결과를 보여 주는 것은 필요한 것이 다르다. 적합은
 * numpy·pandas·statsmodels 와 실거래 11만 건, 수십 초의 계산이 필요하지만,
 * **결과를 보는 쪽은 JSON 한 묶음이면 된다.** 그래서 무거운 쪽은 로컬에 두고
 * 가벼운 쪽만 어디서나 열리게 만든다.
 *
 * `VITE_DATA_MODE=static` 으로 빌드하면 켜진다. 기본은 동적(로컬)이다.
 */
export const STATIC_MODE = import.meta.env.VITE_DATA_MODE === 'static'

/**
 * 정적 사이트에 지도 탭을 실을지.
 *
 * 지도만 **키가 필요하다.** 카카오 지도를 띄우려면 JS 키가 번들에 들어가야 하고,
 * 공개 사이트라면 그 키는 누구나 읽을 수 있다. JS 키는 원래 클라이언트에 노출되는
 * 키라(카카오 지도를 쓰는 모든 사이트의 소스에 보인다) 그 자체가 사고는 아니지만,
 * 보호 수단인 도메인 허용목록이 Referer 기반이어서 우회가 불가능하지는 않다.
 *
 * 그러니 **기본은 끈 상태**로 두고, 켜는 것을 의도적인 행위로 만든다. 켜는 방법은
 * `frontend/.env.static.local`(gitignore 됨)을 만들어 키와 이 변수를 같이 넣는 것이다.
 * 자세한 것은 docs/deploy.md.
 *
 * 백엔드가 지오코딩에 쓰는 `KAKAO_REST_KEY` 는 **다른 키**이고 backend/.env 에만
 * 있다. 이쪽으로는 절대 나가지 않는다.
 */
export const STATIC_MAP = import.meta.env.VITE_STATIC_MAP === '1'

/**
 * 요청을 스냅샷 파일 경로로. **`scripts/export_static.py` 의 `target_of()` 와
 * 반드시 같아야 한다.** 한쪽만 바꾸면 화면은 404 를 받고, 그건 "데이터가 없다"
 * 로 보인다 — 조용히 틀리는 쪽이다. 그래서 규칙을 양쪽 주석에 같이 적는다.
 *
 *   /health                                  -> health/default.json
 *   /model/factors?months=12                 -> model/factors/months=12.json
 *   /complexes/14?months=24                  -> complexes/14/months=24.json
 *   /quotes/ranking?months=12&basis=market   -> quotes/ranking/basis=market~months=12.json
 *
 * 쿼리는 **이름순으로 정렬**한다. 파라미터를 넣는 순서가 화면마다 다를 수 있어서,
 * 정렬하지 않으면 같은 요청이 다른 파일을 가리킨다.
 */
function snapshotPath(path) {
  const [p, query] = path.split('?')
  const sp = new URLSearchParams(query || '')
  const keys = [...sp.keys()].sort()
  const name = keys.length ? keys.map((k) => `${k}=${sp.get(k)}`).join('~') : 'default'
  // import.meta.env.BASE_URL 은 항상 '/' 로 끝난다. GitHub Pages 처럼
  // 하위 경로에 올릴 때 이걸 안 쓰면 루트를 찾아가서 전부 404 가 된다.
  return `${import.meta.env.BASE_URL}snapshot${p}/${name}.json`
}

async function request(path, options = {}) {
  const write = options.method && options.method !== 'GET'

  if (STATIC_MODE) {
    if (write) {
      // 여기 오면 정적에서 숨겼어야 할 화면이 남아 있다는 뜻이다. 조용히
      // 실패하지 않고 사실을 적는다.
      throw new ApiError(
        '이 페이지는 내보낸 스냅샷이라 값을 바꿀 수 없습니다. 로컬 대시보드에서 하세요.',
        405,
      )
    }
    const url = snapshotPath(path)
    let res
    try {
      res = await fetch(url)
    } catch (e) {
      throw new ApiError('스냅샷 파일을 읽을 수 없습니다.', 0)
    }
    if (!res.ok) {
      throw new ApiError(
        `이 조합은 스냅샷에 없습니다 (${path}). 내보내기 목록에 넣고 다시 내보내야 합니다.`,
        res.status,
      )
    }
    return res.json()
  }

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

/**
 * 스냅샷을 언제 어떤 데이터로 내보냈는지. 정적 모드에서만 있다.
 *
 * 이걸 화면에 적는 이유: 정적 사이트는 **보고 있는 값이 언제 것인지 알 수 없다.**
 * 로컬은 부를 때마다 최신이지만 여기는 마지막 내보내기 시점에 멈춰 있다. 그걸
 * 적지 않으면 오래된 값을 최신으로 읽게 된다 — 추정을 사실처럼 보여 주는 것과
 * 같은 종류의 잘못이다.
 */
export async function snapshotMeta() {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}snapshot/meta.json`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}
