/*
 * 매물 담기 — 북마클릿 원본.
 *
 * 이 저장소는 네이버를 자동 수집하지 않는다. 브라우저를 대신 몰지도 않고 봇 감지를
 * 건드리지도 않으며 비공개 API 를 부르지도 않는다. **사람이 보고 있는 화면에서 사람이
 * 누르는** 버튼이고, 하는 일은 화면에 이미 떠 있는 글자를 클립보드에 담는 것뿐이다.
 * 드래그해서 Ctrl+C 하던 것을 한 번 누르는 것으로 줄인다.
 *
 * (Playwright 로 지도를 자동 클릭하는 스크립트를 만들다 접었다. 네이버가
 * `navigator.webdriver` 를 보고 404 로 보내고 있었고, 동작하게 하려면 그 감지를
 * 무력화해야 했다. 약관을 어기는 것과 접근 통제를 우회하는 것은 다른 일이다.)
 *
 * ## 쓰는 법
 *
 * `tools/bookmarklet.html` 을 브라우저로 열어 링크를 북마크바로 끌어다 둔다.
 * (북마크바가 안 보이면 Ctrl+Shift+B. 또는 ⋮ 메뉴 > 북마크 및 목록에서 눌러도 된다.)
 * 네이버 지도에서 단지를 눌러 매물 패널이 뜨면 북마크를 누른다. 누를 때마다
 * **지금까지 담은 전부**가 클립보드에 들어가므로, 여러 단지를 돌고 마지막에 한 번만
 * 붙여넣으면 된다.
 *
 * 패널이 안 열린 상태에서 누르면 담아 둔 것을 비울지 묻는다. 북마클릿은 수식키를
 * 구분할 수 없어서(Shift+클릭 같은 것을 못 받는다) '초기화' 를 그 자리에 둔 것이다.
 *
 * ## 영역이 아니라 카드를 찾는다
 *
 * 처음에는 '가격 줄이 가장 많이 든 영역' 을 패널로 보고 통째로 담았다. 그런데 매물이
 * 여러 묶음으로 흩어져 있으면 그 조건을 만족하는 가장 작은 영역이 결국 **페이지 전체**가
 * 된다. 실제로 헤더·메뉴·지도 라벨까지 전부 복사됐다.
 *
 * 그래서 매물 **카드 하나씩** 찾는다. 카드의 조건은 분명하다.
 *
 *   - 가격 줄(`매매/전세/월세 + 금액`)이 **정확히 하나**
 *   - 면적이나 층이 적혀 있고
 *   - 길이가 사람이 읽는 카드만 하다
 *
 * 이 조건은 요소마다 따로 검사하므로 페이지 구조가 어떻든 헤더나 지도가 끼어들 수 없다.
 * 카드 안에 더 작은 카드가 있으면 안쪽을 쓴다(바깥은 두 건을 묶은 것이다).
 *
 * ## 못 알아보면 아무것도 담지 않는다
 *
 * 예전에는 못 추려내면 원문을 그대로 담았다. "빈손보다 낫다" 고 생각했는데 틀렸다 —
 * 페이지 전체가 클립보드에 들어가고, 쓰는 사람은 그게 수집된 결과인 줄 안다. 못
 * 알아봤으면 **못 알아봤다고 말한다.** 조용히 쓰레기를 주는 것보다 낫다.
 *
 * ## 남기는 줄
 *
 * 단지명 / 가격 / 면적·층 / 날짜. 홍보문구·중개사명·협회·'매물 보러가기'·'관심매물'은
 * 버린다. 규칙은 backend `listing_parse.split_listings()` 와 같고, 추린 결과를 그대로
 * 파서에 넣었을 때 원문을 넣은 것과 **같은 답이 나오는지 대조했다**(4건, 면적·층·호가·
 * 날짜 전부 동일). 규칙을 고칠 일이 생기면 양쪽을 같이 고치고 다시 대조할 것.
 *
 * 날짜를 남기는 이유: 네이버는 **지금 올라와 있는 매물만** 보여 주므로 붙여넣은 시각으로는
 * 매물 간 시점을 가를 수 없다. 매물마다 다른 값은 이 날짜뿐이다. '확인매물 2026.09.23'
 * 도 '등록 2026.10.02' 도 같은 자리에 온다.
 */
