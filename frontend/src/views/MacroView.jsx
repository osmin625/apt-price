import { useEffect, useMemo, useState } from 'react'

import { api } from '../api'
import { fmt, niceTicks, useMeasure, useTooltip } from '../components/Charts'
import Loading from '../components/Loading'
import Modal from '../components/Modal'
import MacroBars from '../components/MacroBars'
import PanelCard from '../components/PanelCard'
import QuadrantScatter from '../components/QuadrantScatter'

/**
 * 매크로 — 한국부동산원 공표 통계를 경기 남부 17개 시군구로 묶어 본다.
 *
 * ## 왜 만들었나
 *
 * KB부동산 데이터허브에도 같은 통계가 있다. 그런데 거기서 경기 남부만 모아 보려
 * 하면 **차트에 5개까지만 그려지고**, 무엇보다 지역 선택이 URL 에도 공유링크에도
 * 남지 않아 열 때마다 17번을 다시 골라야 했다. 여기서는 17개가 기본이다.
 *
 * ## 이 탭의 성격
 *
 * 다른 탭은 전부 **우리 모델**이 낸 값이다. 이 탭만 바깥에서 가져온 **공표 통계**다.
 * 그래서 모델이 맞는지 보는 바깥 기준이 된다 — 예를 들어 평당 매매가격 순위가
 * 분해 모델의 구 계수 순서와 어긋나면 둘 중 하나를 의심해야 한다.
 *
 * 숫자가 KB 와 다른 것은 정상이다. 조사 주체와 표본이 다르다.
 */
