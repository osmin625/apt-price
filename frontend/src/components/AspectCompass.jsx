import { fmt } from './Charts'

/**
 * 향 프리미엄을 **나침반**으로.
 *
 * ## 왜 컴퍼스인가
 *
 * 막대 넷을 세로로 쌓으면 '남·동·서·북' 이 그냥 네 칸이 된다. 그런데 이 값이 말하는
 * 것은 **방향**이라, 방향대로 놓으면 읽는 데 번역이 필요 없다. 북이 위, 남이 아래 —
 * 지도와 같다.
 *
 * ## 0 원과 수염
 *
 * 가운데 점선 원이 **칸 중위**(그 단지·평형의 보통 호가)다. 바깥으로 뻗으면 그보다
 * 비싸게, 안으로 들어가면 싸게 부른다는 뜻이다.
 *
 * 각 방향의 **수염은 95% 구간**이다. 수염이 0 원을 **가로지르면 아직 못 가른다** —
 * 이게 이 그림의 핵심이다. 숫자만 보면 '남향이 +0.67%p' 가 사실처럼 읽히는데,
 * 수염이 원을 넘나드는 것을 보면 단정할 수 없다는 게 한눈에 들어온다.
 *
 * ## 자료가 적은 방향은 **점을 찍지 않는다**
 *
 * 북향은 광고에 거의 안 적혀 칸이 몇 개 안 된다. 그 값을 찍으면 +5.4%p 짜리 가시가
 * 북쪽으로 솟아 그림을 지배한다 — 매물 몇 건이 그림 전체를 끌고 가는 셈이다.
 * 축만 흐리게 그리고 '자료 부족' 이라고 적는다.
 */

// 화면 좌표에서의 방향. 지도와 같게 — 북이 위.
const DIRS = [
  { g: '북', dx: 0, dy: -1, anchor: 'middle', ty: -14 },
  { g: '동', dx: 1, dy: 0, anchor: 'start', ty: 4 },
  { g: '남', dx: 0, dy: 1, anchor: 'middle', ty: 18 },
  { g: '서', dx: -1, dy: 0, anchor: 'end', ty: 4 },
]

const SIZE = 300
const C = SIZE / 2
const R0 = 72 // 0 원
const PER_PCT = 16 // 1%p 당 픽셀
const MAX_R = 128

/* 이름·값이 원 바깥에 붙으므로 viewBox 를 그만큼 넓혀 둔다.
   `overflow: visible` 로 비어져 나오게 뒀더니 아래 범례 글과 겹쳤다 — 재 봤다:
   남향 라벨이 30px, 동향이 32px 넘쳤다. 넘치게 두면 폭에 따라 겹치는 자리가
   달라져 어디서 깨지는지 알 수 없다. 담아 두면 그림이 통째로 줄어들 뿐이다. */
const PAD_X = 52
const PAD_Y = 44

export default function AspectCompass({ groups }) {
  const by = Object.fromEntries((groups || []).map((g) => [g.group, g]))
  const solid = DIRS.filter((d) => by[d.g] && !by[d.g].thin)
  if (!solid.length) return null

  const r = (v) => Math.max(R0 - 56, Math.min(MAX_R, R0 + v * PER_PCT))
  const pt = (d, v) => [C + d.dx * r(v), C + d.dy * r(v)]

  const poly = solid.map((d) => pt(d, by[d.g].vs_cell).join(',')).join(' ')

  return (
    <div className="aspect-compass">
      <svg
        viewBox={`${-PAD_X} ${-PAD_Y} ${SIZE + PAD_X * 2} ${SIZE + PAD_Y * 2}`}
        role="img"
        aria-label="향별 호가 프리미엄 나침반"
      >
        {/* 눈금 원 — 1%p 간격 */}
        {[-2, -1, 1, 2].map((v) => (
          <circle key={v} cx={C} cy={C} r={R0 + v * PER_PCT} className="ac-grid" />
        ))}
        {/* 0 원 — 칸 중위 */}
        <circle cx={C} cy={C} r={R0} className="ac-zero" />

        {/* 축 */}
        {DIRS.map((d) => (
          <line
            key={d.g}
            x1={C}
            y1={C}
            x2={C + d.dx * MAX_R}
            y2={C + d.dy * MAX_R}
            className={`ac-axis${by[d.g] && !by[d.g].thin ? '' : ' is-thin'}`}
          />
        ))}

        {/* 값으로 만든 면 */}
        {solid.length >= 3 && <polygon points={poly} className="ac-area" />}

        {/* 95% 구간 수염 — 0 원을 가로지르면 아직 못 가른다 */}
        {solid.map((d) => {
          const g = by[d.g]
          if (g.lo == null) return null
          const [x1, y1] = pt(d, g.lo)
          const [x2, y2] = pt(d, g.hi)
          return (
            <line key={`w${d.g}`} x1={x1} y1={y1} x2={x2} y2={y2} className="ac-whisker" />
          )
        })}

        {/* 점 */}
        {solid.map((d) => {
          const [x, y] = pt(d, by[d.g].vs_cell)
          return <circle key={`p${d.g}`} cx={x} cy={y} r={4.5} className={`ac-dot${by[d.g].sig ? ' is-sig' : ''}`} />
        })}

        {/* 이름과 값 */}
        {DIRS.map((d) => {
          const g = by[d.g]
          const lx = C + d.dx * (MAX_R + 14)
          const ly = C + d.dy * (MAX_R + 14) + d.ty
          return (
            <g key={`t${d.g}`} className={g && !g.thin ? '' : 'is-thin'}>
              <text x={lx} y={ly} textAnchor={d.anchor} className="ac-name">
                {d.g}향
              </text>
              <text x={lx} y={ly + 14} textAnchor={d.anchor} className="ac-val">
                {!g
                  ? '없음'
                  : g.thin
                    ? `자료 부족 (${fmt(g.cells)}칸)`
                    : `${g.vs_cell > 0 ? '+' : ''}${fmt(g.vs_cell, 2)}%p`}
              </text>
            </g>
          )
        })}
      </svg>

      <p className="muted small ac-legend">
        점선 원이 <b>그 단지·평형의 보통 호가</b>입니다. 바깥이면 더 비싸게, 안쪽이면
        싸게 부른다는 뜻입니다. 눈금 간격은 1%p.
        <br />
        가로지르는 선은 <b>95% 구간</b>입니다 — 그 선이 점선 원을 넘나들면{' '}
        <b>아직 가를 수 없다</b>는 뜻입니다.
      </p>
    </div>
  )
}
