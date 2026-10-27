import { useEffect, useState } from 'react'

import { api } from '../api'
import { fmt } from '../components/Charts'
import Modal from '../components/Modal'
import TimeLines from '../components/TimeLines'
import { heatVars, histZ, zText } from '../components/heat'
import { FactorThen } from './FactorAnalysis'
import { FullTable, Legend, MultiLine } from './RegionMetric'
import { RegionMapPlayer } from './RegionMap'
import { PRICE_METRIC } from './registry'
import { BalanceTable, PipeTable, UnsoldTable } from './SupplyTables'
import Hint from '../components/Hint'

/**
 * 주제 창 — 어느 탭에서 열든 같은 내용이다(`registry.js` 참조).
 *
 * 절은 늘 같은 순서다: **공급 → 지역별 추이 → 가격과의 관계.** 주제에 그 원천이
 * 없으면 그 절만 빠진다. 여는 탭에 따라 순서를 바꾸면 '같은 창' 이 아니게 된다.
 *
 * 각 절은 자기 데이터를 직접 받는다. 여는 탭이 이미 들고 있는 값을 넘겨받으면
 * 빠르지만, 그러면 탭마다 넘기는 것이 달라 창이 다시 갈라진다. 같은 세션 안에서는
 * `load` 가 응답을 기억하므로 두 번째부터는 다시 받지 않는다.
 *
 * `topic`: `topicFor()` 가 돌려준 것. `since`(가격 분석 기간)·`region`(공급 지역)은
 * 여는 쪽이 넘기는 초기값이다. `hidden`·`onToggle` 을 넘기면 숨긴 시군구를 여는 쪽이
 * 들고 있다 — 창을 닫았다 다시 열어도 끈 선이 꺼져 있다. 예전에는 카드도 선 그림이라 카드의
 * 선까지 같이 꺼졌는데, 카드가 지도가 된 뒤(2026-10-27)로는 창 안에서만 뜻이 있다.
 */
export default function TopicModal({ topic, onClose, hidden, onToggle }) {
  const [title, setTitle] = useState(topic.title || '')
  return (
    <Modal title={title || '불러오는 중'} onClose={onClose} wide>
      {topic.supply && <SupplySection topic={topic} />}
      {/* 가격 분석 절은 **모든 주제 창**에 둔다. 주제에 지표가 없으면 매매가격지수다
          (`PRICE_METRIC`) — 공급·요인을 보다가 '그래서 구마다 값은 어떻게 갔나' 를
          보려고 가격 분석 탭으로 건너가지 않게 한다. */}
      <MetricSection topic={topic.metric ? topic : { ...topic, metric: PRICE_METRIC }}
                     fallback={!topic.metric}
                     hidden={topic.metric ? hidden : undefined}
                     onToggle={topic.metric ? onToggle : undefined}
                     onLabel={(l) => topic.metric && !topic.title && setTitle(l)} />
      {topic.factor && (
        <FactorSection topic={topic} onLabel={(l) => !topic.title && !topic.metric && setTitle(l)} />
      )}
    </Modal>
  )
}

/* 같은 세션 안에서는 같은 요청을 다시 하지 않는다. 창을 열 때마다 공급·거시
   응답(수십~수백 KB)을 새로 받을 이유가 없다 — 값은 적재해야 바뀐다. */
const memo = new Map()
function load(key, fn) {
  if (!memo.has(key)) memo.set(key, fn().catch((e) => { memo.delete(key); throw e }))
  return memo.get(key)
}

function useLoad(key, fn) {
  const [state, setState] = useState({ data: null, error: null })
  useEffect(() => {
    let alive = true
    setState({ data: null, error: null })
    load(key, fn)
      .then((data) => alive && setState({ data, error: null }))
      .catch((error) => alive && setState({ data: null, error }))
    return () => {
      alive = false
    }
  }, [key])
  return state
}

function SectionHead({ title, from }) {
  return (
    <h3 className="topic-head">
      {title} <span className="muted small">{from}</span>
    </h3>
  )
}

/* ── 지역별 추이 — 가격 분석 ─────────────────────────────────────────── */
const SINCE = [
  ['202401', '최근 3년'],
  ['202001', '최근 7년'],
  ['201201', '전체(2012~)'],
]

