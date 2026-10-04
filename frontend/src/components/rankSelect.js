/**
 * 순위표에서 **Ctrl(⌘)+클릭으로 좁히기**, 그리고 **열 머리말로 정렬**.
 *
 * ## 왜 셀을 누르나
 *
 * 순위표를 보다가 "이것만 모아 보자" 가 되는 순간은 거의 항상 **그 값을 보고 있을
 * 때**다. 필터를 따로 두면 단지명·동·면적을 기억해 다른 곳에 다시 입력해야 한다.
 * 브라우저의 Ctrl+클릭('다르게 열기')과 같은 결이라 설명 없이도 손이 간다.
 *
 * 수식키 없는 클릭은 원래 하던 일(단지명은 상세로 가기)을 그대로 한다.
 *
 * ## 좁히기는 **덮어쓴다**
 *
 * 동을 누르면 `{단지, 동}`, 면적을 누르면 `{단지, 면적}` 이 된다. 쌓이지 않는다 —
 * 쌓이게 하면 "지금 뭐가 걸려 있지" 를 화면에서 읽을 수 없고, 되돌리려면 누른
 * 순서를 기억해야 한다. 한 번 누르면 한 가지로 좁혀지는 쪽이 예측된다.
 *
 * 면적은 **반올림 ㎡**(`area_key`)로 묶는다. 같은 평형인데 84.78 과 84.99 로 적히는
 * 일이 흔하고, 그것들을 따로 보면 '같은 평형만 모아 보기' 가 안 된다.
 *
 * ## 표와 카드가 같은 함수를 쓴다
 *
 * 각자 쓰면 한쪽만 고쳐져 창 폭에 따라 동작이 달라진다 — `rankBasis.js` 와 같은
 * 이유다. 한쪽에 두고 다른 쪽에서 가져오면 순환 import 가 된다(RankTable 이
 * RankCards 를 쓴다). 그래서 따로 둔다.
 */

export const ONLY_HINT = '클릭: 단지 상세 · Ctrl(⌘)+클릭: 이 단지만 보기'
export const DONG_HINT = 'Ctrl(⌘)+클릭: 이 단지의 이 동만 보기'
export const AREA_HINT = 'Ctrl(⌘)+클릭: 이 단지의 이 면적만 보기'

const isMod = (e) => e.ctrlKey || e.metaKey

/** 단지명. 수식키 없이 누르면 상세로 간다. */
export function nameClick(e, item, onSelect, onScope) {
  if (isMod(e) && onScope) {
    // 버튼이라 기본 동작은 없지만, 브라우저나 확장이 Ctrl+클릭에 뭔가 붙이는 경우가 있다.
    e.preventDefault()
    e.stopPropagation()
    onScope({ complexId: item.complex_id })
    return
  }
  onSelect(item.complex_id)
}

/** 동·면적처럼 **수식키를 눌렀을 때만** 하는 일이 있는 셀. */
export function scopeClick(e, onScope, scope) {
  if (!isMod(e) || !onScope) return
  e.preventDefault()
  e.stopPropagation()
  onScope(scope)
}

/** 좁힌 범위에 들어가는 줄인가. `null` 이면 전부. */
export function inScope(item, scope) {
  if (!scope) return true
  if (item.complex_id !== scope.complexId) return false
  if (scope.dong != null && String(item.dong ?? '') !== String(scope.dong)) return false
  if (scope.areaKey != null && areaKeyOf(item) !== scope.areaKey) return false
  return true
}

/** 면적 묶음 키. 서버가 주면 그것을, 없으면 반올림해서 쓴다. */
export const areaKeyOf = (i) =>
  i.note_key?.area_key ?? (i.exclusive_area != null ? Math.round(i.exclusive_area) : null)

/** 좁힌 범위를 한 줄로. 화면에 그대로 적는다. */
export function scopeLabel(scope, name) {
  if (!scope) return ''
  const parts = [name || '단지']
  if (scope.dong != null) parts.push(`${scope.dong}동`)
  if (scope.areaKey != null) parts.push(`전용 ${scope.areaKey}㎡`)
  return parts.join(' · ')
}

/* ── 정렬 ────────────────────────────────────────────────────────────
 *
 * 기본은 **순위 순서**(서버가 괴리율로 매긴 것)다. 머리말을 누르면 그 열로 정렬하고,
 * 다시 누르면 반대로, 한 번 더 누르면 **기본으로 돌아온다.** 세 번째 누름을 둔 이유:
 * 안 두면 한 번 정렬한 뒤 원래 순서로 돌아갈 길이 없어 새로고침을 하게 된다.
 *
 * 값이 없는 줄(`null`)은 방향과 상관없이 **항상 뒤로** 보낸다. 오름차순에서 맨 위에
 * '—' 가 줄줄이 오면 정렬이 깨진 것처럼 보인다.
 */
export const SORT_COLS = {
  complex_name: { label: '단지', get: (i) => i.complex_name || '', type: 'text' },
  dong: { label: '동', get: (i) => (i.dong ? Number(i.dong) || i.dong : null), type: 'mixed' },
  exclusive_area: { label: '전용', get: (i) => i.exclusive_area, type: 'num' },
  floor: { label: '층', get: (i) => i.floor, type: 'num' },
  asking_price: { label: '호가', get: (i) => i.asking_price, type: 'num' },
  confirmed_on: { label: '확인', get: (i) => i.confirmed_on || null, type: 'text' },
  fair: { label: '적정', get: (i, f) => (f ? i.factor_price : i.fair_price), type: 'num' },
  gap: { label: '대비', get: (i, f) => (f ? i.gap_factor_pct : i.gap_pct), type: 'num' },
  added_on: { label: '추가', get: (i) => i.added_on || null, type: 'text' },
}

export function nextSort(cur, key) {
  if (!cur || cur.key !== key) return { key, dir: 'asc' }
  if (cur.dir === 'asc') return { key, dir: 'desc' }
  return null // 기본(순위)으로
}

export function applySort(items, sort, isFactor) {
  if (!sort || !SORT_COLS[sort.key]) return items
  const { get, type } = SORT_COLS[sort.key]
  const sign = sort.dir === 'desc' ? -1 : 1
  return [...items].sort((a, b) => {
    const x = get(a, isFactor)
    const y = get(b, isFactor)
    // 값 없는 줄은 방향과 상관없이 뒤로.
    if (x == null && y == null) return 0
    if (x == null) return 1
    if (y == null) return -1
    if (type === 'num' || (type === 'mixed' && typeof x === 'number' && typeof y === 'number')) {
      return (x - y) * sign
    }
    return String(x).localeCompare(String(y), 'ko') * sign
  })
}
