import { fmt } from '../../shared/Charts'

/**
 * 장기 기법을 고른 종목에 돌린 것 — 그림·계산 표·카드 한 줄(docs/stock/picks.md '장기 투자').
 *
 * 값은 전부 백엔드가 낸다(backend/app/stock/pick.py). 여기서는 받은 값을 늘어놓기만 한다 — 같은 식을 두 곳에 두면
 * 한쪽만 고쳐진다. 표의 나눗셈(주당 값·비율)은 보이기 위한 것이고 그림의 선은 백엔드 계열 그대로다.
 *
 * 그림은 두 꼴이다. 기법이 **주당 가치**를 내면(그레이엄 숫자·넷넷·DCF·안전마진·배당할인) 주가와 같은 자에 선으로
 * 겹치고, **비율**을 내면(ROE·PER·F-점수 …) 주가 아래 칸에 그린다. 주가는 수정 종가이고 로그 눈금이다 — 테슬라처럼
 * 수백 배 오른 종목을 보통 눈금에 그리면 앞쪽이 바닥에 붙는다.
 */

/** 종목 하나에는 뜻이 없는 기법과 그 까닭 — 카드는 흐리게 두고 창에 이것을 적는다. 백엔드 `pick.NA` 와 같아야 한다. */
export const NA_WHY = {
  'buffett-indicator': '시장 전체의 시가총액을 GDP 로 나누는 잣대라 종목 하나에는 뜻이 없습니다.',
  moat: '사업 구조를 읽고 판단하는 기법이라 숫자 하나로 낼 수 없습니다.',
  'magic-formula': '여러 종목을 두 잣대로 줄 세우는 기법이라 종목 하나로는 순위가 없습니다.',
  momentum: '여러 종목의 지난 수익률을 견주는 기법이라 종목 하나로는 뜻이 없습니다.',
}

const C2 = 'var(--series-2)'
const C3 = 'var(--series-3)'
const C4 = 'var(--series-4)'

/** 주가에 겹치는 선 [키, 이름, 색, 점선]. */
const LINES = {
  'graham-number': [['value', '그레이엄 숫자', C2]],
  'net-net': [['value', '주당 순유동자산', C2], ['buy', '그 2/3', C3, true]],
  dcf: [['value', 'DCF 주당 가치', C2]],
  'margin-of-safety': [['low', '비관', C3, true], ['value', '기준', C2], ['high', '낙관', C4, true]],
  ddm: [['value', '배당할인 주당 가치', C2]],
}

/** 아래 칸 — 이름·계열 [키, 이름, 색, 점선, 막대]·기준선·범위. */
const PANELS = {
  'margin-of-safety': { label: '안전마진(%)', series: [['margin', '안전마진', null, false, true]], levels: [0, 25] },
  roe: { label: 'ROE(%)', series: [['roe', 'ROE', C2]], levels: [0, 15] },
  'owner-earnings': {
    label: '시가총액 대비(%)', series: [['oe', '오너 어닝 수익률', C2], ['ey', '이익 수익률', C3, true]], levels: [0],
  },
  'fed-model': { label: '수익률(%)', series: [['ey', '이익 수익률', C2], ['bond', '10년 국채', C3, true]], levels: [0] },
  'low-pe-pb': { label: 'PER(배)', series: [['pe', 'PER', C2]], levels: [15] },
  peg: { label: 'PEG', series: [['peg', 'PEG', C2]], levels: [1] },
  'f-score': { label: 'F-점수', series: [['score', 'F-점수', null, false, true]], levels: [8], range: [0, 9] },
  defensive: { label: '통과한 기준', series: [['score', '통과', null, false, true]], levels: [7], range: [0, 7] },
  'reverse-dcf': {
    label: '성장률(%)', series: [['implied', '주가가 품은 5년 성장률', C2], ['past', '지난 3년 매출 성장률', C3, true]],
    levels: [0],
  },
  cape: { label: 'CAPE(배)', series: [['cape', 'CAPE', C2]], levels: [15] },
  'trend-position': { label: '추세 대비(%)', series: [['dev', '편차', null, false, true]], levels: [0] },
}

