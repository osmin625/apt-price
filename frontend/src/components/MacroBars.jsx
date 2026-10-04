import { fmt, useTooltip } from './Charts'

/**
 * 17행을 한 줄씩 수평 막대로. 산점도가 아니라 막대인 이유가 있다.
 *
 * 4분면은 **두 축을 겹쳐야** 보이는 것에 쓴다. 표본 두께와 가격 편차는 값이 하나씩
 * 뿐이고, 그럴 때 묻는 것은 "어디가 제일 심한가" 와 "어디까지가 정상 범위인가" 다.
 * 그 둘은 정렬된 막대에서 바로 읽히고, 점으로 흩어 놓으면 오히려 안 읽힌다.
 *
 * 축소판에서는 이름표를 지우고 막대만 남긴다. 300px 폭에 17개 이름을 적으면 글자가
 * 겹쳐서 아무것도 못 읽는다 — 4분면 축소판에서 이름표를 뺀 것과 같은 이유다.
 */
export default function MacroBars({
  items,
  value,                 // (d) => number
  label = (d) => d.name,
  // 0 을 가운데에 두고 좌우로 뻗는다. 플러스·마이너스가 섞이는 값(평균/중위 괴리)에 쓴다.
  diverging = false,
  decimals = 1,
  suffix = '',
  mark = () => false,    // 표시할 행 (얇은 표본 등)
  markLabel = '',
  tip: renderTip,
  compact = false,
  max: maxOverride,
}) {
  const tip = useTooltip()
  const vals = items.map(value).filter((v) => v != null)
  if (!vals.length) return <p className="empty">값이 없습니다.</p>

  // 눈금 범위. diverging 은 좌우를 같은 폭으로 둬야 0 선이 가운데에 선다 — 한쪽만
  // 넓히면 같은 길이의 막대가 다른 값을 뜻하게 된다.
  const hi = maxOverride ?? Math.max(...vals.map((v) => (diverging ? Math.abs(v) : v)))
  const span = hi || 1

  return (
    <div className={`mbars${compact ? ' compact' : ''}`}>
      {items.map((d) => {
        const v = value(d)
        if (v == null) return null
        const w = (Math.abs(v) / span) * (diverging ? 50 : 100)
        const neg = v < 0
        const on = mark(d)
        return (
          <div
            key={d.sgg_cd ?? label(d)}
            className={`mbar-row${on ? ' marked' : ''}`}
            onMouseMove={renderTip ? (e) => tip.show(e, renderTip(d)) : undefined}
            onMouseLeave={renderTip ? tip.hide : undefined}
          >
            {!compact && (
              <span className="mbar-label">
                {label(d)}
                {on && markLabel && <em className="mbar-flag">{markLabel}</em>}
              </span>
            )}
            <span className="mbar-track">
              {diverging && <i className="mbar-zero" />}
              <i
                className={`mbar-fill ${neg ? 'neg' : 'pos'}`}
                style={
                  diverging
                    ? { width: `${w}%`, [neg ? 'right' : 'left']: '50%' }
                    : { width: `${w}%`, left: 0 }
                }
              />
            </span>
            {!compact && (
              <span className="mbar-value">
                {diverging && v > 0 ? '+' : ''}
                {fmt(v, decimals)}
                {suffix}
              </span>
            )}
          </div>
        )
      })}
      {tip.node}
    </div>
  )
}
