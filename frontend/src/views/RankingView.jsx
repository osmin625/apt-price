import { useEffect, useState } from 'react'

import { api, STATIC_MODE } from '../api'
import Hint from '../components/Hint'
import Loading from '../components/Loading'
import RankTable from '../components/RankTable'

/**
 * 지금까지 붙여넣은 **모든 매물**의 순위.
 *
 * 붙여넣기마다 `Quote` 로 남으므로 순위를 따로 저장할 필요가 없다. 기간을 바꾸면
 * 그 기간의 실거래로 전부 다시 계산된다 — 저장된 것은 매물이지 평가가 아니다.
 */
export default function RankingView({ months, setMonths, onSelect }) {
  const [basis, setBasis] = useState('market')
  const [days, setDays] = useState('')
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [err, setErr] = useState(null)

  /**
   * 삭제는 **화면에서 먼저 지우고** 서버를 부른다.
   *
   * 삭제 후 순위를 다시 매기려면 남은 매물 전체를 재평가해야 해서 몇 초가 걸린다.
   * 그동안 아무 반응이 없으면 눌린 건지 알 수 없다. 지운 행은 즉시 사라지게 하고,
   * 순위 번호가 다시 매겨지는 동안만 표를 흐리게 한다.
   */
  const remove = async (id) => {
    setDeleting(id)
    const before = data
    setData((d) => (d ? { ...d, items: d.items.filter((i) => i.quote_id !== id), count: d.count - 1 } : d))
    try {
      await api.deleteQuote(id)
      await api.quoteRanking({ months, basis, days: days || undefined }).then(setData)
    } catch (e) {
      setErr(e.message)
      setData(before)
    } finally {
      setDeleting(null)
    }
  }

  /* 저장한 비고를 **목록 상태에도** 넣는다.
     안 그러면 기준을 바꿨다가 돌아왔을 때 방금 적은 것이 사라진 것처럼 보인다 —
     서버에는 남아 있지만 화면이 옛 응답을 들고 있기 때문이다. */
  const noteSaved = (key, text) =>
    setData((d) =>
      d
        ? {
            ...d,
            items: d.items.map((i) =>
              i.note_key &&
              i.note_key.complex_id === key.complex_id &&
              i.note_key.dong === key.dong &&
              i.note_key.area_key === key.area_key &&
              i.note_key.floor === key.floor
                ? { ...i, note: text }
                : i,
            ),
          }
        : d,
    )

  const load = () => {
    setBusy(true)
    setErr(null)
    api
      .quoteRanking({ months, basis, days: days || undefined })
      .then(setData)
      .catch((e) => {
        setErr(e.message)
        setData(null)
      })
      .finally(() => setBusy(false))
  }

  useEffect(load, [months, basis, days])

  return (
    <div className="card">
      <h2>
        매물 순위
        {data && (
          <span className="muted small">
            {' '}
            {data.count}건 · 최근 {months}개월 실거래 기준
            {data.grouped_away > 0 && ` · 같은 층대로 접힌 매물 ${data.grouped_away}건`}
            {data.factor_months != null && data.factor_months !== months && (
              <>
                {' · '}
                <span data-tone="warn">요인 기준은 {data.factor_months}개월 적합</span>
              </>
            )}
            {data.revised_units > 0 && ` · 호가 바뀐 매물 ${data.revised_units}건`}
          </span>
        )}
        <Hint
          notes={[
            '매물 분석 탭에서 붙여넣은 매물이 모두 여기 쌓입니다. 같은 호가는 중복으로 쌓이지 않습니다.',
            '한 (단지·동·평형·층대)당 한 줄입니다. 가장 최근 확인된 매물을, 같은 날이면 가장 싼 쪽을 대표로 세웁니다.',
            '접힌 매물은 호가 옆 건수 배지에 마우스를 올리면 전부 펼쳐집니다. 합친 게 아니라 접은 것이라 한 건도 사라지지 않습니다 — 다만 그 줄을 지우면 접힌 매물이 함께 지워집니다.',
            '같은 집이 값을 바꿔 다시 올라온 경우는 ▼ 배지로 변동을 표시합니다. 옛 호가와 올라와 있던 기간이 겹치지 않을 때만 같은 집으로 봅니다.',
            '더 저평가된 매물이 위로 갑니다. 분석 기간을 바꾸면 그 기간의 실거래로 전부 다시 계산됩니다.',
            '요인 기준 열은 헤도닉 적합에서 나오는데, 적합은 무거워서 이미 계산된 것만 씁니다. 요청한 기간의 적합이 아직 없으면 다른 기간 것을 쓰고 제목에 그 사실을 적습니다 — 시장 분석 탭을 같은 기간으로 한 번 열면 맞춰집니다.',
          ]}
        />
      </h2>

      <div className="filters">
        <div className="field">
          <label htmlFor="rk-months">분석 기간</label>
          <select id="rk-months" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            <option value={12}>최근 12개월</option>
            <option value={24}>최근 24개월</option>
            <option value={36}>최근 36개월</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="rk-days">확인일자</label>
          <select id="rk-days" value={days} onChange={(e) => setDays(e.target.value)}>
            <option value="">전체</option>
            <option value="7">최근 7일 확인</option>
            <option value="14">최근 14일 확인</option>
            <option value="30">최근 30일 확인</option>
          </select>
        </div>
        <div className="field">
          <label>순위 기준</label>
          <div className="rank-basis" style={{ margin: 0 }}>
            {[
              ['market', '실거래 기준'],
              ['factor', '요인 기준'],
            ].map(([k, t]) => (
              <button key={k} className={`chip${basis === k ? ' on' : ''}`} onClick={() => setBasis(k)}>
                {t}
              </button>
            ))}
          </div>
        </div>
        {/* 정적 사이트에서는 다시 부를 것이 없다 — 같은 파일을 또 읽을 뿐인데
            '새로고침' 은 다시 계산한다는 뜻으로 읽힌다. */}
        {!STATIC_MODE && (
          <button className="ghost" onClick={load} disabled={busy}>
            {busy ? '계산 중…' : '새로고침'}
          </button>
        )}
      </div>

      {err && <p className="empty">{err}</p>}
      {busy && !data && (
        <Loading
          label="매물별 적정가를 계산하는 중"
          hint="매물마다 같은 단지·같은 평형의 실거래를 모아 시점과 층을 보정한 뒤 중앙값을 냅니다. 매물이 많을수록 오래 걸립니다."
        />
      )}

      {data && data.count === 0 && (
        <p className="empty">
          아직 쌓인 매물이 없습니다.{' '}
          {STATIC_MODE ? (
            <>
              로컬 대시보드의 <b>매물 분석</b> 탭에서 붙여넣고 다시 내보내면 여기 보입니다.
            </>
          ) : (
            <>
              <b>매물 분석</b> 탭에서 매물을 붙여넣으면 여기 쌓입니다.
            </>
          )}
        </p>
      )}

      {data?.count > 0 && (
        <>
          {deleting != null && (
            <p className="muted small live" style={{ margin: '0 0 6px' }}>
              삭제 후 남은 매물로 순위를 다시 매기는 중입니다…
            </p>
          )}
          <RankTable
            items={data.items}
            basis={basis}
            /* 정적에서는 지울 수 없다. 눌리는데 실패하는 버튼을 두지 않는다. */
            onDelete={STATIC_MODE ? null : remove}
            deleting={deleting}
            onSelect={onSelect}
            onNoteSaved={noteSaved}
          />
          {data.skipped?.length > 0 && (
            <p className="paste-warn" style={{ marginTop: 8 }}>
              {data.skipped.length}건은 평가하지 못했습니다 —{' '}
              {[...new Set(data.skipped.map((s) => s.reason))].join(', ')}
            </p>
          )}
        </>
      )}
    </div>
  )
}