export default function MacroView() {
  const [meta, setMeta] = useState(null)
  const [metric, setMetric] = useState('avg_unit_price')
  const [since, setSince] = useState('202001')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [hidden, setHidden] = useState(() => new Set())

  const [ins, setIns] = useState(null)
  // 어떤 카드를 창으로 띄웠나. null 이면 격자만 보인다.
  const [open, setOpen] = useState(null)

  useEffect(() => {
    api.macroMetrics().then(setMeta).catch(() => setMeta(null))
    api.macroInsights().then(setIns).catch(() => setIns(null))
  }, [])

  useEffect(() => {
    let alive = true
    setError(null)
    setData(null)
    api
      .macroSeries({ metric, since })
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [metric, since])

  const toggle = (sgg) =>
    setHidden((h) => {
      const n = new Set(h)
      n.has(sgg) ? n.delete(sgg) : n.add(sgg)
      return n
    })

  if (error) {
    return (
      <div className="card">
        <h2>매크로</h2>
        <p className="empty">{error}</p>
      </div>
    )
  }

  return (
    <>
      <div className="card">
        <h2>경기 남부 17개 시군구를 한 화면에</h2>
        <p className="sub">
          한국부동산원이 공표하는 <b>아파트 통계</b>입니다. 다른 탭은 우리 모델이 낸
          값이지만 이 탭만 바깥에서 가져온 공표 통계라, 모델을 견주어 볼 바깥 기준이
          됩니다. KB 등 다른 기관 수치와 다를 수 있습니다 — 조사 주체와 표본이 다릅니다.
        </p>

        <div className="filters">
          <div className="field">
            <label>지표</label>
            <MetricChips
              metrics={meta?.metrics || []}
              value={metric}
              onChange={setMetric}
            />
          </div>
          <div className="field">
            <label htmlFor="mc-since">기간</label>
            <select id="mc-since" value={since} onChange={(e) => setSince(e.target.value)}>
              <option value="202401">최근 3년</option>
              <option value="202001">최근 7년</option>
              <option value="201201">전체(2012~)</option>
            </select>
          </div>
        </div>

        <MetricNote m={(meta?.metrics || []).find((x) => x.key === metric)} />
      </div>

      <div className="macro-grid">
        <PanelCard
          title="지금 어느 국면인가"
          sub={ins ? `시군구 ${ins.cycle.items.length}곳 · 전고점 대비 × 최근 3개월` : '불러오는 중'}
          onOpen={() => setOpen('cycle')}
          ready={!!ins}
        >
          {ins && <CycleChart ins={ins} compact />}
        </PanelCard>

        <PanelCard
          title="그 상승을 전세가 받쳐 줬나"
          sub="12개월 매매 × 전세가율 변화"
          onOpen={() => setOpen('rally')}
          ready={!!ins}
        >
          {ins && <RallyChart ins={ins} compact />}
        </PanelCard>

        <PanelCard
          title="거래가 받쳐 준 상승인가"
          sub={
            ins?.volume?.items?.length
              ? `시군구 ${ins.volume.items.length}곳 · 가격 × 거래량`
              : '거래량 적재가 필요합니다'
          }
          onOpen={() => setOpen('volume')}
          ready={!!ins?.volume?.items?.length}
        >
          {ins?.volume?.items?.length > 0 && <VolumeChart ins={ins} compact />}
        </PanelCard>

        <PanelCard
          title="지수가 몇 건으로 만들어졌나"
          sub={
            ins?.depth?.items?.length
              ? `중위 ${fmt(ins.depth.median, 0)}건/월 · 얇은 곳 ${
                  ins.depth.items.filter((i) => i.thin).length
                }곳`
              : '거래량 적재가 필요합니다'
          }
          onOpen={() => setOpen('depth')}
          ready={!!ins?.depth?.items?.length}
        >
          {ins?.depth?.items?.length > 0 && <DepthBars ins={ins} compact />}
        </PanelCard>

        <PanelCard
          title="구 안의 가격 편차"
          sub={
            ins?.spread?.items?.length
              ? `시군구 ${ins.spread.items.length}곳 · 평균 ÷ 중위`
              : '불러오는 중'
          }
          onOpen={() => setOpen('spread')}
          ready={!!ins?.spread?.items?.length}
        >
          {ins?.spread?.items?.length > 0 && <SpreadBars ins={ins} compact />}
        </PanelCard>

        <PanelCard
          title="모델과 어긋나는 곳"
          sub={
            ins?.model_gap?.spearman != null
              ? `순위상관 ${fmt(ins.model_gap.spearman, 3)}`
              : '적합이 필요합니다'
          }
          onOpen={() => setOpen('gap')}
          ready={!!ins && ins.has_fit}
        >
          {ins && ins.has_fit && <GapChart ins={ins} compact />}
        </PanelCard>

        <PanelCard
          title={data ? data.label : '지표 추이'}
          sub={
            data
              ? `${data.unit} · 시군구 ${data.n_districts}곳 · ${data.months[0]}~${
                  data.months[data.months.length - 1]
                }`
              : '불러오는 중'
          }
          onOpen={() => setOpen('series')}
          ready={!!data}
        >
          {data && <MultiLine data={data} hidden={hidden} compact />}
        </PanelCard>

        <PanelCard
          title="최신값"
          sub={data ? `${data.label} · ${data.items[0]?.latest_ym} 공표` : '불러오는 중'}
          onOpen={() => setOpen('table')}
          ready={!!data}
        >
          {data && <MiniTable data={data} />}
        </PanelCard>
      </div>

      {open === 'cycle' && ins && (
        <Modal title="지금 어느 국면인가" onClose={() => setOpen(null)} wide>
          <p className="muted small">{ins.cycle.note}</p>
          <ChartGuide
            axes={[
              ['가로 — 전고점 대비 (%)', '얼마나 회복했나. 0(맨 오른쪽)은 지금이 역대 최고가라는 뜻이고, 왼쪽으로 갈수록 과거 고점에서 멀다.'],
              ['세로 — 최근 3개월 (%)', '지금 어느 방향인가. 0 위는 오르는 중, 아래는 내리는 중.'],
            ]}
            why="한 축만으로는 구분이 안 된다. 전고점 대비만 보면 '바닥에서 기어오르는 곳' 과 '고점에서 막 꺾인 곳' 이 섞이고, 최근 3개월만 보면 '신고가 경신 중' 인지 '낙폭 과대에서 반등 중' 인지 알 수 없다."
            quadrants={[
              ['오른쪽 위 · 신고가 경신 중', '지금이 고점인데 계속 오른다. 비교할 과거 고점이 없어 과거로는 싸다·비싸다를 판단할 수 없는 구간이다.'],
              ['오른쪽 아래 · 고점 부근에서 꺾임', '고점을 찍은 지 얼마 안 됐는데 최근 3개월이 마이너스다.'],
              ['왼쪽 위 · 바닥에서 반등', '과거 고점에서 크게 빠졌다가 올라오는 중.'],
              ['왼쪽 아래 · 정체·하락', '많이 빠졌는데 회복도 느리고 지금도 거의 안 움직인다.'],
            ]}
            tips={[
              '가로축은 "싸다" 가 아니다. 전고점 대비 -18% 는 저평가라는 뜻이 아니라, 그때 그 값을 찍었는데 지금은 거기 못 미친다는 사실일 뿐이다. 그때가 과열이었을 수도 있다.',
              '세로축은 짧은 창이라 흔들린다. 점에 마우스를 올리면 12개월 변화와 가속도(직전 3개월 대비)가 같이 나온다. 많이 올랐지만 속도는 붙지 않는 곳과, 덜 올랐지만 가팔라지는 곳이 갈린다.',
              '왼쪽 아래에서 오른쪽 위로 가는 대각선으로 읽으면 "덜 회복·정체" → "신고가·가속" 이 된다. 경기 남부가 하나의 시장이 아니라 서로 다른 국면이 섞여 있다는 것이 이 그림의 요점이다.',
            ]}
            caveat="월간 매매가격지수 기준이다. 어디가 어느 국면인지까지만 말하고, 거기서 투자 판단으로 넘어가는 것은 이 데이터 밖이다."
          />
          <CycleChart ins={ins} />
          {ins.cycle.excluded.length > 0 && (
            <p className="paste-warn" style={{ marginTop: 8 }}>
              {ins.cycle.excluded.join(' · ')}는 공표 기간이 24개월이 안 돼 사이클을
              판단할 수 없어 뺐습니다. 분구 시점에 통계가 새로 시작했기 때문입니다.
            </p>
          )}
        </Modal>
      )}

      {open === 'rally' && ins && (
        <Modal title="그 상승을 전세가 받쳐 줬나" onClose={() => setOpen(null)} wide>
          <p className="muted small">{ins.rally.note}</p>
          <ChartGuide
            axes={[
              ['가로 — 12개월 매매 변화 (%)', '지난 1년 동안 얼마나 올랐나.'],
              ['세로 — 전세가율 12개월 변화 (%p)', '매매가 대비 전세가의 거리가 좁아졌나 벌어졌나. 위로 갈수록 전세가 따라붙었다는 뜻이다.'],
            ]}
            why="'얼마나 올랐나' 보다 한 단계 깊은 질문에 답한다 — 그 상승을 전세(실수요)가 받쳐 줬는가. 매매가 전세보다 빨리 오르면 전세가율이 떨어진다."
            quadrants={[
              ['오른쪽 위 · 오르고 전세도 붙음', '실수요가 함께 움직인 상승.'],
              ['오른쪽 아래 · 매매만 간 상승', '올랐지만 전세는 못 따라왔다.'],
              ['왼쪽 위 · 안 올랐는데 전세는 붙음', '매매는 조용한데 전세가 올라와 갭이 좁아지는 중.'],
              ['왼쪽 아래 · 안 오르고 전세도 빠짐', '양쪽 다 힘이 없다.'],
            ]}
            tips={[
              '점들이 오른쪽 아래로 흐르는 모양이 보인다면, 많이 오른 곳일수록 전세가 못 따라왔다는 뜻이다.',
              '전세가율은 매매가가 오르기만 해도 떨어진다. 인과가 아니라 같은 현상의 두 측면으로 읽어야 한다.',
            ]}
            caveat="전세가율이 떨어진 것 자체가 고평가라는 뜻은 아니다. 상승의 성격이 다르다는 것까지만 말해 준다."
          />
          <RallyChart ins={ins} />
        </Modal>
      )}

      {open === 'volume' && ins?.volume?.items?.length > 0 && (
        <Modal title="거래가 받쳐 준 상승인가" onClose={() => setOpen(null)} wide>
          <p className="muted small">{ins.volume.note}</p>
          <ChartGuide
            axes={[
              ['가로 — 12개월 매매가 변화 (%)', '지난 1년 동안 얼마나 올랐나. 다른 차트와 같은 축이다.'],
              ['세로 — 거래량, 5년 평균 대비 (%)', '그 구의 최근 12개월 거래 건수를 직전 5년 연평균과 비교한 값. 0 은 평상시만큼, 위는 평상시보다 활발, 아래는 말랐다는 뜻이다.'],
            ]}
            why="이 탭의 가격 지표 여섯 개는 서로 거의 같은 말을 한다. 거래량은 다른 말을 한다 — 거래 배수와 12개월 가격 변화의 순위상관이 0.352 밖에 안 된다(모델 괴리 차트는 0.882 였고, 거기선 둘이 같아야 정상이다). 가격만 봐서는 '거래가 받쳐 준 상승' 과 '거래 없이 호가만 오른 상승' 이 구분되지 않는다."
            quadrants={[
              ['오른쪽 위 · 거래가 받쳐 준 상승', '올랐고 거래도 평상시보다 많다. 값이 실제로 손바뀜되면서 올라갔다는 뜻이다.'],
              ['오른쪽 아래 · 거래 없이 오른 상승', '올랐는데 거래는 평상시보다 적다. 과천이 여기다 — 거래가 5년 평균의 0.76배인데 가격은 +7.8% 다.'],
              ['왼쪽 위 · 거래는 되는데 안 오름', '손바뀜은 활발한데 가격은 제자리다.'],
              ['왼쪽 아래 · 거래도 가격도 조용함', '양쪽 다 움직이지 않는다.'],
            ]}
            tips={[
              '세로축은 절대 건수가 아니라 그 구의 평상시 대비다. 과천은 월 33건, 동탄은 월 1,137건이라 건수로는 같은 축에 놓을 수 없다.',
              '오른쪽 아래가 곧 거품이라는 뜻은 아니다. 매물이 안 나와서 거래가 없을 수도 있다. 이 그림은 상승의 종류가 다르다는 것까지만 말한다.',
              '가로축 순서와 세로축 순서가 엇갈리는 것이 요점이다. 기흥은 거래 2배에 +12.7%, 수지는 거래 1.57배에 +19.5% — 같은 크기의 상승이 아니다.',
            ]}
            caveat="거래량의 마지막 달은 신고 지연으로 과소집계될 수 있다. 재 보니 13곳 중 4곳이 직전 평균의 0.8배 밑이었지만 12개월 합이라 묻힌다 — 마지막 달을 빼고 다시 재니 배수가 최대 0.11 바뀌고 순위는 인접 한 쌍만 뒤집혔다."
          />
          <VolumeChart ins={ins} />
          {ins.volume.excluded.length > 0 && (
            <p className="paste-warn" style={{ marginTop: 8 }}>
              {ins.volume.excluded.join(' · ')}는 비교할 과거 5년이 없어 뺐습니다.
              분구 시점(2026-02)부터 공표가 시작됐기 때문입니다.
            </p>
          )}
        </Modal>
      )}

      {open === 'depth' && ins?.depth?.items?.length > 0 && (
        <Modal title="지수가 몇 건으로 만들어졌나" onClose={() => setOpen(null)} wide>
          <p className="muted small">{ins.depth.note}</p>
          <ChartGuide
            axes={[
              ['막대 길이 — 월평균 매매 거래 건수', '최근 12개월 평균. 지수가 몇 건의 거래에서 나왔는지를 뜻한다.'],
            ]}
            why="이 탭은 17개 구의 지수를 같은 굵기의 선으로 나란히 그린다. 그런데 과천은 월 33건, 화성 동탄구는 월 1,137건이다 — 34배 차이다. 과천의 '전고점 대비 -5%' 와 동탄의 같은 숫자는 무게가 다른데, 선만 봐서는 구분되지 않았다."
            quadrants={null}
            tips={[
              '표본이 얇다고 값이 틀렸다는 뜻은 아니다. 다만 한두 건의 특이 거래에 지수가 더 흔들린다.',
              "'얇다' 표시는 17곳 중위값의 절반 미만이다. 절대 건수로 선을 그으면 지역 규모가 바뀔 때 거짓이 된다.",
              '국면 차트에서 점에 마우스를 올리면 그 구의 월 거래 건수가 같이 나온다 — 그 점의 무게를 그 자리에서 알 수 있다.',
            ]}
            caveat="한국부동산원 지수의 실제 표본 설계는 공표 거래 건수와 다르다. 이것은 '그 구에서 한 달에 몇 건이 거래되는가' 라는 대리지표이고, 지수 산정에 쓰인 표본 수 그 자체는 아니다."
          />
          <MacroBars
            items={ins.depth.items}
            value={(d) => d.per_month}
            decimals={0}
            suffix="건"
            mark={(d) => d.thin}
            markLabel="얇다"
            tip={(d) => (
              <>
                <div className="t-title">{d.name}</div>
                <div className="t-row">월평균 {fmt(d.per_month, 0)}건 (최근 {d.window}개월)</div>
                <div className="t-row">공표 자료 {d.months}개월 · 최신 {d.latest_ym}</div>
                {d.thin && <div className="t-row">중위 {fmt(ins.depth.median, 0)}건의 절반 미만 — 지수가 더 흔들립니다</div>}
              </>
            )}
          />
        </Modal>
      )}

      {open === 'spread' && ins?.spread?.items?.length > 0 && (
        <Modal title="구 안의 가격 편차" onClose={() => setOpen(null)} wide>
          <p className="muted small">{ins.spread.note}</p>
          <ChartGuide
            axes={[
              ['막대 길이 — 평균 ÷ 중위 (%)', '0 은 평균과 중위가 같다는 뜻. 오른쪽(플러스)은 평균이 중위보다 높고, 왼쪽은 낮다.'],
            ]}
            why="우리 모델은 구마다 계수 하나(`sgg_*`)를 둔다. 그것이 뜻을 가지려면 구가 어느 정도 균질해야 한다. 공표되는 평균과 중위를 나누면 그 가정을 검산할 수 있다 — 편차가 큰 구는 계수 하나로 묶기 어렵다는 신호다."
            quadrants={null}
            tips={[
              '영통구가 +25% 다. 평균이 중위보다 25% 높다는 것은 고가 단지 몇 곳이 평균을 끌어올렸다는 뜻 — 광교와 영통이 한 구에 섞여 있다.',
              '팔달구(-4.3%)와 화성 만세구(-3.6%)는 평균이 중위보다 낮다. 저가 쪽이 아니라 고가 쪽이 얇다는 말이다.',
              '마우스를 올리면 평균 평수(= 한 채 평균가 ÷ 평당가)가 같이 나온다. 평당가 순위와 한 채 가격 순위가 왜 다른지가 여기서 설명된다 — 팔달 21.5평, 수지 27.8평.',
            ]}
            caveat="편차가 크다는 것이 그 구가 비싸다·싸다는 뜻은 아니다. 구 평균값을 그 구의 대표값으로 쓸 때 조심하라는 뜻이다."
          />
          <MacroBars
            items={ins.spread.items}
            value={(d) => d.spread_pct}
            diverging
            suffix="%"
            tip={(d) => (
              <>
                <div className="t-title">{d.name}</div>
                <div className="t-row">
                  평균 {fmt(d.avg, 0)}만원 · 중위 {fmt(d.med, 0)}만원
                </div>
                <div className="t-row">
                  평균이 중위보다 {d.spread_pct > 0 ? '+' : ''}
                  {fmt(d.spread_pct, 1)}%
                </div>
                {d.pyeong != null && <div className="t-row">평균 평수 {fmt(d.pyeong, 1)}평</div>}
              </>
            )}
          />
        </Modal>
      )}

      {open === 'gap' && ins && (
        <Modal title="모델과 어긋나는 곳" onClose={() => setOpen(null)} wide>
          {!ins.has_fit ? (
            <p className="empty">
              적합이 아직 캐시에 없어 비교할 수 없습니다. <b>시장 분석</b> 탭을 한 번
              열면 계산되고, 그 뒤 이 화면으로 돌아오면 보입니다.
            </p>
          ) : (
            <>
              <p className="muted small">{ins.model_gap.note}</p>
              <ChartGuide
                axes={[
                  ['가로 — 부동산원 평당가 순위', '공표되는 ㎡당 평균가격 기준. 오른쪽일수록 비싸다.'],
                  ['세로 — 모델 구 계수 순위', '면적·층·시점·연식 등을 통제한 뒤 남은 구 효과. 위일수록 높게 본다.'],
                ]}
                why="두 값은 서로 다른 데이터와 방법에서 나온다. 부동산원은 보정 없는 공표 평균이고, 우리 계수는 그것들을 통제한 뒤 남은 구 효과다. 그래서 순위가 맞는 것이 기본이고, 크게 벌어지는 지역이 눈여겨볼 곳이다."
                quadrants={null}
                tips={[
                  '점선(45도)에 가까울수록 두 값이 같은 순서다. 선에서 멀리 떨어진 지역이 볼 곳이다.',
                  '선 위쪽에 있으면 모델이 공표 평균보다 그 지역을 낮게 본다 — 평균가는 높은데 면적·연식 구성을 걷어내면 그만큼은 아니라는 뜻이다.',
                  '선 아래쪽은 반대다. 공표 평균은 중간인데 통제하고 나면 높게 나온다.',
                ]}
                caveat="어느 쪽이 맞는지는 이 그림이 말해 주지 않는다. 그 지역의 평형·연식 구성이 특이해 단순 평균이 끌려갔거나, 모델이 뭔가를 놓쳤거나다. 어디를 들여다볼지만 알려 준다."
              />
              <GapChart ins={ins} />
              <GapTable gap={ins.model_gap} />
            </>
          )}
        </Modal>
      )}

      {open === 'series' && data && (
        <Modal title={data.label} onClose={() => setOpen(null)} wide>
          <p className="muted small">{data.note}</p>
          <MultiLine data={data} hidden={hidden} />
          <Legend data={data} hidden={hidden} onToggle={toggle} />
          {data.items.some((i) => i.partial) && (
            <p className="paste-warn" style={{ marginTop: 8 }}>
              화성시 분구(만세·효행·병점·동탄)는 <b>분구 시점부터</b> 공표가 시작돼
              시계열이 짧습니다. 없는 기간을 채우지 않았으므로 선이 중간에서 시작합니다.
            </p>
          )}
        </Modal>
      )}

      {open === 'table' && data && (
        <Modal title="최신값" onClose={() => setOpen(null)} wide>
          <p className="muted small">
            {data.label} 기준 · {data.items[0]?.latest_ym} 공표. 변화율은 선택한 기간의
            처음 대비입니다.
          </p>
          <FullTable data={data} />
        </Modal>
      )}
    </>
  )
}

/* 17개 선을 한 축에. 색은 순위로 돌린다 — 이름마다 고정색을 주면 17개를 구분할
   만큼 색이 없고, 어차피 범례에서 짚어 보게 된다. */
function MultiLine({ data, hidden, compact = false }) {
  const [ref, { width }] = useMeasure()
  const tip = useTooltip()
  const H = compact ? 150 : 300
  const PAD = compact ? { t: 8, r: 8, b: 14, l: 28 } : { t: 12, r: 12, b: 26, l: 52 }

  const shown = data.items.filter((i) => !hidden.has(i.sgg_cd))
  const months = data.months

  const { xOf, yOf, ticks, paths } = useMemo(() => {
    const w = Math.max(width || 640, compact ? 200 : 320)
    const iw = w - PAD.l - PAD.r
    const ih = H - PAD.t - PAD.b
    const idx = new Map(months.map((m, i) => [m, i]))
    const xOf = (ym) => PAD.l + (idx.get(ym) / Math.max(months.length - 1, 1)) * iw

    let lo = Infinity
    let hi = -Infinity
    shown.forEach((s) =>
      s.points.forEach((p) => {
        if (p.value < lo) lo = p.value
        if (p.value > hi) hi = p.value
      }),
    )
    if (!Number.isFinite(lo)) {
      lo = 0
      hi = 1
    }
    const pad = (hi - lo) * 0.08 || 1
    lo -= pad
    hi += pad
    const yOf = (v) => PAD.t + ih - ((v - lo) / (hi - lo || 1)) * ih

    const paths = shown.map((s) => ({
      ...s,
      d: s.points
        .map((p, k) => `${k ? 'L' : 'M'}${xOf(p.ym).toFixed(1)},${yOf(p.value).toFixed(1)}`)
        .join(' '),
    }))
    return { xOf, yOf, ticks: niceTicks(lo, hi, 4), paths }
  }, [width, shown, months, compact])

  // x축 라벨은 연 단위로만. 월까지 찍으면 겹쳐서 못 읽는다.
  const yearMarks = months
    .map((m, i) => ({ m, i }))
    .filter(({ m }) => m.endsWith('01'))

  return (
    <div className="macro-chart" ref={ref}>
      <svg viewBox={`0 0 ${Math.max(width || 640, compact ? 200 : 320)} ${H}`} role="img"
           aria-label={`${data.label} 시군구별 추이`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={(width || 640) - PAD.r} y1={yOf(t)} y2={yOf(t)}
                  stroke="var(--border)" strokeDasharray="2 3" />
            {!compact && (
              <text x={PAD.l - 6} y={yOf(t) + 3} textAnchor="end"
                    fontSize="10" fill="var(--text-muted)">
                {fmt(t, data.decimals)}
              </text>
            )}
          </g>
        ))}
        {!compact && yearMarks.map(({ m }) => (
          <text key={m} x={xOf(m)} y={H - 8} textAnchor="middle"
                fontSize="10" fill="var(--text-muted)">
            {m.slice(0, 4)}
          </text>
        ))}
        {paths.map((p, i) => (
          <path
            key={p.sgg_cd}
            d={p.d}
            fill="none"
            stroke={colorAt(i, paths.length)}
            strokeWidth={compact ? 1.2 : 1.8}
            strokeLinejoin="round"
            onMouseEnter={(e) =>
              tip.show(e, (
                <>
                  <div className="t-title">{p.name}</div>
                  <div className="t-row">
                    최신 {fmt(p.latest, data.decimals)} {data.unit}
                  </div>
                  <div className="t-row">
                    {p.first_ym}~{p.latest_ym}
                    {p.change_pct == null
                      ? ''
                      : ` · ${p.change_pct > 0 ? '+' : ''}${fmt(p.change_pct, 1)}%`}
                  </div>
                </>
              ))
            }
            onMouseLeave={tip.hide}
          />
        ))}
      </svg>
      {tip.node}
    </div>
  )
}

