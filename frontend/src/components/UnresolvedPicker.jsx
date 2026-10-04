import { fmt } from './Charts'

/**
 * 단지를 못 찾은 매물에 **후보를 띄워 고르게** 한다.
 *
 * ## 왜 필요한가
 *
 * 이 저장소는 단지를 보수적으로 붙인다 — 잘못 붙이면 남의 거래가 섞여 시세가 통째로
 * 망가지지만, 안 붙이면 줄이 하나 비는 것뿐이다. 실제로 '성원 102동' 이 정규화 과정에서
 * 안양 '성원1' 에 붙어 수원 매물 11건이 남의 시 시세로 저장된 적이 있다.
 *
 * 그래서 같은 이름이 여럿이면 **고르지 않는다.** 그런데 고를 길도 없으면 그 매물은
 * 그냥 사라진다. 실제 붙여넣기 82건 중 '현대' 20건·'동산' 9건이 그렇게 버려졌다.
 *
 * ## 줄이 아니라 **이름** 단위로 고른다
 *
 * 못 고른 이유가 '이 이름이 여러 곳'이므로, 한 번 고르면 그 이름의 매물이 전부 풀린다.
 * 줄마다 고르게 하면 '현대' 하나에 스무 번을 눌러야 한다.
 *
 * ## 고를 수 있을 만큼 보여 준다
 *
 * 시군구만으로는 못 고른다 — '현대' 는 수원 장안구에만 세 곳이다(천천동·파장동·정자동).
 * 법정동·준공·세대수와 **등록된 동 번호**를 같이 띄운다. 동 번호가 결정적이다:
 * 붙여넣은 매물이 101~104동이면 그 동이 있는 곳이 답이다.
 *
 * 거래 건수도 보여 준다. 0건인 단지를 고르면 적정가를 못 내는데, 고른 뒤에
 * "비교 실거래 없음" 만 뜨면 왜인지 알 수 없다.
 */
export default function UnresolvedPicker({ skipped, nameMap, onPick, busy }) {
  // 이름으로 묶는다. 후보는 어느 줄이나 같으므로 첫 줄의 것을 쓴다.
  const groups = new Map()
  for (const s of skipped || []) {
    if (!s.name || !s.candidates?.length) continue
    if (!groups.has(s.name)) groups.set(s.name, { name: s.name, cands: s.candidates, rows: [] })
    groups.get(s.name).rows.push(s)
  }
  if (!groups.size) return null

  return (
    <div className="unresolved">
      <p className="muted small">
        같은 이름의 단지가 여러 곳이라 자동으로 고르지 않았습니다. 잘못 붙이면 남의
        단지 거래가 시세에 섞이기 때문입니다 — <b>어느 단지인지 눌러 주세요.</b> 한 번
        고르면 그 이름의 매물이 전부 다시 읽힙니다.
      </p>

      {[...groups.values()].map((g) => (
        <div className="unres-group" key={g.name}>
          <div className="unres-head">
            <b>{g.name}</b>
            <span className="muted small">{g.rows.length}건 · 후보 {g.cands.length}곳</span>
            {nameMap[g.name] && (
              <button className="linklike" onClick={() => onPick(g.name, null)}>
                고른 것 지우기
              </button>
            )}
          </div>
          <div className="unres-cands">
            {g.cands.map((c) => (
              <button
                key={c.id}
                className={`unres-cand${nameMap[g.name] === c.id ? ' on' : ''}`}
                disabled={busy}
                onClick={() => onPick(g.name, c.id)}
              >
                <span className="uc-name">{c.name}</span>
                <span className="uc-where">
                  {[c.sgg_name, c.umd_nm].filter(Boolean).join(' ')}
                  {c.jibun ? ` ${c.jibun}` : ''}
                </span>
                <span className="uc-meta">
                  {c.build_year ? `${c.build_year}년` : '준공 미상'}
                  {c.household_count ? ` · ${fmt(c.household_count)}세대` : ''}
                  {' · 거래 '}
                  <b className={c.trade_count ? '' : 'none'}>{fmt(c.trade_count)}건</b>
                </span>
                {c.dongs?.length > 0 && (
                  <span className="uc-dongs">
                    동 {c.dongs.slice(0, 6).join('·')}
                    {c.dongs.length > 6 ? ' …' : ''}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