function MetricSection({ topic, fallback = false, hidden: hiddenProp, onToggle, onLabel }) {
  const [since, setSince] = useState(topic.since || '202001')
  const [own, setOwn] = useState(() => new Set())
  // 지도에서 가리킨 구 — 아래 선 그림의 그 선을 두드러지게 한다.
  const [focus, setFocus] = useState(null)
  const hidden = hiddenProp || own
  const toggle =
    onToggle ||
    ((sgg) =>
      setOwn((h) => {
        const n = new Set(h)
        n.has(sgg) ? n.delete(sgg) : n.add(sgg)
        return n
      }))
  const { data, error } = useLoad(`series:${topic.metric}:${since}`, () =>
    api.macroSeries({ metric: topic.metric, since }),
  )
  useEffect(() => {
    if (data) onLabel(data.label)
  }, [data])

  return (
    <section className="topic-section">
      <SectionHead title={fallback ? '시군구별 매매가격지수' : '시군구별 추이'} from="가격 분석" />
      <div className="field topic-since">
        <label htmlFor={`ts-${topic.id}`}>기간</label>
        <select id={`ts-${topic.id}`} value={since} onChange={(e) => setSince(e.target.value)}>
          {SINCE.map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>
      {error && <p className="empty">{error.message}</p>}
      {!data && !error && <p className="empty">불러오는 중</p>}
      {data && (
        <>
          <p className="muted small">{data.note}</p>
          <RegionMapPlayer data={data} focus={focus} onFocus={setFocus} />
          <MultiLine data={data} hidden={hidden} focus={focus} />
          <Legend data={data} hidden={hidden} onToggle={toggle} />
          {data.items.some((i) => i.partial) && (
            <p className="paste-warn" style={{ marginTop: 8 }}>
              화성시 분구(만세·효행·병점·동탄)는 <b>분구 시점부터</b> 공표가 시작돼
              시계열이 짧습니다. 없는 기간을 채우지 않았으므로 선이 중간에서 시작합니다.
            </p>
          )}

          <h3 className="mt16">
            최신값 <span className="muted small">{data.items[0]?.latest_ym} 공표</span>
          </h3>
          <p className="muted small">변화율은 고른 기간의 처음 대비입니다.</p>
          <FullTable data={data} />
        </>
      )}
    </section>
  )
}

/* ── 요인 — 거시 분석 ───────────────────────────────────────────────── */
/* 요인 하나의 추이와, 지금과 비슷한 자리였던 때 그 뒤. '그 뒤 가격과의 관계'(요인 × 그 뒤 12개월
   겹친 그림, 시차별 상관)가 있었는데 2026-10-19 걷었다 — 요인과 매매지수를 견주는 것은 거시
   분석의 '한 그림에' 가 모든 요인을 한꺼번에 한다(ui-log). */
function FactorSection({ topic, onLabel }) {
  const { data, error } = useLoad('regime', () => api.regimeOverview())
  const f = data?.factors?.find((x) => x.key === topic.factor)
  useEffect(() => {
    if (f) onLabel(f.label)
  }, [f])

  return (
    <section className="topic-section">
      <SectionHead title="지금 위치와 비슷했던 때" from="거시 분석" />
      {error && <p className="empty">{error.message}</p>}
      {!data && !error && <p className="empty">불러오는 중</p>}
      {data && !f && <p className="empty">이 요인의 값이 없습니다</p>}
      {f && (
        <>
          <p className="muted small">
            {/* 이름 뒤에 조사를 붙이지 않는다 — 요인마다 받침이 달라('소비심리과') 틀린다. */}
            {f.label}({f.region}) · {f.transform_label} · {zText(f.z)}
            {f.caveat && <Hint tone="warn" notes={[f.caveat]} />}
          </p>
          <TimeLines
            series={[{ key: f.key, label: f.label, color: 'var(--series-1)',
                       points: f.series.map((p) => ({ ym: p.ym, value: p.v })) }]}
            unit={f.unit}
            // 금리 차(%p)는 0.25 단위로 움직여 소수 둘째 자리까지 봐야 한다.
            decimals={f.unit === '%p' ? 2 : f.unit === '호' ? 0 : 1}
            // 증감률·차이는 0 이 기준이고, 수준값(심리지수·전세가율·누적 공급)은 0 을 넣으면
            // 선이 한쪽에 납작하게 붙는다.
            zero={!f.level_like}
            // 기준선은 백엔드가 준다 — 심리지수 100 은 중립, 누적 공급 0 은 그동안 적정만큼.
            refLine={f.ref_line ?? null}
            height={220}
            ariaLabel={`${f.label}(${f.region}) 추이`}
          />
          <FactorThen t={f.then} />
        </>
      )}
    </section>
  )
}

/* ── 공급 — 공급 분석 ────────────────────────────────────────────────── */
function SupplySection({ topic }) {
  const { data, error } = useLoad('supply', () => api.supplyOverview())
  return (
    <section className="topic-section">
      <SectionHead
        title={SUPPLY_TITLE[topic.supply] || topic.supply}
        from="공급 분석"
      />
      {error && <p className="empty">{error.message}</p>}
      {!data && !error && <p className="empty">불러오는 중</p>}
      {data && topic.supply === 'unsold' && <UnsoldDetail d={data.unsold} />}
      {data && topic.supply === 'pipeline' && (
        <PipelineDetail regions={data.regions} initial={topic.region} />
      )}
      {data && topic.supply === 'balance' && (
        <BalanceDetail regions={data.regions} initial={topic.region} />
      )}
    </section>
  )
}

const SUPPLY_TITLE = {
  pipeline: '인허가 → 착공 → 준공',
  unsold: '지역별 미분양',
  balance: '적정 공급 대비 준공',
}

/* 적정 대비 공급. 공급 분석의 카드와 거시 분석의 '공급' 요인이 같은 데이터라 창도 이것
   하나다. 지역은 고를 수 있고, 거시 분석에서 열면 그 요인의 지역(경기)이 먼저 선다. */
function BalanceDetail({ regions, initial }) {
  const pick = regions.find((r) => r.sgg_cd === initial) || regions.find((r) => r.sgg_cd === '41') || regions[0]
  const [cd, setCd] = useState(pick?.sgg_cd)
  const r = regions.find((x) => x.sgg_cd === cd) || pick
  if (!r) return <p className="empty">값이 없습니다</p>
  return (
    <>
      <div className="seg topic-seg" role="tablist">
        {regions.map((x) => (
          <button key={x.sgg_cd} role="tab" aria-selected={x.sgg_cd === r.sgg_cd}
                  onClick={() => setCd(x.sgg_cd)}>
            {REGION_LABEL[x.region] || x.region}
          </button>
        ))}
      </div>
      <BalanceTable r={r} />
    </>
  )
}

/* 미분양은 지역마다 자릿수가 달라 한 축에 겹치지 않는다(서울 수천 호, 경기 수만
   호). 공급 분석 카드가 지역마다 한 장인 것과 같은 이유로 그래프도 지역마다 그린다. */
function UnsoldDetail({ d }) {
  return (
    <>
      <div className="topic-multiples">
        {d.regions.map((u) => (
          <div key={u.sgg_cd}>
            <div className="topic-multiple-title">{u.region}</div>
            <TimeLines
              series={[{ key: u.sgg_cd, label: u.region, color: 'var(--series-1)',
                         points: u.series.map((p) => ({ ym: p.ym, value: p.value })) }]}
              unit="호"
              height={170}
              ariaLabel={`${u.region} 미분양 추이`}
            />
          </div>
        ))}
      </div>
      <UnsoldTable d={d} />
    </>
  )
}

const PIPE = [
  ['permit', '인허가', 'var(--series-1)'],
  ['start', '착공', 'var(--series-2)'],
  ['done', '준공', 'var(--series-3)'],
]
const REGION_LABEL = { 서울: '서울', 경기: '경기 전체' }

/**
 * 파이프라인을 크게. 카드 축소판은 세 선의 모양만 보여 주고 숫자가 없었다.
 *
 * 숫자 타일은 계열마다 **지금 12개월 누적 · 1년 전 대비 · 역대 범위 안 위치** 셋이다.
 * 위치는 탭 공통의 자(자기 평균 기준 z, `heat.js` 의 `histZ`)다 — 준공이 자기
 * 역사의 어디쯤인지가 '지금 공급이 많은가' 에 대한 가장 짧은 답이다.
 */
function PipelineDetail({ regions, initial }) {
  const pick = regions.find((r) => r.sgg_cd === initial) || regions.find((r) => r.sgg_cd === '41') || regions[0]
  const [cd, setCd] = useState(pick?.sgg_cd)
  const r = regions.find((x) => x.sgg_cd === cd) || pick
  if (!r) return <p className="empty">값이 없습니다</p>
  const s = r.pipeline.series

  return (
    <>
      <div className="seg topic-seg" role="tablist">
        {regions.map((x) => (
          <button key={x.sgg_cd} role="tab" aria-selected={x.sgg_cd === r.sgg_cd}
                  onClick={() => setCd(x.sgg_cd)}>
            {REGION_LABEL[x.region] || x.region}
          </button>
        ))}
      </div>
      <div className="tiles topic-tiles">
        {PIPE.map(([k, label]) => {
          const pts = s[k] || []
          const last = pts[pts.length - 1]
          if (!last) return null
          const prev = pts.find((p) => p.ym === `${+last.ym.slice(0, 4) - 1}${last.ym.slice(4)}`)
          const yoy = prev?.value ? (last.value / prev.value - 1) * 100 : null
          const vals = pts.map((p) => p.value)
          const peak = pts.reduce((a, b) => (b.value > a.value ? b : a))
          const pos = histZ(vals, last.value)
          return (
            <div className="tile" key={k} style={heatVars(pos)}>
              <div className="label">{label} · 12개월 누적</div>
              <div className="value">
                {fmt(last.value)}
                <span className="unit">호</span>
              </div>
              <div className="note">
                {fmtYm(last.ym)}
                {yoy != null && ` · 1년 전보다 ${yoy > 0 ? '+' : ''}${fmt(yoy, 1)}%`}
              </div>
              <div className="note">
                역대 최고 {fmt(peak.value)}호({fmtYm(peak.ym)})
                {pos != null && (
                  <> · <span className="heat-pos">{zText(pos)}</span></>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <TimeLines
        series={PIPE.map(([k, label, color]) => ({ key: k, label, color, points: s[k] || [] }))}
        unit="호"
        height={300}
        ariaLabel={`${REGION_LABEL[r.region] || r.region} 공급 파이프라인`}
      />
      <p className="muted small">
        착공 몇 달 뒤에 준공으로 이어지는지는 공급 분석의 '2~3년 뒤 입주' 카드가 잽니다.
      </p>
      <PipeTable r={r} />
    </>
  )
}

function fmtYm(ym) {
  if (!ym || ym.length !== 6) return ym || '—'
  return `${ym.slice(0, 4)}.${ym.slice(4)}`
}
