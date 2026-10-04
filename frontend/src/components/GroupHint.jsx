import { eok } from './Charts'
import Hint from './Hint'

/**
 * 같은 (단지·동·평형·층대)에 여러 건이 올라와 있을 때의 **접힌 매물 배지**.
 *
 * 130동 40㎡ 고층대에는 매물이 여덟 건 올라와 있었다. 그대로 두면 순위 상위가 한
 * 층대로 도배돼 다른 단지가 보이지 않는다. 그렇다고 합쳐 버리면 실재하는 매물이
 * 사라진다 — 목록에 호가 나오지 않으니 같은 집인지 알 방법이 없고, 확인일자가 같은
 * 날인 걸 보면 서로 다른 집일 가능성이 높다.
 *
 * 그래서 **접는다**. 대표 한 줄만 표에 두고, 몇 건인지는 배지로 밝히고, 전부는
 * 호버로 펼친다. 숨기는 게 아니라 한 단계 뒤로 미루는 것이다.
 */
export default function GroupHint({ item }) {
  if (!(item?.group_count > 1)) return null

  const d = (s) => (s ? s.slice(5).replace('-', '.') : '날짜 없음')

  return (
    <Hint pill wide tone="info" label={`${item.group_count}건`}>
      <span className="fh">
        <span className="fh-group">
          <span className="fh-title">같은 동·평형·층대에 올라온 매물 {item.group_count}건</span>
          {item.group.map((g, n) => (
            <span key={n} className="fh-row">
              <span className="fh-label">
                {d(g.confirmed_on)}
                {g.revisions > 1 && ` · 호가 ${g.revisions}번`}
              </span>
              <span className="fh-value" style={g.is_rep ? { fontWeight: 700 } : null}>
                {eok(g.asking_price)}
              </span>
              <span className="fh-pct">{g.is_rep ? '대표' : ''}</span>
            </span>
          ))}
        </span>
        <span className="fh-foot">
          {eok(item.group_min)} ~ {eok(item.group_max)}. 가장 최근 확인된 매물을, 같은 날이면 가장 싼
          쪽을 대표로 순위에 넣었습니다. 목록에 호가 나오지 않아 같은 집인지 알 수 없으므로
          합치지 않고 접어 두었습니다 — 이 줄을 지우면 {item.group_count}건이 함께 지워집니다.
        </span>
      </span>
    </Hint>
  )
}
