import { useEffect, useState } from 'react'

import { api } from '../../api'
import ChartLink from '../../shared/ChartLink'
import Hint from '../../shared/Hint'
import EffectBars from '../components/EffectBars'
import EffectModal from '../components/EffectModal'
import ForecastCard from '../components/ForecastCard'

/**
 * 지수 분석 — 경제지표가 움직일 때 KOSPI·S&P 500 은 어땠나(맨 위), 그리고 다음 1·3개월 범위(접힌 카드).
 *
 * 2026-11 에 '지수 예측' 에서 바꿨다. 구간 예측 표가 무엇을 말하는지 와닿지 않는다는 말을 듣고, 정말
 * 묻고 싶은 질문 — **금리 같은 지표가 주가에 + 인가 − 인가, 얼마나** — 을 맨 위로 올렸다. 계산은
 * backend/app/stock/effects.py, 지표 목록은 indicators.py, 경위는 docs/stock/effects.md.
 *
 * 단추 셋이 같은 막대의 시점을 바꾼다: 같은 1년(지표가 움직인 그 1년의 지수) · 그 뒤 3개월 · 그 뒤 12개월
 * (지표를 알게 된 뒤의 지수). 막대를 누르면 창에 산점도·오른/내린 시기·앞뒤 절반·함께 넣은 값이 나온다.
 */
const HZ = [
  { id: 'same', label: '같은 1년' },
  { id: 'after3', label: '그 뒤 3개월' },
  { id: 'after12', label: '그 뒤 12개월' },
]
const ym = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}`

function EffectCard({ ix }) {
  const [hz, setHz] = useState('same')
  const [pick, setPick] = useState(null)
  const e = ix.effects[hz]
  const live = e.rows.filter((r) => r.n)
  const clear = live.filter((r) => r.verdict !== 'none').length
  const from = live.length ? live.map((r) => r.from).sort()[0] : null
  const to = live.length ? live.map((r) => r.to).sort().slice(-1)[0] : null
  const row = pick && e.rows.find((r) => r.id === pick)
  const hzLabel = HZ.find((x) => x.id === hz).label

  return (
    <section className="card">
      <h2>
        {ix.label} — 경제지표와 함께
        <Hint
          wide
          notes={[
            '막대는 지표가 평소 폭(1년 움직임의 표준편차)만큼 움직였을 때 지수 수익률이 평균 몇 % 달랐나입니다. 단위가 다른 지표를 같은 길이로 견주려고 평소 폭으로 맞췄습니다. 1단위(1%p·1%)당 값은 줄 오른쪽에 있습니다.',
            '가는 선은 95% 범위입니다. 범위가 0 을 넘지 않으면 초록(+)·빨강(−), 넘으면 회색(뚜렷하지 않음)입니다.',
            '같은 1년: 지표가 움직인 그 1년 동안의 지수. 그 뒤: 지표를 알 수 있게 된 뒤부터의 지수입니다 — 물가·M2·실업률은 다음 달에야 발표되어 한 달 밀어 셉니다.',
            '금리·실업률은 1년 변화(%p), 물가·M2·환율은 1년 상승률(%)입니다. 미국 장단기 금리차만 수준(%p)입니다 — 역전 여부가 신호라서입니다.',
            '연관이지 원인이 아닙니다. 금리가 오른 해에 주가가 내렸어도 경기가 둘을 같이 움직였을 수 있습니다. 지표가 여럿이라 우연히 뚜렷해 보이는 것도 섞일 수 있습니다.',
            '시기에 따라 다름: 표본을 시간순으로 반 나눠 다시 재면 방향이 다릅니다.',
            `지수는 현지 통화(${ix.currency})·배당을 뺀 가격 지수의 월말 종가입니다.`,
          ]}
        />
        <ChartLink id={`${ix.id}-effects`} />
      </h2>
      <div className="seg" role="tablist" aria-label="시점">
        {HZ.map((x) => (
          <button key={x.id} role="tab" aria-selected={x.id === hz} onClick={() => setHz(x.id)}>
            {x.label}
          </button>
        ))}
      </div>
      <p className="muted small">
        {from ? `${ym(from)}~${ym(to)}` : '—'} · 뚜렷한 지표 {clear}/{live.length}개 · 막대를 누르면 자세히
      </p>
      <EffectBars rows={e.rows} onPick={(r) => setPick(r.id)} />
      {row && (
        <EffectModal ix={ix} row={row} joint={e.joint} horizonLabel={hzLabel} onClose={() => setPick(null)} />
      )}
    </section>
  )
}

export default function IndexView() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    api.stockIndices().then((d) => alive && setData(d)).catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [])

  if (error || !data) {
    return (
      <section className="card">
        <h2>지수 분석</h2>
        <p className="empty">{error ? error.message : '불러오는 중…'}</p>
      </section>
    )
  }
  return (
    <>
      {data.indices.map((ix) =>
        ix.available ? (
          <div key={ix.id}>
            <EffectCard ix={ix} />
            <ForecastCard ix={ix} />
          </div>
        ) : (
          <section className="card" key={ix.id}>
            <h2>{ix.label}</h2>
            <p className="empty">일봉이 모자랍니다({ix.n_days}일) — backend 에서 ingest_stock 을 돌리세요.</p>
          </section>
        ),
      )}
    </>
  )
}