function Legend({ data, hidden, onToggle }) {
  const shown = data.items.filter((i) => !hidden.has(i.sgg_cd))
  const indexOfShown = new Map(shown.map((s, i) => [s.sgg_cd, i]))
  return (
    <div className="macro-legend">
      {data.items.map((i) => {
        const off = hidden.has(i.sgg_cd)
        return (
          <button
            key={i.sgg_cd}
            className={`macro-key${off ? ' is-off' : ''}`}
            onClick={() => onToggle(i.sgg_cd)}
            aria-pressed={!off}
            title={off ? '다시 표시' : '숨기기'}
          >
            <i
              style={{
                background: off
                  ? 'var(--text-muted)'
                  : colorAt(indexOfShown.get(i.sgg_cd), shown.length),
              }}
            />
            {i.name}
          </button>
        )
      })}
    </div>
  )
}

/** 순위를 색상환에 고르게 편다. 17개를 구분하려면 고정 팔레트로는 모자란다. */
function colorAt(i, n) {
  if (i == null) return 'var(--text-muted)'
  const hue = Math.round((i / Math.max(n, 1)) * 320)
  return `hsl(${hue} 62% 48%)`
}

/* ── 카드 ──────────────────────────────────────────────────────────────
   시장 분석의 요인 카드와 같은 규격(.factor)을 쓴다. 매크로 탭이 처음에는 전부
   전폭이라 그림 하나 보려고 한참 스크롤해야 했다.

   카드 안에는 **모양만** 둔다. 300px 폭에 이름표 17개를 적으면 읽을 수가 없고,
   읽히지도 않는 글자를 그려 놓는 것은 자리만 먹는다. 자세한 것은 눌러서 띄운다. */