const ym = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}`
const day = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
const usd = (v) => (v == null ? '—' : `${fmt(v, Math.abs(v) < 10 ? 2 : 0)}달러`)
const bn = (v) => (v == null ? '—' : `${fmt(v / 1e8, 0)}억 달러`)
const pct = (v, d = 1) => (v == null ? '—' : `${fmt(v * 100, d)}%`)
const x = (v, d = 1) => (v == null ? '—' : `${fmt(v, d)}배`)
const verdict = (b) => (b == null ? '자료 부족' : b ? '통과' : '미달')
const signed = (v, d = 1) => `${v >= 0 ? '+' : '−'}${fmt(Math.abs(v), d)}`

export const applies = (id) => Boolean(LINES[id] || PANELS[id])

/** 지금 값 — 계열의 마지막 달. 없으면 null. */
function last(co, id, key) {
  const a = co.techniques[id]?.[key]
  return a ? a[a.length - 1] : null
}

/** 로그 눈금 1·2·5 × 10^k — 범위 안의 것만. 너무 많으면 1·10 만. */
function logTicks(vals) {
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const out = []
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
    for (const k of [1, 2, 5]) {
      const v = k * 10 ** e
      if (v >= lo / 1.2 && v <= hi * 1.2) out.push(v)
    }
  }
  return out.length > 6 ? out.filter((v) => Math.log10(v) % 1 === 0) : out
}

/** 아래 칸 값이 한두 달 튀면(이익이 0 근처인 달의 PER 수천 배) 칸 전체가 납작해진다. 5~95% 바깥은 칸 끝에 붙인다. */
function clip(series, levels, range) {
  if (range) return { series, range, clipped: false }
  const all = series.flatMap((s) => s.values).filter((v) => v != null).sort((a, b) => a - b)
  if (all.length < 10) return { series, range: null, clipped: false }
  const q = (p) => all[Math.min(all.length - 1, Math.floor(p * all.length))]
  const lo = Math.min(q(0.05), ...levels, 0)
  const hi = Math.max(q(0.95), ...levels)
  let clipped = false
  const out = series.map((s) => ({
    ...s,
    values: s.values.map((v) => {
      if (v == null) return v
      if (v < lo || v > hi) clipped = true
      return Math.min(hi, Math.max(lo, v))
    }),
  }))
  return { series: out, range: [lo, hi], clipped }
}

/** 그림 스펙(ExampleChart). */
export function chart(id, co) {
  const t = co.techniques[id] || {}
  const overlays = (LINES[id] || []).map(([k, label, color, dash]) => ({ label, color, dash, values: t[k] || [] }))
  const vals = [...co.price, ...overlays.flatMap((o) => o.values)].filter((v) => v != null && v > 0)
  const spec = {
    close: co.price, priceLabel: `${co.label} 수정 주가`, axis: true, log: true, yTicks: logTicks(vals),
    yDigits: Math.min(...vals) < 10 ? 1 : 0,
    dates: [ym(co.months[0]), ym(co.months[co.months.length - 1])], overlays,
  }
  const p = PANELS[id]
  if (p) {
    const raw = p.series.map(([k, label, color, dash, bar]) => ({ label, color, dash, bar, values: t[k] || [] }))
    const c = clip(raw, p.levels || [], p.range)
    spec.panel = { label: p.label, series: c.series, levels: p.levels, range: c.range }
    spec.clipped = c.clipped
  }
  return spec
}

/** 카드의 한 줄 — 지금 값. */
export function short(id, co) {
  const n = co.now
  if (!applies(id)) return null
  if (LINES[id] && id !== 'margin-of-safety') {
    const v = last(co, id, 'value')
    return v == null ? '지금 값 없음' : `${usd(v)} · 주가 ${usd(n.price)}`
  }
  const v = {
    'margin-of-safety': () => {
      const m = last(co, id, 'margin')
      // 주가가 가치의 몇 배면 '안전마진 −5,000%' 는 읽히지 않는다 — 배수로 적는다.
      if (m == null) return null
      return m < -100 ? `주가가 기준 가치의 ${fmt(1 - m / 100, 1)}배` : `안전마진 ${fmt(m, 0)}%`
    },
    roe: () => (last(co, id, 'roe') == null ? null : `ROE ${fmt(last(co, id, 'roe'), 1)}%`),
    'owner-earnings': () => (last(co, id, 'oe') == null ? null : `오너 어닝 수익률 ${fmt(last(co, id, 'oe'), 1)}%`),
    'fed-model': () => (last(co, id, 'gap') == null ? null : `이익 수익률 − 국채 ${signed(last(co, id, 'gap'), Math.abs(last(co, id, 'gap')) < 1 ? 2 : 1)}%p`),
    'low-pe-pb': () => {
      const pe = last(co, id, 'pe')
      const pb = last(co, id, 'pb')
      return pe == null && pb == null ? null : `PER ${pe == null ? '—' : fmt(pe, 1)} · PBR ${pb == null ? '—' : fmt(pb, 1)}`
    },
    peg: () => (last(co, id, 'peg') == null ? null : `PEG ${fmt(last(co, id, 'peg'), 2)}`),
    'f-score': () => {
      const known = n.fscore.filter((b) => b != null).length
      return `${n.fscore.filter(Boolean).length}점 / 아는 ${known}개`
    },
    defensive: () => `${n.defensive.filter(Boolean).length}개 통과 / 아는 ${n.defensive.filter((b) => b != null).length}개`,
    'reverse-dcf': () => (n.implied_g == null ? null : `주가가 품은 성장률 ${signed(n.implied_g * 100)}%`),
    cape: () => (last(co, id, 'cape') == null ? null : `CAPE ${fmt(last(co, id, 'cape'), 1)}배`),
    'trend-position': () => (last(co, id, 'dev') == null ? null : `추세 대비 ${fmt(last(co, id, 'dev'), 0)}%`),
  }[id]?.()
  return v ?? '지금 값 없음'
}

const fsNames = [
  '총자산이익률 > 0', '영업현금흐름 > 0', '총자산이익률이 1년 전보다 높다', '영업현금흐름 > 순이익',
  '장기부채 ÷ 총자산이 1년 전보다 낮다', '유동비율이 1년 전보다 높다', '주식 수가 늘지 않았다',
  '매출총이익률이 1년 전보다 높다', '자산회전율이 1년 전보다 높다',
]

/** 계산 표 [{caption, cols, rows}] — 마지막 달의 실제 숫자. */
export function calc(id, co) {
  const n = co.now
  const sh = n.shares
  const cap = n.cap
  const head = `${co.label} — ${day(n.date)} 실적 발표 기준(${ym(n.end)} 끝 분기, 지난 12개월) · 주가 ${ym(n.month)}`
  const ni = n.net_income
  const eps = ni != null && sh ? ni / sh : null
  const bps = n.equity != null && sh ? n.equity / sh : null
  const r = n.r
  const rRow = ['할인율 = 10년 국채 + 베타 × 위험 프리미엄',
    r == null ? '—' : `${fmt(n.y10, 2)}% + ${fmt(n.beta, 2)} × ${fmt(n.erp, 0)}% = ${pct(r)}`]
  const gRow = ['5년 성장률 = 지난 3년 매출 성장률', n.g_rev == null ? '—'
    : `${pct(n.g_rev)}${n.g !== n.g_rev ? ` → ${pct(n.g)}(${pct(n.g_clip[0], 0)}~${pct(n.g_clip[1], 0)} 로 자름)` : ''}`]
  const t = {
    'graham-number': () => [{
      caption: head, cols: ['항목', '값'],
      rows: [
        ['주당순이익(EPS) = 순이익 ÷ 주식 수', `${bn(ni)} ÷ ${fmt(sh / 1e8, 1)}억 주 = ${usd(eps)}`],
        ['주당순자산(BPS) = 자기자본 ÷ 주식 수', `${bn(n.equity)} ÷ ${fmt(sh / 1e8, 1)}억 주 = ${usd(bps)}`],
        ['그레이엄 숫자 = √(22.5 × EPS × BPS)', eps > 0 && bps > 0 ? usd(Math.sqrt(22.5 * eps * bps)) : '이익이나 순자산이 0 이하라 낼 수 없음'],
        ['주가', usd(n.price)],
      ],
    }],
    'net-net': () => {
      const ncav = n.assets_current != null && n.liabilities != null ? n.assets_current - n.liabilities : null
      return [{
        caption: head, cols: ['항목', '값'],
        rows: [
          ['유동자산', bn(n.assets_current)], ['− 총부채', bn(n.liabilities)], ['= 순유동자산', bn(ncav)],
          ['주당 순유동자산', ncav == null ? '—' : usd(ncav / sh)], ['그 2/3(사는 선)', ncav == null ? '—' : usd((ncav / sh) * 2 / 3)],
          ['주가', usd(n.price)],
        ],
      }]
    },
    dcf: () => {
      const d = n.dcf
      const base = [
        ['잉여현금흐름 = 영업현금흐름 − 설비투자', `${bn(n.cfo)} − ${bn(n.capex)} = ${bn(n.fcf)}`], rRow, gRow,
        ['그 뒤 영구 성장률', pct(n.tg)],
      ]
      if (!d) {
        return [{ caption: head, cols: ['항목', '값'], rows: [...base, ['DCF', '잉여현금흐름이 0 이하이거나 할인율을 못 정해 낼 수 없음']] }]
      }
      return [
        { caption: head, cols: ['가정', '값'], rows: base },
        {
          caption: '해마다의 현금과 지금 값',
          cols: ['해', '현금', '할인 계수', '지금 값'],
          rows: [
            ...d.rows.map(([y, f, k, pv]) => [`${y}년`, bn(f), fmt(k, 3), bn(pv)]),
            ['말기 가치', bn(d.tv), fmt(d.tv_pv / d.tv, 3), bn(d.tv_pv)],
            ['합계(지분 가치)', '', '', bn(d.total)],
            ['÷ 주식 수 = 주당 가치', '', '', usd(d.total / sh)],
            ['주가', '', '', usd(n.price)],
          ],
        },
      ]
    },
    'margin-of-safety': () => {
      const d = n.dcf
      const rows = d ? [
        ['비관', pct(n.g - n.spread), usd(n.dcf_low / sh), pct(1 - n.price / (n.dcf_low / sh), 0)],
        ['기준', pct(n.g), usd(d.total / sh), pct(1 - n.price / (d.total / sh), 0)],
        ['낙관', pct(n.g + n.spread), usd(n.dcf_high / sh), pct(1 - n.price / (n.dcf_high / sh), 0)],
      ] : [['—', '—', 'DCF 를 낼 수 없음', '—']]
      return [{ caption: `${head} · 내재가치는 DCF(5년 성장률만 ±${pct(n.spread, 0)}p)`, cols: ['가정', '5년 성장률', '주당 가치', '안전마진'], rows }]
    },
    ddm: () => {
      const d0 = n.dividends
      const ok = d0 != null && d0 > 0 && r != null && r - n.tg > 0
      return [{
        caption: head, cols: ['항목', '값'],
        rows: [
          ['지난 12개월 배당 총액', bn(d0)], ['주당 배당 D₀', d0 ? usd(d0 / sh) : '배당이 없음'],
          ['내년 배당 D₁ = D₀ × (1 + g)', ok ? usd((d0 / sh) * (1 + n.tg)) : '—'], rRow, ['g(영구 배당 성장률)', pct(n.tg)],
          ['P = D₁ ÷ (r − g)', ok ? usd((d0 / sh) * (1 + n.tg) / (r - n.tg)) : '—'], ['주가', usd(n.price)],
        ],
      }]
    },
    'reverse-dcf': () => [{
      caption: head, cols: ['항목', '값'],
      rows: [
        ['시가총액', bn(cap)], ['잉여현금흐름', bn(n.fcf)], rRow, ['그 뒤 영구 성장률', pct(n.tg)],
        ['시가총액을 맞추는 5년 성장률', n.implied_g == null ? '−50~100% 안에서 못 맞춤' : pct(n.implied_g)],
        ['지난 3년 매출 성장률', pct(n.g_rev)],
      ],
    }],
    roe: () => {
      const m = ni != null && n.revenue ? ni / n.revenue : null
      const tr = n.revenue != null && n.assets ? n.revenue / n.assets : null
      const lv = n.assets != null && n.equity ? n.assets / n.equity : null
      return [{
        caption: head, cols: ['순이익률', '× 자산회전율', '× 레버리지', '= ROE'],
        rows: [[pct(m), x(tr, 2), x(lv, 2), pct(ni != null && n.equity ? ni / n.equity : null)]],
      }]
    },
    'owner-earnings': () => {
      const oe = ni != null && n.dep != null && n.capex != null ? ni + n.dep - n.capex : null
      return [{
        caption: `${head} · 설비투자 전부를 유지 설비투자로 봄`, cols: ['항목', '값'],
        rows: [['순이익', bn(ni)], ['+ 감가상각', bn(n.dep)], ['− 설비투자', bn(n.capex)], ['= 오너 어닝', bn(oe)],
          ['÷ 시가총액', oe == null ? '—' : pct(oe / cap, 2)], ['순이익 ÷ 시가총액', ni == null ? '—' : pct(ni / cap, 2)]],
      }]
    },
    'fed-model': () => [{
      caption: head, cols: ['항목', '값'],
      rows: [['이익 수익률 = 순이익 ÷ 시가총액', ni == null ? '—' : pct(ni / cap, 2)],
        ['10년 국채(전달 평균)', last(co, id, 'bond') == null ? '—' : `${fmt(last(co, id, 'bond'), 2)}%`], ['차이', last(co, id, 'gap') == null ? '—' : `${fmt(last(co, id, 'gap'), 2)}%p`]],
    }],
    'low-pe-pb': () => [{
      caption: head, cols: ['PER', 'PBR', 'PER × PBR'],
      rows: [[ni > 0 ? x(cap / ni) : '이익 0 이하', n.equity > 0 ? x(cap / n.equity, 2) : '—',
        ni > 0 && n.equity > 0 ? fmt((cap / ni) * (cap / n.equity), 1) : '—']],
    }],
    peg: () => [{
      caption: head, cols: ['PER', '지난 3년 주당순이익 성장률', 'PEG'],
      rows: [[ni > 0 ? x(cap / ni) : '이익 0 이하', pct(n.g_eps), last(co, id, 'peg') == null ? '성장률이나 이익이 0 이하' : fmt(last(co, id, 'peg'), 2)]],
    }],
    'f-score': () => [{
      caption: `${head} · 1년 전 같은 분기와 견줌`, cols: ['기준', '판정'],
      rows: fsNames.map((nm, i) => [nm, verdict(n.fscore[i])]),
    }],
    defensive: () => {
      const yrs = (a) => (a.length ? `${a[0][0].slice(0, 4)}~${a[a.length - 1][0].slice(0, 4)} ${a.length}년` : '없음')
      return [{
        caption: `${head} · 자료가 ${n.min_years}년이 안 되는 기준은 자료 부족`, cols: ['기준', '이 종목', '판정'],
        rows: [
          ['규모 — 1972년 매출 1억 달러를 물가로 올린 값 이상', `${bn(n.revenue)} / 기준 ${bn(n.size)}`, verdict(n.defensive[0])],
          ['유동비율 ≥ 2', n.liabilities_current ? x(n.assets_current / n.liabilities_current, 2) : '—', verdict(n.defensive[1])],
          ['장기부채 ≤ 순운전자본', `${bn(n.lt_debt)} / ${n.assets_current != null && n.liabilities_current != null ? bn(n.assets_current - n.liabilities_current) : '—'}`, verdict(n.defensive[2])],
          ['10년 내내 흑자', yrs(n.annual_ni.slice(-10)), verdict(n.defensive[3])],
          ['20년 내내 배당', yrs(n.annual_div.filter(([, v]) => v > 0)), verdict(n.defensive[4])],
          ['10년에 이익 ⅓ 넘게 성장(3년 평균끼리)', n.annual_ni.length >= 13 ? '13년 자료로 견줌' : `${n.annual_ni.length}년뿐`, verdict(n.defensive[5])],
          ['PER(3년 평균 이익) × PBR ≤ 22.5', '', verdict(n.defensive[6])],
        ],
      }]
    },
    cape: () => [{ caption: head, cols: ['항목', '값'], rows: [['CAPE = 실질 시가총액 ÷ 10년 실질 순이익 평균', x(last(co, id, 'cape'))]] }],
    'trend-position': () => [{ caption: `${co.label} 실질 수정 주가`, cols: ['항목', '값'], rows: [['그달까지의 로그 추세 대비', last(co, id, 'dev') == null ? '—' : `${fmt(last(co, id, 'dev'), 1)}%`]] }],
  }[id]
  return t ? t() : []
}
