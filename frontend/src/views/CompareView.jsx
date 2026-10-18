import { useEffect, useState } from 'react'

import { api } from '../api'
import { eok, fmt } from '../components/Charts'
import Hint from '../components/Hint'
import MemoTagPanel from '../components/MemoTagPanel'
import BulkPaste from './BulkPaste'

/**
 * 호가 입력 — 붙여넣은 매물을 적정가로 진단하고, 메모 사전을 관리한다.
 *
 * ## A·B 한 건씩 넣던 기능은 뺐다
 *
 * 예전에는 매물 두 건을 각각 붙여넣어 적정가를 보고, 둘의 평당가 차이를 요인별로
 * 쪼개는 화면이 앞에 있었다. 입력칸이 두 벌이라 자리를 가장 많이 먹었는데, 실제로는
 * **여러 매물 붙여넣기**로 한 번에 넣고 호가 분석 탭에서 보는 쪽이 쓰기 편했다.
 * 두 건만 견주는 일은 순위표에서 두 줄을 보면 끝난다. 그 뒤에 남아 있던
 * `/api/model/compare` 도 2026-10-18 에 지웠다.
 *
 * 남은 것은 둘이다. ('저장한 매물' 도 있었는데, 호가가 `Quote` 로 옮겨 간 뒤 한 번도
 * 그려지지 않아 512bd50 에서 지웠다.)
 *
 * - **여러 매물 붙여넣기**: 목록을 통째로 붙여넣으면 단지·면적·층·호가를 뽑아 쌓는다.
 *   기간을 바꾸면 그 기간의 실거래로 적정가가 다시 계산된다.
 * - **메모 사전**: 중개사 메모에서 뽑는 키워드를 무엇까지 비고에 띄울지 고른다.
 *
 * 탭 이름은 '매물 분석' → '매물 관리' → **'호가 입력'** 으로 바뀌었다. 붙여넣어 읽기만
 * 하던 탭에 설정이 들어오면서 '분석' 이 안 맞았고, 보는 쪽(호가 분석)과 짝을 맞췄다.
 *
 * 요인별 비교는 분해 모델 탭의 계수로 같은 질문에 답할 수 있다.
 */
export default function CompareView({ months: initialMonths, incoming }) {
  const [months, setMonths] = useState(initialMonths ?? 12)
  const [basis, setBasis] = useState('market')

  useEffect(() => setMonths(initialMonths ?? 12), [initialMonths])

  return (
    <>
      <div className="card">
        <h2>
          호가 입력
          <Hint
            notes={[
              '매물 목록을 통째로 붙여넣으면 단지·면적·층·호가를 뽑아 각각 적정가를 진단합니다.',
              '쌓인 매물은 호가 분석 탭에서 한 표로 볼 수 있습니다. 기간을 바꾸면 그 기간의 실거래로 전부 다시 계산됩니다.',
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

      <BulkPaste months={months} incoming={incoming} />

      {/* 붙여넣기 **다음에** 둔다. 사전은 붙여넣어 쌓인 메모를 세서 보여 주므로,
          막 붙여넣은 뒤에 보는 것이 자연스럽다. 메모가 하나도 없으면 그렇게 말한다. */}
      <MemoTagPanel />

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
