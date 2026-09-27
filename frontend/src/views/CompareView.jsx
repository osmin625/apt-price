import { useEffect, useMemo, useState } from 'react'

import { api } from '../api'
import { eok, fmt } from '../components/Charts'
import Hint from '../components/Hint'
import BulkPaste from './BulkPaste'
import FairCard from '../components/FairVerdict'

const BLANK = { complex_id: '', exclusive_area: '', floor: '', asking_price: '', dong: '', areaOpts: [] }
const SIDE_BLANK_FILTER = { q: '', line: '', station: '', household_band: '' }

/**
 * 매물 분석 — 적정가 진단과 A·B 요인 비교를 한 화면에서.
 *
 * 둘은 **다른 질문의 답**이라 원래 탭이 갈려 있었는데, 실제로는 같은 매물에 대해
 * 연달아 묻게 되는 질문이라 입력을 두 번 하게 됐다.
 *
 * - **적정가 진단**: 그 단지 같은 평형의 최근 실거래 대비 이 호가가 적정한가.
 *   단지 고유 프리미엄(학군·브랜드·재건축 기대)을 이미 인정하고 들어간다.
 * - **요인별 비교**: A와 B의 평당가 차이를 면적·층·거리·연식·세대수·노선·구로 쪼개
 *   어느 쪽이 싼가. 단지 프리미엄을 빼고 펀더멘털만 본다.
 *
 * 한쪽만 채우면 그쪽 진단만, 양쪽을 채우면 진단 두 장 + 비교까지 나온다.
 */
