import { bars, channel, crosses, ema, macd, obv, path, rsi, sma, stdev, stochastic, vwap } from './synth'

/**
 * 단기 매매 탭의 기법 저장소 — 기법 하나가 항목 하나다. 화면(`views/TechniqueView.jsx`)은 이 목록을 그대로 깐다.
 *
 * 항목의 꼴(장기 투자 `long.js` 와 같다):
 *   id · group · name · en · by(원전) · need(필요한 데이터)
 *   summary  카드에 펼쳐 두는 한 줄
 *   idea     원리 — 왜 통한다고 보나
 *   rules    어떻게 쓰나 — 진입·청산 규칙
 *   read     예시 그림에서 볼 것
 *   works · traps   잘 통할 때 · 함정
 *   example()       예시 그림 스펙(components/ExampleChart.jsx). 신호는 규칙을 합성 가격에 돌려 얻는다(synth.js)
 *
 * 글은 화면에 나가므로 시간이 지나도 맞는 지식만 적는다(정의·규칙·원전·알려진 한계). 이 기법이 지금 통하는지,
 * 과거 성적이 어땠는지는 적지 않는다 — 그건 재서 붙이는 것이다(docs/stock/trading.md).
 *
 * `need` 는 이 기법을 실제 지수에 적용하려면 무엇이 있어야 하나다. 지금 받는 것은 일봉 종가뿐이라 'close' 만
 * 실제 지수에 돌릴 수 있다. 나머지는 예시로만 보여 준다(2026-11-12 합의 — 설명이 초점).
 */

export const GROUPS = [
  { id: 'trend', label: '추세·돌파' },
  { id: 'reversion', label: '역추세·과열' },
  { id: 'pattern', label: '차트 패턴' },
  { id: 'candle', label: '캔들·거래량·장중' },
]

export const NEED = {
  close: '종가로 잼',
  ohlc: '고가·저가 필요',
  volume: '거래량 필요',
  intraday: '분봉 필요',
}

// 긴 이동평균은 앞부분이 비므로 길게 만들어 뒤만 보여 준다.
function tail(k, close, marks = []) {
  const off = close.length - k
  return {
    close: close.slice(off),
    cut: (a) => a.slice(off),
    marks: marks.filter((m) => m.i >= off).map((m) => ({ ...m, i: m.i - off })),
  }
}

/** 규칙대로 들어가고 나온 날 — 들고 있지 않을 때만 진입, 들고 있을 때만 청산. */
function trade(n, enter, exit) {
  const marks = []
  let pos = false
  for (let i = 1; i < n; i++) {
    if (!pos && enter(i)) {
      marks.push({ i, dir: 1 })
      pos = true
    } else if (pos && exit(i)) {
      marks.push({ i, dir: -1 })
      pos = false
    }
  }
  return marks
}

/** 계획한 날 근처(±w)의 실제 꼭대기·바닥 — 잡음이 얹혀 꼭짓점이 하루 이틀 밀린다. */
const peak = (x, i, w = 6, lo = false) => {
  let b = i
  for (let j = Math.max(0, i - w); j <= Math.min(x.length - 1, i + w); j++) {
    if (lo ? x[j] < x[b] : x[j] > x[b]) b = j
  }
  return b
}

const firstAfter = (from, n, ok) => {
  for (let i = from; i < n; i++) if (ok(i)) return i
  return n - 1
}

