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
 * `heat` 는 카드 색을 정하는 CSS 변수 묶음이다(거시 탭의 자기 역사 백분위). 안 넘기면
 * 지금까지와 같은 카드다 — 가격 분석 탭 카드는 칠하지 않는다.
 */
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
