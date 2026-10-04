import { fmt } from './Charts'

/**
 * 향 프리미엄 그림. 축소판(`compact`)과 창용 두 가지.
 *
 * ## 왜 방향대로 놓나
 *
 * 막대 넷을 세로로 쌓으면 '남·동·서·북' 이 그냥 네 칸이 된다. 이 값이 말하는 것은
 * **방향**이라, 방향대로 놓으면 읽는 데 번역이 필요 없다. 북이 위 — 지도와 같다.
 *
 * ## 축소판은 **색과 글자**로만 말한다
 *
 * 처음에는 축소판에도 눈금 원·수염·다각형을 다 그렸다. 300px 안에서는 선이 너무
 * 많아 "뭘 보라는 거지" 가 됐다. 카드가 답할 질문은 **'어느 쪽이 비싼가'** 하나다.
 * 네 칸을 십자로 놓고 색 진하기로 크기를, 글자로 값을 말한다. 나머지(구간·칸 수·
 * 짝 비교)는 눌러서 띄우는 창에 있다.
 *
 * ## 창에서는 0 원과 수염이 주인공이다
 *
 * 가운데 점선 원이 **칸 중위**(그 단지·평형의 보통 호가)다. 바깥이면 더 비싸게,
 * 안쪽이면 싸게 부른다는 뜻이다. 각 방향의 수염은 95% 구간이고, 그 선이 0 원을
 * **가로지르면 아직 못 가른다.** 숫자만 보면 '남향 +0.67%p' 가 사실처럼 읽히는데,
 * 수염을 보면 단정할 수 없다는 게 한눈에 들어온다.
 *
 * ## 자료가 적은 방향은 값을 그리지 않는다
 *
 * 북향은 광고에 거의 안 적혀 칸이 몇 개 안 된다. 그 값(+5.4%p)을 찍으면 북쪽으로
 * 가시가 솟아 그림을 지배한다 — **매물 몇 건이 그림 전체를 끌고 가는 셈**이다.
 * 자리는 남기되 '자료 부족' 이라고 적는다.
 */

// 화면 좌표에서의 방향. 지도와 같게 — 북이 위.
const DIRS = [
  { g: '북', dx: 0, dy: -1 },
  { g: '동', dx: 1, dy: 0 },
  { g: '남', dx: 0, dy: 1 },
  { g: '서', dx: -1, dy: 0 },
]

/* 색 진하기로 크기를 말한다. 기준은 1%p — 그보다 큰 차이는 실무에서 쓸 만하고,
   그 안쪽은 흥정 범위다(`TARGET_FLOOR` 와 같은 값). */
const tone = (v) => Math.max(0.12, Math.min(1, Math.abs(v) / 1.0))

/** 축소판 — 네 칸 십자. 색과 글자로만 말한다. */
export function AspectCross({ groups }) {
  const by = Object.fromEntries((groups || []).map((g) => [g.group, g]))
  return (
    <div className="ac-cross" aria-label="향별 호가 프리미엄">
      {DIRS.map((d) => {
        const g = by[d.g]
        const thin = !g || g.thin
        const v = g?.vs_cell
        const style =
          thin || v == null
            ? undefined
            : {
                background: `color-mix(in srgb, var(${v < 0 ? '--neg' : '--series-1'}) ${
                  tone(v) * 42
                }%, transparent)`,
              }
        return (
          <div
            key={d.g}
            className={`acx acx-${d.g}${thin ? ' is-thin' : ''}`}
            style={style}
          >
            <b>{d.g}향</b>
            <span>
              {thin || v == null ? '자료 부족' : `${v > 0 ? '+' : ''}${fmt(v, 2)}%p`}
            </span>
          </div>
        )
      })}
      <div className="acx acx-mid">
        보통
        <br />
        호가
      </div>
    </div>
  )
}

const SIZE = 300
const C = SIZE / 2
const R0 = 72 // 0 원
const PER_PCT = 16 // 1%p 당 픽셀
const MAX_R = 128
/* 이름·값이 원 바깥에 붙으므로 viewBox 를 그만큼 넓혀 둔다. `overflow: visible` 로
   비어져 나오게 뒀더니 아래 범례 글과 겹쳤다(재 봤다: 남향 30px, 동향 32px 넘침). */
const PAD_X = 52
const PAD_Y = 44

/** 창용 — 눈금 원·수염까지 전부. */
export default function AspectCompass({ groups }) {
  const by = Object.fromEntries((groups || []).map((g) => [g.group, g]))
  const solid = DIRS.filter((d) => by[d.g] && !by[d.g].thin)
  if (!solid.length) return null

  const r = (v) => Math.max(R0 - 56, Math.min(MAX_R, R0 + v * PER_PCT))
  const pt = (d, v) => [C + d.dx * r(v), C + d.dy * r(v)]
  const poly = solid.map((d) => pt(d, by[d.g].vs_cell).join(',')).join(' ')
  const label = (d) => ({
    x: C + d.dx * (MAX_R + 14),
    y: C + d.dy * (MAX_R + 14) + (d.dy > 0 ? 18 : d.dy < 0 ? -14 : 4),
    anchor: d.dx > 0 ? 'start' : d.dx < 0 ? 'end' : 'middle',
  })

  return (
    <div className="aspect-compass">
      <svg
        viewBox={`${-PAD_X} ${-PAD_Y} ${SIZE + PAD_X * 2} ${SIZE + PAD_Y * 2}`}
        role="img"
        aria-label="향별 호가 프리미엄 나침반"
      >
        {[-2, -1, 1, 2].map((v) => (
          <circle key={v} cx={C} cy={C} r={R0 + v * PER_PCT} className="ac-grid" />
        ))}
        <circle cx={C} cy={C} r={R0} className="ac-zero" />

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

        {solid.length >= 3 && <polygon points={poly} className="ac-area" />}

        {solid.map((d) => {
          const g = by[d.g]
          if (g.lo == null) return null
          const [x1, y1] = pt(d, g.lo)
          const [x2, y2] = pt(d, g.hi)
          return <line key={`w${d.g}`} x1={x1} y1={y1} x2={x2} y2={y2} className="ac-whisker" />
        })}

        {solid.map((d) => {
          const [x, y] = pt(d, by[d.g].vs_cell)
          return (
            <circle
              key={`p${d.g}`}
              cx={x}
              cy={y}
              r={4.5}
              className={`ac-dot${by[d.g].sig ? ' is-sig' : ''}`}
            />
          )
        })}

        {DIRS.map((d) => {
          const g = by[d.g]
          const L = label(d)
          return (
            <g key={`t${d.g}`} className={g && !g.thin ? '' : 'is-thin'}>
              <text x={L.x} y={L.y} textAnchor={L.anchor} className="ac-name">
                {d.g}향
              </text>
              <text x={L.x} y={L.y + 14} textAnchor={L.anchor} className="ac-val">
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
    </div>
  )
}
