import { fmt } from './Charts'

/**
 * 메모 키워드로 **빼는** 필터.
 *
 * ## 고르는 게 아니라 빼는 것이다
 *
 * '세안고 매물만 보기' 보다 '세안고는 빼고 보기' 가 실제로 하는 일이다. 매물을 고를
 * 때 쓰는 문장이 "전세 낀 건 못 들어가니까 빼고" 쪽이기 때문이다. 포함 필터로 만들면
 * 키워드가 아예 없는 매물(메모가 없는 것)이 통째로 사라지는데, 그건 거의 절반이다.
 *
 * 그래서 **누르면 숨긴다.** 누른 칩은 지워진 모양(취소선)이 되어 지금 무엇을 빼고
 * 있는지 한눈에 보인다.
 *
 * ## 지금 목록에 있는 키워드만 띄운다
 *
 * 사전에는 18개가 있지만 쌓인 매물에 안 나오는 것도 있다. 0건짜리 칩을 눌러 봐야
 * 아무 일도 안 일어나므로, 눌리는데 반응 없는 버튼을 두지 않는다 — 이 저장소가
 * 탭을 고를 때 쓰는 규칙과 같다.
 *
 * 순서는 **건수가 많은 것부터**다. 비고에 나가는 우선순위(가격에 걸리는 순)와는
 * 다른데, 여기서 찾는 것은 '무엇이 많이 끼어 있나' 이기 때문이다. 정적 사이트에서도
 * 돌아야 해서 사전 순서를 서버에 묻지 않는다.
 *
 * ## 숫자는 **거르기 전 전체** 기준이다
 *
 * 지금 보이는 목록 기준으로 세면 누를 때마다 다른 칩의 숫자가 같이 흔들리고, 이미
 * 뺀 칩은 0이 된다. 그래서 전체 기준으로 고정한다.
 *
 * 대신 숫자를 더해도 숨김 건수와 안 맞는다 — 한 매물에 키워드가 여럿 붙기 때문이다
 * (실측: 세안고 12 + 올수리 21 + 전망 15 = 48 인데 실제로 숨은 것은 39건). 그래서
 * 칩 숫자는 '이 키워드가 붙은 매물 수' 라고만 말하고, **실제로 몇 건이 숨었는지는
 * 한 곳에서만** 적는다. 두 군데서 다른 숫자를 말하면 어느 쪽이 맞는지 알 수 없다.
 */
export default function TagFilter({ items, excluded, onToggle, onClear, hidden }) {
  const counts = new Map()
  for (const i of items || []) {
    for (const t of i.note_tags || []) counts.set(t, (counts.get(t) || 0) + 1)
  }
  // 빼 둔 키워드는 지금 목록에 안 보이므로 counts 에 없다. 그래도 칩은 남겨야
  // 다시 켤 수 있다 — 사라지면 되돌릴 길이 없다.
  for (const t of excluded) if (!counts.has(t)) counts.set(t, 0)
  if (!counts.size) return null

  const tags = [...counts.entries()].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ko'),
  )

  return (
    <div className="tag-filter">
      <span className="muted small tf-label">키워드 빼기</span>
      {tags.map(([t, n]) => (
        <button
          key={t}
          className={`chip tf-chip${excluded.has(t) ? ' off' : ''}`}
          aria-pressed={excluded.has(t)}
          onClick={() => onToggle(t)}
          title={
            `'${t}' 가 붙은 매물 ${fmt(n)}건` +
            (excluded.has(t)
              ? ' — 지금 숨기고 있습니다. 누르면 다시 보입니다.'
              : ' — 누르면 순위에서 뺍니다. 키워드가 여럿 붙은 매물이 있어' +
                ' 숨는 건수는 이보다 적을 수 있습니다.')
          }
        >
          {t}
          <i className="tf-n">{fmt(n)}</i>
        </button>
      ))}
      {excluded.size > 0 && (
        <button className="linklike tf-clear" onClick={onClear}>
          {hidden > 0 ? `${fmt(hidden)}건 숨김 · 전부 되돌리기` : '전부 되돌리기'}
        </button>
      )}
    </div>
  )
}