function CycleChart({ ins, compact }) {
  return (
    <QuadrantScatter
      items={ins.cycle.items}
      x={(d) => d.from_peak}
      y={(d) => d.m3}
      xLabel={ins.cycle.x_label}
      yLabel={ins.cycle.y_label}
      quadrants={['신고가 경신 중', '바닥에서 반등', '전고점 아래 · 정체/하락', '고점 부근에서 꺾임']}
      xDecimals={0}
      compact={compact}
      height={compact ? 150 : 340}
      tip={(d) => (
        <>
          <div className="t-title">{d.name}</div>
          <div className="t-row">
            전고점({d.peak_ym}) 대비 {d.from_peak > 0 ? '+' : ''}
            {fmt(d.from_peak, 1)}%
          </div>
          <div className="t-row">
            저점({d.trough_ym})에서 +{fmt(d.from_trough, 1)}%
          </div>
          <div className="t-row">
            3개월 {d.m3 > 0 ? '+' : ''}
            {fmt(d.m3, 2)}% · 12개월 {d.m12 > 0 ? '+' : ''}
            {fmt(d.m12, 2)}%
          </div>
          {d.accel != null && (
            <div className="t-row">
              직전 3개월 대비 {d.accel > 0 ? '가속' : '감속'} {fmt(Math.abs(d.accel), 2)}%p
            </div>
          )}
          {/* 이 점의 무게. 월 33건에서 나온 -5% 와 월 1,137건에서 나온 -5% 는 다르다. */}
          {d.vol_pm != null && (
            <div className="t-row">이 구의 거래 월평균 {fmt(d.vol_pm, 0)}건</div>
          )}
        </>
      )}
    />
  )
}

