import { useEffect, useState } from 'react'

import { api } from '../api'
import Loading, { FIT_HINT } from '../components/Loading'
import { PremiumBars, fmt } from '../components/Charts'
import FactorCurve from '../components/FactorCurve'

/**
 * 시장 분석 — **요인별 보정계수만** 보여 준다.
 *
 * 예전에는 구간별 평당가 분포(층·입지·연식·면적대)와 월별 추이를 함께 깔았는데,
 * 같은 화면에 두 가지 다른 숫자가 있으니 계속 헷갈렸다. 구간별 평당가는 **다른
 * 요인이 섞인 관측값**이고, 보정계수는 **나머지를 고정했을 때의 순효과**다.
 * 역에서 먼 단지가 마침 신축이 많으면 '입지별 평당가'는 거리 효과를 거꾸로 보여 준다.
 *
 * 이 탭이 답해야 할 질문은 "무엇이 가격을 얼마나 움직이나" 하나다. 그 답은
 * 보정계수 쪽이므로 그것만 남긴다. 구간별 실제 분포는 단지 비교·지도 탭에 있다.
 *
 * 필터도 **분석 기간만** 남겼다. 자치구·면적대 같은 필터는 모델 적합 대상 자체를
 * 바꾸지 않아서(계수는 전체 표본에서 추정된다) 눌러도 아무 일이 없었다.
 */
export default function MarketView({ filters, setFilters }) {
  return (
    <>
      <div className="card">
        <h2>무엇이 가격을 얼마나 움직이나</h2>
        <p className="sub">
          모든 요인을 <b>같은 기준점 대비 %</b>로 환산해 나란히 둡니다. 나머지를 고정했을
          때의 <b>순효과</b>라, 구간별 실제 평당가 분포(단지 비교·지도 탭)와는 숫자가
          다릅니다 — 그쪽은 다른 요인이 섞인 관측값입니다.
        </p>
        <div className="filters">
          <div className="field">
            <label htmlFor="mk-months">분석 기간</label>
            <select
              id="mk-months"
              value={filters.months}
              onChange={(e) => setFilters({ ...filters, months: Number(e.target.value) })}
            >
              <option value={12}>최근 12개월</option>
              <option value={24}>최근 24개월</option>
              <option value={36}>최근 36개월</option>
            </select>
          </div>
        </div>
      </div>

      <FactorPanel months={filters.months} />
    </>
  )
}


/**
 * 요인별 보정계수 — 층 프리미엄을 모든 요인으로 확장한 것.
 *
 * 계수를 그대로 보여주면 단위가 제각각이라(log 평당가/분, log 평당가/년) 크기를
 * 견줄 수 없다. 전부 **같은 기준점 대비 %**로 환산해 한 화면에 나란히 둔다.
 * 그래야 "역 5분 더 가까운 것"과 "세대수 2배"와 "연식 10년"이 각각 얼마짜리인지
 * 비교가 된다.
 *
 * 모델 의존성이 없는 환경에서는 기존 층 프리미엄만 보여주고 물러난다.
 */
function FactorPanel({ months }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    setFailed(false)
    api
      .factors({ months: Math.max(months, 12) })
      .then((d) => alive && setData(d))
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
    }
  }, [months])

  if (failed) {
    return (
      <section className="card">
        <h2>요인별 보정계수</h2>
        <p className="empty">
          보정계수는 모델이 필요합니다. backend 에서{' '}
          <code>pip install -r requirements.txt</code> 후 다시 열어 보세요.
        </p>
      </section>
    )
  }

  if (!data) {
    return (
      <section className="card">
        <h2>요인별 보정계수</h2>
        <Loading label="모델을 적합하는 중" hint={FIT_HINT} />
      </section>
    )
  }

  return (
    <section className="card">
      <h2>요인별 보정계수</h2>
      <p className="sub">
        {data.note} 기준은 <b>{data.reference}</b> 입니다.
      </p>
      <div className="factor-grid">
        {data.factors.map((f) => (
          <div className="factor" key={f.key}>
            <div className="factor-head">
              <strong>{f.label}</strong>
              {f.linearity?.testable && (
                <span
                  className={`lin-badge ${f.linearity.nonlinear ? 'is-nonlinear' : 'is-linear'}`}
                  title={`${f.linearity.note} (p=${f.linearity.p})`}
                >
                  {f.linearity.nonlinear ? '비선형' : '선형'}
                </span>
              )}
              <span className="muted small">기준 {f.reference}</span>
            </div>
            {/* 연속 요인은 곡선으로 — 로그·2차항·스플라인의 굽은 모양은
                대표 지점 막대만으로는 보이지 않는다. 범주형(층·노선)은 막대. */}
            {f.unresolved ? (
              <p className="paste-warn" style={{ paddingLeft: 0 }}>
                {f.unresolved}
              </p>
            ) : f.curve ? (
              <FactorCurve
                curve={f.curve}
                linearCurve={f.linear_curve}
                points={f.levels}
                xLabel={f.x_label}
                refX={f.ref_x}
              />
            ) : (
              <PremiumBars rows={f.levels} />
            )}
            {f.per_unit && (
              <div className="muted small">
                <b>
                  {f.per_unit.label} {f.per_unit.pct > 0 ? '+' : ''}
                  {fmt(f.per_unit.pct, 2)}%
                </b>
                {f.per_unit.se_pct ? ` (SE ${fmt(f.per_unit.se_pct, 2)}%p)` : ''}
              </div>
            )}
            {f.linearity?.testable && (
              <div className="muted small">
                <b>{f.linearity.nonlinear ? '비선형' : '선형'}</b> (p={f.linearity.p}).{' '}
                {f.linearity.note}
                {f.linear_curve ? ' 점선은 직선으로 제약했을 때의 모습입니다.' : ''}
              </div>
            )}
            <div className="muted small">{f.note}</div>
          </div>
        ))}
      </div>
      <p className="muted small">
        스펙 {data.spec} · 거래 {fmt(data.n_obs)}건 · 단지 {data.n_complexes}곳.
        스펙은 M0(도보만) → M3(법정동 고정효과)까지 사다리로 확인할 수 있습니다
        (거리 모델 탭).
      </p>
    </section>
  )
}
