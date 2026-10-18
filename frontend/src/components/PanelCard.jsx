/**
 * 격자에 들어가는 **접힌 카드**. 누르면 창이 뜬다.
 *
 * 매크로 탭에서 쓰던 모양을 그대로 꺼내 공용으로 둔다. 미시 분석의 향 카드도 같은
 * 모양이어야 하기 때문이다 — 한 화면에서 '누르면 커지는 카드' 가 두 가지 모양이면
 * 어느 쪽이 눌리는지 매번 확인하게 된다.
 *
 * 축소판에는 **그림만** 둔다. 숫자·표·경고는 창에 있다. 카드가 답하는 질문은
 * '볼 만한가' 하나이고, '얼마인가' 는 눌러서 묻는 것이다.
 *
 * `heat` 는 카드 색을 정하는 CSS 변수 묶음이다(`heat.js` 의 `heatVars` — 저점 파랑,
 * 고점 빨강). 안 넘기면 칠하지 않은 카드다. 카드 하나가 **계열 하나의 지금 위치**를
 * 말할 때만 칠한다(거시 요인, 미분양). 17곳을 한 그림에 담은 카드는 점을 칠한다.
 */
// 왼쪽 막대를 '방향'(가격을 올리는 쪽 · 내리는 쪽)으로 칠하던 `edge` 가 있었다. 거시 분석이 예측을
// 그만두며(2026-10-18) 그 판정도 걷었다 — 막대는 바탕과 같은 위치 색이다.
export default function PanelCard({ title, sub, onOpen, ready = true, heat, children }) {
  return (
    <div className={`factor macro-card${heat ? ' is-heat' : ''}`} style={heat}>
      <div className="factor-head">
        <button
          className="linklike factor-open"
          onClick={onOpen}
          disabled={!ready}
          aria-haspopup="dialog"
        >
          <strong>{title}</strong>
          <span className="factor-caret" aria-hidden="true">
            &#10530;
          </span>
        </button>
      </div>
      <div className="muted small">{sub}</div>
      <div className="macro-card-body">{ready ? children : <div className="empty">준비 중</div>}</div>
    </div>
  )
}