export default function CompareView({ months: initialMonths, meta, onSelect }) {
  // 기간은 이 화면에서 직접 고른다. 기본 12개월로는 거래가 적은 단지가 자주
  // 모델에서 빠지는데, 그때마다 다른 탭으로 가서 바꾸게 할 수는 없다.
  const [months, setMonths] = useState(Math.max(initialMonths, 24))
  const [complexes, setComplexes] = useState([])
  const [a, setA] = useState(BLANK)
  const [b, setB] = useState(BLANK)
  const [fa, setFa] = useState(SIDE_BLANK_FILTER)
  const [fb, setFb] = useState(SIDE_BLANK_FILTER)
  const [result, setResult] = useState(null)
  const [evalA, setEvalA] = useState(null)
  const [evalB, setEvalB] = useState(null)
  const [saved, setSaved] = useState([])
  // 순위 기준. 두 기준이 다른 순서를 내는데, 어긋나는 것 자체가 정보다.
  const [basis, setBasis] = useState('market')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState({ a: false, b: false, cmp: false })
  // 오류가 났을 때만 쓰는 재시도 스위치. 값이 바뀌면 자동 계산 훅이 다시 돈다.
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    api
      .complexes({ months: 120, sort: 'name', limit: 1000 })
      .then((d) => setComplexes(d.items || []))
      .catch(() => setComplexes([]))
  }, [])

  const reloadSaved = () =>
    api
      .listings({ months, basis })
      .then((d) => setSaved(d.items || []))
      .catch(() => {})
  useEffect(() => {
    reloadSaved()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [months, basis])

  const loadAreas = (which, id) => {
    const setter = which === 'a' ? setA : setB
    if (!id) return setter((s) => ({ ...s, areaOpts: [], dongOpts: [] }))
    api
      .areaTypes(id)
      .then((d) => setter((s) => ({ ...s, areaOpts: d.items || [] })))
      .catch(() => setter((s) => ({ ...s, areaOpts: [] })))
    // 동 목록은 역거리를 함께 준다. 사용자가 동을 고르면 그 값을 바로 쓴다.
    api
      .dongs(id)
      .then((d) =>
        setter((s) => ({
          ...s,
          dongOpts: d.items || [],
          dongSpread: d.spread_min,
          dongPremSpread: d.premium_spread_pct,
        })),
      )
      .catch(() => setter((s) => ({ ...s, dongOpts: [], dongSpread: null })))
  }

  /**
   * 붙여넣기 파싱 결과를 한쪽에 밀어 넣는다.
   *
   * 단지 목록은 검색어로 걸러지므로, 채워 넣은 단지가 현재 필터에 안 걸리면
   * 선택은 됐는데 목록에는 안 보이는 상태가 된다. 그래서 필터를 비우고
   * 검색어를 그 단지명으로 바꿔 눈에 보이게 한다.
   */
  const applyParsed = (which, p) => {
    const setter = which === 'a' ? setA : setB
    const setFilter = which === 'a' ? setFa : setFb
    setter({
      complex_id: p.complex_id ? String(p.complex_id) : '',
      exclusive_area: p.exclusive_area ?? '',
      floor: p.floor ?? '',
      asking_price: p.asking_price ?? '',
      dong: p.dong ?? '',
      dongWalk: p.dong_walk_min ?? null,
      centerWalk: p.complex_walk_min ?? null,
      areaOpts: p.area_options ?? [],
      dongOpts: [],
      // 경고를 필드별로 묶어 둔다. 각 값 옆 ⓘ 에 그대로 꽂는다.
      notes: (p.warnings ?? []).reduce((acc, w) => {
        const k = w.field ?? 'general'
        ;(acc[k] ||= []).push(w.text)
        return acc
      }, {}),
    })
    if (p.complex_id) loadAreas(which, p.complex_id)
    if (p.complex_id) {
      // 검색어는 응답의 이름을 그대로 쓴다. `complexes` 에서 찾으면, 목록이 아직
      // 안 받아진 상태에서 붙여넣었을 때 빈 문자열이 되어 615곳이 그대로 남는다.
      setFilter({ ...SIDE_BLANK_FILTER, q: p.complex_name ?? '' })
    }
  }

  // 비교는 단지·면적만 있으면 되고, 적정가 진단은 **호가가 있어야** 한다.
  // 괴리율을 낼 대상이 없으면 진단 자체가 성립하지 않는다.
  const canCompare = !!(a.complex_id && a.exclusive_area && b.complex_id && b.exclusive_area)
  const canEval = (s) => !!(s.complex_id && s.exclusive_area && s.asking_price)

  const pack = (s) => ({
    complex_id: Number(s.complex_id),
    exclusive_area: Number(s.exclusive_area),
    floor: s.floor === '' ? null : Number(s.floor),
    asking_price: s.asking_price === '' ? null : Number(s.asking_price),
    // 동이 있으면 역거리를 그 동 좌표로 잡는다. 없으면 서버가 단지 중심점을 쓴다.
    dong: s.dong === '' ? null : s.dong,
  })

  /**
   * 입력이 갖춰지면 알아서 계산한다. 버튼을 누르게 하면 붙여넣기로 줄인 손을
   * 다시 쓰게 만드는 셈이다.
   *
   * 두 가지를 반드시 지켜야 한다.
   *
   * - **디바운스**: 직접 입력 칸을 타이핑하면 글자마다 요청이 나간다. 진단은 가볍지만
   *   비교는 헤도닉 적합이라 수 초씩 걸려서 그대로 두면 서버가 줄줄이 밀린다.
   * - **늦게 온 응답 버리기**: 느린 요청이 빠른 요청보다 나중에 도착하면 화면이
   *   이전 입력의 결과로 되돌아간다. `alive` 로 정리 시점에 끊는다.
   */
  const useAutoRun = (enabled, call, setValue, setBusyFlag, delay, deps) => {
    useEffect(() => {
      if (!enabled) {
        setValue(null)
        setBusyFlag(false)
        return
      }
      let alive = true
      setBusyFlag(true)
      const timer = setTimeout(() => {
        call()
          .then((d) => alive && setValue(d))
          .catch((e) => {
            if (!alive) return
            setValue(null)
            setError(e.message)
          })
          .finally(() => alive && setBusyFlag(false))
      }, delay)
      return () => {
        alive = false
        clearTimeout(timer)
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps)
  }

  // 진단은 단지·평형 거래만 훑으므로 빠르다. 비교는 모델 적합이라 느리니 더 기다린다.
  useAutoRun(
    canEval(a),
    () => api.evaluate(pack(a), { months }),
    setEvalA,
    (v) => setBusy((s) => ({ ...s, a: v })),
    400,
    [a.complex_id, a.exclusive_area, a.floor, a.asking_price, months, retry],
  )
  useAutoRun(
    canEval(b),
    () => api.evaluate(pack(b), { months }),
    setEvalB,
    (v) => setBusy((s) => ({ ...s, b: v })),
    400,
    [b.complex_id, b.exclusive_area, b.floor, b.asking_price, months, retry],
  )
  useAutoRun(
    canCompare,
    () => api.compare({ a: pack(a), b: pack(b), months }),
    setResult,
    (v) => setBusy((s) => ({ ...s, cmp: v })),
    800,
    [
      a.complex_id, a.exclusive_area, a.floor, a.dong,
      b.complex_id, b.exclusive_area, b.floor, b.dong,
      months, retry,
    ],
  )

  // 새 계산이 시작되면 이전 오류 문구는 치운다.
  useEffect(() => setError(null), [
    a.complex_id, a.exclusive_area, b.complex_id, b.exclusive_area, months, retry,
  ])

  // 저장 결과를 버튼에 되돌린다. 눌렀는데 아무 반응이 없으면 됐는지 안 됐는지
  // 알 수가 없다 — 실제로 `dong` 컬럼이 없어 500 이 나던 동안에도 화면은 조용했다.
  const [savedFlash, setSavedFlash] = useState({})
  const saveSide = async (s, tag) => {
    if (!canEval(s)) return
    setSavedFlash((f) => ({ ...f, [tag]: 'saving' }))
    try {
      await api.saveListing({ ...pack(s), label: tag }, { months })
      await reloadSaved()
      setSavedFlash((f) => ({ ...f, [tag]: 'done' }))
      setTimeout(() => setSavedFlash((f) => ({ ...f, [tag]: null })), 2500)
    } catch (e) {
      setSavedFlash((f) => ({ ...f, [tag]: null }))
      setError(`저장 실패: ${e.message}`)
    }
  }

  return (
    <>
      <div className="card">
        {/* 설명은 제목 옆 ⓘ 로. 세 줄짜리 산문이 매번 자리를 차지하면 정작
            결과가 첫 화면 밖으로 밀린다. */}
        <h2>
          매물 분석
          <Hint
            notes={[
              '매물 텍스트를 붙여넣으면 각각 적정가를 진단합니다. 한쪽만 채워도 됩니다.',
              '둘 다 채우면 평당가 차이를 면적·층·역거리·연식·세대수·노선·자치구 기여로 쪼개 어느 쪽이 싼지까지 봅니다.',
            ]}
          />
        </h2>
        <div className="cmp-inputs">
          <ComplexPicker
            tag="A" side={a} set={setA} filter={fa} setFilter={setFa}
            complexes={complexes} meta={meta} onComplex={loadAreas}
            onParsed={applyParsed}
          />
          <ComplexPicker
            tag="B" side={b} set={setB} filter={fb} setFilter={setFb}
            complexes={complexes} meta={meta} onComplex={loadAreas}
            onParsed={applyParsed}
          />
        </div>
        <div className="cmp-actions">
          <div className="field">
            <label htmlFor="cmp-months">분석 기간</label>
            <select
              id="cmp-months"
              value={months}
              onChange={(e) => setMonths(Number(e.target.value))}
            >
              <option value={12}>최근 12개월</option>
              <option value={24}>최근 24개월</option>
              <option value={36}>최근 36개월</option>
            </select>
          </div>
          <span className="muted small cmp-hint">
            {busy.a || busy.b ? (
              <span className="live">적정가 진단 계산 중…</span>
            ) : busy.cmp ? (
              <span className="live">A·B 요인 비교 계산 중…</span>
            ) : evalA || evalB || result ? (
              '고치면 자동으로 다시 계산됩니다.'
            ) : (
              '텍스트를 붙여넣으면 바로 분석합니다.'
            )}
          </span>
          {error && (
            <button className="ghost" onClick={() => setRetry((n) => n + 1)}>
              다시 계산
            </button>
          )}
        </div>
        {error && <p className="empty">{error}</p>}
      </div>

      {/* 계산 중에도 카드 자리를 비워 두지 않는다. 섹션이 사라졌다 나타나면
          아래 비교 결과까지 위아래로 튄다. */}
      {(evalA || evalB || busy.a || busy.b) && (
        <div className="card">
          <h2>
            적정가 진단
            <Hint
              notes={[
                '같은 단지·같은 평형의 최근 실거래를 시점·층·동 보정한 적정가와 호가의 괴리율입니다.',
                '실거래 기준에는 단지 고유 프리미엄(학군·브랜드·재건축 기대)이 이미 들어가 있고, 요인 기준에는 빠져 있습니다. 둘의 차이가 그 프리미엄입니다.',
              ]}
            />
          </h2>
          <div className="fair-grid">
            <FairCard
              tag="A"
              name={complexes.find((c) => String(c.id) === String(a.complex_id))?.name ?? ''}
              result={evalA}
              busy={busy.a}
              onSelect={onSelect}
            />
            <FairCard
              tag="B"
              name={complexes.find((c) => String(c.id) === String(b.complex_id))?.name ?? ''}
              result={evalB}
              busy={busy.b}
              onSelect={onSelect}
            />
          </div>
          <div className="cmp-actions" style={{ marginTop: 12 }}>
            <span className="muted small cmp-hint">
              목록에 담아 두면 <b>기간을 바꿀 때마다 적정가가 다시 계산</b>되고, 새로
              붙여넣어도 남아 있습니다.
              <Hint
                notes={[
                  '저장한 매물은 아래 표에 쌓입니다. 분석 기간을 바꾸면 그 기간의 실거래로 적정가가 다시 계산되므로, 같은 매물이 기간에 따라 어떻게 달라지는지 볼 수 있습니다.',
                  '동 정보도 함께 저장되어 재계산할 때 동 보정이 유지됩니다.',
                ]}
              />
            </span>
            {['A', 'B'].map((tag) => {
              const side = tag === 'A' ? a : b
              if (!canEval(side)) return null
              const st = savedFlash[tag]
              return (
                <button
                  key={tag}
                  className="ghost"
                  disabled={st === 'saving'}
                  onClick={() => saveSide(side, tag)}
                >
                  {st === 'saving' ? '저장 중…' : st === 'done' ? `✓ ${tag} 저장됨` : `${tag} 저장`}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {busy.cmp && !result && (
        <div className="card">
          <h2>요인별 비교</h2>
          <p className="sub live">
            A·B 평당가 차이를 요인별로 쪼개는 중입니다. 헤도닉 적합이라 몇 초 걸립니다.
          </p>
        </div>
      )}
      {result && <CompareResult r={result} />}

      <BulkPaste months={months} />

      {saved.length > 0 && <SavedListings
          saved={saved}
          months={months}
          basis={basis}
          setBasis={setBasis}
          onDelete={(id) => api.deleteListing(id).then(reloadSaved)}
        />}
    </>
  )
}

const TONE = {
  저평가: 'good',
  '다소 저렴': 'good',
  적정: 'mid',
  '다소 비쌈': 'bad',
  고평가: 'bad',
}

/** 저장해 둔 매물 — 기간을 바꾸면 적정가가 다시 계산된다. */
/**
 * 비교한 매물의 순위표.
 *
 * **더 저평가된 매물이 이긴다** — 괴리율이 작을수록(음수일수록) 위로 간다.
 * 순위 기준은 두 가지이고, 서로 다른 순서를 낸다.
 *
 * - **실거래 기준**: 그 단지 같은 평형 시세 대비 싼가. 단지 프리미엄이 값에 포함돼
 *   있으므로, 같은 단지 안에서 고를 때 맞다.
 * - **요인 기준**: 거리·연식·세대수·노선만으로 봤을 때 싼가. 단지를 넘나들며
 *   고를 때 맞다.
 *
 * 실제로 광교 84㎡ 가 실거래 기준 1위인데 요인 기준 4위로 내려간 적이 있다 —
 * 자기 단지 최근 거래보다는 많이 싸지만 펀더멘털 대비로는 아니라는 뜻이다.
 * 그래서 **두 기준을 한 표에 나란히** 두고, 줄 세우는 기준만 고르게 한다.
 */
function SavedListings({ saved, onDelete, months, basis, setBasis }) {
  const label = basis === 'factor' ? '요인 기준' : '실거래 기준'
  return (
    <section className="card">
      <h2>
        매물 순위 <span className="muted small">{saved.length}건 · 최근 {months}개월 기준</span>
        <Hint
          notes={[
            '더 저평가된 매물이 위로 갑니다. 괴리율이 작을수록(음수일수록) 순위가 높습니다.',
            '분석 기간을 바꾸면 그 기간의 실거래로 표 전체가 다시 계산됩니다.',
            '실거래 기준은 그 단지 시세 대비, 요인 기준은 펀더멘털 대비입니다. 두 기준의 순위가 어긋나면 그 자체가 정보입니다.',
          ]}
        />
      </h2>

      <div className="rank-basis">
        <span className="muted small">순위 기준</span>
        {[
          ['market', '실거래 기준'],
          ['factor', '요인 기준'],
        ].map(([k, t]) => (
          <button
            key={k}
            className={`chip${basis === k ? ' on' : ''}`}
            onClick={() => setBasis(k)}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="num">#</th>
              <th>단지</th>
              <th>동</th>
              <th>메모</th>
              <th className="num">전용</th>
              <th className="num">층</th>
              <th className="num">호가</th>
              <th className={`num${basis === 'market' ? ' is-sort' : ''}`}>실거래 대비</th>
              <th className={`num${basis === 'factor' ? ' is-sort' : ''}`}>요인 대비</th>
              <th>판정</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {saved.map((s) => {
              const gf = s.gap_factor
              return (
                <tr key={s.id} className={s.rank === 1 ? 'is-top' : ''}>
                  <td className="num rank-no">{s.rank ?? '—'}</td>
                  <td style={{ fontWeight: 600 }}>{s.fair.complex.name}</td>
                  <td>{s.fair.dong ? `${s.fair.dong}동` : <span className="muted">—</span>}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{s.input.label || '—'}</td>
                  <td className="num">{s.input.exclusive_area}㎡</td>
                  <td className="num">{s.input.floor ?? '—'}</td>
                  <td className="num">{eok(s.input.asking_price)}</td>
                  <td
                    className={`num${basis === 'market' ? ' is-sort' : ''}`}
                    data-tone={s.gap ? (s.gap.pct < -3 ? 'good' : s.gap.pct > 3 ? 'bad' : 'mid') : null}
                  >
                    {s.gap ? `${s.gap.pct > 0 ? '+' : ''}${s.gap.pct}%` : '—'}
                  </td>
                  <td
                    className={`num${basis === 'factor' ? ' is-sort' : ''}`}
                    data-tone={gf ? (gf.pct < -3 ? 'good' : gf.pct > 3 ? 'bad' : 'mid') : null}
                  >
                    {gf ? `${gf.pct > 0 ? '+' : ''}${gf.pct}%` : '—'}
                  </td>
                  <td>
                    {s.gap && (
                      <span className="verdict" data-tone={TONE[s.gap.verdict]} style={{ fontSize: 13 }}>
                        {s.gap.verdict}
                      </span>
                    )}
                  </td>
                  <td>
                    <button className="ghost" onClick={() => onDelete(s.id)}>
                      삭제
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>
        <b>{label}</b>으로 줄 세웠습니다. 두 기준의 순위가 어긋나는 매물은 단지 고유
        프리미엄이 크게 붙어 있다는 뜻입니다.
      </p>
    </section>
  )
}

function PasteBox({ tag, onParsed }) {
  const key = tag === 'A' ? 'a' : 'b'
  const [text, setText] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)

  const run = (value, complexId) => {
    const t = (value ?? text).trim()
    if (!t) return
    setBusy(true)
    api
      .parseListing(t, complexId)
      .then((d) => {
        setRes(d)
        onParsed(key, d)
      })
      .catch((e) => setRes({ warnings: [e.message], candidates: [] }))
      .finally(() => setBusy(false))
  }

  return (
    <div className="paste-box">
      <label htmlFor={`paste-${tag}`}>
        매물 텍스트 붙여넣기
        {!res?.complex_id && <span className="muted small">붙이는 즉시 읽습니다</span>}
      </label>
      <textarea
        id={`paste-${tag}`}
        // 읽고 나면 한 줄로 접는다. 원문을 다시 볼 일은 드문데 3줄을 계속
        // 차지하면 정작 결과가 스크롤 밖으로 밀린다.
        rows={res?.complex_id ? 1 : 3}
        value={text}
        placeholder={'자연앤힐스테이트 101동\n매매 13억 5,000\n112.9/84.97㎡, 중층, 남향'}
        onChange={(e) => setText(e.target.value)}
        // 붙여넣는 즉시 돌린다. 버튼을 한 번 더 누르게 하면 '번거롭다'는 문제가 그대로다.
        // onChange 가 아직 반영되기 전이므로 클립보드 값을 직접 넘긴다.
        onPaste={(e) => {
          const v = e.clipboardData.getData('text')
          if (v && v.trim()) {
            e.preventDefault()
            setText(v)
            run(v)
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) run()
        }}
      />
      <div className="paste-actions">
        <button className="ghost" onClick={() => run()} disabled={busy || !text.trim()}>
          {busy ? '읽는 중…' : '다시 읽기'}
        </button>
        {(text || res) && (
          <button
            className="ghost"
            onClick={() => {
              setText('')
              setRes(null)
            }}
          >
            지우기
          </button>
        )}
      </div>

      {res?.candidates?.length > 0 && !res.complex_id && (
        <div className="paste-cands">
          {res.candidates.map((c) => (
            <button key={c.id} className="chip" onClick={() => run(undefined, c.id)}>
              {c.name} <span className="muted small">{c.umd_nm}</span>
            </button>
          ))}
        </div>
      )}

      {/* 경고 문구는 여기 늘어놓지 않는다. 아래 요약의 해당 값에 붙여
          호버했을 때만 뜨게 한다(`applyParsed` → `side.notes`). 단지 자체를
          못 찾은 경우만 예외 — 붙일 값이 없으니 여기서 말해야 한다. */}
      {res && !res.complex_id && res.warnings?.length > 0 && (
        <p className="paste-warn">{res.warnings[0].text ?? res.warnings[0]}</p>
      )}
    </div>
  )
}

/**
 * 단지 검색·필터.
 *
 * 615곳을 한 드롭다운에 넣으면 고를 수가 없다. 이름 검색과 노선·생활권·세대수
 * 필터로 좁힌 뒤 선택하게 한다. 목록은 이미 받아 둔 전체 배열을 클라이언트에서
 * 거르므로 타이핑할 때마다 서버를 부르지 않는다.
 *
 * 필터는 **양쪽이 따로** 갖는다. 광교와 매탄을 비교하는 것이 이 화면의 목적인데
 * 필터를 공유하면 서로 다른 지역을 고를 수가 없다.
 */
function ComplexPicker({ tag, side, set, filter, setFilter, complexes, meta, onComplex, onParsed }) {
  const key = tag === 'A' ? 'a' : 'b'
  // 직접 입력은 **접어 둔다**. 대부분은 붙여넣기 한 번으로 끝나는데, 검색창·필터 3개·
  // 목록·입력칸 3개가 항상 펼쳐져 있으면 그게 기본 동선처럼 보인다.
  const [open, setOpen] = useState(false)

  const matched = useMemo(() => {
    const q = filter.q.trim().toLowerCase()
    return complexes.filter((c) => {
      if (q && !`${c.name} ${c.umd_nm}`.toLowerCase().includes(q)) return false
      if (filter.line && c.station_line !== filter.line) return false
      if (filter.station && c.station_name !== filter.station) return false
      if (filter.household_band && c.household_band !== filter.household_band) return false
      return true
    })
  }, [complexes, filter])

  const chosen = complexes.find((c) => String(c.id) === String(side.complex_id))

  /** 붙여넣기가 단지나 면적을 못 채웠으면 접어 둘 수 없다 — 손댈 곳이 안 보인다. */
  const handleParsed = (k, d) => {
    onParsed(k, d)
    if (!d.complex_id || !d.exclusive_area) setOpen(true)
  }

  const pyeong = side.exclusive_area
    ? (Number(side.exclusive_area) / 3.305785).toFixed(1)
    : null

  return (
    <div className={`cmp-side is-${key}`}>
      <div className="cmp-tag">{tag}</div>

      <PasteBox tag={tag} onParsed={handleParsed} />

      {/* 무엇이 채워졌는지는 접든 펴든 항상 보여야 한다. */}
      <div className={`cmp-summary${chosen ? '' : ' is-empty'}`}>
        {chosen ? (
          <>
            <b>{chosen.name}</b>
            <span className="muted small">
              {chosen.umd_nm} · {chosen.station_name}({chosen.station_line}) · 준공{' '}
              {chosen.build_year ?? '?'} · 거래 {chosen.trade_count}건
            </span>
            <div className="cmp-specs">
              <Spec
                label="전용"
                value={side.exclusive_area ? `${side.exclusive_area}㎡` : null}
                sub={pyeong && `${pyeong}평`}
                notes={side.notes?.area}
              />
              <Spec
                label="층"
                value={side.floor ? `${side.floor}층` : null}
                notes={side.notes?.floor}
              />
              <Spec
                label="역까지"
                value={
                  side.dongWalk != null
                    ? `${side.dongWalk}분`
                    : side.centerWalk != null
                      ? `${side.centerWalk}분`
                      : null
                }
                sub={side.dongWalk != null ? `${side.dong}동 기준` : '단지 중심점'}
                notes={side.notes?.dong}
              />
              <Spec
                label="호가"
                value={side.asking_price ? `${Number(side.asking_price).toLocaleString()}만원` : null}
                notes={side.notes?.price}
              />
            </div>
          </>
        ) : null}
      </div>

      <button
        className="cmp-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`caret${open ? ' open' : ''}`} aria-hidden="true">›</span>
        직접 입력{chosen ? '·수정' : ''}
      </button>

      {open && (
        <div className="cmp-manual">
          <div className="field">
            <label htmlFor={`q-${tag}`}>단지 검색</label>
            <input
              id={`q-${tag}`}
              type="search"
              value={filter.q}
              onChange={(e) => setFilter({ ...filter, q: e.target.value })}
              placeholder="단지명 또는 법정동"
            />
          </div>

          <div className="cmp-filters">
            <select
              value={filter.line}
              aria-label="노선"
              onChange={(e) => setFilter({ ...filter, line: e.target.value, station: '' })}
            >
              <option value="">노선 전체</option>
              {meta?.lines?.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
            <select
              value={filter.station}
              aria-label="생활권"
              onChange={(e) => setFilter({ ...filter, station: e.target.value })}
            >
              <option value="">생활권 전체</option>
              {(meta?.stations ?? [])
                .filter((st) => !filter.line || st.line === filter.line)
                .map((st) => (
                  <option key={`${st.line}-${st.name}`} value={st.name}>{st.name}</option>
                ))}
            </select>
            <select
              value={filter.household_band}
              aria-label="세대수"
              onChange={(e) => setFilter({ ...filter, household_band: e.target.value })}
            >
              <option value="">세대수 전체</option>
              {meta?.household_bands?.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor={`cx-${tag}`}>
              단지 <span className="muted small">{matched.length}곳</span>
            </label>
            <select
              id={`cx-${tag}`}
              value={side.complex_id}
              size={matched.length > 1 ? 6 : 2}
              onChange={(e) => {
                set({ ...side, complex_id: e.target.value, exclusive_area: '' })
                onComplex(key, e.target.value)
              }}
            >
              {matched.length === 0 && <option value="">조건에 맞는 단지가 없습니다</option>}
              {matched.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.umd_nm} · {c.station_line ?? '?'}
                  {c.household_count ? ` · ${c.household_count.toLocaleString()}세대` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor={`area-${tag}`}>전용면적</label>
            {/* 이 단지에 **실제로 거래된 평형**만 버튼으로 준다. 숫자를 외워서 치게 할
                이유가 없고, 없는 평형을 입력하면 비교 대상이 비어 버린다. */}
            {(side.areaOpts ?? []).length > 0 && (
              <div className="area-chips">
                {side.areaOpts.map((o) => (
                  <button
                    key={o.exclusive_area}
                    className={`chip${
                      Number(side.exclusive_area) === o.exclusive_area ? ' on' : ''
                    }`}
                    onClick={() => set({ ...side, exclusive_area: o.exclusive_area })}
                  >
                    {o.pyeong}평 <span className="muted small">{o.exclusive_area}㎡</span>
                  </button>
                ))}
              </div>
            )}
            <input
              id={`area-${tag}`}
              type="number"
              step="0.01"
              value={side.exclusive_area}
              onChange={(e) => set({ ...side, exclusive_area: e.target.value })}
              placeholder={side.complex_id ? '위에서 고르거나 ㎡ 직접 입력' : '84.97'}
            />
          </div>

          <div className="cmp-pair">
            <div className="field">
              {/* 동을 고르면 역까지 도보를 그 동 좌표로 잡는다. 직접 치게 하면
                  오타도 나고 그 동이 얼마나 먼지도 모른다. */}
              <label htmlFor={`dong-${tag}`}>
                동{' '}
                {side.dongPremSpread ? (
                  <span className="muted small">단지 내 {side.dongPremSpread}% 차</span>
                ) : side.dongSpread ? (
                  <span className="muted small">단지 내 {side.dongSpread}분 차</span>
                ) : (
                  <span className="muted small">선택</span>
                )}
              </label>
              <select
                id={`dong-${tag}`}
                value={side.dong ?? ''}
                onChange={(e) => {
                  const hit = (side.dongOpts ?? []).find((o) => o.dong === e.target.value)
                  set({ ...side, dong: e.target.value, dongWalk: hit?.walk_min ?? null })
                }}
              >
                <option value="">단지 중심점</option>
                {(side.dongOpts ?? []).map((o) => (
                  <option key={o.dong} value={o.dong}>
                    {o.dong}동{o.walk_min != null ? ` · 도보 ${o.walk_min}분` : ' · 좌표없음'}
                    {o.premium_pct != null
                      ? ` · 시세 ${o.premium_pct > 0 ? '+' : ''}${o.premium_pct}%`
                      : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor={`floor-${tag}`}>층</label>
              <input
                id={`floor-${tag}`}
                type="number"
                value={side.floor}
                onChange={(e) => set({ ...side, floor: e.target.value })}
                placeholder="15"
              />
            </div>
            <div className="field">
              <label htmlFor={`price-${tag}`}>호가 (만원)</label>
              <input
                id={`price-${tag}`}
                type="number"
                value={side.asking_price}
                onChange={(e) => set({ ...side, asking_price: e.target.value })}
                placeholder="90000"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** 요약 줄의 항목 하나. 비면 '—' 로 두어 **무엇이 비었는지** 보이게 한다. */
function Spec({ label, value, sub, notes }) {
  return (
    <div className={`spec${value ? '' : ' is-empty'}`}>
      <span className="spec-label">
        {label}
        <Hint notes={notes} />
      </span>
      <span className="spec-value">{value ?? '—'}</span>
      {value && sub && <span className="spec-sub">{sub}</span>}
    </div>
  )
}

function CompareResult({ r }) {
  const v = r.verdict
  return (
    <>
      {v && (
        <div className={`card verdict-card ${v.cheaper === 'A' ? 'is-a' : 'is-b'}`}>
          <div className="verdict-head">
            <span className="verdict-badge">{v.cheaper}</span>
            <strong>{v.text}</strong>
          </div>
          <div className="tiles compact">
            <Tile
              label="모델 예상 차이"
              value={`${r.expected_diff_pct > 0 ? '+' : ''}${fmt(r.expected_diff_pct, 1)}%`}
              sub="요인만으로 설명되는 A−B"
            />
            <Tile
              label="실제 호가 차이"
              value={`${r.actual_diff_pct > 0 ? '+' : ''}${fmt(r.actual_diff_pct, 1)}%`}
              sub="평당가 기준 A−B"
            />
            <Tile
              label="설명되지 않는 차이"
              value={`${r.gap_pct > 0 ? '+' : ''}${fmt(r.gap_pct, 1)}%`}
              sub="양수면 A가 비싼 쪽"
            />
          </div>
        </div>
      )}

      <div className="card">
        <h2>
          요인별 기여
          <Hint notes={[r.note]} />
        </h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>요인</th>
                <th>A · {r.a.name}</th>
                <th>B · {r.b.name}</th>
                <th className="num">A − B</th>
              </tr>
            </thead>
            <tbody>
              {r.factors.map((f) => (
                <tr key={f.key}>
                  <td>
                    {f.label}
                    <div className="muted small">{f.note}</div>
                  </td>
                  <td>{f.a}</td>
                  <td>{f.b}</td>
                  <td className={`num ${f.diff_pct > 0 ? 'tone-neg' : 'tone-pos'}`}>
                    {f.diff_pct > 0 ? '+' : ''}
                    {fmt(f.diff_pct, 1)}%
                  </td>
                </tr>
              ))}
              <tr className="is-current">
                <td colSpan={3}>
                  <b>요인 합계 — 모델이 예상하는 평당가 차이</b>
                </td>
                <td className="num">
                  <b>
                    {r.expected_diff_pct > 0 ? '+' : ''}
                    {fmt(r.expected_diff_pct, 1)}%
                  </b>
                </td>
              </tr>
              {r.a.asking_ppp && r.b.asking_ppp && (
                <tr>
                  <td colSpan={3}>실제 호가 평당가 차이</td>
                  <td className="num">
                    {r.actual_diff_pct > 0 ? '+' : ''}
                    {fmt(r.actual_diff_pct, 1)}%
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {r.skipped?.length > 0 && (
          <div className="notice" style={{ marginTop: 12 }}>
            {r.skipped.map((s) => (
              <div key={s.label}>
                <b>{s.label}</b> — {s.reason}
              </div>
            ))}
          </div>
        )}

        {r.complex_premium_diff_pct != null && (
          <p className="muted small" style={{ marginTop: 10 }}>
            참고: 두 단지의 <b>모델이 설명하지 못하는 고유 프리미엄</b> 차이는{' '}
            {r.complex_premium_diff_pct > 0 ? '+' : ''}
            {fmt(r.complex_premium_diff_pct, 1)}% 입니다. 학군·브랜드·조망·재건축 기대가
            여기 섞여 있어, 위 표의 요인만으로 판단하기 어려운 부분입니다.
          </p>
        )}
      </div>

    </>
  )
}

function Tile({ label, value, sub }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value sm">{value}</div>
      {sub ? <div className="note">{sub}</div> : null}
    </div>
  )
}
