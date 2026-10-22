import { useState } from 'react'

import { fmt } from './Charts'
import CoefTable from './CoefTable'
import Hint from './Hint'
import ChartLink from './ChartLink'

/**
 * 분해 모델의 **입구** — 맨 위에 수식을 두고, 항을 누르면 그 항의 상세가 아래에 뜬다.
 *
 * ## 왜 수식부터인가
 *
 * 이 탭은 계수 78개를 표로 늘어놓고 있었다. 숫자는 다 있는데 **그것들이 어떤 식의 어느
 * 자리에 들어가는지**가 없어서, '도보 1분당 −1%' 가 Stage 2 의 값이고 '같은 단지 안에서
 * 도보 1분' 은 Stage 1 의 값이라는 것을 표만 보고는 알 수 없었다. 식을 먼저 보여 주고 각
 * 항을 그 항의 숫자로 이어 주면 구조와 숫자가 같이 읽힌다.
 *
 * ## 무엇을 상세에 두나
 *
 * 이 탭에만 있는 것 — 그 항이 무엇이고 어떻게 추정했는지, 계수·표준오차·검정. 항의 효과를
 * 기준점 대비 %로 그린 곡선은 매물 분석의 '요인별 보정계수' 카드가 집이다(데이터 하나에
 * 카드 하나). 여기서는 그 카드를 가리키기만 한다.
 *
 * ## 항 목록을 손으로 적지 않는다
 *
 * Stage 2 의 f(·) 항은 응답의 `spline_terms` 에서, 범주형(브랜드·노선·구)은 계수 이름의
 * 접두에서 만든다. 요인을 더하거나 빼면 식도 따라간다 — 손으로 적은 식은 모델과 어긋난다.
 * 화면 문구에는 정의와 읽는 법만 적고 숫자는 응답에서 그 자리에서 꺼낸다.
 */

// Stage 2 스플라인 항의 짧은 이름. 식 안에 '역까지 도보(분)' 을 다 쓰면 한 줄에 안 든다.
// 모르는 변수는 계수 라벨을 그대로 쓴다 — 빠져도 식은 그려진다.
const SHORT = {
  walk_min: '도보',
  gangnam_min: '강남',
  age: '연식',
  log_households: '세대수',
  top_floor: '최고층',
  elem_dist: '초교',
  mid_dist: '중학교',
  academy: '학원',
  adult: '유흥',
}

const CATS = [
  ['brand_', '브랜드', 'b'],
  ['line_', '노선', 'ℓ'],
  ['sgg_', '구', 'g'],
]

