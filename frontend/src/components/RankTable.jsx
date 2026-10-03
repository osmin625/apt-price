import { useEffect, useState } from 'react'

import { eok, fmt } from './Charts'
import FactorHint from './FactorHint'
import GroupHint from './GroupHint'
import Hint from './Hint'
import PriceTrail from './PriceTrail'
import RankCards from './RankCards'
import NoteCell from './NoteCell'
import { gapText, otherOf, toneOf, verdictOf } from './rankBasis'

const TONE = {
  저평가: 'good',
  '다소 저렴': 'good',
  적정: 'mid',
  '다소 비쌈': 'bad',
  고평가: 'bad',
}

/**
 * 매물 순위표. 일괄 붙여넣기 결과와 누적 순위가 같은 표를 쓴다.
 *
 * **선택한 기준의 열만 보여 준다.**
 *
 * 예전에는 둘 다 깔고 선택한 쪽만 강조했다. '기준을 바꿨는데 적정가가 그대로면
 * 고장난 것처럼 보인다' 가 이유였는데, 열이 통째로 바뀌면 그 문제는 더 분명하게
 * 풀린다 — 바뀐 것이 색이 아니라 표 모양이라 못 알아볼 수가 없다. 대신 열이 둘
 * 줄어 단지명·비고가 숨 쉴 자리가 생긴다.
 *
 * **안 보이는 쪽 값은 버리지 않는다.** 보이는 칸에 마우스를 올리면 다른 기준의
 * 적정가와 대비가 같이 뜬다. 두 기준이 어긋나는 것 자체가 정보이기 때문이다 —
 * 광교 84㎡ 가 실거래 기준 1위인데 요인 기준 4위로 내려간 적이 있다.
 *
 * **판정도 기준을 따라간다.** 서버가 `verdict`(실거래)와 `verdict_factor`(요인)를
 * 따로 준다. 안 그러면 요인 기준 화면에서 대비는 -12% 인데 판정은 '적정' 으로
 * 적히는 일이 생긴다 — 열을 숨기면서 생긴 문제라 같이 고쳤다.
 *
 * **같은 단지 매물만 있으면 두 기준의 순위가 같다.** 우연이 아니라 필연이다 —
 * 요인적정/실거래적정 비율이 단지 안에서 상수이기 때문이다(실측 1.1616, 폭 0.0001).
 * 단지 프리미엄은 그 단지 전체에 똑같이 곱해지므로 순서를 바꾸지 못한다.
 * 순위가 갈리려면 **서로 다른 단지**가 섞여야 한다. 그 사실을 표 아래에 적는다.
 */
/**
 * 좁은 화면인가. `matchMedia` 를 쓰는 이유는 CSS 의 중단점과 **같은 값** 하나로
 * 맞추기 위해서다 — 여기서 720px, CSS 에서 720px 로 따로 적으면 언젠가 어긋난다.
 */
function useNarrow(query = '(max-width: 720px)') {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  )
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = (e) => setNarrow(e.matches)
    setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return narrow
}

