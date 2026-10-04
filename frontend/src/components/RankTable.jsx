import { useEffect, useState } from 'react'

import { eok, fmt } from './Charts'
import FactorHint from './FactorHint'
import GroupHint from './GroupHint'
import Hint from './Hint'
import PriceTrail from './PriceTrail'
import RankCards from './RankCards'
import NoteCell from './NoteCell'
import { gapText, otherOf, toneOf, verdictOf } from './rankBasis'
import {
  AREA_HINT,
  DONG_HINT,
  ONLY_HINT,
  SORT_COLS,
  applySort,
  areaKeyOf,
  nameClick,
  nextSort,
  scopeClick,
} from './rankSelect'

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

/* 정렬 가능한 머리말.
 *
 * 누르면 그 열로 오름차순, 다시 누르면 내림차순, 한 번 더 누르면 **기본(순위)으로**
 * 돌아온다. 세 번째 누름을 둔 이유: 안 두면 한 번 정렬한 뒤 원래 순서로 돌아갈 길이
 * 없어 새로고침을 하게 된다. `#` 머리말을 누르면 바로 기본으로 간다.
 *
 * 화살표는 **지금 정렬 중인 열에만** 띄운다. 모든 머리말에 흐린 화살표를 깔아 두는
 * 방식도 있는데, 그러면 표가 온통 화살표가 되고 정작 어디로 정렬됐는지가 안 보인다.
 * 대신 머리말에 밑줄점선을 둬서 누를 수 있다는 것만 알린다.
 */
function Sortable({ k, sort, onSort, children, title }) {
  const on = k != null && sort?.key === k
  return (
    <button
      type="button"
      className={`th-sort${on ? ' on' : ''}`}
      title={title || (k == null ? '기본 순서로' : `${SORT_COLS[k]?.label || ''} 기준 정렬`)}
      onClick={() => onSort(k == null ? null : (cur) => nextSort(cur, k))}
    >
      {children}
      {on && <i className="th-arrow">{sort.dir === 'asc' ? '▲' : '▼'}</i>}
    </button>
  )
}

export default function RankTable({ items, basis, onDelete, deleting, onSelect, onScope, onNoteSaved }) {
  const narrow = useNarrow()
  const isFactor = basis === 'factor'
  /* 정렬은 **표 안에 둔다.** 매물 순위와 붙여넣기 결과가 같은 표를 쓰므로 양쪽이
     공짜로 같은 동작을 얻는다. 거르기(어떤 줄을 볼까)는 바깥(RankingView)에 있고
     정렬(어떤 순서로 볼까)은 여기 있다 — 바깥은 번호를 매기고 여기는 늘어놓는다. */
  const [sort, setSort] = useState(null)
  if (!items?.length) return null

  // 카드에도 같은 순서를 먹인다. 머리말이 없어 카드에서는 바꿀 수 없지만, 표에서
  // 정렬해 두고 창을 줄였을 때 순서가 뒤바뀌면 같은 화면이 아닌 것처럼 보인다.
  const rows = applySort(items, sort, isFactor)

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
          items={rows}
          basis={basis}
          onDelete={onDelete}
          deleting={deleting}
          onSelect={onSelect}
          onScope={onScope}
          onNoteSaved={onNoteSaved}
        />
      ) : (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="num">
                <Sortable k={null} sort={sort} onSort={setSort} title="기본 순서 — 괴리율 순">
                  #
                </Sortable>
              </th>
              <th>
                <Sortable k="complex_name" sort={sort} onSort={setSort}>단지</Sortable>
              </th>
              <th>
                <Sortable k="dong" sort={sort} onSort={setSort}>동</Sortable>
              </th>
              <th className="num">
                <Sortable k="exclusive_area" sort={sort} onSort={setSort}>전용</Sortable>
              </th>
              <th className="num">
                <Sortable k="floor" sort={sort} onSort={setSort}>층</Sortable>
              </th>
              <th>향</th>
              <th className="num">
                <Sortable k="asking_price" sort={sort} onSort={setSort}>호가</Sortable>
              </th>
              <th className="num">
                <Sortable k="confirmed_on" sort={sort} onSort={setSort}>확인</Sortable>
              </th>
              <th className="num is-sort">
                <Sortable k="fair" sort={sort} onSort={setSort}>
                  {isFactor ? '요인 적정' : '실거래 적정'}
                </Sortable>
              </th>
              <th className="num is-sort">
                <Sortable k="gap" sort={sort} onSort={setSort}>대비</Sortable>
              </th>
              <th>판정</th>
              <th className="num">
                <Sortable k="added_on" sort={sort} onSort={setSort}>추가</Sortable>
              </th>
              <th className="col-note">비고</th>
              {onDelete && <th />}
            </tr>
          </thead>
          <tbody>
            {rows.map((i, n) => (
              <tr
                key={i.quote_id ?? n}
                className={`${i.rank === 1 ? 'is-top' : ''}${
                  deleting === i.quote_id ? ' is-deleting' : ''
                }`}
              >
                {/* 필터를 걸면 번호를 다시 매긴다. 그때 원래 순위를 호버에 남긴다 —
                    다시 매긴 번호를 전체 순위로 읽으면 안 된다. */}
                <td
                  className="num rank-no"
                  title={i.rank_all != null ? `거르기 전 ${i.rank_all}위` : undefined}
                >
                  {i.rank ?? '—'}
                  {i.rank_all != null && i.rank_all !== i.rank && <i className="rank-was">*</i>}
                </td>
                <td>
                  {onSelect ? (
                    <button
                      className="linklike"
                      onClick={(e) => nameClick(e, i, onSelect, onScope)}
                      title={ONLY_HINT}
                    >
                      {i.complex_name}
                    </button>
                  ) : (
                    i.complex_name
                  )}
                </td>
                <td>
                  {i.dong ? (
                    <span
                      className={onScope ? 'scopable' : undefined}
                      title={onScope ? DONG_HINT : undefined}
                      onClick={(e) =>
                        scopeClick(e, onScope, { complexId: i.complex_id, dong: String(i.dong) })
                      }
                    >
                      {i.dong}동
                    </span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                  {i.listing_count > 1 && !i.group_count && (
                    <span className="badge" title={`중개사 ${i.listing_count}곳에 올라온 같은 매물`}>
                      x{i.listing_count}
                    </span>
                  )}
                </td>
                <td className="num">
                  <span
                    className={onScope ? 'scopable' : undefined}
                    title={onScope ? AREA_HINT : undefined}
                    onClick={(e) =>
                      scopeClick(e, onScope, {
                        complexId: i.complex_id,
                        areaKey: areaKeyOf(i),
                      })
                    }
                  >
                    {i.exclusive_area}㎡
                  </span>
                </td>
                <td className="num">
                  {i.floor ?? '—'}
                  {i.floor_band && <span className="muted small"> {i.floor_band}</span>}
                </td>
                {/* 향. 매물에 적혀 있는데 지금까지 버리고 있었다 — 같은 단지·같은
                    평형이라도 남향과 북향은 값이 다르다. 모델에는 안 넣는다(실거래에
                    향이 없어 계수를 추정할 수 없다). 보여 주기만 한다. */}
                <td className="aspect">
                  {i.aspect || <span className="muted">—</span>}
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
