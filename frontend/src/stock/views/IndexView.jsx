import { useEffect, useState } from 'react'

import { api } from '../../api'
import ChartLink from '../../shared/ChartLink'
import { fmt } from '../../shared/Charts'
import Hint from '../../shared/Hint'
import EffectModal from '../components/EffectModal'
import ForecastCard from '../components/ForecastCard'

/**
 * 지수 분석 — 경제지표가 움직일 때 S&P 500·KOSPI 는 어땠나(맨 위), 그리고 다음 1·3개월 범위(접힌 카드).
 *
 * 2026-11 에 '지수 예측' 에서 바꿨다. 구간 예측 표가 무엇을 말하는지 와닿지 않는다는 말을 듣고, 정말
 * 묻고 싶은 질문 — **금리 같은 지표가 주가에 + 인가 − 인가, 얼마나** — 을 맨 위로 올렸다. 계산은
 * backend/app/stock/effects.py, 지표 목록은 indicators.py, 경위는 docs/stock/effects.md.
 *
 * ## 지표마다 카드 하나 — 상식의 방향과 잰 값을 나란히
 *
 * 처음에는 지표가 줄 선 가로 막대 하나였다. 2026-11-12 요청으로 거시 분석의 요인 카드처럼 지표마다 작은
 * 카드를 두고, 카드마다 **상식으로는 주가와 같이 가는가 거꾸로 가는가**(`indicators.expect`)를 잰 값
 * 위에 적었다. 막대만 있으면 −3% 가 '예상대로' 인지 '뜻밖' 인지를 읽는 사람이 알아서 떠올려야 했다.
 * 맞는지는 응답의 `agree` 가 정한다 — 범위가 0 을 넘으면 '뚜렷하지 않음' 이고, 막대가 상식 쪽으로
 * 기울었는지(`lean`)만 덧붙인다.
 *
 * 카드 안 작은 띠는 옛 막대를 줄인 것이다. 한 지수 안의 카드들은 **같은 자**를 써서 띠 길이를 견줄 수 있다.
 *
 * 단추 셋이 같은 카드의 시점을 바꾼다: 같은 1년(지표가 움직인 그 1년의 지수) · 그 뒤 3개월 · 그 뒤 12개월
 * (지표를 알게 된 뒤의 지수). 카드를 누르면 창에 산점도·오른/내린 시기·앞뒤 절반·함께 넣은 값이 나온다.
 *
 * 지수는 S&P 500 이 먼저다(2026-11-12 요청 — 주식의 모든 정보는 미국 우선, `indices.INDICES` 의 순서).
 */
const HZ = [
  { id: 'same', label: '같은 1년' },
  { id: 'after3', label: '그 뒤 3개월' },
  { id: 'after12', label: '그 뒤 12개월' },
]
const ym = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}`
const signed = (v, d = 1) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`
const tone = (verdict) => (verdict === 'pos' ? 'tone-pos' : verdict === 'neg' ? 'tone-neg' : 'muted')
const AGREE = { yes: '상식대로', no: '상식과 반대', unclear: '뚜렷하지 않음' }
const KIND = {
  level: '수준(%p) 그대로 봅니다 — 역전 여부가 신호라서입니다.',
  growth: '1년 상승률(%)로 봅니다.',
  diff: '1년 변화(%p)로 봅니다.',
}

/** 0 을 가운데 둔 작은 띠 — 가는 선이 95% 범위, 굵은 칸이 막대. 색은 부호(뚜렷하지 않으면 무채색). */
function Strip({ r, ext }) {
  const at = (v) => `${((v + ext) / (2 * ext)) * 100}%`
  const span = (v) => `${(v / (2 * ext)) * 100}%`
  const c = r.verdict === 'pos' ? 'var(--good)' : r.verdict === 'neg' ? 'var(--neg)' : 'var(--text-muted)'
  return (
    <div className="ix-strip" aria-hidden="true">
      <span className="ix-zero" />
      <span className="ix-range" style={{ left: at(r.lo), width: span(r.hi - r.lo), background: c }} />
      <span
        className="ix-bar"
        style={{ left: at(Math.min(0, r.bar)), width: span(Math.abs(r.bar)), background: c,
                 opacity: r.verdict === 'none' ? 0.45 : 0.9 }}
      />
    </div>
  )
}

