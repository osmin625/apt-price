import { useEffect, useState } from 'react'

import { api } from '../api'
import FitLoading from '../components/FitLoading'
import { PremiumBars, fmt } from '../components/Charts'
import FactorCurve from '../components/FactorCurve'
import Modal from '../components/Modal'
import WalkDetail from '../components/WalkDetail'

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
 * ## 실패했을 때 원인을 단정하지 않는다
 *
 * 예전에는 요청이 실패하면 무조건 "보정계수는 모델이 필요합니다. backend 에서
 * pip install -r requirements.txt 후 다시 열어 보세요" 를 띄웠다. 그런데 실제로
 * 이 문구를 본 상황은 의존성이 멀쩡한 경우였다 — numpy·pandas·statsmodels 가 다
 * 설치돼 있었고 `/api/model/factors` 도 직접 부르면 200 이었다. start.bat 이
 * 프론트(5173)만 기다리고 브라우저를 열어, 아직 안 뜬 백엔드로 첫 요청이 가서
 * 프록시에서 끊긴 것이었다.
 *
 * 그래서 사용자는 멀쩡한 환경에서 pip install 을 다시 돌렸다. **틀린 원인을
 * 단정하는 안내는 없는 안내보다 나쁘다.** 의존성 누락은 백엔드가 503 으로만
 * 알려 주므로 그때만 그 문구를 쓰고, 나머지는 받은 메시지를 그대로 보여 주고
 * 다시 시도할 길을 준다(연결 실패는 서버가 조금 뒤에 뜨면 풀린다).
 */
function FactorPanel({ months }) {
  const [data, setData] = useState(null)
  // 도보거리 카드만 더 깊이 볼 것이 있다. 펼칠 때 따로 받아 온다.
  const [openWalk, setOpenWalk] = useState(false)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    api
      .factors({ months: Math.max(months, 12) })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e))
    return () => {
      alive = false
    }
  }, [months, tick])

  if (error) {
    const deps = error.status === 503
    return (
      <section className="card">
        <h2>요인별 보정계수</h2>
        <p className="empty">
          {deps ? (
            <>
              보정계수는 모델이 필요합니다. backend 에서{' '}
              <code>pip install -r requirements.txt</code> 후 다시 열어 보세요.
            </>
          ) : (
            <>
              {error.message}
              {error.status === 0 && ' 백엔드 창이 아직 뜨는 중일 수 있습니다.'}
            </>
          )}
        </p>
        {!deps && (
          <button className="ghost" onClick={() => setTick((t) => t + 1)}>
            다시 시도
          </button>
        )}
      </section>
    )
  }

  if (!data) {
    return (
      <section className="card">
        <h2>요인별 보정계수</h2>
        <FitLoading months={Math.max(months, 12)} what="보정계수를" />
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
              {f.key === 'walk' ? (
                <button
                  className="linklike factor-open"
                  aria-haspopup="dialog"
                  onClick={() => setOpenWalk((v) => !v)}
                >
                  <strong>{f.label}</strong>
                  <span className="factor-caret" aria-hidden="true">
                    ⤢
                  </span>
                </button>
              ) : (
                <strong>{f.label}</strong>
              )}
              {/* 검출 여부가 먼저다. 효과가 0 과 구분되지 않는 요인에 '선형' 배지를
                  달면 '직선으로 움직인다' 로 읽힌다 — 움직이지 않는 것인데. */}
              {f.linearity?.significant === false && (
                <span
                  className="lin-badge is-null"
                  title={f.linearity.joint_note}
                >
                  검출 안 됨
                </span>
              )}
              {f.linearity?.testable && f.linearity?.significant !== false && (
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
            {/* `f.unresolved` 분기가 있었다. 동 위치 카드가 '검출되지 않았습니다'
                를 띄우던 자리인데, 그 카드를 뺀 뒤로 백엔드가 이 필드를 보내지
                않는다. 죽은 분기는 다음 사람이 '이런 상태가 있나' 하고 찾게 만든다. */}
            {f.curve ? (
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
            {f.linearity?.significant === false && (
              <div className="paste-warn" style={{ paddingLeft: 0 }}>
                이 요인 전체가 0 이라는 가설을 기각하지 못했습니다 (p=
                {f.linearity.joint_p}). 이 표본에서는 <b>효과가 검출되지 않았습니다</b> —
                곡선의 모양을 그대로 믿으면 안 됩니다.
              </div>
            )}
            {f.linearity?.testable && f.linearity?.significant !== false && (
              <div className="muted small">
                <b>{f.linearity.nonlinear ? '비선형' : '선형'}</b> (p={f.linearity.p}).{' '}
                {f.linearity.note}
                {f.linear_curve ? ' 점선은 직선으로 제약했을 때의 모습입니다.' : ''}
              </div>
            )}
            <div className="muted small">{f.note}</div>
            {f.key === 'walk' && (
              <button className="linklike factor-open-hint" onClick={() => setOpenWalk(true)}>
                산점도와 같은 단지 안 비교 보기 →
              </button>
            )}
          </div>
        ))}
      </div>

      {openWalk && (
        <Modal title="역까지 도보거리" onClose={() => setOpenWalk(false)} wide>
          <WalkDetail months={months} />
        </Modal>
      )}

      <p className="muted small">
        스펙 {data.spec} · 거래 {fmt(data.n_obs)}건 · 단지 {data.n_complexes}곳.
        스펙은 M0(도보만) → M3(법정동 고정효과)까지 사다리로 확인할 수 있습니다
        (분해 모델 탭).
      </p>
    </section>
  )
}
