import { useState } from 'react'

import { fmt } from '../../shared/Charts'
import Hint from '../../shared/Hint'
import Modal from '../../shared/Modal'
import ExampleChart from './ExampleChart'
import LiveSection, { day } from './LiveSection'

/**
 * 기법 하나의 설명 창 — 저장소의 초점이 설명이라(2026-11-12 합의) 카드에는 한 줄만 두고 나머지를 여기 둔다.
 *
 * 순서는 '무엇인가 → 왜 → 어떻게 → 예시 → 언제 통하고 언제 틀리나 → 어디서 왔나'. 예시는 늘 '예시' 라고
 * 머리에 적는다 — 합성 가격이나 가상 회사 숫자가 실제 지수·종목으로 읽히지 않게(CLAUDE.md '추정을 사실처럼
 * 보여 주지 않는다').
 *
 * 단기 기법 중 종가로 재는 것은 실제 지수에 돌린 결과(`live`, backend/app/stock/trading.py)가 붙는다 — '실제 지수에서'
 * 절과, 예시의 실제 사례. 사례가 있으면 실제가 먼저, 없으면 합성(2026-11-12 합의). 실제 사례는 고르지 않고 규칙으로
 * 정한다 — 뒤 60거래일이 다 지난 가장 최근 신호. 보기 좋은 것을 고르면 기법이 실제보다 좋아 보인다.
 */
export default function TechniqueModal({ t, needLabel, onClose, live, liveError }) {
  const rule = live?.rules?.[t.id]
  const runs = live !== undefined && t.need === 'close'
  const [ix, setIx] = useState(() => live?.indices?.[0]?.id)
  const index = live?.indices?.find((x) => x.id === ix) || live?.indices?.[0]
  const real = rule && index ? rule.by[index.id]?.example : null
  const [mode, setMode] = useState('real')
  const showReal = real && mode === 'real'
  const ex = t.example()
  const synthChart = ex.chart || (ex.close || ex.bars ? ex : null)
  const chart = showReal
    ? { ...real, priceLabel: `${index.label} 종가`, axis: true, dates: [day(real.first), day(real.last)],
        markNames: rule.kind === 'hold' ? null : ['오름 신호', '내림 신호'] }
    : synthChart
  const virtual = t.need === 'company'
  return (
    <Modal title={`${t.name} · ${t.en}`} onClose={onClose} wide>
      <p className="tq-summary">{t.summary}</p>

      <h3>원리</h3>
      <p>{t.idea}</p>

      <h3>어떻게 쓰나</h3>
      <ol className="tq-list">
        {t.rules.map((r) => <li key={r}>{r}</li>)}
      </ol>

      {runs && (
        <LiveSection rid={t.id} live={live} error={liveError} ix={index?.id} setIx={setIx} />
      )}

      <h3>
        예시 <span className="badge">{virtual ? '가상 회사 숫자' : showReal ? `실제 ${index.label}` : '합성 데이터'}</span>
        <Hint
          notes={[
            showReal
              ? `실제 ${index.label} 종가입니다. 규칙에 맞는 신호 가운데 뒤 ${live.after}거래일이 다 지난 가장 최근 것을 골랐습니다 — 보기 좋은 것을 고르면 기법이 실제보다 좋아 보입니다. 표시는 이 구간 안의 모든 신호입니다.`
              : null,
            showReal ? null : virtual
              ? '실제 회사가 아니라 계산 과정을 보여 주려고 지은 숫자입니다. 표의 값은 위 입력에서 그 자리에서 계산했습니다.'
              : '실제 지수가 아니라 모양을 정해 만든 가짜 가격입니다. 진입·청산 표시는 손으로 찍지 않고 위 규칙을 이 가격에 그대로 돌려 얻었습니다 — 규칙이 늦게 반응하면 표시도 늦게 찍힙니다.',
            !showReal && chart && !chart.yTicks ? '가격 축에 숫자를 적지 않았습니다 — 합성 가격이라 값 자체에는 뜻이 없습니다.' : null,
            rule && !real ? `${index.label} 에서는 규칙에 맞는 신호가 난 적이 없어 합성 예시를 보여 줍니다.` : null,
          ]}
        />
      </h3>
      {real && (
        <div className="seg" role="tablist" aria-label="예시">
          <button role="tab" aria-selected={mode === 'real'} onClick={() => setMode('real')}>실제 사례</button>
          <button role="tab" aria-selected={mode !== 'real'} onClick={() => setMode('synth')}>합성 예시</button>
        </div>
      )}
      {showReal && (
        <p className="muted small">
          {day(real.at)} {real.dir > 0 ? '▲' : '▼'}{real.kind ? ` ${real.kind}` : ''} · 다음 날 종가에서 {live.after}거래일 뒤{' '}
          {real.after == null ? '—' : <b className={real.after >= 0 ? 'tone-pos' : 'tone-neg'}>{real.after >= 0 ? '+' : '−'}{fmt(Math.abs(real.after), 1)}%</b>}
        </p>
      )}
      {chart && <ExampleChart spec={chart} />}
      {!showReal && (ex.calc || []).map((c) => (
        <div key={c.caption} className="tq-calc">
          <div className="muted small">{c.caption}</div>
          <div className="table-wrap">
            <table className="coef">
              <thead>
                <tr>{c.cols.map((h, i) => <th key={i}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {c.rows.map((r, i) => (
                  <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      {!showReal && <p className="tq-read">{t.read}</p>}

      <div className="tq-two">
        <div>
          <h3>잘 통할 때</h3>
          <ul className="tq-list">{t.works.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
        <div>
          <h3>함정</h3>
          <ul className="tq-list">{t.traps.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      </div>

      <h3>원전</h3>
      <p>{t.by}</p>
      <p className="muted small">필요한 데이터: {needLabel}</p>
    </Modal>
  )
}