const pct = (v, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${fmt(v, d)}%`)
const pval = (p) => (p == null ? '—' : p < 0.001 ? '<0.001' : fmt(p, 3))

function stage1Terms(fit) {
  return [
    { id: 'y1', sym: 'log P', name: '로그 평당가', side: 'lhs' },
    { id: 'alpha', sym: 'α', sub: '단지', name: '단지 고정효과' },
    { id: 'area', sym: 'g', arg: '면적', name: '면적 곡선' },
    { id: 'floor', sym: 'φ', sub: '층', name: '층 구간' },
    { id: 'month', sym: 'μ', sub: '월', name: '계약월' },
    { id: 'dong', sym: 'δ·d', sub: '동', name: '동 도보편차' },
    fit.stage1.deal_type && { id: 'deal', sym: 'κ', sub: '직거래', name: '거래 유형' },
    { id: 'eps', sym: 'ε', name: '거래 오차' },
  ].filter(Boolean)
}

function stage2Terms(fit) {
  const spline = Object.keys(fit.spline_terms || {}).map((v) => ({
    id: `s:${v}`,
    sym: 'f',
    arg: SHORT[v] || fit.terms.find((t) => t.name === v)?.label || v,
    name: fit.terms.find((t) => t.name === v)?.label || v,
    varName: v,
  }))
  const cats = CATS.filter(([p]) => fit.terms.some((t) => t.name.startsWith(p))).map(
    ([p, label, idx]) => ({ id: `c:${p}`, sym: 'Σ', sub: label, name: `${label} 더미`, prefix: p, idx }),
  )
  return [
    { id: 'y2', sym: 'α̂', sub: '단지', name: '추정한 단지 수준', side: 'lhs' },
    { id: 'const', sym: 'β₀', name: '절편' },
    ...spline,
    ...cats,
    { id: 'u', sym: 'u', sub: '단지', name: '단지 오차' },
  ]
}

function Term({ t, active, linked, onPick }) {
  return (
    <button
      type="button"
      className={`mf-term${active ? ' is-on' : ''}${linked ? ' is-linked' : ''}${t.side === 'lhs' ? ' is-lhs' : ''}`}
      aria-pressed={active}
      onClick={() => onPick(active ? null : t.id)}
      title={t.name}
    >
      <span className="mf-sym">
        {t.sym}
        {t.sub && <sub>{t.sub}</sub>}
        {t.arg && <>({t.arg})</>}
      </span>
      <span className="mf-name">{t.name}</span>
    </button>
  )
}

function Line({ label, terms, pick, setPick, linkedId }) {
  const [lhs, ...rhs] = terms
  return (
    <div className="mf-line">
      <div className="mf-stage">{label}</div>
      <div className="mf-eq">
        <Term t={lhs} active={pick === lhs.id} linked={linkedId === lhs.id} onPick={setPick} />
        <span className="mf-op">=</span>
        {rhs.map((t, i) => (
          <span className="mf-cell" key={t.id}>
            {i > 0 && <span className="mf-op">+</span>}
            <Term t={t} active={pick === t.id} linked={linkedId === t.id} onPick={setPick} />
          </span>
        ))}
      </div>
    </div>
  )
}

/** 항 하나의 상세. 문구는 정의·읽는 법뿐이고, 숫자는 전부 `fit` 에서 꺼낸다. */
function Detail({ id, fit, setPick }) {
  const s1 = fit.stage1
  const box = (title, body) => (
    <div className="mf-detail" role="region" aria-label={`${title} 상세`}>
      <h3>{title}</h3>
      {body}
    </div>
  )
  const toMarket = (
    <p className="muted small">
      기준점 대비 %로 그린 효과 곡선은 <b>매물 분석</b> 탭의 '요인별 보정계수' 카드에 있습니다.
    </p>
  )

  if (id === 'all') {
    return box('전체 계수표 — Stage 2', <CoefTable fit={fit} />)
  }
  if (id === 'y1') {
    return box('log P — 로그 평당가', (
      <>
        <p>
          거래 하나의 <b>전용면적 기준 평당가</b>(거래금액 ÷ 전용 평)에 로그를 씌운 값입니다.
          로그를 씌우면 오른쪽의 각 항이 <b>'몇 % 비싸고 싼가'</b> 로 읽히고, 곱으로 얽힌
          요인들이 더하기로 풀립니다.
        </p>
        <p className="muted small">{fit.dep_var} · 거래 {fmt(s1.n_obs)}건 · 단지 {fmt(s1.n_complexes)}곳</p>
      </>
    ))
  }
  if (id === 'alpha') {
    return box('α단지 — 단지 고정효과', (
      <>
        <p>
          단지마다 하나씩 두는 상수입니다. 학군·브랜드·조망·관리 상태처럼 <b>단지 안에서
          변하지 않는 것은 관측하지 못한 것까지 전부</b> 여기에 흡수됩니다. 그래서 같은 식의
          층·면적·동 효과는 단지끼리의 차이에 휘둘리지 않습니다.
        </p>
        <p>
          대신 역거리·연식·세대수처럼 단지마다 값이 하나뿐인 요인은 여기서 잴 수 없습니다.
          그래서 이 값을 다시 종속변수로 삼아 <b>Stage 2</b> 에서 요인으로 나눕니다.
        </p>
        <p className="muted small">
          기준점 {s1.reference} 에서의 단지 로그 평당가 · 단지 {fmt(s1.n_complexes)}곳 ·
          Stage 1 within-R² {fmt(s1.within_r2, 3)}
        </p>
        <button className="linklike" onClick={() => setPick('y2')}>Stage 2 의 α̂단지 로 →</button>
      </>
    ))
  }
  if (id === 'area') {
    const a = s1.area_linearity || {}
    return box('g(면적) — 전용면적 곡선', (
      <>
        <p>
          전용 84㎡ 를 0 으로 둔 로그 면적의 곡선입니다(제한 3차 스플라인). 평당가 기준이라
          '클수록 비싸다' 가 아니라 <b>작을수록 평당 단가가 높다</b>로 읽습니다.
        </p>
        <table className="coef">
          <tbody>
            <tr><td>형태</td><td>{a.verdict || '—'} (p={pval(a.p)}) · 매듭 {a.knots?.length ?? '—'}개</td></tr>
            <tr><td>직선으로 제약할 때 기울기</td><td>{a.linear_coef == null ? '—' : `${fmt(a.linear_coef, 4)} (SE ${fmt(a.linear_se, 4)})`}</td></tr>
          </tbody>
        </table>
        {a.note && <p className="muted small">{a.note}</p>}
        {toMarket}
      </>
    ))
  }
  if (id === 'floor') {
    return box('φ층 — 층 구간', (
      <>
        <p>
          같은 단지·같은 평형·같은 달이라면 몇 층이 얼마나 비싼가. 기준은 <b>중층</b>(0)입니다.
        </p>
        <table className="coef">
          <thead><tr><th>층 구간</th><th className="num">기준 대비</th><th className="num">95% 구간</th><th className="num">계수</th></tr></thead>
          <tbody>
            {(s1.floor_terms || []).map((f) => (
              <tr key={f.band}>
                <td>{f.band}{f.reference ? ' (기준)' : ''}</td>
                <td className="num">{pct(f.premium_pct)}</td>
                <td className="num muted">{f.reference ? '—' : `${fmt(f.ci_pct[0], 2)} ~ ${fmt(f.ci_pct[1], 2)}%`}</td>
                <td className="num muted">{fmt(f.coef, 5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    ))
  }
  if (id === 'month') {
    return box('μ월 — 계약월', (
      <>
        <p>
          달마다 하나씩 둔 상수입니다. 기준은 <b>최신월</b>(0)이라, 과거 거래를 지금 시세로
          옮겨 같은 자로 견줍니다. 시장 전체가 오르내린 몫이 여기에 들어가므로 다른 항은
          '그 달의 시장' 을 빼고 읽힙니다.
        </p>
        <p className="muted small">평균 월 상승률 {pct(s1.month_trend_pct, 3)}/월</p>
      </>
    ))
  }
  if (id === 'dong') {
    const w = s1.within_walk || {}
    return box('δ·d동 — 같은 단지 안 동 도보편차', (
      <>
        <p>
          동에서 역까지 도보분이 <b>그 단지 평균보다 몇 분 더 먼가</b>입니다. 단지 평균을 뺐으므로
          단지 고정효과와 겹치지 않고, 같은 단지 안의 '역 가까운 동 vs 먼 동' 비교로만
          추정됩니다 — 학군·브랜드·연식이 모두 같은 비교라 가장 깨끗한 도보 효과입니다.
        </p>
        <p className="muted small">
          {w.label} {pct(w.pct, 3)} (t={fmt(w.t, 1)}) · 거래 {fmt(w.n_trades)}건
        </p>
        {w.note && <p className="muted small">{w.note}</p>}
      </>
    ))
  }
  if (id === 'deal') {
    const d = s1.deal_type
    return box('κ직거래 — 거래 유형', (
      <>
        <p>
          직거래(중개 없이 신고한 거래)에 붙는 할인입니다. 증여성·친족 간 거래가 섞여 같은
          단지·평형 안에서도 싸게 신고됩니다. 거래를 버리지 않고 이 할인만 걷어 내므로, 직거래가
          많은 단지가 그 때문에 싸 보이지 않습니다.
        </p>
        <p className="muted small">
          중개거래 대비 {pct(d.pct)} ({fmt(d.ci_pct[0], 2)} ~ {fmt(d.ci_pct[1], 2)}%) · 직거래{' '}
          {fmt(d.n_direct)}건(전체의 {fmt(d.share_pct, 2)}%)
        </p>
      </>
    ))
  }
  if (id === 'eps') {
    return box('ε — 거래 오차', (
      <p>
        위 항들로 설명되지 않는 거래마다의 차이 — 인테리어·급매·조망 같은 집 하나의 사정입니다.
        Stage 1 이 설명하는 몫(within-R²)은 {fmt(s1.within_r2, 3)} 입니다.
      </p>
    ))
  }
  if (id === 'y2') {
    return box('α̂단지 — 추정한 단지 수준', (
      <>
        <p>
          Stage 1 이 단지마다 추정한 α 를 다시 왼쪽에 둡니다. 역거리·연식·세대수는 단지 안에서
          변하지 않아 거래 단위로 넣으면 같은 정보를 거래 수만큼 반복해 세게 되므로, <b>단지를
          하나의 관측치로 접어</b> 단지 단위로 회귀합니다.
        </p>
        <p>
          α̂ 는 추정값이라 단지마다 정밀도가 다릅니다. 거래가 많은 단지일수록 믿을 만하므로
          <b> 가중최소제곱</b>(가중치 1 ÷ (표준오차² + τ²))으로 적합합니다.
        </p>
        <p className="muted small">
          스펙 {fit.spec} {fit.spec_label} · 단지 {fmt(fit.n_complexes)}곳 · R² {fmt(fit.r2, 3)}
        </p>
        {fit.excluded_note && <p className="muted small">{fit.excluded_note}</p>}
        <button className="linklike" onClick={() => setPick('alpha')}>← Stage 1 의 α단지 로</button>
      </>
    ))
  }
  if (id === 'const') {
    const c = fit.terms.find((t) => t.name === 'const')
    return box('β₀ — 절편', (
      <p>
        모든 요인이 기준점이고 브랜드·노선·구 더미가 기준 범주일 때의 단지 로그 평당가입니다.
        단독으로는 뜻이 적고, 다른 항이 이것에서 얼마나 위아래로 미는지를 읽습니다.
        <span className="muted small"> 계수 {fmt(c?.coef, 4)} (SE {fmt(c?.se, 4)})</span>
      </p>
    ))
  }
  if (id === 'u') {
    return box('u단지 — 단지 오차', (
      <>
        <p>
          요인으로 설명되지 않고 남는 <b>단지 프리미엄</b>입니다. 관측하지 못한 학군·재건축 기대·
          조망 같은 것이 여기에 남습니다. 매물 분석의 '요인 기준' 적정가와 '실거래 기준' 적정가가
          갈리는 크기가 대략 이것입니다.
        </p>
        <p className="muted small">
          τ(단지 오차의 표준편차) {fmt(fit.tau, 3)} — 단지 수준으로 약 ±{fmt(fit.tau_pct, 1)}% ·
          조정 R² {fmt(fit.adj_r2, 3)}
        </p>
      </>
    ))
  }
  if (id.startsWith('s:')) {
    const v = id.slice(2)
    const knots = fit.knots?.[v]
    const range = fit.var_range?.[v] || fit.var_range?.[v.replace(/^log_/, '')]
    const head = fit.terms.find((t) => t.name === v)
    return box(`f(${SHORT[v] || v}) — ${head?.label || v}`, (
      <>
        <p>
          단지마다 하나인 값이라 Stage 2 에서 잽니다. 직선을 가정하지 않고 <b>제한 3차
          스플라인</b>으로 곡선을 맞춥니다 — 계수 여러 개가 함께 곡선 하나를 이루므로 낱개 계수는
          단독으로 읽지 않습니다. 직선인지 아닌지는 형태를 가정하지 않고 검정합니다.
        </p>
        <p className="muted small">
          매듭 {knots ? knots.length : '—'}개
          {range && <> · 표본 범위 {fmt(range.lo, 1)} ~ {fmt(range.hi, 1)} (중위 {fmt(range.median, 1)})</>}
        </p>
        <CoefTable fit={fit} only={(name) => name === v} />
        {v === 'walk_min' && fit.walk_vs_ride_ratio && (
          <p className="muted small">{fit.walk_vs_ride_ratio.label} — {fit.walk_vs_ride_ratio.note}</p>
        )}
        {toMarket}
      </>
    ))
  }
  if (id.startsWith('c:')) {
    const p = id.slice(2)
    const label = CATS.find(([x]) => x === p)?.[1]
    const read = {
      brand_: '브랜드마다 하나. 다른 요인을 다 통제하고도 남는 브랜드 프리미엄이지만, 그 브랜드를 올릴 만한 입지가 섞여 있어 위쪽으로 치우친 값으로 읽습니다.',
      line_: '노선마다 하나. 강남 소요시간을 이미 넣었으므로, 이동시간으로 설명되지 않는 노선 몫(지나는 지역의 개발·상권)입니다.',
      sgg_: '구마다 하나. 구 단위 입지·행정을 통째로 흡수해, 역이 가까운 곳일수록 좋은 동네라는 교란을 걷어 냅니다.',
    }[p]
    return box(`Σ${label} — ${label} 더미`, (
      <>
        <p>{read} 기준 범주 대비 로그 차이라, 계수 c 는 <b>exp(c) − 1</b> 만큼 비싸거나 쌉니다.</p>
        <CoefTable fit={fit} only={(name) => name.startsWith(p)} />
      </>
    ))
  }
  return null
}

export default function ModelFormula({ fit }) {
  const [pick, setPick] = useState(null)
  // α단지(Stage 1)와 α̂단지(Stage 2)는 같은 것이다. 하나를 고르면 다른 하나도 표시한다 —
  // 두 단계가 이 항으로 이어진다는 것이 이 식의 요점이다.
  const linkedId = pick === 'alpha' ? 'y2' : pick === 'y2' ? 'alpha' : null
  return (
    <div className="card mf">
      <h2>
        모델은 이렇게 생겼다
        <Hint
          notes={[
            '두 단계입니다. Stage 1 은 거래 하나하나로 층·면적·시점과 단지마다의 수준(α)을 나누고, Stage 2 는 그 단지 수준을 역거리·연식 같은 단지 요인으로 다시 나눕니다.',
            '항을 누르면 그 항이 무엇이고 얼마로 추정됐는지가 아래에 나옵니다.',
          ]}
        />
        <ChartLink id="formula" />
      </h2>
      <Line label="Stage 1 · 거래 단위" terms={stage1Terms(fit)} pick={pick} setPick={setPick} linkedId={linkedId} />
      <Line label="Stage 2 · 단지 단위" terms={stage2Terms(fit)} pick={pick} setPick={setPick} linkedId={linkedId} />
      <div className="mf-foot">
        <button type="button" className={`mf-term mf-all${pick === 'all' ? ' is-on' : ''}`}
                aria-pressed={pick === 'all'} onClick={() => setPick(pick === 'all' ? null : 'all')}>
          <span className="mf-name">전체 계수표</span>
        </button>
      </div>
      {pick ? <Detail id={pick} fit={fit} setPick={setPick} /> : (
        <p className="muted small mf-hint">항을 하나 눌러 보세요.</p>
      )}
    </div>
  )
}