(() => {
  /*
   * 안내에 버전을 적는다.
   *
   * 북마크는 한 번 등록하면 **내용이 갱신되지 않는다.** 코드를 고쳐도 사용자가 다시
   * 끌어다 놓기 전까지는 옛 코드가 돈다. 그런데 둘 다 조용히 동작해서, 옛 것이
   * 도는지 새 것이 도는지 알 방법이 없었다 — 실제로 '페이지 전체가 복사된다' 는
   * 신고가 들어왔을 때 옛 코드였는지 새 코드의 버그였는지 가릴 수가 없었다.
   *
   * 토스트에 버전을 적어 두면 한 번 눌러 보는 것으로 가려진다.
   */
  const VER = 'v3';

  /*
   * 담아 두는 자리에 **버전을 넣는다.**
   *
   * 안 넣었다가 당했다. 코드를 고쳐도 예전에 담아 둔 것은 그대로 남아 있고, 새 코드는
   * 거기에 덧붙이기만 한다. 그래서 v1 이 담아 둔 '페이지 전체 텍스트' 가 계속 앞에
   * 붙어 나왔다 — 새 코드가 멀쩡히 도는데도 결과는 예전과 똑같아 보였고, 어느 쪽이
   * 문제인지 가릴 수가 없었다.
   *
   * 키에 버전을 넣으면 버전이 바뀌는 순간 옛 버퍼는 보이지 않는다. 남은 옛 키는
   * 지워 둔다 — sessionStorage 는 탭마다 따로라 양이 크지 않지만, 남겨 둘 이유도 없다.
   */
  const KEY = 'aptPriceCollected.' + VER;
  try {
    for (const k of Object.keys(sessionStorage)) {
      if (k.indexOf('aptPriceCollected') === 0 && k !== KEY) sessionStorage.removeItem(k);
    }
  } catch (e) {
    /* 접근이 막힌 환경 — 어차피 아래에서 빈 배열로 시작한다 */
  }
  const PRICE_G = /^\s*(매매|전세|월세)\s*[\d억]/gm;
  const PRICE_1 = /^\s*(매매|전세|월세)\s*[\d억]/;
  const DATE = /(20\d\d|\d\d)\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2}/;
  const countOf = (t) => ((t || '').match(PRICE_G) || []).length;
  const idOf = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 120);

  const toast = (msg, bad) => {
    const d = document.createElement('div');
    d.textContent = msg + '  ·  ' + VER;
    d.style.cssText = [
      'position:fixed', 'left:50%', 'top:24px', 'transform:translateX(-50%)',
      'z-index:2147483647', 'padding:10px 16px', 'border-radius:8px',
      'font:600 13px/1.5 -apple-system,BlinkMacSystemFont,"Malgun Gothic",sans-serif',
      'color:#fff', 'box-shadow:0 4px 16px rgba(0,0,0,.25)', 'pointer-events:none',
      'white-space:pre-line', 'text-align:center', 'max-width:80vw',
      'background:' + (bad ? '#d14343' : '#2a78d6'),
    ].join(';');
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 3000);
  };

  /*
   * 중개사 메모는 **따옴표 줄로 감싸여** 온다. 실제 카드에서
   *
   *     아파트17평 (전용12)3/25층남서향
   *     "
   *     달리는 황소 입주가능,시에2대 지동사거리 접근 좋아 대중교통용이
   *     "
   *     집주인확인매물 2026.09.23
   *
   * 처럼 나온다. 이 울타리가 있어서 '어느 줄이 메모인가' 를 길이나 어휘로 추측할
   * 필요가 없다 — 추측했다면 중개사명('황소단지내공인중개사사무소')이나 홍보문구를
   * 섞었을 것이고, 그건 조용히 틀린다.
   *
   * 백엔드 `listing_parse.parse_memo()` 와 **같은 규칙**이다. 한쪽을 고치면 양쪽을
   * 같이 고칠 것. 울타리를 그대로 실어 보내므로 파서가 다시 읽을 수 있다.
   */
  const memoOf = (filled) => {
    const at = [];
    for (let i = 0; i < filled.length; i++) if (filled[i] === '\u0022') at.push(i);
    if (at.length < 2) return null;
    const body = filled.slice(at[0] + 1, at[1]).filter((t) => t);
    return body.length ? body.join(' ').slice(0, 300) : null;
  };

  // 카드 한 장을 네댓 줄로. 못 알아보면 null.
  const cardText = (raw) => {
    const lines = (raw || '').split('\n').map((l) => l.trim());
    const filled = lines.filter((l) => l);
    const pi = filled.findIndex((l) => PRICE_1.test(l));
    if (pi < 1) return null; // 가격 줄 위에 단지명이 있어야 한다

    const out = [filled[pi - 1], filled[pi]];

    // 면적·층이 든 줄. 보통 가격 바로 다음이지만 한두 줄 밀릴 때가 있다.
    for (let i = pi + 1; i < Math.min(pi + 4, filled.length); i++) {
      const t = filled[i];
      if (t.includes('㎡') || t.includes('평') || t.includes('층')) {
        out.push(t);
        break;
      }
    }
    if (out.length < 3) return null; // 면적도 층도 없으면 매물로 보지 않는다

    for (const t of filled) {
      if (DATE.test(t) && !PRICE_1.test(t)) {
        out.push(t);
        break;
      }
    }

    // 메모는 울타리째 싣는다. 파서가 그 울타리로 찾기 때문이다. 메모가 없는 카드도
    // 많다 — 중개사 여러 곳이 올린 매물은 접혀서 "중개사 4곳에서 등록했어요" 만
    // 나온다(실측 46건 중 메모가 붙은 것은 33건).
    const memo = memoOf(filled);
    if (memo) out.push('\u0022', memo, '\u0022');

    return out.join('\n');
  };

  /*
   * 카드 모으기.
   *
   * 가격 줄이 **정확히 하나**인 요소만 카드 후보다. 둘 이상이면 여러 건을 묶은
   * 바깥 상자이고, 영(0)이면 매물이 아니다. 이 검사는 요소마다 따로 하므로 헤더나
   * 지도가 끼어들 자리가 없다 — 페이지 전체가 복사되던 원인이 여기였다.
   */
  const collect = () => {
    const cands = [];
    for (const n of document.querySelectorAll('li,article,div,section')) {
      const t = n.innerText || '';
      if (!t || t.length > 1200) continue;
      if (countOf(t) !== 1) continue;
      if (!/[㎡평]|층/.test(t)) continue;
      cands.push(n);
    }
    // 겹친 후보는 안쪽만 남긴다. 바깥은 같은 카드를 한 번 더 감싼 것이다.
    const inner = cands.filter((n) => !cands.some((o) => o !== n && n.contains(o)));

    const seen = new Set();
    const out = [];
    for (const n of inner) {
      const t = cardText(n.innerText);
      if (!t) continue;
      const k = idOf(t);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(t);
    }
    return out;
  };

  const load = () => {
    try {
      return JSON.parse(sessionStorage.getItem(KEY) || '[]');
    } catch (e) {
      return [];
    }
  };
  const save = (a) => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(a));
    } catch (e) {
      /* 용량 초과 — 클립보드에는 이미 들어갔으므로 조용히 넘어간다 */
    }
  };

  // 클립보드. 북마클릿 클릭은 사용자 제스처라 writeText 가 허용된다.
  // 거부되는 환경(구형·권한 차단)을 위해 textarea 폴백을 둔다.
  const copy = (text) => {
    const fallback = () => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;left:-9999px;top:0';
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try {
        ok = document.execCommand('copy');
      } catch (e) {
        ok = false;
      }
      ta.remove();
      return ok;
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(() => true, fallback);
    }
    return Promise.resolve(fallback());
  };

  const items = load();
  const found = collect();

  // 매물이 안 보일 때 — 비우기를 여기 둔다. 북마클릿은 Shift+클릭 같은 수식키를
  // 받을 수 없어서, 초기화를 넣을 자리가 여기밖에 없다.
  if (!found.length) {
    if (!items.length) {
      toast('매물을 찾지 못했습니다.\n단지를 눌러 매물 목록을 띄운 뒤 다시 눌러 주세요.', true);
      return;
    }
    if (confirm(`매물이 보이지 않습니다.\n\n담아 둔 ${items.length}건을 비울까요?\n취소하면 그대로 다시 복사합니다.`)) {
      save([]);
      toast('비웠습니다.');
      return;
    }
    const all = items.join('\n\n');
    copy(all).then((ok) =>
      toast(ok ? `${items.length}건 다시 복사했습니다.` : '복사하지 못했습니다.', !ok),
    );
    return;
  }

  const have = new Set(items.map(idOf));
  const added = found.filter((t) => !have.has(idOf(t)));
  const merged = items.concat(added);
  save(merged);

  const all = merged.join('\n\n');
  copy(all).then((ok) => {
    if (!ok) return toast('클립보드에 넣지 못했습니다.', true);
    const head = added.length
      ? `${added.length}건 담았습니다.`
      : '이미 담은 매물입니다.';
    toast(`${head}\n모두 ${merged.length}건 복사됨`);
  });
})();