export const TECHNIQUES = [
  /* ── 추세·돌파 ── */
  {
    id: 'ma-cross', group: 'trend', name: '이동평균 교차', en: 'Golden / Death Cross',
    by: '오래된 실무 규칙. 50일·200일 조합이 가장 널리 쓰인다.',
    need: 'close',
    summary: '짧은 평균이 긴 평균을 위로 뚫으면 진입(골든크로스), 아래로 뚫으면 청산(데드크로스).',
    idea: '이동평균은 그 기간 산 사람들의 평균 단가다. 짧은 평균이 긴 평균 위에 있으면 최근에 산 사람들이 더 비싸게 샀다 — 사려는 쪽이 세다는 뜻으로 읽는다. 잡음을 걸러 추세만 남기는 대신 늦게 반응한다.',
    rules: [
      '짧은 평균(예: 50일)이 긴 평균(예: 200일)을 아래에서 위로 뚫은 날 종가에 산다.',
      '반대로 아래로 뚫은 날 판다. 그 사이에는 아무것도 하지 않는다.',
      '변형: 가격이 200일선 위에 있을 때만 들고 있는다(추세 필터).',
    ],
    read: '교차는 바닥·꼭대기보다 한참 뒤에 난다. 오르는 구간의 앞부분과 내리는 구간의 앞부분을 내주고 가운데를 먹는 기법이다.',
    works: ['몇 달씩 한 방향으로 길게 가는 장', '큰 하락을 피하는 것이 목적일 때(하락장의 대부분을 비켜 간다)'],
    traps: ['옆으로 기는 장에서는 교차가 잦아 사고팔 때마다 조금씩 잃는다(휩소)', '신호가 늦어 반등의 첫 구간을 놓친다', '평균 기간을 과거에 잘 맞던 값으로 고르면 과적합이다'],
    example() {
      const full = path([[0, 100], [120, 92], [250, 135], [330, 112], [410, 104], [459, 128]], { seed: 11, noise: 0.007 })
      const m50 = sma(full, 50)
      const m200 = sma(full, 200)
      const marks = crosses(m50, m200).map((c) => ({ i: c.i, dir: c.dir, label: c.dir > 0 ? '골든' : '데드' }))
      const t = tail(260, full, marks)
      return {
        close: t.close,
        overlays: [
          { label: '50일 평균', values: t.cut(m50), color: 'var(--series-1)' },
          { label: '200일 평균', values: t.cut(m200), color: 'var(--series-2)' },
        ],
        marks: t.marks,
      }
    },
  },
  {
    id: 'macd', group: 'trend', name: 'MACD', en: 'Moving Average Convergence Divergence',
    by: '제럴드 아펠(Gerald Appel), 1970년대. 히스토그램은 토머스 아스프레이가 더했다.',
    need: 'close',
    summary: '12일·26일 지수평균의 차이(MACD 선)가 그 9일 평균(신호선)을 넘으면 진입, 밑돌면 청산.',
    idea: '두 평균의 차이는 추세의 속도다. 차이가 벌어지면 가속, 좁혀지면 감속이다. 신호선은 그 속도의 평균이라, MACD 선이 신호선을 넘는 것은 속도가 다시 붙기 시작했다는 뜻으로 읽는다.',
    rules: [
      'MACD 선 = 12일 지수평균 − 26일 지수평균, 신호선 = MACD 선의 9일 지수평균.',
      'MACD 선이 신호선을 위로 뚫으면 진입, 아래로 뚫으면 청산.',
      '0 선 위에서의 교차만 쓰거나(추세 방향과 맞출 때), 가격과 MACD 의 엇갈림(다이버전스)을 반전 신호로 본다.',
    ],
    read: '아래 칸의 막대(히스토그램)가 0 을 지나는 날이 교차다. 이동평균 교차보다 빨리 나는 대신 잦다.',
    works: ['추세가 있고 그 안에서 출렁임이 중간쯤인 장'],
    traps: ['옆으로 기는 장에서 교차가 잦다', '기간(12·26·9)은 관례다 — 과거에 잘 맞던 값으로 바꿔 쓰면 과적합이다'],
    example() {
      const close = path([[0, 100], [40, 112], [70, 104], [120, 126], [150, 118], [199, 132]], { seed: 21, noise: 0.006 })
      const m = macd(close)
      const marks = crosses(m.line, m.signal).filter((c) => c.i > 30)
      return {
        close,
        overlays: [],
        marks,
        panel: {
          label: 'MACD',
          series: [
            { label: '히스토그램', values: m.hist, bar: true },
            { label: 'MACD 선', values: m.line, color: 'var(--series-1)' },
            { label: '신호선', values: m.signal, color: 'var(--series-2)', dash: true },
          ],
          levels: [0],
        },
      }
    },
  },
  {
    id: 'donchian', group: 'trend', name: '신고가 돌파 (돈치안·터틀)', en: 'Donchian Channel Breakout',
    by: '리처드 돈치안의 채널 돌파 규칙. 1983년 리처드 데니스·윌리엄 에크하트의 \'터틀\' 실험이 이 규칙을 썼다.',
    need: 'close',
    summary: '지난 20일 최고가를 넘으면 진입, 지난 10일 최저가 아래로 내려가면 청산.',
    idea: '새 고점은 지난 20일 동안 판 사람이 모두 손해가 아닌 자리다. 팔려는 물량이 가벼워 추세가 이어지기 쉽다고 본다. 진입보다 청산 기간을 짧게 둬서 추세가 꺾이면 빨리 나온다.',
    rules: [
      '오늘 종가가 어제까지 20일의 최고가를 넘으면 산다.',
      '들고 있는 동안 종가가 어제까지 10일의 최저가 아래로 내려가면 판다.',
      '터틀은 변동성(ATR)으로 한 번에 살 양을 정했다 — 규칙의 절반은 진입이 아니라 얼마나 사나였다.',
    ],
    read: '띠의 위쪽 선이 20일 최고가다. 박스 안에서는 아무 일도 없다가, 박스를 벗어나는 날 들어간다.',
    works: ['몇 번의 큰 추세가 작은 손실 여러 번을 메우는 구조 — 승률은 낮고 이길 때 크게 이긴다'],
    traps: ['가짜 돌파(올라섰다가 바로 박스로 돌아옴)가 잦다', '승률이 낮아 연속 손실을 견디기 어렵다'],
    example() {
      const close = path([[0, 100], [60, 103], [70, 99], [90, 104], [140, 125], [160, 117], [180, 123], [219, 108]], { seed: 31, noise: 0.006 })
      const c20 = channel(close, 20)
      const c10 = channel(close, 10)
      const marks = trade(close.length, (i) => c20[i].hi != null && close[i] > c20[i].hi,
        (i) => c10[i].lo != null && close[i] < c10[i].lo)
      return {
        close,
        band: { hi: c20.map((c) => c.hi), lo: c20.map((c) => c.lo), label: '20일 최고·최저' },
        overlays: [{ label: '10일 최저(청산선)', values: c10.map((c) => c.lo), color: 'var(--series-2)', dash: true }],
        marks,
      }
    },
  },

  /* ── 역추세·과열 ── */
  {
    id: 'rsi', group: 'reversion', name: 'RSI 과매수·과매도', en: 'Relative Strength Index',
    by: 'J. 웰스 와일더, 『New Concepts in Technical Trading Systems』(1978).',
    need: 'close',
    summary: '14일 동안 오른 폭이 전체 움직임에서 차지하는 비율. 30 아래는 과매도, 70 위는 과매수.',
    idea: '짧은 기간에 한쪽으로 너무 많이 움직이면 되돌아온다고 본다. RSI 는 오른 날의 평균 상승폭과 내린 날의 평균 하락폭을 견줘 0~100 으로 줄인 값이다.',
    rules: [
      'RSI 가 30 아래로 내려갔다가 다시 30 위로 올라오면 산다.',
      'RSI 가 70 위로 올라갔다가 다시 70 아래로 내려오면 판다.',
      '변형: 200일선 위에서 2일 RSI 가 10 아래로 떨어지면 사서 5일선 위로 오르면 파는 짧은 판(래리 코너스)이 있다.',
    ],
    read: '아래 칸에서 30 선을 위로 넘는 날이 진입, 70 선을 아래로 넘는 날이 청산이다.',
    works: ['큰 추세 없이 오르내리는 장', '지수처럼 한 종목의 악재에 무너지지 않는 대상'],
    traps: ['강한 추세에서는 과매수가 몇 주씩 이어진다 — 오르는 장에서 70 에 팔면 추세를 통째로 놓친다', '하락장의 과매도는 더 떨어지는 칼날일 수 있다'],
    example() {
      const close = path([[0, 110], [25, 98], [45, 108], [70, 116], [90, 102], [110, 99], [140, 114], [170, 104], [199, 115]], { seed: 41, noise: 0.008 })
      const r = rsi(close, 14)
      const marks = trade(close.length, (i) => r[i - 1] != null && r[i - 1] < 30 && r[i] >= 30,
        (i) => r[i - 1] != null && r[i - 1] > 70 && r[i] <= 70)
      return {
        close,
        marks,
        panel: { label: 'RSI(14)', series: [{ label: 'RSI', values: r, color: 'var(--series-1)' }], levels: [30, 70], range: [0, 100] },
      }
    },
  },
  {
    id: 'bollinger', group: 'reversion', name: '볼린저 밴드', en: 'Bollinger Bands',
    by: '존 볼린저, 1980년대. 『Bollinger on Bollinger Bands』(2001).',
    need: 'close',
    summary: '20일 평균 ± 표준편차 2배의 띠. 띠 아래로 닫으면 진입, 평균을 되찾으면 청산.',
    idea: '띠의 폭은 최근 변동성이다. 가격이 띠 밖으로 나가는 것은 최근 움직임에 비해 드문 일이라 평균으로 돌아오기 쉽다고 본다. 반대로 띠가 좁아진 뒤(스퀴즈) 벗어나면 큰 움직임의 시작으로 보는 쓰임도 있다.',
    rules: [
      '되돌림 판: 종가가 아래 띠 밑에서 닫으면 산다. 종가가 20일 평균 위로 오르면 판다.',
      '돌파 판(스퀴즈): 띠 폭이 몇 달 중 가장 좁아진 뒤 위 띠를 넘으면 산다.',
      '볼린저 자신은 띠만으로 사고팔지 말고 다른 지표와 함께 쓰라고 했다.',
    ],
    read: '띠 밖으로 나간 날 바로 다음부터 평균선으로 돌아오는 구간을 먹는다. 띠가 좁아진 곳을 함께 보라.',
    works: ['옆으로 출렁이는 장(되돌림 판)'],
    traps: ['추세가 시작되면 가격이 띠를 타고 간다 — 되돌림 판으로는 계속 손해', '2배는 정규분포의 95% 를 떠올리게 하지만 수익률은 꼬리가 두꺼워 띠 밖이 생각보다 잦다'],
    example() {
      const close = path([[0, 100], [30, 104], [45, 96], [70, 103], [95, 99], [110, 92], [130, 102], [150, 100], [165, 101], [199, 114]], { seed: 51, noise: 0.007 })
      const m = sma(close, 20)
      const s = stdev(close, 20)
      const hi = m.map((v, i) => (v == null ? null : v + 2 * s[i]))
      const lo = m.map((v, i) => (v == null ? null : v - 2 * s[i]))
      const marks = trade(close.length, (i) => lo[i] != null && close[i] < lo[i], (i) => m[i] != null && close[i] > m[i])
      return {
        close,
        band: { hi, lo, label: '20일 ± 2σ' },
        overlays: [{ label: '20일 평균', values: m, color: 'var(--series-1)', dash: true }],
        marks,
      }
    },
  },
  {
    id: 'stochastic', group: 'reversion', name: '스토캐스틱', en: 'Stochastic Oscillator',
    by: '조지 레인(George Lane), 1950년대.',
    need: 'ohlc',
    summary: '지난 14일 고가·저가 범위에서 오늘 종가가 어디쯤인가(%K)와 그 3일 평균(%D). 20 아래·80 위가 기준.',
    idea: '오르는 장에서는 종가가 그날 범위의 위쪽에서, 내리는 장에서는 아래쪽에서 닫히는 경향이 있다. 종가가 범위 아래쪽에 붙어 있다가 올라오기 시작하면 하락의 힘이 빠진 것으로 본다.',
    rules: [
      '%K = (종가 − 14일 최저가) ÷ (14일 최고가 − 14일 최저가) × 100, %D = %K 의 3일 평균.',
      '20 아래에서 %K 가 %D 를 위로 뚫으면 산다. 80 위에서 아래로 뚫으면 판다.',
    ],
    read: '고가·저가로 범위를 잡으므로 캔들로 그렸다. 아래 칸의 두 선이 20·80 선 밖에서 엇갈리는 날을 본다.',
    works: ['오르내림이 규칙적인 장'],
    traps: ['RSI 보다 더 민감해 신호가 잦다', '추세장에서는 RSI 와 같은 함정 — 과열이 오래 간다'],
    example() {
      const close = path([[0, 104], [20, 96], [40, 106], [60, 99], [85, 109], [105, 100], [130, 108], [149, 101]], { seed: 61, noise: 0.006 })
      const b = bars(close, { seed: 62 })
      const s = stochastic(b)
      const marks = []
      crosses(s.k, s.d).forEach((c) => {
        if (c.dir > 0 && s.k[c.i] < 25) marks.push(c)
        if (c.dir < 0 && s.k[c.i] > 75) marks.push(c)
      })
      return {
        bars: b,
        marks,
        panel: {
          label: '스토캐스틱(14, 3)',
          series: [
            { label: '%K', values: s.k, color: 'var(--series-1)' },
            { label: '%D', values: s.d, color: 'var(--series-2)', dash: true },
          ],
          levels: [20, 80],
          range: [0, 100],
        },
      }
    },
  },
  {
    id: 'ma-gap', group: 'reversion', name: '이격도', en: 'Disparity Index',
    by: '일본·한국 시장에서 흔히 쓰는 지표.',
    need: 'close',
    summary: '종가 ÷ 20일 평균 × 100. 100 에서 멀어질수록 평균에서 벗어난 것이다.',
    idea: '가격은 평균에서 멀리 가면 되돌아온다는 가정이다. RSI 가 상승·하락의 비율을 본다면 이격도는 평균과의 거리를 직접 본다. 지수는 20일 이격도 95 아래를 과매도, 105 위를 과열로 흔히 본다.',
    rules: [
      '이격도가 기준(예: 95) 아래로 내려갔다가 다시 올라오면 산다.',
      '과열 기준(예: 105) 위로 올라갔다가 다시 내려오면 판다.',
      '기준은 대상의 변동성에 따라 다르다 — 변동이 큰 종목은 90·110 처럼 넓게 잡는다.',
    ],
    read: '아래 칸의 100 선이 평균이다. 기준선을 넘어갔다 돌아오는 날을 본다.',
    works: ['평균 근처를 오가는 장'],
    traps: ['기준이 고정 숫자라 변동성이 바뀌면 신호가 사라지거나 넘친다', '추세장에서는 RSI 와 같은 함정'],
    example() {
      const close = path([[0, 100], [25, 108], [40, 101], [55, 92], [75, 100], [100, 108], [115, 99], [140, 93], [160, 101], [199, 106]], { seed: 71, noise: 0.008 })
      const m = sma(close, 20)
      const gap = close.map((c, i) => (m[i] == null ? null : (c / m[i]) * 100))
      const marks = trade(close.length, (i) => gap[i - 1] != null && gap[i - 1] < 95 && gap[i] >= 95,
        (i) => gap[i - 1] != null && gap[i - 1] > 105 && gap[i] <= 105)
      return {
        close,
        overlays: [{ label: '20일 평균', values: m, color: 'var(--series-1)', dash: true }],
        marks,
        panel: { label: '20일 이격도', series: [{ label: '이격도', values: gap, color: 'var(--series-1)' }], levels: [95, 100, 105] },
      }
    },
  },

  /* ── 차트 패턴 ── */
  {
    id: 'head-shoulders', group: 'pattern', name: '헤드앤숄더', en: 'Head and Shoulders',
    by: '20세기 초 차트 분석에서 정리됐다. 패턴 통계는 토머스 불코우스키의 『Encyclopedia of Chart Patterns』가 널리 인용된다.',
    need: 'close',
    summary: '세 봉우리(가운데가 가장 높다) 뒤 목선을 깨면 상승 추세가 끝났다고 본다. 거꾸로 선 꼴은 바닥 신호.',
    idea: '왼쪽 어깨와 머리는 오르는 추세 그대로다. 오른쪽 어깨에서 처음으로 앞 고점을 넘지 못한다 — 사려는 힘이 빠졌다는 첫 증거다. 두 골짜기를 이은 목선이 깨지면 그 아래에서 기다리던 매수가 없다는 것이 확인된다.',
    rules: [
      '두 골짜기를 이어 목선을 긋는다.',
      '오른쪽 어깨 뒤 종가가 목선 아래로 닫으면 판다(또는 공매도).',
      '목표: 머리에서 목선까지의 높이만큼 목선 아래. 손절: 오른쪽 어깨 위.',
    ],
    read: '어깨·머리는 규칙이 아니라 사람이 고른다 — 같은 차트에서 사람마다 다르게 긋는다. 목선을 깨는 날 전에는 패턴이 아니다.',
    works: ['긴 상승 뒤 꼭대기 부근'],
    traps: ['목선을 깨기 전에 미리 들어가면 패턴이 완성되지 않는 경우가 많다', '목선을 깬 뒤 다시 목선까지 올라오는 일(되돌림)이 잦다', '지나고 나서 보면 어디서나 보인다 — 정해진 규칙 없이 찾으면 사후 해석이 된다'],
    example() {
      const close = path([[0, 100], [30, 118], [47, 108], [75, 128], [97, 108.5], [120, 119], [138, 106], [175, 90]], { seed: 81, noise: 0.004 })
      const ls = peak(close, 30)
      const hd = peak(close, 75)
      const rs = peak(close, 120)
      const t1 = peak(close, 47, 6, true)
      const t2 = peak(close, 97, 6, true)
      const slope = (close[t2] - close[t1]) / (t2 - t1)
      const neck = (i) => close[t1] + slope * (i - t1)
      const brk = firstAfter(rs, close.length, (i) => close[i] < neck(i))
      const h = close[hd] - neck(hd)
      return {
        close,
        points: [{ i: ls, label: '왼쪽 어깨' }, { i: hd, label: '머리' }, { i: rs, label: '오른쪽 어깨' }],
        lines: [
          { i0: t1 - 10, v0: neck(t1 - 10), i1: brk + 12, v1: neck(brk + 12), label: '목선' },
          { i0: brk, v0: neck(brk) - h, i1: close.length - 1, v1: neck(brk) - h, label: '목표' },
        ],
        marks: [{ i: brk, dir: -1, label: '목선 이탈' }],
      }
    },
  },
  {
    id: 'double-bottom', group: 'pattern', name: '이중 바닥·이중 천장', en: 'Double Bottom / Top',
    by: '고전 차트 패턴. W(바닥)·M(천장) 꼴이라 부른다.',
    need: 'close',
    summary: '비슷한 높이의 바닥 두 번 뒤 그 사이 고점(목선)을 넘으면 하락이 끝났다고 본다.',
    idea: '두 번째로 같은 자리까지 내려왔는데 더 내려가지 않았다 — 그 가격에 사려는 사람이 아직 있다는 증거다. 사이 고점을 넘으면 첫 반등 때 팔았던 사람들의 물량을 다 받아냈다는 뜻이다.',
    rules: [
      '두 바닥의 높이 차이가 작아야 한다(흔히 몇 % 안).',
      '두 바닥 사이 고점을 종가로 넘는 날 산다.',
      '목표: 바닥에서 목선까지 높이만큼 목선 위. 손절: 두 번째 바닥 아래.',
    ],
    read: '두 번째 바닥에서는 아직 아무것도 모른다 — 세 번째, 네 번째 바닥이 될 수도 있다. 목선을 넘는 날이 신호다.',
    works: ['긴 하락 뒤'],
    traps: ['두 번째 바닥에서 미리 사면 바닥이 깨지는 경우를 그대로 맞는다', '두 바닥 사이 간격이 너무 짧으면 그냥 잡음이다'],
    example() {
      const close = path([[0, 122], [35, 100], [58, 113], [88, 100.5], [118, 118], [159, 127]], { seed: 91, noise: 0.004 })
      const b1 = peak(close, 35, 6, true)
      const b2 = peak(close, 88, 6, true)
      const mid = peak(close, 58)
      const neck = close[mid]
      const brk = firstAfter(b2, close.length, (i) => close[i] > neck)
      const h = neck - Math.min(close[b1], close[b2])
      return {
        close,
        points: [{ i: b1, label: '첫 바닥', below: true }, { i: b2, label: '둘째 바닥', below: true }],
        lines: [
          { i0: mid - 8, v0: neck, i1: brk + 12, v1: neck, label: '목선' },
          { i0: brk, v0: neck + h, i1: close.length - 1, v1: neck + h, label: '목표' },
        ],
        marks: [{ i: brk, dir: 1, label: '목선 돌파' }],
      }
    },
  },
  {
    id: 'triangle', group: 'pattern', name: '삼각 수렴', en: 'Triangle',
    by: '고전 차트 패턴. 대칭·상승(위가 평평)·하강(아래가 평평) 세 갈래.',
    need: 'close',
    summary: '고점은 낮아지고 저점은 높아지며 폭이 좁아지다가, 한쪽으로 벗어나는 날 그 방향을 따른다.',
    idea: '사려는 쪽과 팔려는 쪽이 서로 양보하며 가격 범위가 좁아지는 구간이다. 결국 한쪽이 물러서면 쌓인 주문이 한 번에 움직인다. 대칭 삼각형은 방향을 미리 말하지 않는다 — 벗어나는 쪽이 답이다.',
    rules: [
      '고점 둘 이상을 잇는 선, 저점 둘 이상을 잇는 선을 긋는다.',
      '종가가 위쪽 선을 넘으면 산다(아래쪽 선을 깨면 판다).',
      '목표: 삼각형 입구의 높이만큼. 꼭짓점에 너무 가까워진 뒤의 돌파는 힘이 약하다고 본다.',
    ],
    read: '두 선은 사람이 긋는다 — 어느 고점을 잇느냐에 따라 돌파한 날이 달라진다.',
    works: ['추세 중간의 쉬는 구간(이어지는 쪽으로 벗어날 때가 많다고 본다)'],
    traps: ['가짜 돌파', '선을 긋는 기준이 사람마다 달라 같은 차트도 다른 신호가 된다'],
    example() {
      const close = path([[0, 100], [15, 120], [35, 104], [55, 117], [72, 107], [88, 114], [100, 109], [110, 112.5], [125, 112], [159, 128]], { seed: 101, noise: 0.003 })
      const h1 = peak(close, 15, 4)
      const h2 = peak(close, 55, 4)
      const l1 = peak(close, 35, 4, true)
      const l2 = peak(close, 72, 4, true)
      const up = (i) => close[h1] + ((close[h2] - close[h1]) / (h2 - h1)) * (i - h1)
      const dn = (i) => close[l1] + ((close[l2] - close[l1]) / (l2 - l1)) * (i - l1)
      const brk = firstAfter(h2 + 10, close.length, (i) => close[i] > up(i))
      return {
        close,
        lines: [
          { i0: h1, v0: up(h1), i1: brk + 4, v1: up(brk + 4), label: '고점 선' },
          { i0: l1, v0: dn(l1), i1: brk + 4, v1: dn(brk + 4), label: '저점 선' },
        ],
        marks: [{ i: brk, dir: 1, label: '돌파' }],
      }
    },
  },
  {
    id: 'flag', group: 'pattern', name: '깃발·페넌트', en: 'Flag / Pennant',
    by: '고전 차트 패턴. 짧은 기간에 나타나는 이어짐 패턴이다.',
    need: 'close',
    summary: '가파른 상승(깃대) 뒤 짧게 비스듬히 쉬는 구간(깃발)을 위로 벗어나면 상승이 이어진다고 본다.',
    idea: '급하게 오른 뒤에는 차익을 챙기는 매물로 잠시 쉰다. 쉬는 동안 하락폭이 작고 기간이 짧으면 새로 사려는 사람이 그 매물을 다 받아낸 것으로 본다. 쉬는 구간이 평행한 통로면 깃발, 좁아지는 삼각형이면 페넌트다.',
    rules: [
      '깃대가 먼저 있어야 한다 — 짧은 기간의 큰 상승.',
      '쉬는 구간의 위·아래 선을 긋고, 위 선을 종가로 넘으면 산다.',
      '목표: 깃대의 길이만큼 돌파 지점 위. 쉬는 구간이 깃대만큼 길어지면 패턴이 아니라고 본다.',
    ],
    read: '깃발은 아래로 기울어 있다 — 쉬는 동안에도 조금씩 내리는 것이 정상이다.',
    works: ['강한 추세 한가운데'],
    traps: ['깃대 없이 쉬는 구간만 보고 찾으면 그냥 하락이다'],
    example() {
      const close = path([[0, 100], [25, 102], [40, 125], [52, 120], [58, 123], [66, 118], [72, 121.5], [80, 120], [119, 142]], { seed: 111, noise: 0.003 })
      const top = peak(close, 40, 3)
      const lo = peak(close, 66, 4, true)
      const s = (close[peak(close, 58, 3)] - close[top]) / (peak(close, 58, 3) - top)
      const up = (i) => close[top] + s * (i - top)
      const dn = (i) => close[lo] + s * (i - lo)
      const brk = firstAfter(lo + 2, close.length, (i) => close[i] > up(i))
      return {
        close,
        points: [{ i: 25, label: '깃대 시작', below: true }, { i: top, label: '깃대 끝' }],
        lines: [
          { i0: top, v0: up(top), i1: brk + 2, v1: up(brk + 2), label: '' },
          { i0: top, v0: dn(top), i1: brk + 2, v1: dn(brk + 2), label: '깃발' },
        ],
        marks: [{ i: brk, dir: 1, label: '돌파' }],
      }
    },
  },
  {
    id: 'cup-handle', group: 'pattern', name: '컵앤핸들', en: 'Cup with Handle',
    by: '윌리엄 오닐, 『How to Make Money in Stocks』(1988).',
    need: 'close',
    summary: '둥근 바닥(컵) 뒤 앞 고점 근처에서 짧게 쉬고(손잡이), 그 고점을 넘으면 산다.',
    idea: '컵의 왼쪽 고점에서 산 사람들은 오래 물려 있다가 본전 근처에서 판다. 손잡이는 그 매물을 소화하는 구간이다. 소화가 끝나고 앞 고점을 넘으면 위에 팔려는 사람이 거의 없다.',
    rules: [
      '컵은 U 자로 둥글어야 한다(V 자는 아니다). 깊이는 앞 고점의 3분의 1 안쪽이 흔한 기준이다.',
      '손잡이는 컵 위쪽 절반에서, 짧고 얕게.',
      '손잡이 고점(또는 컵 가장자리)을 넘는 날 산다. 오닐은 그날 거래량이 평소보다 크게 늘어야 한다고 했다.',
    ],
    read: '가장자리 선이 컵 왼쪽 고점이다. 손잡이에서 한 번 더 눌린 뒤 넘는다.',
    works: ['시장 전체가 오르는 때의 주도 종목(오닐의 CAN SLIM 은 시장 방향을 함께 본다)'],
    traps: ['거래량 조건을 빼면 반쪽 규칙이다 — 지수 종가만으로는 확인할 수 없다', '컵 모양의 판단이 주관적이다'],
    example() {
      const close = path([[0, 128], [20, 122], [50, 101], [80, 104], [108, 127], [118, 121], [130, 125], [140, 126], [179, 143]], { seed: 121, noise: 0.003 })
      const left = peak(close, 0, 4)
      const right = peak(close, 108, 5)
      const rim = Math.max(close[left], close[right])
      const brk = firstAfter(right + 12, close.length, (i) => close[i] > rim)
      return {
        close,
        points: [{ i: peak(close, 55, 15, true), label: '컵 바닥', below: true }, { i: peak(close, 118, 5, true), label: '손잡이', below: true }],
        lines: [{ i0: left, v0: rim, i1: brk + 10, v1: rim, label: '가장자리' }],
        marks: [{ i: brk, dir: 1, label: '돌파' }],
      }
    },
  },
  {
    id: 'support-resistance', group: 'pattern', name: '지지·저항', en: 'Support / Resistance',
    by: '차트 분석의 기본 개념.',
    need: 'close',
    summary: '여러 번 멈춘 가격대는 다시 멈추기 쉽다. 뚫리면 저항은 지지로, 지지는 저항으로 바뀐다.',
    idea: '같은 가격에서 여러 번 사고판 기억이 남는다. 저항선 근처에서 물렸던 사람은 본전에 팔고, 지지선 근처에서 못 산 사람은 다시 오면 산다. 뚫린 뒤에는 그 기억의 방향이 뒤집힌다.',
    rules: [
      '두세 번 이상 멈춘 가격을 선으로 긋는다(정확한 값이 아니라 띠로 보는 편이 낫다).',
      '지지선 근처에서 사고 저항선 근처에서 판다(박스 매매).',
      '저항을 종가로 넘으면 산다. 되돌아와 그 선에서 멈추면(역할 전환) 확인으로 본다.',
    ],
    read: '박스 안에서는 위·아래 선에서 꺾인다. 위로 벗어난 뒤 옛 저항선까지 내려와서 받쳐지는 구간을 보라.',
    works: ['박스권', '많은 사람이 같은 선을 보는 큰 대상(지수의 어림수 같은)'],
    traps: ['선을 어디에 긋느냐가 사람마다 다르다', '많이 알려진 선일수록 그 근처에서 일부러 흔드는 움직임이 나온다'],
    example() {
      const close = path([[0, 104], [15, 112], [30, 100.5], [48, 111.5], [65, 100], [85, 112], [100, 104], [118, 118], [135, 112.5], [159, 124]], { seed: 131, noise: 0.003 })
      const brk = firstAfter(90, close.length, (i) => close[i] > 112.8)
      return {
        close,
        lines: [
          { i0: 0, v0: 100, i1: brk, v1: 100, label: '지지' },
          { i0: 0, v0: 112.5, i1: close.length - 1, v1: 112.5, label: '저항→지지' },
        ],
        marks: [{ i: brk, dir: 1, label: '돌파' }],
      }
    },
  },

  /* ── 캔들·거래량·장중 ── */
  {
    id: 'hammer', group: 'candle', name: '망치형·교수형', en: 'Hammer / Hanging Man',
    by: '일본 쌀 시장의 캔들 분석(18세기 혼마 무네히사로 전해진다). 서양에는 스티브 니슨의 『Japanese Candlestick Charting Techniques』(1991)가 소개했다.',
    need: 'ohlc',
    summary: '몸통이 작고 아래꼬리가 몸통의 두 배 넘게 긴 캔들. 하락 끝에서 나오면 망치형(반등), 상승 끝에서 나오면 교수형(하락).',
    idea: '그날 장중에 크게 밀렸다가 거의 시가 근처까지 되돌아와 닫혔다. 아래에서 강하게 사들인 사람이 있었다는 흔적이다. 같은 모양이 꼭대기에서 나오면, 장중에 큰 매도가 처음 나왔다는 경고로 읽는다.',
    rules: [
      '아래꼬리가 몸통의 2배 이상, 위꼬리는 거의 없다.',
      '하락이 이어지던 끝에서 나와야 망치형이다. 다음 날 종가가 망치의 몸통 위로 닫히면 확인으로 본다.',
      '손절은 망치의 저가 아래.',
    ],
    read: '한 개의 캔들이다. 앞의 흐름(하락 끝)과 다음 날 확인이 함께 있어야 뜻이 있다.',
    works: ['과매도와 겹칠 때(RSI 30 아래 등)'],
    traps: ['캔들 하나는 하루의 정보다 — 혼자서는 잡음과 구분하기 어렵다', '지수는 시가가 전날 종가와 거의 같아 캔들 모양이 개별 종목보다 단조롭다'],
    example() {
      const close = path([[0, 120], [40, 104], [44, 103], [70, 116], [99, 121]], { seed: 141, noise: 0.004 })
      const k = 43
      const b = bars(close, {
        seed: 142,
        shape: { [k]: (x) => ({ o: x.c * 1.002, c: x.c * 1.004, h: x.c * 1.005, l: x.c * 0.962 }) },
      })
      return { bars: b, points: [], marks: [{ i: k + 1, dir: 1, label: '다음 날 확인' }], callout: { i: k, label: '망치형' } }
    },
  },
  {
    id: 'engulfing', group: 'candle', name: '장악형', en: 'Engulfing',
    by: '일본 캔들 분석. 니슨(1991).',
    need: 'ohlc',
    summary: '앞 캔들의 몸통을 다음 캔들의 몸통이 통째로 감싼다. 하락 끝의 양봉이 음봉을 감싸면 상승 장악형.',
    idea: '어제는 파는 쪽이 이겼는데, 오늘은 어제의 시가·종가 범위를 모두 넘어서며 사는 쪽이 이겼다. 하루 만에 주도권이 넘어갔다는 그림이다.',
    rules: [
      '하락 끝의 작은 음봉 다음에, 그 몸통을 모두 덮는 큰 양봉.',
      '다음 날 종가가 장악형 양봉의 종가 위면 확인으로 본다.',
      '하락 장악형은 반대 — 상승 끝에서 큰 음봉이 앞 양봉을 덮는다.',
    ],
    read: '두 개의 캔들을 함께 본다. 두 번째 몸통이 첫 번째 몸통보다 위·아래로 모두 크다.',
    works: ['지지선·과매도와 겹칠 때'],
    traps: ['지수는 갭이 작아 이 모양이 잘 생기지 않는다', '혼자 쓰면 망치형과 같은 한계'],
    example() {
      const close = path([[0, 118], [45, 103], [48, 103], [75, 114], [99, 118]], { seed: 151, noise: 0.004 })
      const k = 46
      const b = bars(close, {
        seed: 152,
        shape: {
          [k]: (x) => ({ o: x.c * 1.006, c: x.c, h: x.c * 1.008, l: x.c * 0.997 }),
          [k + 1]: (x, prev) => ({ o: prev * 0.996, c: prev * 1.014, h: prev * 1.016, l: prev * 0.994, v: x.v * 1.8 }),
        },
      })
      return { bars: b, marks: [{ i: k + 2, dir: 1, label: '확인' }], callout: { i: k + 1, label: '상승 장악형' } }
    },
  },
  {
    id: 'doji', group: 'candle', name: '도지', en: 'Doji',
    by: '일본 캔들 분석. 니슨(1991).',
    need: 'ohlc',
    summary: '시가와 종가가 거의 같아 몸통이 선처럼 얇은 캔들. 긴 추세 끝에서 나오면 망설임의 신호.',
    idea: '하루 종일 오르내렸지만 결국 시작한 자리로 돌아왔다 — 어느 쪽도 이기지 못했다. 계속 이기던 쪽이 처음 이기지 못한 날이라, 긴 상승 끝의 도지를 힘이 빠진 증거로 본다.',
    rules: [
      '몸통이 그날 범위의 아주 작은 부분(흔히 10% 안).',
      '긴 추세 끝에서만 뜻을 둔다. 다음 날 반대 방향으로 닫히면 확인.',
      '꼬리 모양에 따라 잠자리형(아래꼬리)·비석형(위꼬리)으로 나눈다.',
    ],
    read: '추세 끝 한 개의 얇은 캔들과 다음 날의 방향을 본다.',
    works: ['과매수·저항선과 겹칠 때'],
    traps: ['박스권에서는 도지가 흔해 뜻이 없다'],
    example() {
      const close = path([[0, 100], [50, 122], [53, 123], [80, 110], [99, 106]], { seed: 161, noise: 0.004 })
      const k = 52
      const b = bars(close, { seed: 162, shape: { [k]: (x) => ({ o: x.c, c: x.c * 1.0005, h: x.c * 1.012, l: x.c * 0.988 }) } })
      return { bars: b, marks: [{ i: k + 1, dir: -1, label: '확인' }], callout: { i: k, label: '도지' } }
    },
  },
  {
    id: 'volume-breakout', group: 'candle', name: '거래량 실린 돌파', en: 'Volume Breakout',
    by: '차트 분석의 오래된 원칙 — \'거래량이 가격에 앞선다\'.',
    need: 'volume',
    summary: '박스를 벗어나는 날 거래량이 평소보다 크게 늘면 진짜 돌파, 거래량 없이 벗어나면 가짜로 본다.',
    idea: '거래량은 그 움직임에 얼마나 많은 사람이 동의했나다. 적은 거래로 벗어난 것은 몇 사람의 움직임이라 쉽게 되돌아간다. 많은 거래로 벗어난 것은 위에 있던 매물을 실제로 받아낸 것이다.',
    rules: [
      '박스 위 선을 종가로 넘고, 그날 거래량이 지난 50일 평균의 1.5배(흔한 기준) 이상이면 산다.',
      '거래량 없이 넘은 날은 기다린다.',
    ],
    read: '아래 칸의 거래량 막대가 돌파한 날 튀어 오른다.',
    works: ['개별 종목의 박스권 돌파'],
    traps: ['지수 거래량은 만기일·지수 편입 같은 일정에도 튄다', '거래량 기준(1.5배)에 근거가 있는 것은 아니다'],
    example() {
      const close = path([[0, 104], [20, 111], [40, 102], [60, 111], [80, 103], [100, 110], [104, 117], [139, 126]], { seed: 171, noise: 0.003 })
      const b = bars(close, { seed: 172 })
      const brk = firstAfter(96, close.length, (i) => close[i] > 112)
      for (let i = brk; i < brk + 3; i++) b[i] = { ...b[i], v: b[i].v * 3 }
      return {
        bars: b,
        volume: true,
        lines: [{ i0: 0, v0: 112, i1: brk + 8, v1: 112, label: '박스 위' }],
        marks: [{ i: brk, dir: 1, label: '거래량 동반' }],
      }
    },
  },
  {
    id: 'obv', group: 'candle', name: 'OBV', en: 'On-Balance Volume',
    by: '조 그랜빌, 『Granville\'s New Key to Stock Market Profits』(1963).',
    need: 'volume',
    summary: '오른 날의 거래량은 더하고 내린 날의 거래량은 빼서 쌓은 선. 가격보다 먼저 움직인다고 본다.',
    idea: '가격이 옆으로 기는 동안 OBV 가 오르면, 오르는 날에 더 많은 거래가 몰린다는 뜻이다 — 누군가 조용히 모으고 있다고 읽는다. 가격과 OBV 가 엇갈리면(다이버전스) 가격이 따라갈 것으로 본다.',
    rules: [
      'OBV = 어제 OBV + (오늘 오르면 거래량, 내리면 −거래량, 같으면 0).',
      '가격은 박스인데 OBV 가 고점을 높이면 위로 벗어날 준비로 본다.',
      'OBV 의 값 자체는 시작일에 따라 달라 뜻이 없다 — 방향만 본다.',
    ],
    read: '가격은 박스 안인데 아래 칸의 OBV 는 계속 오른다. 그 뒤 가격이 위로 벗어난다.',
    works: ['거래량이 정보를 담는 개별 종목'],
    traps: ['큰 거래 하루가 선 전체를 바꾼다', '지수는 거래량이 시장 전체의 일정에 휘둘린다'],
    example() {
      const close = path([[0, 100], [25, 105], [45, 100], [70, 105.5], [90, 100.5], [110, 106], [125, 113], [149, 120]], { seed: 181, noise: 0.004 })
      const b = bars(close, { seed: 182 }).map((x, i) => (i > 0 && x.c > x.o ? { ...x, v: x.v * 1.6 } : x))
      return {
        bars: b,
        panel: { label: 'OBV', series: [{ label: 'OBV', values: obv(b), color: 'var(--series-1)' }] },
      }
    },
  },
  {
    id: 'gap', group: 'candle', name: '갭 메우기', en: 'Gap Fill',
    by: '차트 분석의 오래된 관찰. 갭을 보통·돌파·지속·소진 갭으로 나눈다.',
    need: 'ohlc',
    summary: '시가가 전날 종가에서 크게 떨어져 생긴 빈칸(갭)은 나중에 메워지는 일이 많다고 본다. 메워지지 않는 갭은 강한 추세의 증거.',
    idea: '밤사이 소식에 시가가 튀면, 그 사이 가격에서는 거래가 없었다. 과하게 튄 것이면 차익 매물로 빈칸을 메우러 돌아온다. 큰 거래량과 함께 박스를 벗어나는 돌파 갭은 메워지지 않고 그대로 간다.',
    rules: [
      '갭 메우기 매매: 큰 상승 갭 뒤 첫 몇 시간·며칠에 힘이 빠지면, 전날 종가를 목표로 판다(또는 반대로).',
      '갭이 박스 돌파와 함께, 큰 거래량으로 나오면 메우기를 노리지 않는다.',
    ],
    read: '점선이 갭 전날 종가(갭 아래)다. 며칠 뒤 가격이 그 선까지 돌아온다.',
    works: ['뚜렷한 소식 없이 생긴 갭'],
    traps: ['돌파 갭을 메우기 갭으로 잘못 보면 추세를 거슬러 들어간다', '갭은 시가가 있어야 잰다 — 종가만으로는 보이지 않는다'],
    example() {
      const close = path([[0, 100], [39, 104], [40, 109], [44, 110], [58, 103.5], [79, 107]], { seed: 191, noise: 0.003 })
      const k = 40
      const b = bars(close, { seed: 192, shape: { [k]: (x, prev) => ({ o: prev * 1.045, l: prev * 1.04, v: x.v * 2.2 }) } })
      const base = b[k - 1].c
      const fill = firstAfter(k + 1, close.length, (i) => b[i].l <= base)
      return {
        bars: b,
        lines: [{ i0: k - 3, v0: base, i1: fill + 6, v1: base, label: '갭 아래' }],
        marks: [{ i: k + 3, dir: -1, label: '힘 빠짐' }],
        callout: { i: k, label: '상승 갭' },
      }
    },
  },
  {
    id: 'vwap', group: 'candle', name: 'VWAP', en: 'Volume-Weighted Average Price',
    by: '기관의 주문 집행 기준으로 쓰이던 값이 장중 매매의 기준선이 됐다.',
    need: 'intraday',
    summary: '그날 장 시작부터 지금까지 거래량으로 가중한 평균 가격. 그 위면 사는 쪽, 아래면 파는 쪽이 우세하다고 본다.',
    idea: 'VWAP 은 오늘 산 사람 전체의 평균 단가다. 가격이 그 위에 있으면 오늘 산 사람 대부분이 이익이라 쉽게 팔지 않는다. 큰 주문은 VWAP 근처에서 나눠 체결되므로, 오르는 날 VWAP 까지 눌리면 받쳐 준다고 본다.',
    rules: [
      'VWAP = Σ(전형가 × 거래량) ÷ Σ거래량, 전형가 = (고가 + 저가 + 종가) ÷ 3. 매일 장 시작에 다시 센다.',
      '가격이 VWAP 위에서 놀다가 VWAP 까지 눌렸다 다시 오르면 산다.',
      'VWAP 아래로 확실히 내려가면 나온다. 그날 장이 끝나기 전에 정리한다.',
    ],
    read: '5분봉 하루치다. 장 초반 위로 간 뒤, 두 번 VWAP 까지 눌렸다가 올라간다.',
    works: ['거래가 많은 대형 종목·지수 선물의 장중'],
    traps: ['분봉이 있어야 잰다', '하루가 지나면 뜻이 없다(매일 다시 센다)', '수수료와 호가 차이가 이익의 큰 몫을 먹는다'],
    example() {
      const close = path([[0, 100], [12, 103], [22, 101.6], [36, 104], [48, 102.6], [62, 105.5], [77, 105]], { seed: 201, noise: 0.0015 })
      const b = bars(close, { seed: 202 })
      const w = vwap(b)
      const marks = trade(b.length, (i) => i > 10 && b[i - 1].l <= w[i - 1] * 1.002 && b[i].c > w[i] * 1.003,
        (i) => b[i].c < w[i] * 0.997 || i === b.length - 1)
      return {
        bars: b,
        overlays: [{ label: 'VWAP', values: w, color: 'var(--series-4)' }],
        marks,
        xUnit: '봉(5분)',
      }
    },
  },
  {
    id: 'scalping', group: 'candle', name: '스캘핑', en: 'Scalping',
    by: '장내 매매자의 오래된 방식. 전자 거래 뒤 초 단위로 짧아졌다.',
    need: 'intraday',
    summary: '몇 초~몇 분 안에 작은 폭을 여러 번 먹는 매매. 한 번의 이익이 작아 비용과 체결이 성패를 가른다.',
    idea: '짧은 시간의 움직임에는 주문의 쏠림(호가창의 한쪽이 얇다, 큰 주문이 들어온다)이 드러난다. 그 쏠림이 가격에 반영되는 몇 초~몇 분을 먹고 바로 나온다. 방향을 맞히기보다 많이 하는 것이 핵심이다.',
    rules: [
      '대상: 거래가 많고 호가 차이가 가장 작은 것(대형주·지수 선물).',
      '목표와 손절을 진입 전에 정한다 — 보통 목표가 몇 틱, 손절도 몇 틱.',
      '들고 있는 시간을 짧게 정하고, 그 시간이 지나면 이익이든 손해든 나온다.',
    ],
    read: '1분봉 한 시간이다. 짧은 출렁임마다 들어가고 나온다 — 한 번의 폭이 작다.',
    works: ['수수료가 아주 낮고 체결이 빠른 환경'],
    traps: ['한 번의 이익이 호가 차이·수수료와 비슷해 비용을 빼면 남는 것이 없기 쉽다', '분봉·호가 자료가 있어야 잰다', '개인은 체결 속도에서 불리하다'],
    example() {
      const close = path([[0, 100], [8, 100.35], [14, 100.1], [22, 100.45], [30, 100.2], [38, 100.55], [46, 100.3], [59, 100.6]], { seed: 211, noise: 0.0006 })
      const b = bars(close, { seed: 212 })
      const e = ema(close, 5)
      const marks = trade(b.length, (i) => i > 5 && close[i] > e[i] && close[i - 1] <= e[i - 1], (i) => close[i] < e[i])
      return {
        bars: b,
        overlays: [{ label: '5봉 지수평균', values: e, color: 'var(--series-2)' }],
        marks,
        xUnit: '봉(1분)',
      }
    },
  },
]