function RallyChart({ ins, compact }) {
  return (
    <QuadrantScatter
      items={ins.rally.items}
      x={(d) => d.sale_12m}
      y={(d) => d.ratio_12m}
      xLabel={ins.rally.x_label}
      yLabel={ins.rally.y_label}
      quadrants={['오르고 전세도 붙음', '안 올랐는데 전세는 붙음', '안 오르고 전세도 빠짐', '매매만 간 상승']}
      xDecimals={0}
      compact={compact}
      height={compact ? 150 : 340}
      tip={(d) => (
        <>
          <div className="t-title">{d.name}</div>
          <div className="t-row">
            12개월 매매 {d.sale_12m > 0 ? '+' : ''}
            {fmt(d.sale_12m, 1)}%
          </div>
          <div className="t-row">
            전세가율 {fmt(d.ratio_now, 1)}% ({d.ratio_12m > 0 ? '+' : ''}
            {fmt(d.ratio_12m, 1)}%p)
          </div>
        </>
      )}
    />
  )
}

function VolumeChart({ ins, compact }) {
  return (
    <QuadrantScatter
      items={ins.volume.items}
      x={(d) => d.sale_12m}
      y={(d) => d.vol_pct}
      xLabel={ins.volume.x_label}
      yLabel={ins.volume.y_label}
      quadrants={[
        '거래가 받쳐 준 상승',
        '거래는 되는데 안 오름',
        '거래도 가격도 조용함',
        '거래 없이 오른 상승',
      ]}
      xDecimals={0}
      yDecimals={0}
      compact={compact}
      height={compact ? 150 : 340}
      tip={(d) => (
        <>
          <div className="t-title">{d.name}</div>
          <div className="t-row">
            12개월 매매 {d.sale_12m > 0 ? '+' : ''}
            {fmt(d.sale_12m, 1)}%
          </div>
          <div className="t-row">
            거래 {fmt(d.vol_12m, 0)}건 · 5년 평균 {fmt(d.vol_base, 0)}건 대비{' '}
            {d.vol_pct > 0 ? '+' : ''}
            {fmt(d.vol_pct, 0)}%
          </div>
          <div className="t-row">월평균 {fmt(d.vol_pm, 0)}건 · 최신 {d.latest_ym}</div>
        </>
      )}
    />
  )
}

