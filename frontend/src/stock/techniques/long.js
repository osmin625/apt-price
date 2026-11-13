import { fmt } from '../../shared/Charts'
import { rng } from './synth'

/**
 * 장기 투자 탭의 기법 저장소 — 꼴은 `short.js` 와 같다(id·group·name·en·by·need·summary·idea·rules·read·
 * works·traps·example). 다른 점은 예시가 그림(`chart`)이 아니라 **계산 표**(`calc`)인 기법이 많다는 것이다.
 *
 * ## 예시의 숫자는 가상 회사다
 *
 * 버핏·그레이엄의 기법은 한 회사의 재무에 쓰는 것이라 지수에는 적용할 수 없다. 그래서 '가나전자' 같은 가상
 * 회사 숫자로 계산 과정을 보여 준다. 표의 값은 손으로 적지 않고 입력에서 **그 자리에서 계산한다** — 손으로
 * 적으면 한 칸을 고칠 때 합계가 어긋난다. 화면은 표마다 '가상 회사' 라고 적는다.
 *
 * 지수 평가 넷(버핏 지표·이익 수익률·CAPE·추세)은 실제 지수에 돌린 계열이 창에 먼저 나온다
 * (backend/app/stock/valuation.py). 여기의 합성 예시는 그 옆 단추로 남는다 — 읽는 법만 보여 주는 그림이다.
 */

export const GROUPS = [
  { id: 'index-value', label: '지수 평가' },
  { id: 'buffett', label: '버핏' },
  { id: 'graham', label: '그레이엄·가치주' },
  { id: 'dcf', label: '현금흐름 할인' },
  { id: 'quant', label: '성장·계량' },
]

export const NEED = {
  index: '지수에 적용',
  company: '종목 재무 필요',
}

const won = (v) => `${fmt(Math.round(v))}원`
const eok = (v) => `${fmt(Math.round(v))}억`
const pct = (v, d = 1) => `${fmt(v * 100, d)}%`
const x = (v, d = 1) => `${fmt(v, d)}배`
const ok = (b) => (b ? '통과' : '미달')

/** 평균으로 돌아오는 계열 — 지수 평가 예시용. */
function meanRevert(n, { mean, sd, drift = 0, phi = 0.985, seed = 1, start }) {
  const r = rng(seed)
  const out = []
  let v = start ?? mean
  for (let i = 0; i < n; i++) {
    const m = mean + drift * i
    const z = Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r())
    v = m + phi * (v - m) + z * sd * Math.sqrt(1 - phi * phi)
    out.push(v)
  }
  return out
}

const flat = (n, v) => Array(n).fill(v)
const sdOf = (a) => {
  const m = a.reduce((s, v) => s + v, 0) / a.length
  return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / a.length)
}

/** DCF — 5년 고성장 뒤 영구 성장. 반환: 해마다의 줄과 합계. */
function dcf({ fcf0, g, r, tg, years = 5 }) {
  const rows = []
  let f = fcf0
  let pv = 0
  for (let t = 1; t <= years; t++) {
    f *= 1 + g
    const d = 1 / (1 + r) ** t
    rows.push({ t, f, d, pv: f * d })
    pv += f * d
  }
  const tv = (f * (1 + tg)) / (r - tg)
  const tvPv = tv / (1 + r) ** years
  return { rows, pv, tv, tvPv, ev: pv + tvPv }
}

