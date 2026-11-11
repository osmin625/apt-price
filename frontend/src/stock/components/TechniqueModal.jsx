import Hint from '../../shared/Hint'
import Modal from '../../shared/Modal'
import ExampleChart from './ExampleChart'

/**
 * 기법 하나의 설명 창 — 저장소의 초점이 설명이라(2026-11-12 합의) 카드에는 한 줄만 두고 나머지를 여기 둔다.
 *
 * 순서는 '무엇인가 → 왜 → 어떻게 → 예시 → 언제 통하고 언제 틀리나 → 어디서 왔나'. 예시는 늘 '예시' 라고
 * 머리에 적는다 — 합성 가격이나 가상 회사 숫자가 실제 지수·종목으로 읽히지 않게(CLAUDE.md '추정을 사실처럼
 * 보여 주지 않는다').
 */
export default function TechniqueModal({ t, needLabel, onClose }) {
  const ex = t.example()
  const chart = ex.chart || (ex.close || ex.bars ? ex : null)
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

      <h3>
        예시 <span className="badge">{virtual ? '가상 회사 숫자' : '합성 데이터'}</span>
        <Hint
          notes={[
            virtual
              ? '실제 회사가 아니라 계산 과정을 보여 주려고 지은 숫자입니다. 표의 값은 위 입력에서 그 자리에서 계산했습니다.'
              : '실제 지수가 아니라 모양을 정해 만든 가짜 가격입니다. 진입·청산 표시는 손으로 찍지 않고 위 규칙을 이 가격에 그대로 돌려 얻었습니다 — 규칙이 늦게 반응하면 표시도 늦게 찍힙니다.',
            chart && !chart.yTicks ? '가격 축에 숫자를 적지 않았습니다 — 합성 가격이라 값 자체에는 뜻이 없습니다.' : null,
          ]}
        />
      </h3>
      {chart && <ExampleChart spec={chart} />}
      {(ex.calc || []).map((c) => (
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
      <p className="tq-read">{t.read}</p>

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
