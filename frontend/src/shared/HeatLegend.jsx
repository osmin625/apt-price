import Hint from './Hint'

/**
 * `heat.js` 색의 범례. 색이 무엇을 뜻하는지 그 그림 바로 위에서 말한다.
 *
 * 범례 막대만 펼쳐 두고, 덧붙이는 말(`children`)은 호버로 접는다. 예전에는 막대 옆에
 * 한 줄로 펼쳐 놓았는데, 탭마다 같은 '좋고 나쁨이 아닙니다' 가 되풀이돼 화면이 설명으로
 * 덮였다.
 */
export default function HeatLegend({ lo = '평균보다 낮음', hi = '평균보다 높음', children }) {
  return (
    <div className="heat-legend">
      <span aria-hidden="true">{lo}</span>
      <span className="heat-legend-bar" aria-hidden="true" />
      <span aria-hidden="true">{hi}</span>
      {children && <Hint>{children}</Hint>}
    </div>
  )
}