/* 카드 축소판. 이름표가 없으면 '어디가 얇은가' 는 못 읽지만 **분포의 모양**은
   읽힌다 — 맨 아래 한두 개가 유독 짧은 것이 과천이고, 그게 이 카드의 요점이다. */
function DepthBars({ ins, compact }) {
  return (
    <MacroBars
      items={ins.depth.items}
      value={(d) => d.per_month}
      decimals={0}
      suffix="건"
      mark={(d) => d.thin}
      markLabel="얇다"
      compact={compact}
    />
  )
}

function SpreadBars({ ins, compact }) {
  return (
    <MacroBars
      items={ins.spread.items}
      value={(d) => d.spread_pct}
      diverging
      suffix="%"
      compact={compact}
    />
  )
}

function GapChart({ ins, compact }) {
  return (
    <QuadrantScatter
      items={ins.model_gap.items}
      x={(d) => d.rank_reb}
      y={(d) => d.rank_coef}
      xLabel={ins.model_gap.x_label}
      yLabel={ins.model_gap.y_label}
      xOrigin={null}
      yOrigin={null}
      invertX
      invertY
      diagonal
      xDecimals={0}
      yDecimals={0}
      compact={compact}
      height={compact ? 150 : 340}
      tip={(d) => (
        <>
          <div className="t-title">{d.name}</div>
          <div className="t-row">
            부동산원 {d.rank_reb}위 · 평당 {fmt(d.reb, 0)}만원
          </div>
          <div className="t-row">
            모델 {d.rank_coef}위 · 구 계수 {d.coef_pct > 0 ? '+' : ''}
            {fmt(d.coef_pct, 1)}%{d.is_base ? ' (기준구)' : ''}
          </div>
          <div className="t-row">
            순위 차 {d.rank_gap > 0 ? '+' : ''}
            {d.rank_gap}
          </div>
        </>
      )}
    />
  )
}