/** 지표 하나 — 이름 · 상식의 방향 · 잰 값과 띠 · 맞는지. 누르면 창. */
function IndicatorTile({ r, ext, onPick }) {
  const up = r.expect > 0
  const head = (
    <div className="rg-tile-head">
      <strong>{r.label}</strong>
      {/* 창을 여는 카드 안의 ⓘ — 누른 것이 카드까지 올라가 창이 열리지 않게 막는다. */}
      <span onClick={(e) => e.stopPropagation()}>
        <Hint
          notes={[
            `상식: ${r.why}`,
            KIND[r.kind],
            r.n
              ? `평소 폭(1년 ${fmt(r.sd, 2)}${r.unit})만큼 오를 때 ${signed(r.bar)}% · 1${r.unit}당 `
                + `${signed(r.slope, 2)}% · 95% 범위 ${signed(r.lo)} ~ ${signed(r.hi)}% · ${r.n}개월`
              : null,
            r.pub_lag ? "다음 달에야 발표되어 '그 뒤' 는 한 달 밀어 셉니다." : null,
            `출처: ${r.source}.`,
          ]}
        />
      </span>
    </div>
  )
  const dir = (
    <div className="ix-dir">
      <span className={up ? 'tone-pos' : 'tone-neg'}>{up ? '↗ 정방향' : '↘ 역방향'}</span>
      <span className="muted small">{up ? '오르면 주가도 오른다' : '오르면 주가는 내린다'}</span>
    </div>
  )
  if (!r.n) {
    return (
      <div className="rg-tile ix-tile">
        {head}
        {dir}
        <div className="muted small">표본이 짧아 재지 않음</div>
      </div>
    )
  }
  return (
    <div
      className={`rg-tile ix-tile is-${r.verdict}`}
      role="button"
      tabIndex={0}
      onClick={() => onPick(r)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onPick(r)
        }
      }}
    >
      {head}
      {dir}
      <div className="rg-tile-val">
        <b className={tone(r.verdict)}>{signed(r.bar)}%</b>
        <span className="muted small">평소 폭만큼 오를 때</span>
      </div>
      <Strip r={r} ext={ext} />
      <div className={`ix-agree is-${r.agree}`}>
        {r.agree === 'yes' ? '✓ ' : r.agree === 'no' ? '✗ ' : ''}
        {AGREE[r.agree]}
        {r.agree === 'unclear' && <span> · 값은 {r.lean ? '상식 쪽' : '반대 쪽'}</span>}
      </div>
      {r.flip && <div className="ix-flip small">시기에 따라 다름</div>}
    </div>
  )
}

function EffectCard({ ix }) {
  const [hz, setHz] = useState('same')
  const [pick, setPick] = useState(null)
  const e = ix.effects[hz]
  const live = e.rows.filter((r) => r.n)
  const count = (a) => live.filter((r) => r.agree === a).length
  const from = live.length ? live.map((r) => r.from).sort()[0] : null
  const to = live.length ? live.map((r) => r.to).sort().slice(-1)[0] : null
  const ext = Math.max(5, ...live.flatMap((r) => [Math.abs(r.lo), Math.abs(r.hi), Math.abs(r.bar)]))
  const row = pick && e.rows.find((r) => r.id === pick)
  const hzLabel = HZ.find((x) => x.id === hz).label

  return (
    <section className="card">
      <h2>
        {ix.label} — 경제지표와 함께
        <Hint
          wide
          notes={[
            '정방향·역방향은 상식입니다 — 그 지표가 오를 때 주가가 같이 오른다고(정방향) 또는 내린다고(역방향) 흔히 말하는 쪽입니다. 잰 값이 아니라 잰 값과 견줄 기준이라 손으로 적었습니다. 이유는 카드의 ⓘ 에 있습니다.',
            '값은 지표가 평소 폭(1년 움직임의 표준편차)만큼 올랐을 때 지수 수익률이 평균 몇 % 달랐나입니다. 단위가 다른 지표를 같은 길이로 견주려고 평소 폭으로 맞췄습니다.',
            '띠의 가는 선은 95% 범위입니다. 범위가 0 을 넘지 않으면 초록(+)·빨강(−)이고 상식과 맞는지를 적습니다. 넘으면 회색(뚜렷하지 않음)이고 값이 상식 쪽인지 반대 쪽인지만 덧붙입니다. 한 지수 안의 띠는 같은 자입니다.',
            '같은 1년: 지표가 움직인 그 1년 동안의 지수. 그 뒤: 지표를 알 수 있게 된 뒤부터의 지수입니다 — 물가·M2·실업률은 다음 달에야 발표되어 한 달 밀어 셉니다.',
            '금리·실업률은 1년 변화(%p), 물가·M2·환율은 1년 상승률(%)입니다. 미국 장단기 금리차만 수준(%p)입니다 — 역전 여부가 신호라서입니다.',
            '연관이지 원인이 아닙니다. 금리가 오른 해에 주가가 내렸어도 경기가 둘을 같이 움직였을 수 있습니다. 지표가 여럿이라 우연히 뚜렷해 보이는 것도 섞일 수 있습니다.',
            '시기에 따라 다름: 표본을 시간순으로 반 나눠 다시 재면 방향이 다릅니다.',
            `지수는 현지 통화(${ix.currency})·배당을 뺀 가격 지수의 월말 종가입니다. 카드를 누르면 자세히 봅니다.`,
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
        {from ? `${ym(from)}~${ym(to)}` : '—'} · 상식대로 {count('yes')} · 반대 {count('no')} · 뚜렷하지
        않음 {count('unclear')}
      </p>
      <div className="rg-tiles ix-tiles">
        {e.rows.map((r) => <IndicatorTile key={r.id} r={r} ext={ext} onPick={(x) => setPick(x.id)} />)}
      </div>
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
