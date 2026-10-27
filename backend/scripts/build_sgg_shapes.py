"""경기 남부 시군구 경계를 화면용 SVG 경로로 만든다 — 가격 분석의 시군구 지도.

사용법:
    python -m scripts.build_sgg_shapes <행정동.geojson>

입력은 vuski/admdongkor 의 행정동 경계(통계청 경계를 버전별로 정리한 것)다.
    https://github.com/vuski/admdongkor  →  ver<날짜>/HangJeongDong_ver<날짜>.geojson
출력은 `frontend/src/topics/sgg_shapes.json` 하나다. 커밋해 두고 화면은 그것만 읽는다 —
정적 사이트에서도 돌아야 하고, 35MB 원본을 매번 받을 이유가 없다.

## 왜 행정동을 직접 녹이나

시군구 경계 파일은 대부분 화성시 분구(2026-02, 41591~41597) 이전 것이다. 행정동 경계는
분기마다 새 버전이 나와 분구가 반영돼 있으므로 그것을 시군구 코드(`sgg`)로 묶어 녹인다.
shapely 없이 녹인다(이 저장소는 그것 하나 때문에 GEOS 를 들이지 않는다): 같은 시군구 안
두 행정동이 공유하는 변은 서로 반대 방향으로 두 번 나오므로, 두 번 나온 변을 지우면 바깥
윤곽만 남는다.

## 단순화는 이웃과 같은 선을 쓴다

시군구마다 따로 Douglas–Peucker 를 돌리면 이웃끼리 경계가 다르게 깎여 틈과 겹침이 생긴다.
그래서 윤곽을 **이웃이 바뀌는 점에서 끊어 호(arc)로 만들고**, 호를 정해진 방향으로 한 번만
단순화해 양쪽이 같은 결과를 쓴다.

## 검사

조용히 틀리는 것을 막으려고 매번 확인한다 — 대상 17곳이 전부 있나, 이름이 `molit.DISTRICTS`
와 맞나, 녹인 윤곽이 닫혀 있나, 이웃 둘이 공유하는 호가 양쪽에서 같은 점열인가.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.molit import DISTRICTS  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "topics" / "sgg_shapes.json"
WIDTH = 1000  # viewBox 폭. 높이는 위도 범위에서 나온다
TOL = 1.4  # 단순화 허용 오차(viewBox 단위). 카드에서는 300px 안팎이라 0.4px 쯤이다
MIN_ISLAND = 40.0  # 이보다 작은 섬(viewBox 면적)은 버린다 — 카드에서는 점으로도 안 보인다


def _rings(geom: dict):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            yield [(round(x, 6), round(y, 6)) for x, y in ring]


def dissolve(rings: list[list[tuple]]) -> list[tuple]:
    """방향 있는 변 목록 → 두 번 나온 변(내부 경계)을 뺀 나머지."""
    count: dict[frozenset, int] = defaultdict(int)
    edges = []
    for r in rings:
        for a, b in zip(r, r[1:]):
            if a == b:
                continue
            edges.append((a, b))
            count[frozenset((a, b))] += 1
    return [(a, b) for a, b in edges if count[frozenset((a, b))] == 1]


def chain(edges: list[tuple]) -> list[list[tuple]]:
    """변을 이어 닫힌 고리로. 한 점에서 갈래가 둘 이상이면(꼭짓점만 닿는 두 조각) 아무 쪽이나
    고른다 — 그래도 고리는 전부 닫힌다."""
    nxt: dict[tuple, list[tuple]] = defaultdict(list)
    for a, b in edges:
        nxt[a].append(b)
    rings = []
    while nxt:
        start = next(iter(nxt))
        ring = [start]
        cur = start
        while True:
            outs = nxt.get(cur)
            if not outs:
                raise SystemExit(f"[X] 윤곽이 닫히지 않습니다 — {cur} 에서 끊김")
            b = outs.pop()
            if not outs:
                del nxt[cur]
            ring.append(b)
            cur = b
            if cur == start:
                break
        rings.append(ring)
    return rings


def _seg_dist(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def dp(pts: list[tuple], tol: float) -> list[tuple]:
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        best, k = -1.0, -1
        for m in range(i + 1, j):
            d = _seg_dist(pts[m], pts[i], pts[j])
            if d > best:
                best, k = d, m
        if best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, f in zip(pts, keep) if f]


def area(ring: list[tuple]) -> float:
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))


def label_point(rings: list[list[tuple]]) -> tuple[float, float]:
    """가장 큰 고리 안에서 경계와 가장 먼 점(격자 탐색). 무게중심은 오목한 모양(화성 서쪽
    해안)에서 바깥으로 나간다."""
    ring = max(rings, key=lambda r: abs(area(r)))
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    best, at = -1.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    n = 40
    for i in range(1, n):
        for j in range(1, n):
            p = (min(xs) + (max(xs) - min(xs)) * i / n, min(ys) + (max(ys) - min(ys)) * j / n)
            if not inside(p, ring):
                continue
            d = min(_seg_dist(p, a, b) for a, b in zip(ring, ring[1:]))
            if d > best:
                best, at = d, p
    return at


def inside(p, ring) -> bool:
    x, y = p
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def main(src: str) -> None:
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    by_sgg: dict[str, list] = defaultdict(list)
    names: dict[str, str] = {}
    for f in data["features"]:
        p = f["properties"]
        if p["sgg"] in DISTRICTS:
            by_sgg[p["sgg"]].extend(_rings(f["geometry"]))
            names[p["sgg"]] = p["sggnm"]

    missing = sorted(set(DISTRICTS) - set(by_sgg))
    if missing:
        raise SystemExit(f"[X] 경계 파일에 없는 시군구: {missing} — 분구 이전 버전이 아닌지 보세요")
    for cd, nm in names.items():
        if nm.replace(" ", "") != DISTRICTS[cd].replace(" ", ""):
            raise SystemExit(f"[X] {cd} 이름이 다릅니다 — 경계 '{nm}' · molit '{DISTRICTS[cd]}'")

    # 위경도 → viewBox. 이 넓이(위도 0.4도)에서는 등장방형에 cos(위도)만 곱하면 충분하다.
    allpts = [pt for rs in by_sgg.values() for r in rs for pt in r]
    lon0, lon1 = min(p[0] for p in allpts), max(p[0] for p in allpts)
    lat0, lat1 = min(p[1] for p in allpts), max(p[1] for p in allpts)
    kx = math.cos(math.radians((lat0 + lat1) / 2))
    s = WIDTH / ((lon1 - lon0) * kx)
    height = (lat1 - lat0) * s

    def proj(p):
        return ((p[0] - lon0) * kx * s, (lat1 - p[1]) * s)

    # 녹인 윤곽(위경도 그대로 — 변 짝 맞추기는 반올림한 원좌표로 해야 정확하다)
    outlines = {cd: chain(dissolve(rs)) for cd, rs in by_sgg.items()}

    # 변마다 반대편 주인. 없으면 바깥(대상 밖 시군구나 바다)이다.
    owner: dict[tuple, str] = {}
    for cd, rings in outlines.items():
        for r in rings:
            for a, b in zip(r, r[1:]):
                owner[(a, b)] = cd

    def nb(a, b):
        return owner.get((b, a))

    # 호로 자르고 호마다 한 번만 단순화. 열쇠는 방향 없는 (이웃 쌍, 시작·끝) 이다.
    simplified: dict[tuple, list[tuple]] = {}

    def simplify_arc(pts: list[tuple]) -> list[tuple]:
        fwd = tuple(pts)
        rev = tuple(reversed(pts))
        key = min(fwd, rev)
        if key not in simplified:
            simplified[key] = dp([proj(p) for p in key], TOL)
        out = simplified[key]
        return out if key == fwd else list(reversed(out))

    items = []
    for cd in sorted(outlines):
        parts = []
        for r in outlines[cd]:
            if abs(area([proj(p) for p in r])) < MIN_ISLAND:
                continue
            seq = r[:-1]
            # 이웃이 바뀌는 점에서 시작하도록 돌린다(바뀌는 점이 없으면 고리 전체가 한 호).
            tags = [nb(seq[i], seq[(i + 1) % len(seq)]) for i in range(len(seq))]
            cuts = [i for i in range(len(seq)) if tags[i] != tags[i - 1]]
            if not cuts:
                pts = simplify_arc(r)
            else:
                k = cuts[0]
                seq = seq[k:] + seq[:k]
                tags = tags[k:] + tags[:k]
                cuts = [i for i in range(len(seq)) if tags[i] != tags[i - 1]] + [len(seq)]
                pts = []
                for i, j in zip(cuts, cuts[1:]):
                    arc = seq[i : j + 1] if j < len(seq) else seq[i:] + [seq[0]]
                    sp = simplify_arc(arc)
                    pts.extend(sp if not pts else sp[1:])
            if len(pts) >= 4:
                parts.append(pts)
        if not parts:
            raise SystemExit(f"[X] {cd} 윤곽이 비었습니다")
        lx, ly = label_point(parts)
        d = " ".join(
            "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts[:-1]) + "Z" for pts in parts
        )
        items.append({
            "sgg_cd": cd,
            "name": DISTRICTS[cd],
            "short": DISTRICTS[cd].split()[-1],
            "d": d,
            "lx": round(lx, 1),
            "ly": round(ly, 1),
        })
        print(f"  {cd} {DISTRICTS[cd]:<10} 고리 {len(parts)} · 점 {sum(map(len, parts))}")

    # 공유 호가 양쪽에서 같은지 — simplify_arc 가 같은 열쇠를 쓰면 성립한다. 그래도 직접 센다.
    shared = sum(1 for (a, b), cd in owner.items() if nb(a, b))
    if shared == 0:
        raise SystemExit("[X] 이웃과 공유하는 변이 하나도 없습니다 — 좌표가 어긋난 원본인지 보세요")

    out = {
        "source": Path(src).name,
        "viewBox": f"0 0 {WIDTH} {height:.0f}",
        "items": items,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  공유 변 {shared} · {OUT.relative_to(OUT.parents[2]).as_posix()} {OUT.stat().st_size / 1024:.1f}KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
