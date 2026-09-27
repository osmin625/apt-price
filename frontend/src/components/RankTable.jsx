import { eok, fmt } from './Charts'
import FactorHint from './FactorHint'
import GroupHint from './GroupHint'
import Hint from './Hint'
import PriceTrail from './PriceTrail'

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
 * **적정가를 두 개 다 보여 준다.** 기준을 바꿨는데 적정가가 그대로면 고장난 것처럼
 * 보인다 — 실제로 그랬다. 실거래 기준과 요인 기준은 서로 다른 값이고, 선택한 쪽을
 * 강조하되 둘 다 두어야 왜 다른지가 보인다.
 *
 * **같은 단지 매물만 있으면 두 기준의 순위가 같다.** 우연이 아니라 필연이다 —
 * 요인적정/실거래적정 비율이 단지 안에서 상수이기 때문이다(실측 1.1616, 폭 0.0001).
 * 단지 프리미엄은 그 단지 전체에 똑같이 곱해지므로 순서를 바꾸지 못한다.
 * 순위가 갈리려면 **서로 다른 단지**가 섞여야 한다. 그 사실을 표 아래에 적는다.
 */
export default function RankTable({ items, basis, onDelete, deleting }) {
  if (!items?.length) return null

  const byMarket = [...items].sort((a, b) => (a.gap_pct ?? 9e9) - (b.gap_pct ?? 9e9))
  const byFactor = [...items].sort(
    (a, b) => (a.gap_factor_pct ?? 9e9) - (b.gap_factor_pct ?? 9e9),
  )
  const sameOrder =
    byFactor.every((x, i) => x === byMarket[i]) &&
    items.some((i) => i.gap_factor_pct != null)
  const complexes = new Set(items.map((i) => i.complex_id)).size

  return (
    <>
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
              <th className={`num${basis === 'market' ? ' is-sort' : ''}`}>실거래 적정</th>
              <th className={`num${basis === 'market' ? ' is-sort' : ''}`}>대비</th>
              <th className={`num${basis === 'factor' ? ' is-sort' : ''}`}>요인 적정</th>
              <th className={`num${basis === 'factor' ? ' is-sort' : ''}`}>대비</th>
              <th>판정</th>
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
                <td>{i.complex_name}</td>
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
                <td className={`num muted${basis === 'market' ? ' is-sort' : ''}`}>
                  {eok(i.fair_price)}
                </td>
                <td
                  className={`num${basis === 'market' ? ' is-sort' : ''}`}
                  data-tone={i.gap_pct < -3 ? 'good' : i.gap_pct > 3 ? 'bad' : 'mid'}
                >
                  {i.gap_pct > 0 ? '+' : ''}
                  {fmt(i.gap_pct, 1)}%
                </td>
                <td className={`num muted${basis === 'factor' ? ' is-sort' : ''}`}>
                  {i.factor_price ? eok(i.factor_price) : '—'}
                  <FactorHint parts={i.factor_parts} />
                </td>
                <td
                  className={`num${basis === 'factor' ? ' is-sort' : ''}`}
                  data-tone={
                    i.gap_factor_pct == null
                      ? null
                      : i.gap_factor_pct < -3
                        ? 'good'
                        : i.gap_factor_pct > 3
                          ? 'bad'
                          : 'mid'
                  }
                >
                  {i.gap_factor_pct == null
                    ? '—'
                    : `${i.gap_factor_pct > 0 ? '+' : ''}${fmt(i.gap_factor_pct, 1)}%`}
                </td>
                <td>
                  <span className="verdict" data-tone={TONE[i.verdict]} style={{ fontSize: 13 }}>
                    {i.verdict}
                  </span>
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
