/** `heat.js` 색의 범례. 색이 무엇을 뜻하는지 그 그림 바로 위에서 말한다. */
export default function HeatLegend({ lo = '저점', hi = '고점', children }) {
  return (
    <div className="heat-legend" aria-hidden="true">
      <span>{lo}</span>
      <span className="heat-legend-bar" />
      <span>{hi}</span>
      {children && <span className="muted">— {children}</span>}
    </div>
  )
}
