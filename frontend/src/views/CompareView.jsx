import { useEffect, useState } from 'react'

import { api } from '../api'
import { eok, fmt } from '../components/Charts'
import Hint from '../components/Hint'
import BulkPaste from './BulkPaste'

/**
 * 매물 분석 — 붙여넣은 매물을 적정가로 진단한다.
 *
 * ## A·B 한 건씩 넣던 기능은 뺐다
 *
 * 예전에는 매물 두 건을 각각 붙여넣어 적정가를 보고, 둘의 평당가 차이를 요인별로
 * 쪼개는 화면이 앞에 있었다. 입력칸이 두 벌이라 자리를 가장 많이 먹었는데, 실제로는
 * **여러 매물 붙여넣기**로 한 번에 넣고 매물 순위에서 보는 쪽이 쓰기 편했다.
 * 두 건만 견주는 일은 순위표에서 두 줄을 보면 끝난다.
 *
 * 남은 것은 둘이다.
 *
 * - **여러 매물 붙여넣기**: 목록을 통째로 붙여넣으면 단지·면적·층·호가를 뽑아 쌓는다.
 * - **저장한 매물**: 기간을 바꾸면 그 기간의 실거래로 적정가가 다시 계산된다.
 *
 * 요인별 비교는 분해 모델 탭의 계수로 같은 질문에 답할 수 있다.
 */
export default function CompareView({ months: initialMonths }) {
  const [months, setMonths] = useState(initialMonths ?? 12)
  const [saved, setSaved] = useState([])
  const [basis, setBasis] = useState('market')

  useEffect(() => setMonths(initialMonths ?? 12), [initialMonths])

  const reloadSaved = () =>
    api
      .listings({ months })
      .then((d) => setSaved(d.items || []))
      .catch(() => setSaved([]))

  useEffect(() => {
    reloadSaved()
  }, [months])

  return (
    <>
      <div className="card">
        <h2>
          매물 분석
          <Hint
            notes={[
              '매물 목록을 통째로 붙여넣으면 단지·면적·층·호가를 뽑아 각각 적정가를 진단합니다.',
              '쌓인 매물은 매물 순위 탭에서 한 표로 볼 수 있습니다. 기간을 바꾸면 그 기간의 실거래로 전부 다시 계산됩니다.',
            ]}
          />
        </h2>
        <div className="filters">
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
        </div>
      </div>

      <BulkPaste months={months} />

      {saved.length > 0 && (
        <SavedListings
          saved={saved}
          months={months}
          basis={basis}
          setBasis={setBasis}
          onDelete={(id) => api.deleteListing(id).then(reloadSaved)}
        />
      )}
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
