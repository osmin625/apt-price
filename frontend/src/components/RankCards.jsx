import { eok, fmt } from './Charts'
import { gapText, otherOf, verdictOf } from './rankBasis'
import FactorHint from './FactorHint'
import GroupHint from './GroupHint'
import Hint from './Hint'
import PriceTrail from './PriceTrail'
import NoteCell from './NoteCell'

const TONE = {
  저평가: 'good',
  '다소 저렴': 'good',
  적정: 'mid',
  '다소 비쌈': 'bad',
  고평가: 'bad',
}

/**
 * 좁은 화면용 매물 순위 — 표 대신 카드.
 *
 * ## 왜 표를 그대로 두지 않았나
 *
 * 순위표는 열이 열한 개다. 375px 에 넣으면 각 열이 30px 남짓으로 눌려
 * **단지명이 글자마다 세로로 쪼개졌다**(수/원/센/트/럴/아/이/파/크/자/이).
 * 표에 `min-width` 를 줘서 가로 스크롤로 만들 수도 있지만, 한 줄을 읽으려고
 * 매번 옆으로 밀어야 하고 머리글은 밀려나 사라진다.
 *
 * 그래서 **정보 구조를 다시 짰다.** 열을 그대로 세로로 눕히는 게 아니라,
 * 휴대폰에서 실제로 보는 순서대로 놓는다.
 *
 *   1) 순위 · 단지 · 판정      — 이 매물이 뭐고 쌀까 비쌀까
 *   2) 호가 · 괴리율           — 가장 크게. 답이 여기 있다
 *   3) 선택한 기준의 적정가    — 근거
 *   4) 확인일자 · 접힌 건수     — 곁다리
 *
 * 호버가 없는 기기라 `Hint` 류는 탭으로 열린다(`tabIndex`/`focus` 로 이미 동작한다).
 */
export default function RankCards({ items, basis, onDelete, deleting, onSelect, onNoteSaved }) {
  /* 표와 **같은 규칙**을 쓴다. 각자 고르면 같은 매물이 표와 카드에서 다른 판정을
     달게 된다 — 화면 폭에 따라 답이 달라지는 셈이다. */
  const isFactor = basis === 'factor'
  return (
    <ul className="rank-cards">
      {items.map((i, n) => {
        const primary = basis === 'factor' ? i.gap_factor_pct : i.gap_pct
        const tone = primary == null ? null : primary < -3 ? 'good' : primary > 3 ? 'bad' : 'mid'
        return (
          <li
            key={i.quote_id ?? n}
            className={`rank-card${deleting === i.quote_id ? ' is-deleting' : ''}`}
          >
            <div className="rc-head">
              <span className="rc-rank">{i.rank ?? '—'}</span>
              {onSelect ? (
                <button className="rc-name linklike" onClick={() => onSelect(i.complex_id)}>
                  {i.complex_name}
                </button>
              ) : (
                <span className="rc-name">{i.complex_name}</span>
              )}
              <span className="verdict" data-tone={TONE[verdictOf(i, isFactor)]}>
                {verdictOf(i, isFactor) || '—'}
              </span>
            </div>

            <div className="rc-spec">
              {i.dong ? `${i.dong}동` : '동 미상'} · {i.exclusive_area}㎡ ·{' '}
              {i.floor ?? '—'}층{i.floor_band ? ` (${i.floor_band})` : ''}
            </div>

            <div className="rc-answer">
              <span className="rc-ask">
                {eok(i.asking_price)}
                {i.price_is_range && (
                  <Hint
                    notes={['목록에 가격이 범위로 올라와 있어 낮은 쪽을 썼습니다.']}
                    tone="warn"
                  />
                )}
                <PriceTrail item={i} />
                <GroupHint item={i} />
              </span>
              <span className="rc-gap" data-tone={tone}>
                {primary == null ? '—' : `${primary > 0 ? '+' : ''}${fmt(primary, 1)}%`}
              </span>
            </div>

            {/* 선택한 기준만 적는다. 다른 기준 값은 호버/탭으로 내린다 — 두 기준이
                어긋나는 것 자체가 정보라, 안 보인다고 버리지는 않는다. */}
            <div className="rc-basis">
              <span className="is-sort" title={otherOf(i, isFactor)}>
                {isFactor ? '요인' : '실거래'}{' '}
                {isFactor ? (i.factor_price ? eok(i.factor_price) : '—') : eok(i.fair_price)}
                <em> {gapText(isFactor ? i.gap_factor_pct : i.gap_pct)}</em>
                {isFactor && <FactorHint parts={i.factor_parts} />}
              </span>
              <span className="rc-other muted small">{otherOf(i, isFactor)}</span>
            </div>

            {/* 비고는 카드에서도 고칠 수 있어야 한다. 좁은 화면이라고 읽기만
                되게 두면 휴대폰으로 보던 사람이 적어 둘 데가 없다. */}
            {i.note_key && (
              <div className="rc-note">
                <NoteCell item={i} onSaved={onNoteSaved} />
              </div>
            )}

            <div className="rc-foot">
              <span className="muted small">
                {i.confirmed_on ? `확인 ${i.confirmed_on.slice(5).replace('-', '.')}` : '확인일자 없음'}
                {i.added_on ? ` · 추가 ${i.added_on.slice(5).replace('-', '.')}` : ''}
              </span>
              {onDelete && (
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
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
