import { useEffect, useState } from 'react'

import { api } from '../api'
import Hint from './Hint'

/**
 * 메모 사전 — 중개사 메모에서 뽑는 키워드를 **무엇까지 비고에 띄울지** 고른다.
 *
 * ## 사전 자체는 여기서 못 고친다
 *
 * 규칙(정규식)은 `backend/app/services/memo_tags.py` 의 `RULES` 에 있고 코드다.
 * 화면에서 고칠 수 있게 하면 '실제 메모에 재 보고 적중 수를 남긴다' 는 고리가
 * 끊긴다 — 아무 데서나 고칠 수 있으면 아무도 재지 않는다. 이 저장소에서 추측이
 * 틀린 적이 여러 번 있고 그때마다 잰 쪽이 맞았다.
 *
 * 대신 **무엇을 띄울지**는 취향이라 여기서 고른다. 실측에서 제일 많이 걸린 것이
 * '시스템에어컨'(22/50)인데 가격 판단에는 거의 쓸모가 없다. 그런 것을 끄는 자리다.
 *
 * ## 끄는 것은 '안 보여 주기' 지 '안 읽기' 가 아니다
 *
 * 꺼도 원문은 그대로 저장되고 호버에서 보인다. 다시 켜면 그 자리에서 되살아난다.
 * 그래서 끄는 데 망설일 이유가 없다.
 *
 * ## 횟수를 같이 보여 주는 이유
 *
 * 0회인 태그는 **지울 것이거나 패턴이 실제 표기와 어긋난 것**이다. 숫자가 없으면
 * 그 구분이 안 되고, 안 걸리는 규칙이 영원히 남는다.
 */
export default function MemoTagPanel() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [open, setOpen] = useState(false)

  const load = () =>
    api
      .memoTags()
      .then(setData)
      .catch((e) => setErr(e.message))

  useEffect(() => {
    load()
  }, [])

  /* 먼저 화면을 바꾸고 서버를 부른다. 버튼이 한 박자 늦게 움직이면 눌렸는지 모른다.
   *
   * **함수형 갱신을 쓴다.** 렌더 시점의 `data` 로 다음 상태를 만들면 연달아 누를 때
   * 뒤의 것이 앞의 것을 덮는다 — 동 버튼에서 실측으로 겪었다(107·119·130 을 연속으로
   * 누르니 서버에는 셋 다 들어갔는데 화면에는 130 만 켜졌다). 되돌릴 때도 통째로
   * 복원하지 않고 실패한 태그 하나만 되돌린다. */
  const patch = (name, enabled) => (d) =>
    d ? { ...d, tags: d.tags.map((t) => (t.name === name ? { ...t, enabled } : t)) } : d

  const toggle = async (name, next) => {
    setBusy(name)
    setErr(null)
    setData(patch(name, next))
    try {
      await api.setMemoTag(name, next)
    } catch (e) {
      setData(patch(name, !next))
      setErr(`${name} 설정을 저장하지 못했습니다.`)
    } finally {
      setBusy(null)
    }
  }

  if (err && !data) return null // 사전은 곁가지다. 못 읽어도 탭 전체를 막지 않는다.
  if (!data) return null

  const on = data.tags.filter((t) => t.enabled)
  const dead = data.tags.filter((t) => t.n === 0)

  return (
    <section className="card">
      <h2>
        메모 사전
        <span className="muted small">
          {' '}
          {data.tags.length}개 · 켜 둔 것 {on.length}개
        </span>
        <Hint
          notes={[
            '중개사가 매물에 적은 한 줄 메모에서 키워드를 뽑아 매물 순위의 비고에 띄웁니다.',
            '누르면 비고에 띄울지가 바뀝니다. 꺼도 원문은 그대로 저장되고, 다시 켜면 그 자리에서 되살아납니다.',
            '숫자는 쌓인 메모에서 그 키워드가 몇 번 나왔는지입니다. 볼 때마다 다시 셉니다.',
          ]}
        />
      </h2>
      <p className="sub">
        누르면 <b>비고에 띄울지</b>가 바뀝니다. 비고 칸이 좁아 켜 둔 것 중{' '}
        <b>앞 {data.max_badges}개</b>만 배지로 나가고 나머지는 <code>+N</code> 으로
        접힙니다 — 앞 순서일수록 가격에 걸리는 키워드입니다.
      </p>
      {err && <p className="paste-warn">{err}</p>}

      {data.n_memos === 0 ? (
        <p className="empty">
          아직 읽은 메모가 없습니다. 북마클릿(v3 이상)으로 담아 붙여넣으면 쌓입니다.
        </p>
      ) : (
        <>
          <div className="dong-chips">
            {data.tags.map((t) => (
              <button
                key={t.name}
                className={`dong-chip memo-chip${t.enabled ? ' is-on' : ''}${
                  t.n === 0 ? ' is-dead' : ''
                }`}
                aria-pressed={t.enabled}
                disabled={busy === t.name}
                onClick={() => toggle(t.name, !t.enabled)}
                title={
                  `우선순위 ${t.priority}번 · 메모 ${t.n}건에서 나왔습니다.` +
                  (t.n === 0
                    ? ' 한 번도 안 걸렸습니다 — 지울 규칙이거나 패턴이 실제 표기와 어긋난 것입니다.'
                    : '') +
                  (t.enabled ? ' 누르면 비고에서 뺍니다.' : ' 누르면 비고에 띄웁니다.')
                }
              >
                {t.name}
                <i className="memo-chip-n">{t.n}</i>
              </button>
            ))}
          </div>

          <p className="muted small" style={{ marginTop: 10 }}>
            메모 <b>{data.n_memos}건</b>을 읽었고 그중 <b>{data.n_untagged}건</b>은
            어느 키워드에도 안 걸렸습니다
            {dead.length > 0 && (
              <>
                . 한 번도 안 걸린 규칙 <b>{dead.length}개</b>(
                {dead.map((t) => t.name).join(' · ')})
              </>
            )}
            .{' '}
            <button className="linklike" onClick={() => setOpen((v) => !v)}>
              {open ? '사전에 없는 말 접기 ▴' : '사전에 없는 말 보기 ▾'}
            </button>
          </p>

          {open && (
            <div className="memo-unknown">
              <p className="muted small">
                아직 아무 규칙에도 안 걸리는 낱말입니다(2번 이상). 규칙을 늘릴 거리가
                여기 있습니다 — 다만 사전은 코드(<code>app/services/memo_tags.py</code>)
                에 있고, 늘린 뒤에는 <code>python -m scripts.memo_report</code> 로 다시
                재서 적중 수를 주석에 남깁니다. 눈으로 보고 늘리지 않습니다.
              </p>
              {data.unknown.length > 0 ? (
                <div className="dong-chips">
                  {data.unknown.map((u) => (
                    <span className="dong-chip is-static" key={u.word}>
                      {u.word}
                      <i className="memo-chip-n">{u.n}</i>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="muted small">2번 이상 나온 낱말이 없습니다.</p>
              )}

              {data.untagged.length > 0 && (
                <>
                  <p className="muted small" style={{ marginTop: 10 }}>
                    어느 키워드에도 안 걸린 메모
                  </p>
                  <ul className="memo-untagged">
                    {data.untagged.map((m, i) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
