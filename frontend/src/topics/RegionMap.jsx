import { useEffect, useMemo, useState } from 'react'

import { fmt, useTooltip } from '../components/Charts'
import Hint from '../components/Hint'
import SHAPES from './sgg_shapes.json'

/**
 * 시군구 지도 — 한 달의 값을 색으로. 가격 분석 지표(매매지수·전세가율·거래량 …)를 그린다.
 *
 * ## 왜 선이 아니라 지도인가
 *
 * 17개 선을 한 축에 놓으면(`MultiLine`) 선들이 서로 감겨 어느 선이 어느 구인지 범례를 오가며
 * 짚어야 했다. 카드 축소판(300px)에서는 더 심했다. 지도는 '어디가 높은가' 를 한눈에 주고,
 * 이웃끼리 같이 움직이는지(수원 4구, 동탄·병점)도 보인다. 대신 시간이 빠지므로 창에서는 달을
 * 옮겨 가며 보고, 선 그림은 그 아래에 그대로 둔다 — 추이의 모양은 선이 더 잘 말한다.
 *
 * ## 색
 *
 * '값' 은 낮음→높음 한 색(`--series-1`) 진하기다. 부호 없는 크기라 초록·빨강을 쓰지 않는다
 * (docs/screens/conventions.md '오름은 초록, 내림은 빨강'). '변화' 는 고른 기간의 첫 달 대비라
 * 부호가 있으므로 + 초록, − 빨강이다.
 *
 * 색의 자는 둘이 다르다. '값' 은 **그 달의 최저·최고** — 그 달 안에서 어디가 높은가를 묻는다.
 * 처음에는 기간 전체를 자로 썼는데, 매매지수가 64~124 를 오가는 사이 마지막 달 17곳은 100~105 에
 * 몰려 전부 같은 파랑이었다. 시군구가 같이 움직이는 지표라 기간 전체의 자로는 구끼리 갈리지 않는다.
 * '변화' 는 **기간 전체**가 자다. 달을 옮길 때 값이 그대로여도 색이 바뀌면 움직이는 것이 값인지
 * 자인지 알 수 없다 — 시간에 따른 움직임은 이쪽에서 본다.
 *
 * 경계는 `scripts/build_sgg_shapes.py` 가 행정동 경계를 녹여 만든 `sgg_shapes.json` 이다.
 */

const MODES = [
  ['value', '값'],
  ['change', '변화'],
]

/** 지역별 그 달 값. 화성 분구처럼 그 달에 공표가 없으면 빠진다. */
function valuesAt(data, ym, mode) {
  const out = new Map()
  for (const it of data.items) {
    const p = it.points.find((x) => x.ym === ym)
    if (!p) continue
    if (mode === 'change') {
      const base = it.points.find((x) => x.ym === data.months[0])
      if (!base || !base.value) continue
      out.set(it.sgg_cd, ((p.value - base.value) / base.value) * 100)
    } else {
      out.set(it.sgg_cd, p.value)
    }
  }
  return out
}

/** 색의 자 — `months` 의 값 전체의 범위. */
function domainOf(data, mode, months) {
  let lo = Infinity
  let hi = -Infinity
  for (const ym of months) {
    for (const v of valuesAt(data, ym, mode).values()) {
      if (v < lo) lo = v
      if (v > hi) hi = v
    }
  }
  if (!Number.isFinite(lo)) return [0, 1]
  if (mode === 'change') {
    const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1
    return [-m, m]
  }
  return [lo, hi === lo ? lo + 1 : hi]
}

function colorOf(v, [lo, hi], mode) {
  if (v == null) return 'color-mix(in srgb, var(--text-muted) 18%, var(--surface-1))'
  if (mode === 'change') {
    const t = Math.min(1, Math.abs(v) / hi)
    return `color-mix(in srgb, var(${v >= 0 ? '--good' : '--neg'}) ${Math.round(8 + t * 82)}%, var(--surface-1))`
  }
  const t = (v - lo) / (hi - lo)
  return `color-mix(in srgb, var(--series-1) ${Math.round(8 + t * 87)}%, var(--surface-1))`
}

/**
 * `month` 를 안 넘기면 마지막 달. `focus`/`onFocus` 는 창에서 선 그림과 짝을 지을 때 쓴다 —
 * 지도에서 구를 가리키면 선 그림의 그 선이 두드러진다.
 */