export const TECHNIQUES = [
  /* ── 지수 평가 ── */
  {
    id: 'buffett-indicator', group: 'index-value', name: '버핏 지표', en: 'Market Cap to GDP',
    by: '워런 버핏이 2001년 포춘 기고에서 시장 전체의 값을 재는 가장 좋은 단일 잣대로 꼽았다.',
    need: 'index',
    summary: '주식시장 전체 시가총액 ÷ 국내총생산(GDP). 경제 규모에 비해 주식이 얼마나 비싼가.',
    idea: '기업 이익은 길게 보면 경제 전체의 크기를 따라간다. 그런데 시가총액이 GDP 보다 훨씬 빨리 커졌다면 미래 이익을 너무 앞당겨 값을 매긴 것이다. 버핏은 이 비율이 낮을 때 사고 높을 때 조심하라고 했다.',
    rules: [
      '시가총액(주식 시장 전체) ÷ 명목 GDP 를 분기마다 잰다.',
      '자기 역사 평균·추세와 견준다 — 절대 기준(100% 같은)보다 자기 과거와의 거리가 낫다.',
      '높을수록 그 뒤 10년 수익률이 낮았다는 관계를 쓴다. 다음 달·다음 해를 맞히는 지표가 아니다.',
    ],
    read: '평균선과 ±1 표준편차 띠다. 띠 위로 오래 머무는 구간이 비싼 시기다. 평균 자체가 시간이 지나며 오르는 것에 주의.',
    works: ['10년 단위의 기대 수익을 가늠할 때'],
    traps: ['해외 매출이 큰 기업이 많으면 GDP(국내)가 분모로 맞지 않는다', '금리가 오래 낮으면 비율의 평균 자체가 올라간다', '비싸도 몇 년씩 더 비싸질 수 있다 — 매매 시점을 주지 않는다'],
    example() {
      const n = 480
      const v = meanRevert(n, { mean: 70, sd: 22, drift: 0.09, phi: 0.993, seed: 301, start: 60 })
      const m = v.reduce((s, a) => s + a, 0) / n
      const s = sdOf(v)
      return {
        chart: {
          close: v,
          overlays: [{ label: '평균', values: flat(n, m), color: 'var(--series-2)', dash: true }],
          band: { hi: flat(n, m + s), lo: flat(n, m - s), label: '평균 ± 1σ' },
          yTicks: [50, 100, 150], yUnit: '%', xUnit: '개월',
          priceLabel: '시가총액 ÷ GDP',
        },
      }
    },
  },
  {
    id: 'fed-model', group: 'index-value', name: '이익 수익률 vs 국채 (연준 모델)', en: 'Earnings Yield vs Bond Yield',
    by: '1997년 미국 연준 보고서의 그림에서 시작해 에드 야데니가 \'연준 모델\' 이라 불렀다.',
    need: 'index',
    summary: '주가수익비율(PER)을 뒤집은 이익 수익률(이익 ÷ 주가)을 10년 국채 금리와 견준다.',
    idea: '주식을 사면 이익의 몫을, 국채를 사면 이자를 받는다. 이익 수익률이 국채 금리보다 한참 높으면 주식이 상대적으로 싸다고 본다. 그 차이를 주식이 위험을 지는 대가(위험 프리미엄)의 어림으로 쓴다.',
    rules: [
      '이익 수익률 = 지수의 주당 이익 ÷ 지수(또는 1 ÷ PER).',
      '차이 = 이익 수익률 − 10년 국채 금리. 차이가 클수록 주식이 채권보다 매력적이라고 본다.',
      '물가를 감안하면 이익(실질)과 명목 금리를 견주는 어긋남이 있다 — 물가연동 국채 금리와 견주기도 한다.',
    ],
    read: '위는 두 수익률, 아래 칸은 그 차이다. 차이가 0 아래로 가는 구간(주식이 채권보다 덜 버는)을 본다.',
    works: ['주식과 채권 사이의 비중을 정할 때'],
    traps: ['이론적으로 이익 수익률은 실질, 금리는 명목이라 둘을 바로 견주는 것은 근사다', '금리가 아주 낮을 때 주식이 언제나 싸 보이게 만든다'],
    example() {
      const n = 360
      const bond = meanRevert(n, { mean: 6, sd: 1.6, drift: -0.012, phi: 0.995, seed: 311, start: 8 })
      const prem = meanRevert(n, { mean: 1, sd: 1.6, phi: 0.98, seed: 312 })
      const ey = bond.map((b, i) => b + prem[i])
      return {
        chart: {
          close: ey,
          priceLabel: '이익 수익률',
          overlays: [{ label: '10년 국채', values: bond, color: 'var(--series-2)' }],
          yTicks: [0, 4, 8, 12], yUnit: '%', xUnit: '개월',
          panel: { label: '차이(%p)', series: [{ label: '차이', values: ey.map((v, i) => v - bond[i]), bar: true }], levels: [0] },
        },
      }
    },
  },
  {
    id: 'cape', group: 'index-value', name: '실러 CAPE', en: 'Cyclically Adjusted P/E',
    by: '로버트 실러·존 캠벨(1988). 그레이엄·도드가 여러 해 평균 이익으로 값을 매기라고 한 것을 따랐다.',
    need: 'index',
    summary: '주가 ÷ 지난 10년 물가 조정 평균 이익. 한 해의 호황·불황에 흔들리지 않는 PER.',
    idea: '한 해의 이익은 경기에 따라 크게 오르내려, 불황 끝에는 PER 이 높게(이익이 꺼져서), 호황 끝에는 낮게 나온다. 10년 평균 이익을 쓰면 그 흔들림이 빠진다. 실러는 이 값이 높을수록 그 뒤 10년 실질 수익률이 낮았음을 보였다.',
    rules: [
      '이익을 물가로 실질화하고 10년 평균을 낸다. 지수(실질)를 그 평균으로 나눈다.',
      '자기 역사 평균과 견준다. 높을수록 그 뒤 10년 기대 수익을 낮게 잡는다.',
      '변형: 자사주 매입이 배당을 대신하는 것을 감안해 총수익 판(TR-CAPE)을 쓴다.',
    ],
    read: '평균선 위로 크게 솟은 두세 구간이 비싼 시기다. 그 뒤로도 한동안 높게 머무는 것을 보라.',
    works: ['10년 단위의 기대 수익'],
    traps: ['회계 기준이 바뀌면(손상 처리 등) 과거 이익과 견주기 어렵다', '평균 자체가 시대에 따라 다르다 — 낮은 금리 시대엔 평균보다 높게 머문다', '다음 1~2년에는 거의 아무것도 말하지 않는다'],
    example() {
      const n = 600
      const v = meanRevert(n, { mean: 17, sd: 6, drift: 0.008, phi: 0.994, seed: 321, start: 12 }).map((a) => Math.max(5, a))
      const m = v.reduce((s, a) => s + a, 0) / n
      return {
        chart: {
          close: v,
          priceLabel: 'CAPE',
          overlays: [{ label: '평균', values: flat(n, m), color: 'var(--series-2)', dash: true }],
          yTicks: [10, 20, 30, 40], yUnit: '배', xUnit: '개월',
        },
      }
    },
  },
  {
    id: 'trend-position', group: 'index-value', name: '장기 추세 대비 위치', en: 'Deviation from Long-Run Trend',
    by: '로그 가격에 직선을 맞추는 단순한 방법. 가치평가라기보다 가격의 위치다.',
    need: 'index',
    summary: '지수를 로그로 놓고 긴 기간에 맞춘 직선(추세)에서 지금이 몇 % 위·아래인가.',
    idea: '지수는 길게 보면 대략 일정한 비율로 커진다(로그로 직선). 추세 위로 멀리 가면 미래 상승을 앞당겨 쓴 것, 아래로 멀리 가면 반대로 본다. 이익·GDP 같은 다른 자료가 필요 없어 어떤 지수에도 쓸 수 있다.',
    rules: [
      '월말 지수의 로그에 직선을 맞춘다(수십 년).',
      '편차 = 지수 ÷ 추세값 − 1. 자기 역사의 표준편차 몇 배인지로 본다.',
      '추세는 기간을 늘리면 바뀐다 — 맞춘 기간을 함께 적는다.',
    ],
    read: '아래 칸이 추세에서의 거리다. 0 선을 중심으로 오가지만 한쪽에 몇 년씩 머문다.',
    works: ['길게 보는 비중 조절'],
    traps: ['추세를 지금 자료까지 써서 맞추면 과거의 편차에 미래 정보가 섞인다(나중 자료가 추세를 바꾼다)', '경제의 성장률이 바뀌면 직선 가정이 무너진다'],
    example() {
      const n = 480
      const dev = meanRevert(n, { mean: 0, sd: 0.22, phi: 0.99, seed: 331 })
      const lp = dev.map((d, i) => 4.6 + 0.006 * i + d)
      const trend = lp.map((_, i) => 4.6 + 0.006 * i)
      const s = sdOf(dev)
      return {
        chart: {
          close: lp.map(Math.exp),
          priceLabel: '지수(로그 눈금)',
          log: true,
          overlays: [{ label: '추세', values: trend.map(Math.exp), color: 'var(--series-2)', dash: true }],
          band: { hi: trend.map((t) => Math.exp(t + s)), lo: trend.map((t) => Math.exp(t - s)), label: '추세 ± 1σ' },
          xUnit: '개월',
          panel: { label: '추세 대비(%)', series: [{ label: '편차', values: dev.map((d) => (Math.exp(d) - 1) * 100), bar: true }], levels: [0] },
        },
      }
    },
  },

  /* ── 버핏 ── */
  {
    id: 'moat', group: 'buffett', name: '경제적 해자', en: 'Economic Moat',
    by: '워런 버핏(버크셔 해서웨이 주주 서한·주주총회). 다섯 갈래 분류는 모닝스타가 정리했다.',
    need: 'company',
    summary: '경쟁자가 따라와도 높은 자본수익률을 오래 지키게 해 주는 구조적 우위.',
    idea: '돈을 잘 버는 사업에는 경쟁자가 몰려와 이익률을 깎는다. 그런데도 10년, 20년 높은 수익률을 지키는 회사에는 성 둘레의 해자 같은 무언가가 있다. 버핏은 해자가 넓고 넓어지는 회사를 적정한 값에 사서 오래 들고 있으라고 했다.',
    rules: [
      '해자의 원천을 이름으로 댈 수 있어야 한다 — 무형자산(브랜드·특허·허가), 전환 비용, 네트워크 효과, 원가 우위, 효율적 규모.',
      '숫자로 확인한다: 투하자본수익률(ROIC)이 자본비용보다 높게 10년 넘게 유지되는가.',
      '해자가 좁아지는 신호(가격 인하 경쟁, 대체 기술)를 계속 본다.',
    ],
    read: '가상의 두 회사다. 해자가 있는 회사는 수익률이 높게 유지되고, 없는 회사는 경쟁으로 자본비용까지 내려온다.',
    works: ['오래 들고 있을 회사를 고를 때'],
    traps: ['지나고 나서야 해자였는지 안다 — 지금 높은 수익률이 해자인지 일시적 호황인지 가르기 어렵다', '기술 변화가 해자를 한 번에 메운다'],
    example() {
      const n = 15
      const r = rng(341)
      const wide = Array.from({ length: n }, () => 22 + (r() - 0.5) * 3)
      const none = Array.from({ length: n }, (_, i) => 8 + 17 * Math.exp(-i / 3.5) + (r() - 0.5) * 2)
      return {
        chart: {
          close: wide, priceLabel: '해자 있는 회사 ROIC',
          overlays: [
            { label: '해자 없는 회사 ROIC', values: none, color: 'var(--series-2)' },
            { label: '자본비용', values: flat(n, 8), color: 'var(--text-muted)', dash: true },
          ],
          yTicks: [0, 10, 20, 30], yUnit: '%', xUnit: '년',
        },
        calc: [{
          caption: '해자의 다섯 갈래와 확인할 것',
          cols: ['원천', '무엇인가', '숫자로 보이는 흔적'],
          rows: [
            ['무형자산', '브랜드·특허·인허가', '경쟁사보다 높은 가격에도 팔리는가(총이익률)'],
            ['전환 비용', '고객이 옮기기 번거롭다', '해지율이 낮고 가격을 올려도 고객이 남는가'],
            ['네트워크 효과', '쓰는 사람이 늘수록 가치가 커진다', '점유율이 오를수록 이익률도 오르는가'],
            ['원가 우위', '같은 것을 더 싸게 만든다', '업계 최저 원가·가격 경쟁에서도 이익'],
            ['효율적 규모', '작은 시장을 소수가 나눠 갖는다', '새 진입자가 들어와도 둘 다 손해인 구조'],
          ],
        }],
      }
    },
  },
  {
    id: 'roe', group: 'buffett', name: 'ROE 와 듀폰 분해', en: 'Return on Equity / DuPont',
    by: '버핏은 주당이익보다 자기자본이익률을 보라고 했다. 분해는 1920년대 듀폰사의 방식.',
    need: 'company',
    summary: '순이익 ÷ 자기자본. 같은 ROE 라도 이익률·회전율·빚 가운데 무엇에서 나왔는지 나눠 본다.',
    idea: '주주가 맡긴 돈 1원으로 해마다 얼마를 버나다. 버핏은 빚을 많이 지지 않고도 ROE 가 높게 꾸준한 회사를 찾았다. 듀폰 분해는 ROE 를 순이익률 × 자산회전율 × 레버리지로 나눠, 빚으로 부풀린 ROE 를 가려낸다.',
    rules: [
      'ROE = 순이익률(순이익 ÷ 매출) × 자산회전율(매출 ÷ 자산) × 레버리지(자산 ÷ 자기자본).',
      '여러 해 꾸준한지 본다(버핏의 흔한 기준은 15% 안팎을 10년).',
      '레버리지가 ROE 의 대부분이면 경기가 나빠질 때 무너진다.',
    ],
    read: '두 가상 회사의 ROE 는 같다. 가나전자는 이익률에서, 다라건설은 빚에서 나온다.',
    works: ['꾸준함을 볼 때'],
    traps: ['자사주 매입·손실 누적으로 자기자본이 작아지면 ROE 가 부풀려 보인다', '한 해 값으로는 아무것도 모른다'],
    example() {
      const co = [
        { name: '가나전자', sales: 1000, ni: 200, assets: 1250, eq: 1000 },
        { name: '다라건설', sales: 2000, ni: 100, assets: 2000, eq: 500 },
      ]
      return {
        calc: [{
          caption: '가상 회사 — 단위 억원',
          cols: ['', '순이익률', '× 자산회전율', '× 레버리지', '= ROE'],
          rows: co.map((c) => [c.name, pct(c.ni / c.sales), x(c.sales / c.assets, 2), x(c.assets / c.eq, 2), pct(c.ni / c.eq)]),
        }],
      }
    },
  },
  {
    id: 'owner-earnings', group: 'buffett', name: '오너 어닝', en: 'Owner Earnings',
    by: '워런 버핏, 1986년 버크셔 해서웨이 주주 서한.',
    need: 'company',
    summary: '주인이 사업을 망가뜨리지 않고 해마다 꺼내 쓸 수 있는 돈. 회계 이익 대신 쓴다.',
    idea: '회계 이익에는 감가상각처럼 돈이 나가지 않는 비용이 빠져 있고, 사업을 지금 수준으로 유지하는 데 필요한 설비투자는 들어 있지 않다. 버핏은 이 둘을 고쳐야 주인 입장의 진짜 이익이 나온다고 했다.',
    rules: [
      '오너 어닝 = 순이익 + 감가상각 등 비현금 비용 − 지금 수준을 유지하는 데 드는 평균 설비투자 (− 필요한 운전자본 증가).',
      '유지 설비투자는 재무제표에 따로 없다 — 추정해야 한다(버핏도 추정이라고 했다).',
      '이 값으로 가치를 매긴다(DCF 의 현금흐름으로).',
    ],
    read: '가상 회사의 회계 이익과 오너 어닝이 다르다. 설비를 계속 갈아 줘야 하는 사업일수록 차이가 크다.',
    works: ['설비가 무거운 사업의 이익을 볼 때'],
    traps: ['유지 설비투자와 성장 설비투자를 가르는 것이 주관적이다'],
    example() {
      const ni = 100
      const dep = 40
      const capex = 55
      const wc = 5
      const oe = ni + dep - capex - wc
      return {
        calc: [{
          caption: '가상 회사 — 단위 억원',
          cols: ['항목', '값'],
          rows: [
            ['순이익', eok(ni)],
            ['+ 감가상각', eok(dep)],
            ['− 유지 설비투자(추정)', eok(capex)],
            ['− 운전자본 증가', eok(wc)],
            ['= 오너 어닝', eok(oe)],
            ['순이익 대비', pct(oe / ni, 0)],
          ],
        }],
      }
    },
  },
  {
    id: 'margin-of-safety', group: 'buffett', name: '내재가치와 안전마진', en: 'Intrinsic Value & Margin of Safety',
    by: '벤저민 그레이엄, 『현명한 투자자』(1949) 마지막 장. 버핏이 \'투자에서 가장 중요한 세 단어\' 라 불렀다.',
    need: 'company',
    summary: '추정한 내재가치보다 충분히 싸게 살 때만 산다. 추정이 틀려도 손해 보지 않을 여유.',
    idea: '내재가치는 하나의 숫자가 아니라 범위다 — 어떤 가정을 쓰느냐에 따라 달라진다. 가격이 그 범위의 아래쪽보다도 낮을 때만 사면, 가정이 꽤 틀려도 손해가 작다. 안전마진은 틀릴 것을 전제로 한 여유다.',
    rules: [
      '내재가치를 비관·기준·낙관 세 가정으로 추정한다(DCF·오너 어닝 등).',
      '안전마진 = 1 − 가격 ÷ 내재가치. 흔한 기준은 기준 가정 대비 25~50%.',
      '확신이 낮을수록(사업이 복잡할수록) 더 큰 마진을 요구한다.',
    ],
    read: '같은 가격이 가정에 따라 싸기도, 비싸기도 하다. 비관 가정에서도 가격이 아래인가를 본다.',
    works: ['추정이 틀릴 수 있다는 것을 받아들일 때'],
    traps: ['마진이 큰 이유가 시장이 아는 나쁜 사실 때문일 수 있다(가치 함정)', '내재가치 추정 자체가 낙관에 치우치기 쉽다'],
    example() {
      const price = 35000
      const v = [['비관', 42000], ['기준', 55000], ['낙관', 72000]]
      return {
        calc: [{
          caption: '가상 회사 — 주가 35,000원',
          cols: ['가정', '내재가치', '안전마진'],
          rows: v.map(([k, val]) => [k, won(val), pct(1 - price / val, 0)]),
        }],
      }
    },
  },

  /* ── 그레이엄·가치주 ── */
  {
    id: 'graham-number', group: 'graham', name: '그레이엄 숫자', en: 'Graham Number',
    by: '그레이엄의 방어적 투자자 기준(PER 15배·PBR 1.5배)을 한 숫자로 합친 것.',
    need: 'company',
    summary: '√(22.5 × 주당순이익 × 주당순자산). 방어적 투자자가 낼 수 있는 가격의 상한.',
    idea: '그레이엄은 PER 15배, PBR 1.5배를 넘지 말라고 했다. 둘을 곱하면 22.5 다 — 이익이 좋으면 자산 대비로는 조금 비싸도, 자산이 많으면 이익 대비로는 조금 비싸도 봐주는 셈이다. 그 곱의 상한을 가격으로 바꾼 것이 이 숫자다.',
    rules: [
      '그레이엄 숫자 = √(22.5 × EPS × BPS).',
      '주가가 이 숫자보다 낮으면 방어적 기준 안이다.',
      '이익이 적자면 쓰지 않는다.',
    ],
    read: '가상 회사의 주당 이익과 자산에서 상한을 계산하고 주가와 견준다.',
    works: ['자산이 실물인 전통 산업'],
    traps: ['자산이 장부에 안 잡히는 회사(소프트웨어·브랜드)는 언제나 비싸 보인다', '성장을 전혀 반영하지 않는다'],
    example() {
      const eps = 3000
      const bps = 25000
      const price = 35000
      const g = Math.sqrt(22.5 * eps * bps)
      return {
        calc: [{
          caption: '가상 회사',
          cols: ['항목', '값'],
          rows: [
            ['주당순이익(EPS)', won(eps)],
            ['주당순자산(BPS)', won(bps)],
            ['그레이엄 숫자 = √(22.5 × EPS × BPS)', won(g)],
            ['주가', won(price)],
            ['판정', price < g ? `주가가 ${pct(1 - price / g, 0)} 아래` : `주가가 ${pct(price / g - 1, 0)} 위`],
          ],
        }],
      }
    },
  },
  {
    id: 'net-net', group: 'graham', name: '순유동자산 (넷넷)', en: 'Net-Net / NCAV',
    by: '벤저민 그레이엄·데이비드 도드, 『증권 분석』(1934).',
    need: 'company',
    summary: '(유동자산 − 부채 전부)보다 시가총액이 싸면 산다. 공장·브랜드를 공짜로 얻는 셈.',
    idea: '유동자산(현금·매출채권·재고)에서 부채를 모두 갚고 남는 것만으로도 회사 값보다 크다면, 지금 청산해도 주주가 이득이다. 그레이엄은 그 값의 3분의 2 아래에서 여러 종목을 나눠 사라고 했다.',
    rules: [
      '순유동자산 = 유동자산 − 총부채(우선주 포함).',
      '시가총액이 순유동자산의 3분의 2 아래면 산다.',
      '한 종목이 아니라 여러 종목에 나눠 산다 — 하나하나는 문제가 있는 회사가 많다.',
    ],
    read: '가상 회사의 주당 순유동자산과 그 3분의 2 를 주가와 견준다.',
    works: ['시장 전체가 크게 빠진 뒤(이런 회사가 많아진다)'],
    traps: ['오늘날 큰 시장에서는 거의 없다 — 있으면 대개 적자로 자산을 태우는 중이다', '재고·매출채권이 장부값에 팔리지 않는다'],
    example() {
      const ca = 1000
      const debt = 400
      const shares = 1000
      const price = 3500
      const ncav = ((ca - debt) * 1e8) / (shares * 1e4)
      return {
        calc: [{
          caption: '가상 회사 — 유동자산·부채 단위 억원, 주식 1,000만 주',
          cols: ['항목', '값'],
          rows: [
            ['유동자산', eok(ca)],
            ['− 총부채', eok(debt)],
            ['= 순유동자산', eok(ca - debt)],
            ['주당 순유동자산', won(ncav)],
            ['그 3분의 2', won((ncav * 2) / 3)],
            ['주가', won(price)],
            ['판정', price < (ncav * 2) / 3 ? '기준 안' : '기준 밖'],
          ],
        }],
      }
    },
  },
  {
    id: 'low-pe-pb', group: 'graham', name: '저PER·저PBR', en: 'Value (Low P/E, Low P/B)',
    by: '그레이엄에서 시작해 산조이 바수(1977)·파마와 프렌치(1992)가 \'가치 프리미엄\' 으로 정리했다.',
    need: 'company',
    summary: '이익이나 순자산에 비해 싼 종목 묶음을 사고 비싼 것을 피한다.',
    idea: '시장은 나쁜 소식이 있는 회사를 지나치게 싸게, 인기 있는 회사를 지나치게 비싸게 매기는 경향이 있다고 본다. 싼 종목 여럿을 사 두면 그중 일부의 회복이 나머지를 메운다. 학계에서는 싼 주식이 더 위험해서 더 버는 것이라는 해석도 있다.',
    rules: [
      'PER(주가 ÷ 주당순이익), PBR(주가 ÷ 주당순자산)로 줄을 세운다.',
      '싼 쪽 일부(예: 하위 20~30%)를 산다 — 한 종목이 아니라 묶음.',
      '정기적으로 다시 줄 세운다.',
    ],
    read: '가상 다섯 회사다. PBR 이 가장 낮은 회사의 ROE 도 가장 낮다 — 싼 데는 이유가 있을 수 있다.',
    works: ['여러 종목을 묶어 오래'],
    traps: ['가치 함정 — 싸 보이는 것이 계속 싸진다', '무형자산이 큰 회사가 늘어 장부가 기준이 약해졌다', '몇 년씩 성장주에 뒤처지는 시기가 있다'],
    example() {
      const co = [
        ['가나전자', 8, 0.6, 0.07], ['다라건설', 6, 0.4, 0.05], ['마바식품', 14, 1.4, 0.1],
        ['사아소프트', 32, 6.5, 0.2], ['자차화학', 11, 0.9, 0.08],
      ].sort((a, b) => a[2] - b[2])
      return {
        calc: [{
          caption: '가상 회사 — PBR 낮은 순',
          cols: ['회사', 'PER', 'PBR', 'ROE'],
          rows: co.map(([n, pe, pb, roe]) => [n, x(pe), x(pb), pct(roe, 0)]),
        }],
      }
    },
  },
  {
    id: 'defensive', group: 'graham', name: '방어적 투자자의 일곱 기준', en: 'Graham\'s Defensive Criteria',
    by: '벤저민 그레이엄, 『현명한 투자자』 14장.',
    need: 'company',
    summary: '규모·재무·이익 안정·배당·성장·PER·PBR 일곱 가지를 모두 통과한 회사만 산다.',
    idea: '분석에 시간을 쓰지 않는 투자자를 위한 체크리스트다. 크고, 튼튼하고, 오래 이익과 배당을 낸 회사를 적당한 값에만 사면 크게 틀리지 않는다는 생각이다.',
    rules: [
      '적정한 규모(당시 기준 연 매출 1억 달러 이상 — 지금은 시장마다 다시 잡는다).',
      '유동비율 2 이상, 장기부채가 순유동자산 이하.',
      '지난 10년 매년 흑자. 20년 연속 배당.',
      '10년 동안 주당이익이 3분의 1 이상 늘었다(처음·끝 3년 평균으로).',
      'PER 은 3년 평균 이익의 15배 이하, PBR 은 1.5배 이하(또는 PER × PBR ≤ 22.5).',
    ],
    read: '가상 회사의 숫자로 일곱 칸을 하나씩 채운다. 하나라도 미달이면 사지 않는다.',
    works: ['종목을 고를 시간이 없을 때의 거르개'],
    traps: ['요즘 기준으로는 통과하는 회사가 아주 적다', '성장 기업은 거의 다 떨어진다'],
    example() {
      const c = { sales: 15000, cr: 2.3, ltd: 300, ncav: 450, loss: 0, div: 22, eps0: 1800, eps1: 2600, pe: 13, pb: 1.9 }
      return {
        calc: [{
          caption: '가상 회사 — 매출·부채 단위 억원',
          cols: ['기준', '가상 회사', '결과'],
          rows: [
            ['규모', `매출 ${eok(c.sales)}`, ok(c.sales >= 10000)],
            ['유동비율 2 이상', x(c.cr), ok(c.cr >= 2)],
            ['장기부채 ≤ 순유동자산', `${eok(c.ltd)} vs ${eok(c.ncav)}`, ok(c.ltd <= c.ncav)],
            ['10년 매년 흑자', `적자 ${c.loss}해`, ok(c.loss === 0)],
            ['20년 연속 배당', `${c.div}년`, ok(c.div >= 20)],
            ['주당이익 3분의 1 이상 성장', `${won(c.eps0)} → ${won(c.eps1)} (${pct(c.eps1 / c.eps0 - 1, 0)})`, ok(c.eps1 / c.eps0 - 1 >= 1 / 3)],
            ['PER 15 이하 · PBR 1.5 이하(또는 곱 22.5 이하)', `${x(c.pe)} · ${x(c.pb)} (곱 ${fmt(c.pe * c.pb, 1)})`,
              ok(c.pe <= 15 && (c.pb <= 1.5 || c.pe * c.pb <= 22.5))],
          ],
        }],
      }
    },
  },

  /* ── 현금흐름 할인 ── */
  {
    id: 'dcf', group: 'dcf', name: '현금흐름 할인 (DCF)', en: 'Discounted Cash Flow',
    by: '존 버 윌리엄스, 『투자가치 이론』(1938)이 \'자산의 값은 앞으로 나올 현금의 현재 가치\' 로 정리했다.',
    need: 'company',
    summary: '앞으로 벌 잉여현금흐름을 할인율로 지금 값으로 바꿔 더한다. 모든 가치평가의 바탕.',
    idea: '내일의 1원은 오늘의 1원보다 덜 가치 있다 — 기다리는 시간과 위험의 값만큼. 회사의 값은 앞으로 그 회사가 낼 현금을 모두 오늘 값으로 바꿔 더한 것이다. 몇 년은 하나하나 예측하고, 그 뒤는 일정한 성장으로 묶는다(말기 가치).',
    rules: [
      '몇 년(예: 5년)의 잉여현금흐름을 예측한다.',
      '말기 가치 = 마지막 해 현금 × (1 + 영구 성장률) ÷ (할인율 − 영구 성장률).',
      '모두 할인해 더하면 기업가치. 순부채를 빼면 주주가치.',
      '가정 하나에 매달리지 말고 할인율·성장률을 흔든 표를 함께 본다.',
    ],
    read: '말기 가치가 전체의 대부분이다 — 먼 미래의 가정이 값을 정한다. 아래 표에서 할인율 1%p 가 값을 얼마나 바꾸는지 보라.',
    works: ['현금흐름이 안정적이고 예측할 만한 사업'],
    traps: ['입력을 조금만 바꿔도 값이 크게 바뀐다 — 원하는 값을 만들기 쉽다', '영구 성장률이 할인율에 가까워지면 값이 무한히 커진다'],
    example() {
      const base = { fcf0: 100, g: 0.08, r: 0.09, tg: 0.025 }
      const d = dcf(base)
      const grid = [0.08, 0.09, 0.1].map((r) => [pct(r, 0), ...[0.02, 0.025, 0.03].map((tg) => eok(dcf({ ...base, r, tg }).ev))])
      return {
        calc: [
          {
            caption: '가상 회사 — 올해 잉여현금흐름 100억, 5년 연 8% 성장, 할인율 9%, 영구 성장 2.5%',
            cols: ['해', '잉여현금흐름', '할인 계수', '현재 가치'],
            rows: [
              ...d.rows.map((w) => [`${w.t}년 뒤`, eok(w.f), fmt(w.d, 3), eok(w.pv)]),
              ['말기 가치', eok(d.tv), fmt(1 / 1.09 ** 5, 3), eok(d.tvPv)],
              ['기업가치', '', '', eok(d.ev)],
              ['말기 가치의 몫', '', '', pct(d.tvPv / d.ev, 0)],
            ],
          },
          {
            caption: '할인율(줄) × 영구 성장률(칸)을 흔들면 — 기업가치',
            cols: ['할인율', '2%', '2.5%', '3%'],
            rows: grid,
          },
        ],
      }
    },
  },
  {
    id: 'ddm', group: 'dcf', name: '배당할인 (고든 성장)', en: 'Dividend Discount Model',
    by: '마이런 고든(1959). 지수에도 배당 수익률과 성장률로 근사해 쓸 수 있다.',
    need: 'company',
    summary: '주가 = 내년 배당 ÷ (요구수익률 − 배당 성장률). 배당이 일정하게 자라는 회사의 값.',
    idea: '주주가 결국 받는 것은 배당이다. 배당이 해마다 같은 비율로 자란다면 그 무한한 흐름의 현재 가치는 간단한 식 하나로 줄어든다. 거꾸로 쓰면 지금 주가가 가정하는 성장률이나 기대 수익률을 구할 수 있다.',
    rules: [
      'P = D₁ ÷ (r − g). D₁ 은 내년 배당, r 은 요구수익률, g 는 영구 배당 성장률.',
      '거꾸로: r = D₁ ÷ P + g — 배당 수익률 + 성장률이 기대 수익률이다.',
      'g 가 r 보다 작아야 한다.',
    ],
    read: '분모가 r − g 라서 둘이 가까워지면 값이 폭발한다. 아래 표의 오른쪽 위를 보라.',
    works: ['배당이 안정적인 성숙 기업(공공요금·통신)'],
    traps: ['배당을 안 주거나 자사주로 돌려주는 회사에는 맞지 않는다', '작은 가정 차이가 큰 값 차이가 된다'],
    example() {
      const d1 = 2000
      const grid = [0.07, 0.08, 0.09].map((r) => [pct(r, 0), ...[0.03, 0.04, 0.05].map((g) => won(d1 / (r - g)))])
      return {
        calc: [
          {
            caption: '가상 회사 — 내년 배당 2,000원',
            cols: ['항목', '값'],
            rows: [['내년 배당 D₁', won(d1)], ['요구수익률 r', '8%'], ['배당 성장률 g', '4%'], ['P = D₁ ÷ (r − g)', won(d1 / (0.08 - 0.04))]],
          },
          { caption: '요구수익률(줄) × 성장률(칸)을 흔들면 — 주가', cols: ['요구수익률', '3%', '4%', '5%'], rows: grid },
        ],
      }
    },
  },
  {
    id: 'reverse-dcf', group: 'dcf', name: '역 DCF', en: 'Reverse DCF / Expectations Investing',
    by: '마이클 모부신·앨프리드 래퍼포트, 『Expectations Investing』(2001).',
    need: 'company',
    summary: '값을 추정하는 대신, 지금 주가가 맞으려면 앞으로 얼마나 성장해야 하는지를 거꾸로 푼다.',
    idea: 'DCF 의 약점은 성장률 가정이다. 그렇다면 가정을 내가 정하지 말고, 시장 가격이 이미 품고 있는 가정을 꺼내 보자는 생각이다. 꺼낸 성장률이 그 회사가 해낼 만해 보이면 싸고, 터무니없으면 비싸다.',
    rules: [
      '할인율·영구 성장률·예측 기간은 DCF 와 같이 정한다.',
      '지금 기업가치(시가총액 + 순부채)와 DCF 값이 같아지는 성장률을 푼다.',
      '그 성장률을 회사의 과거 성장, 업계 성장과 견준다.',
    ],
    read: '같은 회사라도 주가가 높을수록 요구되는 성장률이 가파르게 오른다.',
    works: ['인기 종목이 무엇을 약속받고 있는지 볼 때'],
    traps: ['할인율을 바꾸면 꺼낸 성장률도 바뀐다 — 할인율 가정은 그대로 남는다'],
    example() {
      const fcf0 = 100
      const r = 0.09
      const tg = 0.025
      const solve = (ev) => {
        let lo = -0.2
        let hi = 0.6
        for (let k = 0; k < 80; k++) {
          const mid = (lo + hi) / 2
          if (dcf({ fcf0, g: mid, r, tg }).ev < ev) lo = mid
          else hi = mid
        }
        return (lo + hi) / 2
      }
      const evs = [1500, 2000, 2800, 4000]
      return {
        calc: [{
          caption: '가상 회사 — 올해 잉여현금흐름 100억, 할인율 9%, 5년 뒤 영구 성장 2.5%',
          cols: ['지금 기업가치', '주가가 맞으려면 5년 연 성장률'],
          rows: evs.map((ev) => [eok(ev), pct(solve(ev))]),
        }],
      }
    },
  },

  /* ── 성장·계량 ── */
  {
    id: 'peg', group: 'quant', name: 'PEG (피터 린치)', en: 'Price/Earnings to Growth',
    by: '피터 린치, 『전설로 떠나는 월가의 영웅(One Up on Wall Street)』(1989).',
    need: 'company',
    summary: 'PER ÷ 이익 성장률(%). 성장을 감안한 PER — 1 근처면 적정, 그보다 낮으면 싸다고 본다.',
    idea: 'PER 30배는 비싸 보이지만 이익이 해마다 30% 자란다면 몇 년 뒤에는 싸진다. 린치는 공정한 PER 은 성장률과 같다고 보고, PER 이 성장률의 절반이면 아주 매력적이라고 했다.',
    rules: [
      'PEG = PER ÷ 앞으로(또는 최근) 몇 년의 연 이익 성장률(% 숫자).',
      '1 이하를 적정, 0.5 안팎을 아주 싸다고 본다.',
      '린치는 배당 수익률을 성장률에 더하는 판도 썼다.',
    ],
    read: 'PER 이 가장 높은 회사(사아소프트)의 PEG 가 PER 이 가장 낮은 회사(마바식품)보다 낮다 — PER 만 보면 거꾸로 고른다.',
    works: ['꾸준히 자라는 중간 성장 기업'],
    traps: ['성장률 추정이 틀리면 전부 틀린다', '성장이 아주 높거나 아주 낮으면 숫자가 뜻을 잃는다'],
    example() {
      const co = [['사아소프트', 30, 30], ['마바식품', 12, 4], ['가나전자', 15, 20]]
      return {
        calc: [{
          caption: '가상 회사',
          cols: ['회사', 'PER', '연 이익 성장률', 'PEG'],
          rows: co.map(([n, pe, g]) => [n, x(pe), `${g}%`, fmt(pe / g, 2)]),
        }],
      }
    },
  },
  {
    id: 'magic-formula', group: 'quant', name: '마법공식 (그린블랫)', en: 'Magic Formula',
    by: '조엘 그린블랫, 『주식시장을 이기는 작은 책(The Little Book That Beats the Market)』(2005).',
    need: 'company',
    summary: '좋은 회사(자본수익률 높은)를 싸게(이익 수익률 높은) — 두 순위를 더해 위에서부터 산다.',
    idea: '버핏의 \'적정한 값의 훌륭한 회사\' 를 기계적인 규칙 두 개로 바꿨다. 자본수익률은 사업의 질, 이익 수익률은 값이다. 하나만 보면 비싼 좋은 회사나 싼 나쁜 회사를 고르기 쉽지만, 두 순위의 합은 둘 다 괜찮은 회사를 올린다.',
    rules: [
      '자본수익률 = 영업이익(EBIT) ÷ (순운전자본 + 순고정자산).',
      '이익 수익률 = 영업이익 ÷ 기업가치(시가총액 + 순부채).',
      '각각 순위를 매겨 더하고, 합이 작은 순서로 20~30 종목을 산다. 1년마다 바꾼다.',
      '금융·공공요금 업종은 뺀다.',
    ],
    read: '가상 여섯 회사다. 어느 한쪽만 1등인 회사보다 둘 다 상위인 회사가 위로 온다.',
    works: ['몇 년 이상 규칙을 그대로 지킬 때(그린블랫도 몇 년씩 지는 시기가 있다고 했다)'],
    traps: ['지는 해가 이어지면 규칙을 버리기 쉽다 — 그 때문에 오히려 통한다는 해석도 있다'],
    example() {
      const co = [
        ['가나전자', 120, 800, 400], ['다라건설', 90, 500, 900], ['마바식품', 60, 900, 300],
        ['사아소프트', 200, 4000, 350], ['자차화학', 150, 1100, 1200], ['카타유통', 40, 300, 500],
      ].map(([n, ebit, ev, cap]) => ({ n, roc: ebit / cap, ey: ebit / ev }))
      const rank = (k) => {
        const s = [...co].sort((a, b) => b[k] - a[k])
        return Object.fromEntries(s.map((c, i) => [c.n, i + 1]))
      }
      const r1 = rank('roc')
      const r2 = rank('ey')
      const rows = co.map((c) => ({ ...c, a: r1[c.n], b: r2[c.n], s: r1[c.n] + r2[c.n] })).sort((p, q) => p.s - q.s || p.a - q.a)
      return {
        calc: [{
          caption: '가상 회사 — 순위 합이 작은 순',
          cols: ['회사', '자본수익률', '순위', '이익 수익률', '순위', '합'],
          rows: rows.map((c) => [c.n, pct(c.roc, 0), c.a, pct(c.ey, 1), c.b, c.s]),
        }],
      }
    },
  },
  {
    id: 'f-score', group: 'quant', name: '피오트로스키 F-점수', en: 'Piotroski F-Score',
    by: '조지프 피오트로스키(2000). 싼 주식(높은 장부가 대비) 가운데 좋은 것을 가려내려고 만들었다.',
    need: 'company',
    summary: '수익성·재무 건전성·효율의 아홉 가지를 각각 0·1점으로 매긴 합. 8~9점이 튼튼한 회사.',
    idea: '저PBR 주식 가운데에는 정말 무너지는 회사와 오해받는 회사가 섞여 있다. 재무제표에서 \'나아지고 있는가\' 를 아홉 번 묻고 점수가 높은 것만 고르면, 가치주의 함정을 상당 부분 피한다고 보였다.',
    rules: [
      '수익성 4: ROA 가 양수, 영업현금흐름이 양수, ROA 가 작년보다 높다, 영업현금흐름이 순이익보다 크다.',
      '재무 3: 장기부채 비율이 줄었다, 유동비율이 높아졌다, 새 주식을 찍지 않았다.',
      '효율 2: 매출총이익률이 높아졌다, 자산회전율이 높아졌다.',
      '저PBR 종목 가운데 8~9점을 산다.',
    ],
    read: '가상 회사의 올해·작년 숫자로 아홉 칸을 하나씩 채운다. 새 주식을 찍어 한 칸을 잃었다.',
    works: ['싼 종목 묶음 안에서 거를 때'],
    traps: ['해마다 바뀌는 회계 숫자의 \'변화\' 를 보므로 한 해 일회성 항목에 흔들린다'],
    example() {
      const a = { ni: 120, assets: 1500, cfo: 160, ltd: 300, ca: 600, cl: 380, sh: 1050, sales: 2000, gp: 640 }
      const b = { ni: 100, assets: 1450, ltd: 340, ca: 560, cl: 370, sh: 1000, sales: 1900, gp: 600 }
      const roa = a.ni / a.assets
      const roa0 = b.ni / b.assets
      const checks = [
        ['ROA 양수', pct(roa), roa > 0],
        ['영업현금흐름 양수', eok(a.cfo), a.cfo > 0],
        ['ROA 증가', `${pct(roa0)} → ${pct(roa)}`, roa > roa0],
        ['영업현금흐름 > 순이익', `${eok(a.cfo)} vs ${eok(a.ni)}`, a.cfo > a.ni],
        ['장기부채 비율 감소', `${pct(b.ltd / b.assets)} → ${pct(a.ltd / a.assets)}`, a.ltd / a.assets < b.ltd / b.assets],
        ['유동비율 증가', `${x(b.ca / b.cl, 2)} → ${x(a.ca / a.cl, 2)}`, a.ca / a.cl > b.ca / b.cl],
        ['새 주식 없음', `${fmt(b.sh)}만 → ${fmt(a.sh)}만 주`, a.sh <= b.sh],
        ['매출총이익률 증가', `${pct(b.gp / b.sales)} → ${pct(a.gp / a.sales)}`, a.gp / a.sales > b.gp / b.sales],
        ['자산회전율 증가', `${x(b.sales / b.assets, 2)} → ${x(a.sales / a.assets, 2)}`, a.sales / a.assets > b.sales / b.assets],
      ]
      return {
        calc: [{
          caption: '가상 회사 — 단위 억원',
          cols: ['항목', '작년 → 올해', '점수'],
          rows: [...checks.map(([k, v, p]) => [k, v, p ? 1 : 0]), ['합계', '', `${checks.filter((c) => c[2]).length} / 9`]],
        }],
      }
    },
  },
  {
    id: 'momentum', group: 'quant', name: '모멘텀', en: 'Cross-Sectional Momentum',
    by: '나라시만 제가디시·셰리든 티트먼(1993).',
    need: 'company',
    summary: '지난 12개월(최근 1개월 제외) 가장 많이 오른 종목을 사고 가장 적게 오른 종목을 피한다.',
    idea: '좋은 소식은 한 번에 값에 다 반영되지 않고 몇 달에 걸쳐 스며든다고 본다. 그래서 오른 것이 조금 더 오른다. 최근 1개월을 빼는 것은 아주 짧은 기간에는 반대로 되돌아오는 경향(단기 반전)이 있어서다.',
    rules: [
      '12-1 수익률 = 12개월 전부터 1개월 전까지의 수익률.',
      '상위(예: 10~30%)를 사고, 매달 다시 줄 세운다.',
      '가치(저PBR)와 섞으면 서로의 나쁜 시기를 메운다고 본다.',
    ],
    read: '가상 여섯 종목이다. 최근 한 달에 크게 오른 종목이 12-1 로는 순위가 내려간다.',
    works: ['추세가 이어지는 장'],
    traps: ['시장이 급반등할 때 크게 진다(모멘텀 붕괴)', '매달 바꾸므로 거래 비용이 크다'],
    example() {
      const co = [['가나전자', 0.42, 0.03], ['다라건설', -0.12, 0.05], ['마바식품', 0.08, -0.02], ['사아소프트', 0.55, 0.25], ['자차화학', 0.3, -0.04], ['카타유통', -0.2, -0.01]]
        .map(([n, r12, r1]) => ({ n, r12, r1, m: (1 + r12) / (1 + r1) - 1 }))
        .sort((a, b) => b.m - a.m)
      return {
        calc: [{
          caption: '가상 종목 — 12-1 수익률 높은 순',
          cols: ['종목', '12개월', '최근 1개월', '12-1'],
          rows: co.map((c, i) => [`${i + 1}. ${c.n}`, pct(c.r12, 0), pct(c.r1, 0), pct(c.m, 0)]),
        }],
      }
    },
  },
]
