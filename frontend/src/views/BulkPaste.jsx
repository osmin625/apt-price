import { useEffect, useState } from 'react'

import { api } from '../api'
import Hint from '../components/Hint'
import RankTable from '../components/RankTable'

/**
 * 목록을 통째로 붙여넣어 **여러 매물을 한 번에** 줄 세운다.
 *
 * 네이버 부동산은 공개 API 가 없고 자동 수집은 이용약관 문제가 있어 이 프로젝트가
 * 처음부터 제외했다. 하지만 **사용자가 보고 있는 목록을 복사해 붙여넣는 것**은
 * 자동 수집이 아니다. 필터를 건 목록 화면을 그대로 복사하면 그게 곧 스크리닝이다.
 *
 * 한 물건을 중개사 여러 곳이 올리므로 목록에는 같은 매물이 반복된다. 합치지 않으면
 * 순위 상위가 같은 값 여러 줄로 채워져 아무것도 알 수 없다 — 서버에서 합치고
 * 몇 곳에 올라와 있는지를 `x4` 로 표시한다.
 */
export default function BulkPaste({ months, incoming }) {
  const [text, setText] = useState('')
  /* 새로 들어온 것만 볼까.
   *
   * 북마클릿은 누를 때마다 **지금까지 담은 전부**를 클립보드에 넣는다 — 여러 단지를
   * 돌고 마지막에 한 번만 붙여넣게 하려는 것이다. 그 대가로 두 번째 붙여넣기부터는
   * 결과에 이미 본 매물이 섞이고, 새로 뭐가 들어왔는지 눈으로 골라야 했다.
   *
   * 기본을 **새 것만**으로 둔다. 붙여넣은 직후에 궁금한 것은 '이번에 뭐가 늘었나'
   * 이고, 전체 목록은 어차피 매물 순위 탭에 늘 있다. 다만 **숨긴 건수는 적는다** —
   * 몇 건이 어디로 갔는지 안 보이면 읽다 만 줄 알게 된다. */
  const [onlyNew, setOnlyNew] = useState(true)
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [basis, setBasis] = useState('market')
  const [err, setErr] = useState(null)

  /* 바깥(App 의 전역 Ctrl+V)에서 밀어 넣은 텍스트. 탭을 열고 입력칸을 누르는
     과정을 없앤다 — 북마클릿으로 담은 뒤 대시보드에서 그냥 붙여넣으면 끝이다. */
  useEffect(() => {
    if (!incoming) return
    setText(incoming.text)
    run(incoming.text)
    // incoming.at 이 바뀔 때마다 — 같은 글을 다시 붙여넣어도 동작해야 한다
  }, [incoming?.at])

  /* 클립보드에서 바로 가져오기. Ctrl+V 조차 생략한다.
     localhost 는 보안 컨텍스트라 readText 가 허용된다. 권한이 막히면 그렇게 말한다. */
  const fromClipboard = async () => {
    try {
      const t = await navigator.clipboard.readText()
      if (!t.trim()) return setErr('클립보드가 비어 있습니다.')
      setText(t)
      run(t)
    } catch (e) {
      setErr('클립보드를 읽지 못했습니다. 입력칸에 Ctrl+V 로 붙여넣어 주세요.')
    }
  }

  const run = async (value, nextBasis = basis) => {
    const t = (value ?? text).trim()
    if (!t) return
    setBusy(true)
    setErr(null)
    try {
      setRes(await api.parseBulk(t, { months, basis: nextBasis }))
    } catch (e) {
      setErr(e.message)
      setRes(null)
    } finally {
      setBusy(false)
    }
  }

  /* `is_new` 가 없는 응답(저장이 실패한 줄, 또는 옛 백엔드)은 **숨기지 않는다.**
     모르는 것을 '이미 읽은 것' 으로 치면 읽은 매물이 조용히 사라진다. */
  const items = res?.items || []
  const newCount = items.filter((i) => i.is_new !== false).length
  const shownItems = onlyNew ? items.filter((i) => i.is_new !== false) : items
  const hidden = items.length - shownItems.length

  return (
    <div className="card">
      <h2>
        여러 매물 한 번에
        <Hint
          notes={[
            '네이버 부동산 목록 화면을 통째로 복사해 붙여넣으면 매물을 하나씩 읽어 적정가를 진단하고 줄 세웁니다.',
            '한 물건을 중개사 여러 곳이 올린 경우는 합칩니다(x2 표시). 층을 저/중/고로만 밝힌 매물은 같은 구간이 같은 대표층이 되므로, 가격까지 같으면 합쳐질 수 있습니다.',
            '읽은 호가는 누적되어 동별 호가 추이로도 쌓입니다.',
          ]}
        />
      </h2>

      <div className="bulk-actions">
        <button className="ghost" onClick={fromClipboard} disabled={busy}>
          {busy ? '읽는 중…' : '📋 클립보드에서 가져오기'}
        </button>
        <span className="muted small">
          또는 아래에 붙여넣기. 대시보드 아무 곳에서나 <b>Ctrl+V</b> 해도 됩니다.
        </span>
      </div>

      <textarea
        className="bulk-input"
        rows={res ? 2 : 4}
        value={text}
        placeholder={'네이버 부동산 목록을 그대로 복사해 붙여넣으세요.\n단지명 / 매매가 / 면적·층이 한 덩어리인 형태면 됩니다.'}
        onChange={(e) => setText(e.target.value)}
        onPaste={(e) => {
          const v = e.clipboardData.getData('text')
          if (v && v.trim()) {
            e.preventDefault()
            setText(v)
            run(v)
          }
        }}
      />

      <div className="cmp-actions" style={{ marginTop: 8, paddingTop: 0, border: 'none' }}>
        <span className="muted small cmp-hint">
          {busy
            ? <span className="live">읽는 중…</span>
            : res
              ? `${res.found}건 발견 · 중복 ${res.merged_away}건 합쳐 ${res.count}건 · 새로 저장 ${res.new_saved}건` +
                (onlyNew && hidden > 0 ? ` · 이미 읽은 ${hidden}건 숨김` : '')
              : '붙여넣는 즉시 읽습니다.'}
        </span>
        {res && (
          <>
            {[
              [true, `새로 ${newCount}건`],
              [false, `전부 ${res.items.length}건`],
            ].map(([k, t]) => (
              <button
                key={String(k)}
                className={`chip${onlyNew === k ? ' on' : ''}`}
                onClick={() => setOnlyNew(k)}
              >
                {t}
              </button>
            ))}
            {[
              ['market', '실거래 기준'],
              ['factor', '요인 기준'],
            ].map(([k, t]) => (
              <button
                key={k}
                className={`chip${basis === k ? ' on' : ''}`}
                onClick={() => {
                  setBasis(k)
                  run(undefined, k)
                }}
              >
                {t}
              </button>
            ))}
            <button
              className="ghost"
              onClick={() => {
                setText('')
                setRes(null)
              }}
            >
              지우기
            </button>
          </>
        )}
      </div>

      {err && <p className="empty">{err}</p>}

      {res?.items?.length > 0 && (
        <div style={{ marginTop: 10 }}>
          {shownItems.length > 0 ? (
            <RankTable items={shownItems} basis={basis} />
          ) : (
            <p className="empty">
              새로 들어온 매물이 없습니다. 담아 둔 {res.items.length}건은 이미 읽은
              것입니다 — <b>전부</b>를 누르면 보입니다.
            </p>
          )}
        </div>
      )}

      {res?.skipped?.length > 0 && (
        <p className="paste-warn" style={{ marginTop: 8 }}>
          {res.skipped.length}건은 읽지 못했습니다 — {res.skipped.slice(0, 3).map((s) => s.reason).join(', ')}
        </p>
      )}
    </div>
  )
}