export default function RegionMap({ data, month, mode = 'value', compact = false, focus, onFocus }) {
  const tip = useTooltip()
  const ym = month || data.months[data.months.length - 1]
  const domain = useMemo(() => domainOf(data, mode, mode === 'change' ? data.months : [ym]), [data, mode, ym])
  const vals = useMemo(() => valuesAt(data, ym, mode), [data, ym, mode])
  const unit = mode === 'change' ? '%' : data.unit
  const dec = mode === 'change' ? 1 : data.decimals
  const [lo, hi] = domain

  return (
    <div className={`region-map${compact ? ' is-compact' : ''}`}>
      <svg viewBox={SHAPES.viewBox} role="img" aria-label={`${data.label} 시군구 지도 ${ym}`}>
        {SHAPES.items.map((s) => {
          const v = vals.get(s.sgg_cd)
          return (
            <path
              key={s.sgg_cd}
              d={s.d}
              fill={colorOf(v, domain, mode)}
              className={focus === s.sgg_cd ? 'is-focus' : undefined}
              onMouseMove={(e) => {
                onFocus?.(s.sgg_cd)
                tip.show(e, (
                  <>
                    <div className="t-title">{s.name}</div>
                    <div className="t-row">
                      {v == null
                        ? mode === 'change' && data.items.find((x) => x.sgg_cd === s.sgg_cd)?.points.some((x) => x.ym === ym)
                          ? `${data.months[0]} 공표가 없어 변화를 셀 수 없음`
                          : `${ym} 공표 없음`
                        : `${ym} · ${mode === 'change' && v > 0 ? '+' : ''}${fmt(v, dec)} ${unit}`}
                    </div>
                  </>
                ))
              }}
              onMouseLeave={() => {
                onFocus?.(null)
                tip.hide()
              }}
            />
          )
        })}
        {!compact &&
          SHAPES.items.map((s) => {
            const v = vals.get(s.sgg_cd)
            return (
              // 이름만 적는다. 값까지 두 줄로 적었더니 팔달·영통, 만안·동안처럼 작은 구끼리 글자가
              // 겹쳤다. 값은 가리키면 나오고, 아래 표에 전부 있다.
              <text key={s.sgg_cd} x={s.lx} y={s.ly} dy="0.35em" textAnchor="middle"
                    className={`region-map-label${v == null ? ' is-empty' : ''}`}>
                {s.short}
              </text>
            )
          })}
      </svg>
      <div className="region-map-scale">
        <span>{mode === 'change' ? `${fmt(lo, 1)}%` : fmt(lo, data.decimals)}</span>
        <span
          className="region-map-bar"
          style={{
            background:
              mode === 'change'
                ? 'linear-gradient(90deg, var(--neg), var(--surface-1) 50%, var(--good))'
                : 'linear-gradient(90deg, color-mix(in srgb, var(--series-1) 8%, var(--surface-1)), var(--series-1))',
          }}
          aria-hidden="true"
        />
        <span>
          {mode === 'change' ? `+${fmt(hi, 1)}%` : fmt(hi, data.decimals)} {mode === 'change' ? '' : unit}
        </span>
        {!compact && (
          <Hint
            notes={[
              mode === 'change'
                ? '고른 기간의 첫 달 대비 변화입니다. 오르면 초록, 내리면 빨강. 색의 자는 기간 전체라 달을 옮겨도 같은 값은 같은 색입니다.'
                : '진할수록 높습니다. 색의 자는 그 달의 최저·최고라, 그 달 안에서 어디가 높은가를 봅니다. 시간에 따른 움직임은 "변화" 에서 봅니다.',
              mode === 'change'
                ? '회색은 그 달이나 기간 첫 달 공표가 없는 곳입니다 — 화성시 분구는 분구 시점부터 공표됩니다.'
                : '회색은 그 달 공표가 없는 곳입니다 — 화성시 분구는 분구 시점부터 공표됩니다.',
            ]}
          />
        )}
      </div>
      {tip.node}
    </div>
  )
}

/**
 * 창에 두는 지도 — 달을 옮기는 막대와 재생 단추, 값·변화 전환이 붙는다.
 * `focus`/`onFocus` 는 아래 선 그림과 나눈다.
 */
export function RegionMapPlayer({ data, focus, onFocus }) {
  const last = data.months.length - 1
  const [i, setI] = useState(last)
  const [mode, setMode] = useState('value')
  const [playing, setPlaying] = useState(false)

  // 기간을 바꾸면 달 목록이 바뀐다 — 마지막 달로 돌아간다.
  useEffect(() => {
    setI(data.months.length - 1)
    setPlaying(false)
  }, [data])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => {
      setI((k) => {
        if (k >= last) {
          setPlaying(false)
          return k
        }
        return k + 1
      })
    }, 120)
    return () => clearInterval(id)
  }, [playing, last])

  const ym = data.months[Math.min(i, last)]
  return (
    <div className="region-map-player">
      <div className="region-map-controls">
        <div className="seg" role="tablist" aria-label="색으로 볼 것">
          {MODES.map(([k, l]) => (
            <button key={k} role="tab" aria-selected={mode === k} onClick={() => setMode(k)}>
              {l}
            </button>
          ))}
        </div>
        <button
          className="ghost"
          onClick={() => {
            if (!playing && i >= last) setI(0)
            setPlaying(!playing)
          }}
          aria-label={playing ? '멈춤' : '처음부터 재생'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <input
          type="range"
          min={0}
          max={last}
          value={Math.min(i, last)}
          onChange={(e) => {
            setPlaying(false)
            setI(Number(e.target.value))
          }}
          aria-label="달"
        />
        <span className="region-map-ym">{ym.slice(0, 4)}.{ym.slice(4)}</span>
      </div>
      <RegionMap data={data} month={ym} mode={mode} focus={focus} onFocus={onFocus} />
    </div>
  )
}