function GapTable({ gap }) {
  const top = [...gap.items]
    .sort((a, b) => Math.abs(b.rank_gap) - Math.abs(a.rank_gap))
    .slice(0, 5)
  return (
    <>
      <div className="table-wrap" style={{ marginTop: 10 }}>
        <table>
          <thead>
            <tr>
              <th>시군구</th>
              <th className="num">부동산원</th>
              <th className="num">모델</th>
              <th className="num">순위 차</th>
            </tr>
          </thead>
          <tbody>
            {top.map((d) => (
              <tr key={d.sgg_cd}>
                <td>{d.name}</td>
                <td className="num">
                  {d.rank_reb}위 <span className="muted small">{fmt(d.reb, 0)}만원/평</span>
                </td>
                <td className="num">
                  {d.rank_coef}위{' '}
                  <span className="muted small">
                    {d.coef_pct > 0 ? '+' : ''}
                    {fmt(d.coef_pct, 1)}%
                  </span>
                </td>
                <td className={`num ${d.rank_gap > 0 ? 'tone-neg' : 'tone-pos'}`}>
                  {d.rank_gap > 0 ? '+' : ''}
                  {d.rank_gap}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        가장 많이 벌어진 다섯 곳입니다. 어느 쪽이 맞는지는 이 표가 말해 주지 않습니다 —
        그 지역의 평형·연식 구성이 특이해 단순 평균이 끌려갔거나, 모델이 뭔가를
        놓쳤거나입니다. <b>어디를 들여다볼지</b>만 알려 줍니다.
      </p>
    </>
  )
}

/* 카드 안에는 위아래 세 곳씩만. 전체는 눌러서 본다. */
function MiniTable({ data }) {
  const n = data.items.length
  const row = (i) => (
    <tr key={i.sgg_cd}>
      <td>{i.name}</td>
      <td className="num">
        <b>{fmt(i.latest, data.decimals)}</b>
      </td>
      <td
        className={`num ${
          i.change_pct > 0 ? 'tone-pos' : i.change_pct < 0 ? 'tone-neg' : ''
        }`}
      >
        {i.change_pct == null
          ? '—'
          : `${i.change_pct > 0 ? '+' : ''}${fmt(i.change_pct, 1)}%`}
      </td>
    </tr>
  )
  return (
    <table className="macro-mini">
      <tbody>
        {data.items.slice(0, 3).map(row)}
        {n > 6 && (
          <tr className="macro-mini-gap">
            <td colSpan={3} className="muted small">
              ⋯ {n - 6}곳 더
            </td>
          </tr>
        )}
        {n > 3 && data.items.slice(-3).map(row)}
      </tbody>
    </table>
  )
}

function FullTable({ data }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>시군구</th>
            <th className="num">{data.label}</th>
            <th className="num">기간 변화</th>
            <th>시작</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((i) => (
            <tr key={i.sgg_cd}>
              <td>{i.name}</td>
              <td className="num">
                <b>{fmt(i.latest, data.decimals)}</b>
                <span className="muted small"> {data.unit}</span>
              </td>
              <td
                className={`num ${
                  i.change_pct > 0 ? 'tone-pos' : i.change_pct < 0 ? 'tone-neg' : ''
                }`}
              >
                {i.change_pct == null
                  ? '—'
                  : `${i.change_pct > 0 ? '+' : ''}${fmt(i.change_pct, 1)}%`}
              </td>
              <td className="muted small">
                {i.first_ym}
                {i.partial ? ' (분구 후)' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


/* 지표 칩. 마우스를 올리면 그 숫자가 **무엇이고 어떻게 읽는지**가 뜬다.
 *
 * 지표 이름만으로는 알 수 없는 것들이 있다. '전세가율' 이 내려간 것이 좋은 신호인지
 * 나쁜 신호인지, '매매가격지수 102' 가 비싼 동네라는 뜻인지 아닌지 — 이름은 아무
 * 말도 해 주지 않는다.
 *
 * 호버는 터치 화면에 없으므로, 고른 지표의 설명은 칩 아래에 **항상** 적어 둔다
 * (`MetricNote`). 호버는 고르기 전에 미리 볼 수 있다는 점에서만 더하는 것이다.
 */
function MetricChips({ metrics, value, onChange }) {
  const tip = useTooltip()
  return (
    <div className="rank-basis" style={{ margin: 0 }}>
      {metrics.map((m) => (
        <button
          key={m.key}
          className={`chip${value === m.key ? ' on' : ''}`}
          onClick={() => onChange(m.key)}
          onMouseEnter={(e) =>
            tip.show(
              e,
              <>
                <div className="t-title">
                  {m.label} <span className="muted">({m.unit})</span>
                </div>
                <div className="t-row">{m.what}</div>
                <div className="t-row" style={{ marginTop: 4 }}>
                  {m.read}
                </div>
                {m.base && (
                  <div className="t-row" style={{ marginTop: 4 }}>
                    기준시점 {m.base}
                  </div>
                )}
              </>,
              'is-wide',
            )
          }
          onMouseLeave={tip.hide}
        >
          {m.label}
        </button>
      ))}
      {tip.node}
    </div>
  )
}

/* 고른 지표의 설명. 호버가 없는 터치 화면에서도 읽을 수 있어야 한다. */
function MetricNote({ m }) {
  if (!m) return null
  return (
    <p className="metric-note">
      <b>{m.label}</b>
      <span className="muted"> ({m.unit}{m.base ? ` · 기준시점 ${m.base}` : ''})</span>
      {' — '}
      {m.what} {m.read}
    </p>
  )
}

/* 그림 읽는 법.
 *
 * 사분면 이름만으로는 축이 무엇인지까지는 알 수 없다. 그렇다고 설명을 늘 펼쳐 두면
 * 정작 그림이 아래로 밀린다 — 매크로 탭을 카드로 줄인 이유와 같다.
 *
 * 그래서 접어 둔다. 처음 보는 사람은 한 번 펼쳐 읽고, 아는 사람은 건드리지 않는다.
 * 창 안에 두는 이유: 카드 축소판에는 축 눈금도 사분면 이름도 없어서 읽는 법을 적어
 * 봐야 가리킬 것이 없다.
 */
function ChartGuide({ axes, why, quadrants, tips, caveat }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="chart-guide">
      <button
        className="linklike guide-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? '읽는 법 접기 ▴' : '읽는 법 ▾'}
      </button>

      {open && (
        <div className="guide-body">
          <dl className="guide-axes">
            {axes.map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>

          {why && <p className="guide-why">{why}</p>}

          {quadrants && (
            <ul className="guide-quad">
              {quadrants.map(([k, v]) => (
                <li key={k}>
                  <b>{k}</b>
                  <span>{v}</span>
                </li>
              ))}
            </ul>
          )}

          {tips?.length > 0 && (
            <ul className="guide-tips">
              {tips.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          )}

          {caveat && <p className="guide-caveat">{caveat}</p>}
        </div>
      )}
    </div>
  )
}
