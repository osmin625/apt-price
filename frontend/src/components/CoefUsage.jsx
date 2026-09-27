import Hint from './Hint'

/**
 * 이 계수가 **어느 화면의 어느 숫자**를 만드는지.
 *
 * ## 왜 화면에 있어야 하나
 *
 * 세 탭이 하나의 적합을 공유하지만, 그 계수가 모든 숫자에 쓰이지는 않는다.
 * 특히 매물 분석에는 **회귀를 쓰는 숫자와 안 쓰는 숫자가 나란히** 있다 —
 * '요인 기준' 은 여기 계수에서 나오고, '실거래 기준' 은 비교표본 중앙값이라
 * 계수와 무관하다(동 효과만 빌려 쓴다).
 *
 * 그걸 모르면 "같은 모델인데 왜 두 값이 다르지" 에서 멈춘다. 문서에만 적어 두면
 * 화면을 보는 사람은 끝내 모른다. 그래서 계수 옆에 둔다.
 *
 * 확인한 사실이다: 회귀가 예측한 단지 수준을 +10% 하면 요인 기준만 움직이고,
 * 회귀가 낸 동 효과를 +10% 하면 실거래 기준만 움직인다.
 */
export default function CoefUsage() {
  const rows = [
    {
      where: '분해 모델 (이 탭)',
      uses: true,
      what: 'Stage 1·2 계수를 그대로 보여 준다',
    },
    {
      where: '시장 분석 — 요인별 보정계수',
      uses: true,
      what: '같은 계수를 기준점 대비 %로 환산한 것',
    },
    {
      where: '매물 분석 · 순위 — 요인 기준',
      uses: true,
      what: '회귀가 예측한 단지 수준에서 출발해 매물 하나로 옮긴 값',
    },
    {
      where: '매물 분석 · 순위 — 실거래 기준',
      uses: false,
      what: '비교표본 중앙값(비모수). 동 효과만 여기서 빌린다',
    },
  ]

  return (
    <div className="card">
      <h2>
        이 계수는 어디에 쓰이나
        <Hint
          notes={[
            '세 탭이 하나의 적합을 공유하지만, 그 계수가 모든 숫자에 쓰이지는 않습니다.',
            '회귀가 예측한 단지 수준을 +10% 하면 요인 기준만 움직이고, 회귀가 낸 동 효과를 +10% 하면 실거래 기준만 움직입니다 — 서로 다른 경로입니다.',
            '층 계수도 두 경로가 따로 냅니다. 여기서는 Stage 1 의 층 더미를, 적정가 진단은 비교표본에서 직접 잰 값을 씁니다.',
          ]}
        />
      </h2>
      <p className="sub">
        두 방법은 서로 다른 질문에 답하고 서로의 검산이 됩니다 — 회귀는 “펀더멘털 대비
        얼마여야 하나”, 비교표본은 “그 단지 같은 평형이 실제로 얼마에 팔리나”.
      </p>
      <ul className="usage">
        {rows.map((r) => (
          <li key={r.where} className={r.uses ? 'is-on' : 'is-off'}>
            <span className="usage-mark" aria-hidden="true">
              {r.uses ? '●' : '○'}
            </span>
            <span className="usage-where">{r.where}</span>
            <span className="usage-what muted small">{r.what}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
