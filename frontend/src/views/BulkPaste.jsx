import { useState } from 'react'

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
export default function BulkPaste({ months }) {
  const [text, setText] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [basis, setBasis] = useState('market')
  const [err, setErr] = useState(null)

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
              ? `${res.found}건 발견 · 중복 ${res.merged_away}건 합쳐 ${res.count}건 · 새로 저장 ${res.new_saved}건`
              : '붙여넣는 즉시 읽습니다.'}
        </span>
        {res && (
          <>
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
          <RankTable items={res.items} basis={basis} />
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