export default function RankTable({ items, basis, onDelete, deleting, onSelect, onNoteSaved }) {
  const narrow = useNarrow()
  const isFactor = basis === 'factor'
  if (!items?.length) return null

  const byMarket = [...items].sort((a, b) => (a.gap_pct ?? 9e9) - (b.gap_pct ?? 9e9))
  const byFactor = [...items].sort(
    (a, b) => (a.gap_factor_pct ?? 9e9) - (b.gap_factor_pct ?? 9e9),
  )
  const sameOrder =
    byFactor.every((x, i) => x === byMarket[i]) &&
    items.some((i) => i.gap_factor_pct != null)
  const complexes = new Set(items.map((i) => i.complex_id)).size
  /* 요인 기준을 골랐는데 **값이 한 줄도 없는** 경우. 적합이 캐시에 없으면 서버가
     요인 적정가를 못 낸다. 예전에는 실거래 열이 옆에 있어 표가 비어 보이지 않았는데,
     선택한 기준의 열만 남기면서 '— 만 가득한 표' 가 될 수 있게 됐다. 그건 고장처럼
     보이고, 왜 그런지도 안 적혀 있다. 그래서 말해 준다. */
  const noFactor = isFactor && items.every((i) => i.gap_factor_pct == null)

  return (
    <>
      {noFactor && (
        <p className="paste-warn" style={{ marginBottom: 8 }}>
          요인 적정가가 아직 없습니다. <b>분석</b> 탭을 한 번 열면 계산되고, 그 뒤
          이 화면으로 돌아오면 채워집니다. 그때까지는 <b>실거래 기준</b>으로 보세요.
        </p>
      )}
      {narrow ? (
        <RankCards
          items={items}
          basis={basis}
          onDelete={onDelete}
          deleting={deleting}
          onSelect={onSelect}
          onNoteSaved={onNoteSaved}
        />
      ) : (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="num">#</th>
              <th>단지</th>
              <th>동</th>
              <th className="num">전용</th>
              <th className="num">층</th>
              <th className="num">호가</th>
              <th className="num">확인</th>
              <th className="num is-sort">{isFactor ? '요인 적정' : '실거래 적정'}</th>
              <th className="num is-sort">대비</th>
              <th>판정</th>
              <th className="num">추가</th>
              <th className="col-note">비고</th>
              {onDelete && <th />}
            </tr>
          </thead>
          <tbody>
            {items.map((i, n) => (
              <tr
                key={i.quote_id ?? n}
                className={`${i.rank === 1 ? 'is-top' : ''}${
                  deleting === i.quote_id ? ' is-deleting' : ''
                }`}
              >
                <td className="num rank-no">{i.rank ?? '—'}</td>
                <td>
                  {onSelect ? (
                    <button className="linklike" onClick={() => onSelect(i.complex_id)}>
                      {i.complex_name}
                    </button>
                  ) : (
                    i.complex_name
                  )}
                </td>
                <td>
                  {i.dong ? `${i.dong}동` : <span className="muted">—</span>}
                  {i.listing_count > 1 && !i.group_count && (
                    <span className="badge" title={`중개사 ${i.listing_count}곳에 올라온 같은 매물`}>
                      x{i.listing_count}
                    </span>
                  )}
                </td>
                <td className="num">{i.exclusive_area}㎡</td>
                <td className="num">
                  {i.floor ?? '—'}
                  {i.floor_band && <span className="muted small"> {i.floor_band}</span>}
                </td>
                <td className="num">
                  {eok(i.asking_price)}
                  {i.price_is_range && (
                    <Hint notes={['목록에 가격이 범위로 올라와 있어 낮은 쪽을 썼습니다.']} tone="warn" />
                  )}
                  <PriceTrail item={i} />
                  <GroupHint item={i} />
                </td>
                <td className="num muted small">
                  {i.confirmed_on ? i.confirmed_on.slice(5).replace('-', '.') : '—'}
                </td>
                <td className="num muted is-sort" title={otherOf(i, isFactor)}>
                  {isFactor
                    ? i.factor_price
                      ? eok(i.factor_price)
                      : '—'
                    : eok(i.fair_price)}
                  {isFactor && <FactorHint parts={i.factor_parts} />}
                </td>
                <td
                  className="num is-sort"
                  title={otherOf(i, isFactor)}
                  data-tone={toneOf(isFactor ? i.gap_factor_pct : i.gap_pct)}
                >
                  {gapText(isFactor ? i.gap_factor_pct : i.gap_pct)}
                </td>
                <td>
                  <span
                    className="verdict"
                    data-tone={TONE[verdictOf(i, isFactor)]}
                    style={{ fontSize: 13 }}
                  >
                    {verdictOf(i, isFactor) || '—'}
                  </span>
                </td>
                {/* 우리가 이 줄을 **언제 넣었나**. 매물에 적힌 '확인' 일자와 다르다 —
                    확인은 중개사가 매물을 확인한 날이고 이쪽은 우리 데이터 기준이다. */}
                <td className="num muted small">{i.added_on ? i.added_on.slice(5) : '—'}</td>
                <td className="col-note">
                  {i.note_key ? (
                    <NoteCell item={i} onSaved={onNoteSaved} />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                {onDelete && (
                  <td>
                    <button
                      className="ghost"
                      disabled={deleting != null}
                      onClick={() => onDelete(i.quote_id)}
                    >
                      {deleting === i.quote_id
                        ? '삭제 중…'
                        : i.revisions > 1
                          ? `삭제 (${i.revisions})`
                          : '삭제'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}

      {sameOrder && (
        <p className="muted small" style={{ marginTop: 8 }}>
          두 기준의 순위가 같습니다
          {complexes === 1 ? ' — 매물이 모두 같은 단지이기 때문입니다.' : '.'}
          <Hint
            notes={[
              '요인 적정가 ÷ 실거래 적정가 비율은 한 단지 안에서 상수입니다(실측 1.1616, 폭 0.0001). 단지 프리미엄이 그 단지 전체에 똑같이 곱해지기 때문입니다.',
              '상수를 곱해도 순서는 바뀌지 않으므로, 같은 단지 매물만 모으면 두 기준의 순위는 반드시 같습니다.',
              '순위가 갈리려면 서로 다른 단지가 섞여야 합니다 — 그때 단지 프리미엄 차이가 드러납니다.',
            ]}
          />
        </p>
      )}
    </>
  )
}
