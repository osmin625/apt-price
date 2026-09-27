"""헤도닉 적합 결과를 API 페이로드로 조립한다.

hedonic.py 는 통계만 하고, 이 모듈이 화면이 필요로 하는 모양으로 바꾼다:
지도 마커, 등가격 링 반경, 합성 데이터의 참값 곡선 오버레이.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import pickle
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select

from .. import pricing
from ..config import BASE_DIR
from ..models import Complex, ComplexDong, ComplexStation, Station, Trade
from . import fit_worker, hedonic

TRUTH_PATH = BASE_DIR / "data" / "seed_truth.json"
RING_LEVELS_PCT = (-5.0, -10.0, -15.0, -20.0)

# 적합 결과 캐시. **여러 칸이 필요하다** — 탭마다 요청하는 기간이 다르기 때문이다
# (시장 분석 12개월, 매물 분석 24개월). 한 칸만 두면 탭을 오갈 때마다 캐시가 어긋나
# 13초짜리 재적합이 매번 돈다. 간단한 LRU 로 둔다.
log = logging.getLogger(__name__)

CACHE_SIZE = 4
_cache: "OrderedDict[tuple, dict]" = OrderedDict()


def _cache_key(db, months: int, spec: str) -> tuple:
    # 거래가 추가되면 자동으로 무효화된다.
    stamp = db.execute(select(func.max(Trade.id), func.count(Trade.id))).one()
    return (months, spec, stamp[0], stamp[1])


def load_truth() -> dict | None:
    if not TRUTH_PATH.exists():
        return None
    try:
        return json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _truth_curve(truth: dict, xs: list[float], x_ref: float) -> list[float]:
    """참 도보 곡선을 모델 곡선과 같은 '기준점 대비 %' 로 변환."""
    lam = truth["walk_semi_elast"]
    knee = truth["walk_flatten_after"]
    ratio = truth["walk_flatten_ratio"]
    cap = pricing.WALK_CAP_MIN

    def eff(w: float) -> float:
        w = min(w, cap)
        return lam * w if w <= knee else lam * knee + lam * ratio * (w - knee)

    base = eff(x_ref)
    return [round((math.exp(eff(x) - base) - 1) * 100, 3) for x in xs]


# 적합 결과를 디스크에도 둔다.
#
# 메모리 캐시는 프로세스가 죽으면 같이 죽는다. `--reload` 는 파일을 저장할 때마다
# 서버를 다시 띄우므로, 개발 중에는 거리 모델 탭을 열 때마다 처음부터 다시 적합했다.
# 배포에서도 재시작·스케일아웃마다 첫 방문자가 그 값을 치른다.
#
# 적합은 **데이터와 코드만의 함수**다. 같은 거래에 같은 코드면 결과가 같으므로,
# 그 둘을 키에 넣으면 디스크에 두고 재사용해도 안전하다.
#
#   - 데이터: 이미 메모리 캐시 키가 쓰는 (최대 거래 id, 거래 수)
#   - 코드: 모델을 만드는 모듈들의 소스 해시. 버전 상수를 손으로 올리는 방식은
#     언젠가 올리는 것을 잊는다. 소스가 바뀌면 자동으로 키가 달라지게 한다.
FIT_CACHE_DIR = BASE_DIR / "data" / "fitcache"
FIT_CACHE_KEEP = 8
# 디스크 캐시를 끄는 탈출구. 모델을 고치며 결과를 계속 비교할 때 쓴다.
FIT_CACHE_OFF = os.environ.get("FIT_CACHE", "1").strip() in {"0", "false", "no"}


@lru_cache(maxsize=1)
def _code_fingerprint() -> str:
    """적합 결과를 좌우하는 모듈들의 소스 해시."""
    h = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for rel in ("hedonic.py", "model_view.py", "../pricing.py"):
        try:
            h.update((here / rel).resolve().read_bytes())
        except OSError:
            return "nofingerprint"
    return h.hexdigest()[:16]


def _disk_path(key: tuple) -> Path:
    name = hashlib.sha256(
        (repr(key) + "|" + _code_fingerprint()).encode()
    ).hexdigest()[:32]
    return FIT_CACHE_DIR / f"{name}.pkl"


def _disk_load(key: tuple) -> dict | None:
    if FIT_CACHE_OFF:
        return None
    p = _disk_path(key)
    try:
        if not p.exists():
            return None
        with p.open("rb") as f:
            fit = pickle.load(f)
    except Exception:
        # 깨진 파일·다른 파이썬으로 만든 파일 등. 캐시 때문에 서비스가 죽으면 안 된다.
        log.warning("적합 디스크 캐시를 읽지 못했습니다: %s", p.name, exc_info=True)
        try:
            p.unlink()
        except OSError:
            pass
        return None
    return fit if isinstance(fit, dict) and "alpha" in fit else None


def _disk_store(key: tuple, fit: dict) -> None:
    if FIT_CACHE_OFF:
        return
    try:
        FIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # 파생 조회표(`_index`)는 저장하지 않는다 — 읽은 쪽에서 다시 만들면 된다.
        payload = {k: v for k, v in fit.items() if k != "_index"}
        tmp = _disk_path(key).with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(_disk_path(key))
        # 오래된 것부터 정리. 거래가 늘거나 코드가 바뀌면 키가 달라져 쌓이기만 한다.
        files = sorted(FIT_CACHE_DIR.glob("*.pkl"), key=lambda p: p.stat().st_mtime)
        for old in files[:-FIT_CACHE_KEEP]:
            old.unlink(missing_ok=True)
    except Exception:
        log.warning("적합 디스크 캐시를 쓰지 못했습니다", exc_info=True)


def get_fit(db, months: int = 24, spec: str = hedonic.DEFAULT_SPEC) -> dict:
    """적합 결과(캐시). alpha DataFrame 을 포함하므로 API 직렬화 전에 걸러야 한다."""
    key = _cache_key(db, months, spec)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    # 프로세스가 다시 떠도 같은 적합을 두 번 계산하지 않는다.
    cached = _disk_load(key)
    if cached is not None:
        _cache[key] = cached
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return cached

    # 적합은 별도 프로세스에서 돈다. 14초 동안 GIL 을 쥐고 있어서, 인프로세스로
    # 돌리면 그 사이 다른 요청이 전부 멈춘다(`fit_worker` 모듈 주석 참조).
    fit = fit_worker.run(months, spec, key)

    # 참값 오버레이는 **실제로 합성 데이터일 때만** 의미가 있다. seed_truth.json 은
    # 시드를 한 번이라도 돌렸으면 남아 있으므로, 파일 존재가 아니라 거래의 출처로
    # 판단한다. 실거래가에 시드 참값 곡선을 겹쳐 그리면 거짓말이 된다.
    seed_n = db.scalar(
        select(func.count()).select_from(Trade).where(Trade.source == "seed")
    ) or 0
    molit_n = db.scalar(
        select(func.count()).select_from(Trade).where(Trade.source == "molit")
    ) or 0
    truth = load_truth() if (seed_n > 0 and molit_n == 0) else None
    if truth:
        curve = fit["curves"]["walk_minutes"]
        curve["truth_pct"] = _truth_curve(truth, curve["x"], curve["reference_x"])
        fit["synthetic"] = True
        fit["truth"] = {
            "walk_semi_elast": truth["walk_semi_elast"],
            "gangnam_semi_elast": truth["gangnam_semi_elast"],
            "log_area_elast": truth["log_area_elast"],
            "monthly_drift_pct": truth["monthly_drift"] * 100,
            "note": "합성 데이터입니다. 점선은 시드가 심어둔 참값이며, "
                    "모델이 이를 되찾아오는지 비교할 수 있습니다.",
        }
    else:
        fit["synthetic"] = False

    # 어느 기간으로 적합했는지 결과에 박아 둔다. `peek_fit` 으로 집어 간 쪽이
    # '이 값은 최근 N개월 적합에서 나왔다' 고 화면에 밝힐 수 있어야 한다.
    fit["months"] = months
    _disk_store(key, fit)
    _cache[key] = fit
    _cache.move_to_end(key)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)  # 가장 오래 안 쓴 것부터 버린다
    return fit


# alpha 는 DataFrame, dong_effects 는 (단지,동) 튜플 키 dict 라 그대로는 직렬화되지 않는다.
_NON_JSON = ("alpha", "residuals", "dong_effects")


def peek_fit(
    db, months: int | None = None, spec: str = hedonic.DEFAULT_SPEC
) -> dict | None:
    """**이미 계산된** 적합만 돌려준다. 없으면 None — 새로 돌리지 않는다.

    가벼운 엔드포인트가 십수 초짜리 적합을 기다리게 만들면 안 되므로, 캐시에 있는
    것만 쓰고 없으면 그 정보를 빼고 응답한다.

    ## months 를 주면 그것부터 찾는다

    예전에는 인자 없이 **캐시의 가장 최근 것**을 그냥 돌려줬다. 동 프리미엄처럼
    '있으면 좋은' 보조 정보에만 쓸 때는 기간이 좀 달라도 상관없었다.

    그런데 지금은 여기서 나온 적합이 **요인 기준 적정가 전체**를 만든다. 그래서
    같은 매물을 같은 조건으로 조회해도 캐시에 마지막으로 들어간 것이 무엇이냐에 따라
    답이 달라졌다 — 실측으로 요인 적정가가 7.03억 ↔ 7.17억(2%)로 갈렸다. 시장 분석
    탭에서 기간을 바꾸고 순위표로 돌아오면 숫자가 변하는 셈이다.

    요청한 기간의 적합이 캐시에 있으면 그것을 쓴다. 없으면 종전처럼 가장 최근 것을
    주되, 호출한 쪽이 **무엇을 썼는지 화면에 밝힐 수 있도록** `fit["months"]` 를
    함께 읽어 가도록 한다. 기다리지 않는다는 성질은 그대로다.
    """
    if not _cache:
        return None
    if months is not None:
        for key, fit in _cache.items():
            if key[0] == months and key[1] == spec:
                return fit
    return next(reversed(_cache.values()), None)


def fit_payload(fit: dict) -> dict:
    """API 응답 — DataFrame 과 내부 객체를 제외한 순수 JSON.

    ## 이름 목록만으로는 못 막는다

    적합 dict 는 캐시에 오래 살아 있고, 계산하는 쪽이 파생값을 여기에 붙인다.
    `fit_index` 가 붙이는 `_index` 가 그랬다. 이름 목록(`_NON_JSON`)에 없으니
    그대로 응답에 실렸고, 그 안의 `log_households`·`dong_walk_mean` 은 세대수나 동
    좌표가 없는 단지에서 NaN 이라 JSON 인코딩이 터졌다(500).

    고약한 점은 **두 번째 요청부터** 터진다는 것이다. 거리 모델을 처음 열 때는
    `_index` 가 아직 없어서 멀쩡하고, 매물 분석이나 순위가 같은 적합을 한 번 집어
    가면 그때 붙는다. 그래서 '두 번째로 불러올 때 500' 이라는 모양이 된다.

    이름을 하나 더 적는 것으로 끝낼 수도 있지만 다음에 또 붙으면 같은 일이 난다.
    그래서 **규칙**으로 바꾼다 — `_` 로 시작하는 키는 내부용이라 내보내지 않는다.
    """
    return {
        k: v for k, v in fit.items()
        if k not in _NON_JSON and not k.startswith("_")
    }


def detour_stats(db) -> dict:
    """관측된 우회율과 보행 속도. 도보 '분' 을 지도상 '반경' 으로 바꿀 때 쓴다."""
    ratios, paces = [], []
    for cs in db.execute(select(ComplexStation)).scalars().all():
        if not cs.walk_distance_m or not cs.walk_seconds or not cs.straight_distance_m:
            continue
        if cs.straight_distance_m > 0:
            ratios.append(cs.walk_distance_m / cs.straight_distance_m)
        if cs.walk_seconds > 0:
            paces.append(cs.walk_distance_m / (cs.walk_seconds / 60.0))
    ratios.sort()
    paces.sort()
    return {
        "detour_ratio": ratios[len(ratios) // 2] if ratios else pricing.WALK_DETOUR_FACTOR,
        "meters_per_min": paces[len(paces) // 2] if paces else pricing.WALK_METERS_PER_MIN,
        "n": len(ratios),
    }


def rings(fit: dict, stats: dict) -> list[dict]:
    """등가격 링 — 적합 곡선이 -5/-10/-15/-20% 를 지나는 지점의 지도 반경(m).

    station_band 의 임의적인 400/800/1200m 링을 모델이 유도한 등고선으로 대체한다.
    곡선은 도보 '분' 단위이므로 관측된 보행 속도와 우회율로 직선 반경으로 되돌린다.
    """
    curve = fit["curves"]["walk_minutes"]
    xs, ys = curve["x"], curve["fit_pct"]
    pace = stats["meters_per_min"]
    detour = max(stats["detour_ratio"], 1e-6)

    out = []
    for level in RING_LEVELS_PCT:
        hit = None
        for i in range(1, len(xs)):
            y0, y1 = ys[i - 1], ys[i]
            if (y0 - level) * (y1 - level) <= 0 and y0 != y1:
                t = (level - y0) / (y1 - y0)
                hit = xs[i - 1] + t * (xs[i] - xs[i - 1])
                break
        if hit is None:
            continue
        out.append(
            {
                "pct": level,
                "walk_min": round(hit, 1),
                "radius_m": round(hit * pace / detour, 0),
                "label": f"{level:+.0f}% · 도보 {hit:.0f}분",
            }
        )
    return out


def _curve_at(curve: dict, w: float) -> float:
    """곡선을 도보 w분에서 선형보간 — 기준점 대비 %."""
    xs, ys = curve["x"], curve["fit_pct"]
    if w <= xs[0]:
        return ys[0]
    if w >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if w <= xs[i]:
            t = (w - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def map_payload(db, fit: dict) -> dict:
    """지도 전용 경량 페이로드. /api/complexes 보다 가볍게 — 팬 할 때마다 불린다."""
    alpha = fit["alpha"]
    resid = {r["complex_id"]: r for r in fit["residuals"]}
    curve = fit["curves"]["walk_minutes"]

    stations = {s.id: s for s in db.execute(select(Station)).scalars().all()}
    complexes = {c.id: c for c in db.execute(select(Complex)).scalars().all()}

    # 한 단지에 여러 쌍이 있으면 tmap 이 하나라도 있으면 tmap 으로 본다.
    walk_sources: dict[int, str] = {}
    for cs in db.execute(select(ComplexStation)).scalars().all():
        if walk_sources.get(cs.complex_id) != "tmap":
            walk_sources[cs.complex_id] = cs.walk_source

    items = []
    lats, lngs = [], []
    for _, row in alpha.iterrows():
        cid = int(row["complex_id"])
        cx = complexes.get(cid)
        if cx is None or cx.lat is None:
            continue
        r = resid.get(cid, {})
        near = stations.get(cx.nearest_station_id)
        best = stations.get(cx.best_access_station_id)
        n = int(row["trade_count"])

        items.append(
            {
                "id": cid,
                "name": row["complex_name"],
                "lat": cx.lat,
                "lng": cx.lng,
                "umd_nm": cx.umd_nm,
                "sgg_cd": cx.sgg_cd,
                "sgg_name": cx.sgg_name,
                "build_year": cx.build_year,
                "trade_count": n,
                "ppp": round(float(row["ppp_median"]), 1),
                "normalized_ppp": round(math.exp(float(row["alpha"])), 1),
                "predicted_ppp": (
                    round(math.exp(r["predicted_alpha"]), 1) if "predicted_alpha" in r else None
                ),
                "walk_min": round(float(row["walk_min"]), 1),
                "walk_distance_m": cx.walk_distance_m,
                "walk_source": walk_sources.get(cid),
                "station_id": cx.nearest_station_id,
                "station_name": near.name if near else cx.station_name,
                "station_line": near.line if near else cx.station_line,
                "best_station_id": cx.best_access_station_id,
                "best_station_name": best.name if best else None,
                "total_access_min": cx.total_access_min,
                "residual_pct": r.get("residual_pct"),
                "residual_shrunk_pct": r.get("residual_shrunk_pct"),
                "residual_z": r.get("residual_z"),
                # 부분잔차 — 도보거리 효과만 남기고 나머지(면적·층·연식·강남·구)를
                # 걷어낸 값. 이것이 있어야 산점도의 점과 적합 곡선을 같은 축에서
                # 비교할 수 있다. 원자료를 그냥 흩뿌리면 다른 요인들 때문에
                # 곡선과 전혀 맞지 않아 보인다.
                "partial_pct": (
                    round(
                        (
                            math.exp(
                                r["residual"]
                                + math.log1p(_curve_at(curve, float(row["walk_min"])) / 100.0)
                            )
                            - 1
                        )
                        * 100,
                        2,
                    )
                    if "residual" in r
                    else None
                ),
                # 기존 매물 진단 탭과 같은 신뢰도 어휘를 쓴다.
                "confidence": "높음" if n >= 10 else "보통" if n >= 5 else "낮음",
            }
        )
        lats.append(cx.lat)
        lngs.append(cx.lng)

    def span(vals: list[float], key: str) -> dict:
        xs = sorted(v for v in vals if v is not None)
        if not xs:
            return {}
        return {
            "min": round(xs[0], 1),
            "p50": round(xs[len(xs) // 2], 1),
            "max": round(xs[-1], 1),
            "key": key,
        }

    return {
        "count": len(items),
        "bounds": (
            {"sw": [min(lats), min(lngs)], "ne": [max(lats), max(lngs)]} if lats else None
        ),
        "metrics": {
            "normalized_ppp": {
                "label": "보정 평당가",
                "unit": "만원/평",
                "scale": "sequential",
                "note": "전용 84㎡ · 중층 · 최신월 기준으로 환산한 값",
                **span([i["normalized_ppp"] for i in items], "normalized_ppp"),
            },
            "ppp": {
                "label": "중앙 평당가",
                "unit": "만원/평",
                "scale": "sequential",
                "note": "보정하지 않은 실제 거래 중앙값",
                **span([i["ppp"] for i in items], "ppp"),
            },
            "residual_shrunk_pct": {
                "label": "모델 잔차",
                "unit": "%",
                "scale": "diverging",
                "center": 0,
                "note": "도보거리·강남접근성·면적·층·연식·구로 설명되지 않는 부분. "
                        "학군·브랜드·조망·재건축 기대가 여기 섞여 있다.",
                **span([i["residual_shrunk_pct"] for i in items], "residual_shrunk_pct"),
            },
        },
        "items": items,
    }


# 요인별 보정계수를 읽을 기준점. 전형적인 수원 아파트 한 채를 상정한다.
# 모든 %는 "이 기준 대비 얼마나 비싼가"로 읽힌다.
FACTOR_REF = {
    "area_m2": 84.0,
    "walk_min": 10.0,
    "gangnam_min": 55.0,
    "age": 15.0,
    "households": 800.0,
}
_AREA_POINTS = [(39, "39㎡"), (49, "49㎡"), (59, "59㎡"), (74, "74㎡"),
                (84, "84㎡"), (101, "101㎡"), (114, "114㎡"), (135, "135㎡")]
_WALK_POINTS = [(2, "도보 2분"), (5, "도보 5분"), (10, "도보 10분"),
                (15, "도보 15분"), (20, "도보 20분"), (30, "도보 30분")]
_GANGNAM_POINTS = [(30, "30분"), (35, "35분"), (45, "45분"),
                   (55, "55분"), (60, "60분"), (65, "65분")]
_AGE_POINTS = [(1, "1년"), (5, "5년"), (10, "10년"), (15, "15년"),
               (20, "20년"), (30, "30년"), (40, "40년")]
_HH_POINTS = [(150, "150세대"), (300, "300세대"), (600, "600세대"),
              (800, "800세대"), (1200, "1200세대"), (2000, "2000세대"), (3000, "3000세대")]

# 연속 요인은 대표 지점(막대)뿐 아니라 **조밀한 곡선**으로도 보낸다.
# 막대만 보면 log·2차항·스플라인의 굽은 모양이 보이지 않는다.
#
# 아래는 **데이터가 없을 때의 대비책**이다. 실제 범위는 적합이 돌려준 관측 분포
# (`fit["var_range"]`, p1~p99)에서 가져온다. 범위를 코드에 박아 두면 대상 지역을
# 넓혔을 때 곡선이 어긋난다 — 수원만 볼 때 강남 소요시간은 30~65분이었지만 경기
# 남부로 넓히면 23~78분이라, 박아 둔 (28, 68)은 양쪽 끝을 잘라 먹는다.
_CURVE_RANGE = {
    "area": (30.0, 140.0),
    "walk": (1.0, 30.0),
    "gangnam": (28.0, 68.0),
    "age": (0.0, 45.0),
    "households": (100.0, 3500.0),
}
# 요인 키 → 적합이 쓰는 분포 이름
_RANGE_VAR = {
    "area": "area_m2", "walk": "walk_min", "gangnam": "gangnam_min",
    "age": "age", "households": "households",
}
_CURVE_N = 120


def _ranges_from(fit: dict) -> dict[str, tuple[float, float]]:
    """관측 분포로 곡선 범위를 정한다. 없으면 기존 상수를 쓴다."""
    vr = fit.get("var_range") or {}
    out = dict(_CURVE_RANGE)
    for key, var in _RANGE_VAR.items():
        d = vr.get(var)
        if not d:
            continue
        lo, hi = float(d["lo"]), float(d["hi"])
        if hi > lo:
            out[key] = (lo, hi)
    return out


def _points_in(points, lo: float, hi: float, unit: str, vr: dict | None):
    """막대로 찍을 대표 지점. 관측 범위 밖은 빼고, 모자라면 분위수로 채운다.

    대표 지점을 코드에 박아 두면 두 방향으로 틀린다. 관측이 없는 지점(도보 2분짜리
    단지가 없는 지역)에 막대가 서고, 관측이 있는 구간(도보 40분)은 통째로 빠진다.
    """
    kept = [(x, lbl) for x, lbl in points if lo <= x <= hi]
    if vr:
        # 사분위와 양 끝을 더해 실제 분포를 덮는다.
        for q in ("lo", "q1", "median", "q3", "hi"):
            x = float(vr[q])
            if any(abs(x - px) < max(1.0, abs(x) * 0.04) for px, _ in kept):
                continue
            lbl = f"{x:,.0f}{unit}" if abs(x) >= 10 else f"{x:,.1f}{unit}"
            kept.append((round(x, 1), lbl))
    return sorted(kept, key=lambda p: p[0])


def _curve(key: str, fn) -> dict:
    """[lo, hi] 를 촘촘히 훑어 기준 대비 %를 만든다."""
    lo, hi = _CURVE_RANGE[key]
    step = (hi - lo) / (_CURVE_N - 1)
    xs = [lo + step * i for i in range(_CURVE_N)]
    return {
        "x": [round(x, 2) for x in xs],
        "pct": [_pct(fn(x)) for x in xs],
    }


def _pct(delta_log: float) -> float:
    return round((math.exp(delta_log) - 1) * 100, 2)


def _per_unit(label: str, delta_log: float, se_log: float | None = None) -> dict:
    """'단위 하나 움직이면 몇 %' 를 **이미 환산해서** 보낸다.

    계수를 날것으로 보내면 프론트가 단위를 알아야 한다. log(면적) 계수는
    탄력도라 exp(coef)-1 이 아무 의미가 없는데, 화면에서 그렇게 계산해
    '-33%' 라는 틀린 숫자가 나왔다. 단위를 아는 쪽에서 환산해 보내는 게 맞다.
    """
    out = {"label": label, "pct": round((math.exp(delta_log) - 1) * 100, 2)}
    if se_log is not None:
        out["se_pct"] = round(se_log * 100, 2)
    return out


def _eval_spline(coefs: list[float], knots, x: float) -> float:
    """적합된 스플라인을 한 점에서 평가한다. 매듭이 없으면 단순 선형."""
    if not knots:
        return coefs[0] * x
    basis = pricing.rcs_basis(x, knots)
    return sum(c * b for c, b in zip(coefs, basis))


def _factor(
    key: str, label: str, unit: str, x_label: str, ref_x: float,
    to_model_x, coefs, knots, lin: dict | None, points, note: str,
    per_unit: dict | None = None, span: tuple[float, float] | None = None,
) -> dict:
    """연속 요인 하나를 곡선·점·선형비교선·판정으로 조립한다.

    `to_model_x` 는 화면 x(㎡, 분, 세대수)를 모델이 쓰는 값(log 면적 등)으로
    바꾸는 함수다. 화면은 사람이 읽는 단위로, 평가는 모델 단위로 해야 한다.
    """
    ref_m = to_model_x(ref_x)
    base = _eval_spline(coefs, knots, ref_m)

    def at(x: float) -> float:
        return _eval_spline(coefs, knots, to_model_x(x)) - base

    # 범위는 호출자가 적합의 관측 분포에서 뽑아 넘긴다. 상수는 대비책일 뿐이다.
    lo, hi = span or _CURVE_RANGE[key]
    step = (hi - lo) / (_CURVE_N - 1)
    xs = [lo + step * i for i in range(_CURVE_N)]

    out = {
        "key": key, "label": label, "unit": unit,
        "x_label": x_label, "ref_x": ref_x,
        "reference": f"{ref_x:,.0f}{unit}".replace(".0", ""),
        "note": note,
        "levels": [{"band": lbl, "x": x, "premium_pct": _pct(at(x))} for x, lbl in points],
        "curve": {"x": [round(x, 2) for x in xs], "pct": [_pct(at(x)) for x in xs]},
    }
    if per_unit:
        out["per_unit"] = per_unit

    if lin:
        out["linearity"] = {
            "testable": lin.get("testable", False),
            "nonlinear": lin.get("nonlinear"),
            "verdict": lin.get("verdict"),
            "p": lin.get("p"),
            "note": lin.get("note"),
        }
        # 비선형항을 뺀 제약 모델의 직선. 곡선과 겹쳐 그려 굽은 정도를 보여 준다.
        lc = lin.get("linear_coef")
        if lc is not None:
            lb = lc * ref_m
            out["linear_curve"] = {
                "x": out["curve"]["x"],
                "pct": [_pct(lc * to_model_x(x) - lb) for x in xs],
            }
    return out


# 단지 내 동 순위를 몇 개 구간으로 나눌지. 층 구간과 같은 눈금 수로 맞춘다.
_DONG_RANK_BANDS = (
    ("최고가 동", 1.00),
    ("상위 동", 0.75),
    ("중간 동", 0.50),
    ("하위 동", 0.25),
    ("최저가 동", 0.0),
)


def _dong_rank_levels(fit: dict) -> list[dict]:
    """동 프리미엄을 **단지 내 순위 구간**으로 묶는다.

    동 하나하나의 계수는 그 단지 안에서만 뜻이 있어서, 3,001개를 한 화면에 낼 수도
    없고 내 봐야 읽히지도 않는다. 대신 "같은 단지에서 상위 동이냐 하위 동이냐"로
    묶으면 층 구간과 같은 방식으로 읽힌다.

    동이 3개 미만인 단지는 뺀다 — 순위가 의미를 갖지 못한다.
    """
    effects = fit.get("dong_effects") or {}
    if not effects:
        return []

    by_complex: dict[int, list[dict]] = {}
    for (cid, _), v in effects.items():
        by_complex.setdefault(int(cid), []).append(v)

    buckets: dict[str, list[float]] = {name: [] for name, _ in _DONG_RANK_BANDS}
    n_complexes = 0
    for items in by_complex.values():
        if len(items) < 3:
            continue
        n_complexes += 1
        ranked = sorted(items, key=lambda v: v["coef"])
        last = len(ranked) - 1
        for i, v in enumerate(ranked):
            q = i / last if last else 0.5
            if i == last:
                name = "최고가 동"
            elif i == 0:
                name = "최저가 동"
            elif q >= 0.66:
                name = "상위 동"
            elif q >= 0.33:
                name = "중간 동"
            else:
                name = "하위 동"
            buckets[name].append(v["coef"])

    if n_complexes < 5:
        return []

    levels = []
    for name, _ in _DONG_RANK_BANDS:
        vals = buckets[name]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        levels.append({
            "band": name,
            "premium_pct": _pct(mean),
            "n": len(vals),
        })
    return levels


def factor_payload(fit: dict) -> dict:
    """모델 계수를 '기준 대비 %'로 환산한 요인별 보정계수.

    함수 형태를 미리 정하지 않는다. 연속 요인은 전부 제한 3차 스플라인으로
    유연하게 적합한 뒤 **비선형항이 유의한지 검정**해서, 선형인지 아닌지를
    데이터가 답하게 한다. 실제로 수원 데이터에서는 미리 정했던 형태가
    절반쯤 틀렸다 — 도보거리는 직선이었고 강남 접근성은 직선이 아니었다.
    """
    terms = {t["name"]: t for t in fit["terms"]}
    spans = _ranges_from(fit)
    vranges = fit.get("var_range") or {}
    knots = fit.get("knots") or {}
    sterms = fit.get("spline_terms") or {}
    lin = fit.get("linearity") or {}
    out: list[dict] = []

    def coefs_of(var: str) -> list[float] | None:
        names = sterms.get(var)
        if not names:
            return None
        got = [terms[n]["coef"] for n in names if n in terms]
        return got if len(got) == len(names) else None

    # 1) 층 — 범주형
    floors = [
        {"band": f["band"], "premium_pct": f["premium_pct"], "ci_pct": f.get("ci_pct")}
        for f in fit["stage1"]["floor_terms"]
    ]
    if floors:
        out.append({
            "key": "floor", "label": "층", "unit": "", "reference": "중층",
            "note": "단지·평형·시점 효과를 제거한 순수 층 효과.",
            "levels": floors,
        })

    # 2) 전용면적 — Stage 1. 매듭이 log 공간에 있으므로 x 를 log 로 바꿔 평가한다.
    al = fit["stage1"].get("area_linearity")
    if al and al.get("coefs"):
        ref = FACTOR_REF["area_m2"]
        lo, hi = spans["area"]
        out.append(_factor(
            "area", "전용면적", "㎡", "전용면적(㎡)", ref,
            lambda a: math.log(a / ref), al["coefs"], al.get("knots"), al,
            _points_in(_AREA_POINTS, lo, hi, "㎡", vranges.get("area_m2")),
            "평당가 기준이므로 '면적이 클수록 비싸다'가 아니라 "
            "'작을수록 평당 단가가 높다'로 읽어야 한다.",
            span=(lo, hi),
        ))

    # 3~6) Stage 2 연속 요인
    plan = [
        ("walk", "walk_min", "역까지 도보거리", "분", "역까지 도보(분)",
         FACTOR_REF["walk_min"], _WALK_POINTS,
         "구간으로 자르지 않고 연속 추정한 값.", lambda x: x),
        ("gangnam", "gangnam_min", "강남까지 전철", "분", "강남까지 전철(분)",
         FACTOR_REF["gangnam_min"], _GANGNAM_POINTS,
         "최적 접근역 기준. 노선 FE 를 함께 넣었으므로 '노선으로 설명되지 않는 "
         "이동시간 효과'로 읽어야 한다.", lambda x: x),
        ("age", "age", "연식", "년", "연식(년)",
         FACTOR_REF["age"], _AGE_POINTS,
         "노후 단지의 재건축 기대가 섞여 단순 감소가 아닐 수 있다.", lambda x: x),
        ("households", "log_households", "단지 규모(세대수)", "세대", "세대수",
         FACTOR_REF["households"], _HH_POINTS,
         "커뮤니티 시설·관리비 규모의 경제·거래 유동성이 함께 들어온다.",
         lambda n: math.log(n)),
    ]
    for key, var, label, unit, xlab, ref, points, note, fx in plan:
        cs = coefs_of(var)
        if cs is None:
            continue
        pu = None
        t = lin.get(var, {})
        if t.get("linear_coef") is not None:
            mult = math.log(2) if key == "households" else 1.0
            pu = _per_unit(
                "세대수 2배당" if key == "households" else ("1분당" if unit == "분" else "1년당"),
                t["linear_coef"] * mult,
                (t.get("linear_se") or 0) * mult or None,
            )
        lo, hi = spans[key]
        out.append(_factor(
            key, label, unit, xlab, ref, fx, cs, knots.get(var), t,
            _points_in(points, lo, hi, unit, vranges.get(_RANGE_VAR[key])),
            note, pu, span=(lo, hi),
        ))

    # 7) 동 위치 — 범주형. 동은 3,001개라 하나씩 낼 수 없으므로 **단지 안에서의
    # 순위**로 묶는다. 층을 1층/저층/중층/고층/최상층으로 묶는 것과 같은 발상이고,
    # "같은 단지에서 제일 좋은 동과 제일 나쁜 동이 몇 % 차이냐"가 바로 읽힌다.
    dp = fit.get("dong_premium") or {}
    if dp:
        if dp.get("detected"):
            out.append({
                "key": "dong", "label": "동 위치", "unit": "",
                "reference": "단지 내 중간 동",
                "note": (
                    "같은 단지·같은 평형 안에서 동에 따른 차이입니다. 역거리로 설명되는 "
                    f"부분은 이미 빠져 있습니다. τ={dp.get('tau_pct')}%."
                ),
                "levels": _dong_rank_levels(fit),
            })
        else:
            # 0짜리 막대 다섯 개를 그리면 '동은 가격과 무관' 으로 읽힌다. 실제로는
            # '이 표본으로는 잴 수 없다' 이므로, 그 말을 그대로 적는다.
            out.append({
                "key": "dong", "label": "동 위치", "unit": "",
                "reference": "단지 내 중간 동",
                "unresolved": (
                    f"검출되지 않았습니다 (τ={dp.get('tau_pct')}%, 검출 한계 약 "
                    f"{dp.get('detection_floor_pct')}%). 같은 단지·같은 평형끼리 비교한 "
                    f"동 {dp.get('n_dongs'):,}개에서 동에 따른 가격 차이는 잡음과 "
                    "구분되지 않습니다."
                ),
                "note": (
                    "단지 안에서만 비교하면 τ=2.5% 가 나오지만 그건 평형 교란입니다 — "
                    "40㎡가 두 동에만 있는 단지에서는 면적 곡선의 오차가 그 동들의 "
                    "'동 효과'로 둔갑합니다. 평형을 통제하면 사라집니다. "
                    "동 위치가 가격에 미치는 영향 중 이 표본에서 잡히는 경로는 "
                    "역까지 도보거리뿐입니다(위 '역까지 도보거리' 카드 참조). "
                    f"같은 평형을 나눠 갖는 동이 없어 비교가 불가능한 동 "
                    f"{dp.get('n_unidentified', 0):,}개는 제외했습니다."
                ),
                "levels": [],
            })

    # 8) 노선 — 범주형
    line_terms = [(n, t) for n, t in terms.items() if n.startswith("line_")]
    if line_terms:
        present = {n[5:] for n, _ in line_terms}
        base_line = next(
            (ln for ln in ("1호선", "수인분당선", "신분당선") if ln not in present), "기준 노선"
        )
        levels = [{"band": f"{base_line} (기준)", "premium_pct": 0.0}]
        levels += [
            {"band": n[5:], "premium_pct": _pct(t["coef"]), "p": t["p"]}
            for n, t in sorted(line_terms, key=lambda kv: kv[1]["coef"])
        ]
        out.append({
            "key": "line", "label": "지하철 노선", "unit": "", "reference": base_line,
            "note": "강남 소요시간을 이미 통제한 뒤 남는 노선 프리미엄입니다. "
                    "이동시간만으로 설명되지 않는 부분 — 노선이 지나는 지역의 "
                    "개발 수준·상권·학군이 여기 섞여 있습니다.",
            "levels": levels,
        })

    return {
        "spec": fit["spec"],
        "spec_label": fit["spec_label"],
        "n_obs": fit["n_obs"],
        "n_complexes": fit["n_complexes"],
        "reference": (
            f"전용 {FACTOR_REF['area_m2']:.0f}㎡ · 중층 · 최신월 · "
            f"도보 {FACTOR_REF['walk_min']:.0f}분 · 강남 {FACTOR_REF['gangnam_min']:.0f}분 · "
            f"연식 {FACTOR_REF['age']:.0f}년 · {FACTOR_REF['households']:.0f}세대"
        ),
        "note": (
            "각 요인을 기준값에서 움직였을 때 전용 평당가가 몇 % 달라지는지입니다. "
            "다른 요인은 모두 고정한 순효과입니다. 연속 요인은 형태를 미리 정하지 않고 "
            "스플라인으로 적합한 뒤 직선인지 아닌지를 검정했습니다."
        ),
        "factors": out,
    }


def fit_index(fit: dict) -> dict:
    """적합에서 **매번 다시 만들던 조회표**를 한 번만 만들어 들고 있는다.

    ## 왜

    `model_price` 는 매물 하나를 평가할 때마다 단지 전체를 훑어 조회표를 만들었다.

        rows = {int(r["complex_id"]): r for _, r in fit["alpha"].iterrows()}

    단지 하나를 꺼내려고 2,018곳을 도는 셈인데, `iterrows()` 는 행마다 Series 를
    새로 만들기까지 한다. 매물 56건을 평가하면 113,008번이 돌고, 프로파일에서
    순위 계산 16.7초 중 **12.8초**가 여기였다. 수원만 볼 때(497곳)는 4분의 1
    규모라 눈에 띄지 않았는데, 대상을 넓히자 드러났다.

    조회표는 적합이 바뀌지 않는 한 그대로다. 그래서 적합 dict 에 매달아 둔다 —
    적합 캐시(`_cache`)가 살아 있는 동안 같이 산다.

    `to_dict("records")` 로 만든 평범한 dict 를 돌려준다. 읽는 쪽은 `row["alpha"]`,
    `"dong_walk_mean" in row`, NaN 자기비교를 쓰는데 전부 dict 에서도 같게 동작한다.
    """
    idx = fit.get("_index")
    if idx is None:
        alpha = fit["alpha"]
        idx = {
            "alpha_rows": {
                int(r["complex_id"]): r for r in alpha.to_dict("records")
            },
            "resid": {r["complex_id"]: r for r in fit["residuals"]},
            "terms": {t["name"]: t for t in fit["terms"]},
            "floors": {
                f["band"]: f["coef"] for f in fit["stage1"]["floor_terms"]
            },
        }
        fit["_index"] = idx
    return idx


def model_price(db, fit: dict, side: dict) -> dict | None:
    """매물 하나의 **모델 기준 적정가**. 실거래 비교와는 다른 질문에 답한다.

    실거래 기준(`analysis.estimate_fair_price`)은 "그 단지 같은 평형이 얼마에 팔리나"를
    묻는다. 표본이 그 단지 안에 있으므로 학군·브랜드·재건축 기대가 전부 값에 포함된
    상태다. 재건축 기대가 잔뜩 낀 단지라도 "시세대로면 적정" 이 나온다.

    여기서는 **측정 가능한 요인만으로** 값을 다시 세운다.

    - **요인 기준**: Stage 2 가 역거리·강남접근성·연식·세대수·노선·자치구로 예측한
      단지 수준(predicted α̂)에서 출발. 그 단지의 관측되지 않은 프리미엄은 빼고,
      펀더멘털만으로 얼마여야 하는지를 낸다.
    - **시장 기준**: 실제 관측된 단지 수준(α̂_c)에서 출발. 단지 프리미엄을 인정한다.

    둘 다 α 는 `전용 84㎡ · 중층 · 최신월` 기준이므로, 여기에 이 매물의 면적·층·
    동 도보편차를 더해 해당 유닛으로 옮긴다.

    두 값의 차이가 곧 **단지 프리미엄**이다. 갈리는 것 자체가 정보다 — 요인 대비
    비싸지만 시세 대비 적정이면, 그 단지에 값이 붙어 있다는 뜻이다.
    """
    idx = fit_index(fit)
    cid = int(side["complex_id"])
    row = idx["alpha_rows"].get(cid)
    if row is None:
        return None

    resid = idx["resid"]
    terms = idx["terms"]
    knots = fit.get("knots") or {}
    sterms = fit.get("spline_terms") or {}
    floors = idx["floors"]
    area_lin = fit["stage1"].get("area_linearity") or {}

    cx = db.get(Complex, cid)
    area = float(side["exclusive_area"])
    floor = side.get("floor")
    band = pricing.floor_band(floor, cx.max_floor if cx else None)

    # α 기준점(전용 84㎡·중층)에서 이 유닛까지의 조정
    adj = 0.0
    parts = []
    if area_lin.get("coefs"):
        a = _eval_spline(
            area_lin["coefs"], area_lin.get("knots"),
            math.log(area / FACTOR_REF["area_m2"]),
        )
        adj += a
        parts.append({"key": "area", "label": f"전용 {area:g}㎡", "pct": _pct(a)})
    fb = floors.get(band, 0.0)
    adj += fb
    parts.append({"key": "floor", "label": f"{band}", "pct": _pct(fb)})

    dong, dong_walk = _dong_walk(db, cid, side.get("dong"))
    within = (fit.get("stage1") or {}).get("within_walk") or {}
    w_coef = float(within.get("coef") or 0.0)
    dmean = (
        float(row["dong_walk_mean"])
        if "dong_walk_mean" in row and row["dong_walk_mean"] == row["dong_walk_mean"]
        else None
    )
    if dong_walk is not None and dmean is not None and w_coef:
        dv = w_coef * (dong_walk - dmean)
        adj += dv
        parts.append({
            "key": "dong_walk",
            "label": f"{dong}동 도보 {dong_walk:.1f}분 (단지 평균 {dmean:.1f}분)",
            "pct": _pct(dv),
        })

    pred = resid.get(cid, {}).get("predicted_alpha")
    if pred is None:
        return None
    pyeong = pricing.to_pyeong(area)
    factor_ppp = math.exp(float(pred) + adj)
    market_ppp = math.exp(float(row["alpha"]) + adj)

    # 단지 수준을 만든 요인들 — 기준 단지 대비 기여. 시장 분석 탭과 같은 축이다.
    def spline_val(var: str, x: float) -> float:
        names = sterms.get(var)
        if not names:
            return 0.0
        cs = [terms[n]["coef"] for n in names if n in terms]
        if len(cs) != len(names):
            return 0.0
        return _eval_spline(cs, knots.get(var), x)

    complex_parts = []
    for key, var, label, unit, fmt_ in (
        ("walk", "walk_min", "역까지 도보", "분", "{:.1f}"),
        ("gangnam", "gangnam_min", "강남까지 전철", "분", "{:.0f}"),
        ("age", "age", "연식", "년", "{:.0f}"),
    ):
        v = float(row[var])
        d = spline_val(var, v) - spline_val(var, FACTOR_REF[var if var != "walk_min" else "walk_min"])
        complex_parts.append({
            "key": key, "label": label,
            "value": fmt_.format(v) + unit,
            "pct": _pct(d),
        })
    lh = row["log_households"]
    if lh == lh:
        d = spline_val("log_households", float(lh)) - spline_val(
            "log_households", math.log(FACTOR_REF["households"])
        )
        complex_parts.append({
            "key": "households", "label": "세대수",
            "value": f"{cx.household_count:,}세대" if cx and cx.household_count else "—",
            "pct": _pct(d),
        })
    lt = terms.get(f"line_{row['line']}")
    if lt:
        complex_parts.append({
            "key": "line", "label": "지하철 노선",
            "value": str(row["line"]), "pct": _pct(lt["coef"]),
        })

    return {
        "spec": fit["spec"],
        "factor_ppp": round(factor_ppp, 1),
        "factor_price": round(factor_ppp * pyeong),
        "market_ppp": round(market_ppp, 1),
        "market_price": round(market_ppp * pyeong),
        # 요인으로 설명되지 않고 그 단지에 붙어 있는 값. 축소(shrinkage)한 잔차다.
        "complex_premium_pct": resid.get(cid, {}).get("residual_shrunk_pct"),
        "unit_parts": parts,
        "complex_parts": complex_parts,
        "reference": fit["stage1"].get("reference"),
        "note": (
            "요인 기준은 역거리·강남접근성·연식·세대수·노선·자치구만으로 세운 값입니다. "
            "학군·브랜드·재건축 기대처럼 측정하지 않은 것은 빠져 있습니다. "
            "시장 기준은 그 단지가 실제로 거래되는 수준에서 출발합니다. "
            "둘의 차이가 그 단지에 붙어 있는 프리미엄입니다."
        ),
    }


def _dong_walk(db, complex_id: int, dong: str | None) -> tuple[str | None, float | None]:
    """그 동의 도보시간(분). 동을 모르거나 좌표를 못 잡았으면 (None, None).

    `129동` 처럼 접미사가 붙어 와도 받는다. 테이블에는 `129` 로 들어 있다.
    """
    if not dong:
        return None, None
    key = str(dong).strip().removesuffix("동").strip()
    if not key:
        return None, None
    row = db.execute(
        select(ComplexDong).where(
            ComplexDong.complex_id == complex_id, ComplexDong.dong == key
        )
    ).scalar_one_or_none()
    if row is None or row.walk_seconds is None:
        return key, None
    return key, pricing.walk_minutes_from_seconds(row.walk_seconds)


def compare_listings(db, fit: dict, a: dict, b: dict) -> dict:
    """매물 두 개를 요인별로 분해해 비교한다.

    두 매물의 평당가가 다른 이유를 **요인별 기여로 쪼갠다**. 면적이 달라서 얼마,
    층이 달라서 얼마, 역이 가까워서 얼마… 를 더하면 모델이 예상하는 평당가 차이가
    나온다. 그걸 실제 호가 차이와 견주면 "요인을 감안했을 때 어느 쪽이 싼가"가 나온다.

    ## 두 가지 기준선을 모두 낸다

    - **요인 기준**: 측정 가능한 요인(면적·층·거리·연식·세대수·노선·구)만으로 계산한
      기대 평당가. 단지 고유의 관측되지 않은 프리미엄(학군·브랜드·재건축 기대)은 뺀다.
    - **시장 기준**: 그 단지가 실제로 거래되는 수준(α̂_c)에서 출발. 단지 프리미엄을
      이미 인정하고, 면적·층만 보정한다.

    둘은 다른 질문의 답이다. 요인 기준은 "펀더멘털 대비 싼가", 시장 기준은
    "그 단지 시세 대비 싼가"다. 재건축 기대가 붙은 단지는 두 값이 크게 갈린다.
    """
    idx = fit_index(fit)
    terms = idx["terms"]
    knots = fit.get("knots") or {}
    sterms = fit.get("spline_terms") or {}
    resid = idx["resid"]
    area_lin = fit["stage1"].get("area_linearity") or {}
    floors = idx["floors"]

    rows = idx["alpha_rows"]

    def spline_val(var: str, x: float) -> float:
        names = sterms.get(var)
        if not names:
            return 0.0
        cs = [terms[n]["coef"] for n in names if n in terms]
        if len(cs) != len(names):
            return 0.0
        return _eval_spline(cs, knots.get(var), x)

    def prep(side: dict) -> dict | None:
        cid = int(side["complex_id"])
        row = rows.get(cid)
        if row is None:
            return None
        cx = db.get(Complex, cid)
        area = float(side["exclusive_area"])
        floor = side.get("floor")
        band = pricing.floor_band(floor, cx.max_floor if cx else None)
        asking = side.get("asking_price")
        dong, dong_walk = _dong_walk(db, cid, side.get("dong"))
        return {
            "complex_id": cid,
            "name": row["complex_name"],
            "umd_nm": row["umd_nm"],
            "sgg_cd": row["sgg_cd"],
            "sgg_name": row["sgg_name"],
            "line": row["line"],
            "exclusive_area": area,
            "pyeong": round(pricing.to_pyeong(area), 1),
            "floor": floor,
            "max_floor": cx.max_floor if cx else None,
            "floor_band": band,
            "walk_min": float(row["walk_min"]),
            "dong": dong,
            "dong_walk_min": dong_walk,
            "dong_premium": (fit.get("dong_effects") or {}).get((cid, dong or "")),
            "dong_walk_mean": (
                float(row["dong_walk_mean"])
                if "dong_walk_mean" in row and row["dong_walk_mean"] == row["dong_walk_mean"]
                else None
            ),
            "gangnam_min": float(row["gangnam_min"]),
            "age": float(row["age"]),
            "households": (cx.household_count if cx else None),
            "log_households": float(row["log_households"])
            if row["log_households"] == row["log_households"]
            else None,
            "alpha": float(row["alpha"]),
            "predicted_alpha": resid.get(cid, {}).get("predicted_alpha"),
            "residual_pct": resid.get(cid, {}).get("residual_shrunk_pct"),
            "trade_count": int(row["trade_count"]),
            "asking_price": asking,
            "asking_ppp": (
                round(pricing.price_per_pyeong(asking, area), 1) if asking else None
            ),
        }

    A, B = prep(a), prep(b)
    if A is None or B is None:
        # 어느 단지가 왜 빠졌는지 말해 줘야 사용자가 손을 쓸 수 있다.
        missing = []
        for side, tag in ((a, "A"), (b, "B")):
            cid = int(side["complex_id"])
            if cid in rows:
                continue
            cx = db.get(Complex, cid)
            n = db.scalar(
                select(func.count()).select_from(Trade).where(Trade.complex_id == cid)
            ) or 0
            missing.append(f"{tag}({cx.name if cx else cid}, 전체 기간 거래 {n}건)")
        return {
            "error": (
                f"{' · '.join(missing)} 은(는) 선택한 기간에 거래가 "
                f"{hedonic.MIN_TRADES_PER_COMPLEX}건 미만이라 모델에서 제외됐습니다. "
                "분석 기간을 24개월 이상으로 늘리거나 다른 단지를 선택해 보세요."
            )
        }

    # --- 요인별 기여 (log 평당가 차이) ---
    factors = []

    def add(key, label, a_disp, b_disp, la, lb, note):
        factors.append({
            "key": key, "label": label,
            "a": a_disp, "b": b_disp,
            "diff_pct": _pct(la - lb),
            "note": note,
        })

    ref = FACTOR_REF["area_m2"]
    if area_lin.get("coefs"):
        la = _eval_spline(area_lin["coefs"], area_lin.get("knots"), math.log(A["exclusive_area"] / ref))
        lb = _eval_spline(area_lin["coefs"], area_lin.get("knots"), math.log(B["exclusive_area"] / ref))
        add("area", "전용면적", f"{A['exclusive_area']:.1f}㎡", f"{B['exclusive_area']:.1f}㎡",
            la, lb, "평당가 기준이라 작을수록 단가가 높다(59㎡ 부근이 정점).")

    add("floor", "층", f"{A['floor']}층 ({A['floor_band']})", f"{B['floor']}층 ({B['floor_band']})",
        floors.get(A["floor_band"], 0.0), floors.get(B["floor_band"], 0.0),
        "단지 최고층 대비 상대 위치로 구간을 나눈다.")

    # 동을 알면 **그 동 기준**으로 본다. 같은 단지라도 동에 따라 역까지 100~330m,
    # 많게는 6분 넘게 차이난다.
    #
    # 다만 동 편차에 단지 간 계수를 그대로 쓰면 안 된다. 단지 간 도보 계수는
    # 입지 전반을 함께 싣고 있어 동 편차 계수(-0.52%/분)의 2배쯤 되기 때문이다.
    # 그래서 **단지 중심점까지는 스플라인, 거기서 동까지의 편차는 within 계수**로
    # 나눠 더한다. 후자는 단지 고정효과와 직교하게 추정된 값이다.
    within = (fit.get("stage1") or {}).get("within_walk") or {}
    w_coef = float(within.get("coef") or 0.0)

    def walk_terms(S: dict) -> tuple[float, str]:
        base = spline_val("walk_min", S["walk_min"])
        if S["dong_walk_min"] is None or S["dong_walk_mean"] is None or not w_coef:
            return base, f"{S['walk_min']:.1f}분"
        dev = S["dong_walk_min"] - S["dong_walk_mean"]
        return base + w_coef * dev, f"{S['dong_walk_min']:.1f}분 ({S['dong']}동)"

    la, a_disp = walk_terms(A)
    lb, b_disp = walk_terms(B)
    has_dong = A["dong_walk_min"] is not None or B["dong_walk_min"] is not None
    add("walk", "역까지 도보", a_disp, b_disp, la, lb,
        "동 좌표가 있으면 그 동 기준, 없으면 단지 중심점 기준."
        if has_dong
        else "단지 중심점 기준 — 동 정보가 없습니다.")

    # 동 고유 프리미엄. 위 도보 항에서 **거리는 이미 뺐으므로** 겹쳐 세지 않는다.
    # 여기 남는 것은 조망·향·소음·단지 내 위치처럼 좌표로 안 잡히는 차이다.
    if (A["dong_premium"] or {}).get("coef") or (B["dong_premium"] or {}).get("coef"):
        def dong_disp(S):
            dp = S["dong_premium"]
            if not dp:
                return f"{S['dong']}동 (표본부족)" if S["dong"] else "동 정보 없음"
            return f"{S['dong']}동 ({dp['n']}건)"

        add("dong", "동 (거리 외 요인)", dong_disp(A), dong_disp(B),
            (A["dong_premium"] or {}).get("coef", 0.0),
            (B["dong_premium"] or {}).get("coef", 0.0),
            "조망·향·소음·단지 내 위치. 거래가 적은 동은 단지 평균 쪽으로 수축했다.")

    add("gangnam", "강남까지 전철", f"{A['gangnam_min']:.0f}분", f"{B['gangnam_min']:.0f}분",
        spline_val("gangnam_min", A["gangnam_min"]), spline_val("gangnam_min", B["gangnam_min"]),
        "최적 접근역 기준. 노선 효과와 함께 읽어야 한다.")

    add("age", "연식", f"{A['age']:.0f}년", f"{B['age']:.0f}년",
        spline_val("age", A["age"]), spline_val("age", B["age"]),
        "재건축 기대가 섞여 단순 감소가 아니다.")

    skipped: list[dict] = []
    if A["log_households"] is None or B["log_households"] is None:
        # 조용히 빼면 "세대수가 같다"로 오해한다. 빠졌다는 사실을 드러낸다.
        missing = [s["name"] for s in (A, B) if s["log_households"] is None]
        skipped.append({
            "label": "세대수",
            "reason": f"{', '.join(missing)} 의 세대수 정보가 없어 비교에서 제외했습니다. "
                      "K-apt 에 매칭되지 않은 단지입니다.",
        })
    else:
        add("households", "세대수",
            f"{A['households']:,}세대" if A["households"] else "정보없음",
            f"{B['households']:,}세대" if B["households"] else "정보없음",
            spline_val("log_households", A["log_households"]),
            spline_val("log_households", B["log_households"]),
            "커뮤니티·관리비 규모의 경제·거래 유동성이 함께 들어온다.")

    def dummy(prefix: str, val: str) -> float:
        t = terms.get(f"{prefix}{val}")
        return t["coef"] if t else 0.0

    add("line", "지하철 노선", A["line"], B["line"],
        dummy("line_", A["line"]), dummy("line_", B["line"]),
        "이동시간으로 설명되지 않는 노선 프리미엄.")

    add("sgg", "자치구", A["sgg_name"], B["sgg_name"],
        dummy("sgg_", A["sgg_cd"]), dummy("sgg_", B["sgg_cd"]),
        "구 단위로 남는 지역 효과.")

    # --- 합계와 판정 ---
    total_log = sum(math.log1p(f["diff_pct"] / 100) for f in factors)
    expected_diff_pct = _pct(total_log)

    out = {
        "a": A, "b": B,
        "factors": factors,
        "skipped": skipped,
        "expected_diff_pct": expected_diff_pct,
        "note": (
            "요인별 %는 그 요인 하나만 다를 때 A가 B보다 평당가가 몇 % 높은지입니다. "
            "전부 곱하면 모델이 예상하는 평당가 차이가 됩니다."
        ),
    }

    # 단지 고유 프리미엄(관측되지 않은 요인)
    out["complex_premium_diff_pct"] = (
        _pct((A["alpha"] - (A["predicted_alpha"] or A["alpha"]))
             - (B["alpha"] - (B["predicted_alpha"] or B["alpha"])))
        if A["predicted_alpha"] is not None and B["predicted_alpha"] is not None
        else None
    )

    if A["asking_ppp"] and B["asking_ppp"]:
        actual = _pct(math.log(A["asking_ppp"] / B["asking_ppp"]))
        out["actual_diff_pct"] = actual
        # 실제 차이 - 요인으로 설명되는 차이. 양수면 A 가 설명보다 비싸다.
        gap = _pct(math.log(A["asking_ppp"] / B["asking_ppp"]) - total_log)
        out["gap_pct"] = gap
        cheaper = "B" if gap > 0 else "A"
        out["verdict"] = {
            "cheaper": cheaper,
            "gap_pct": abs(gap),
            "text": (
                f"요인을 모두 감안하면 {cheaper} 쪽이 {abs(gap):.1f}% 저렴합니다."
                if abs(gap) >= 1.0
                else "요인을 감안하면 두 매물의 가격 차이는 거의 없습니다."
            ),
        }
    return out


GROUP_BY = {
    "sgg": "자치구",
    "umd": "법정동",
    "line": "지하철 노선",
    "station": "역 생활권",
    "line_umd": "생활권 (법정동 × 노선)",
}


def group_payload(db, fit: dict, by: str = "line") -> dict:
    """그룹별 보정 평당가와 모델 잔차.

    비교에 쓰는 값은 원자료 평당가가 아니라 **α̂_c**(전용 84㎡·중층·최신월 환산)다.
    면적·층·시점 구성이 이미 제거돼 있어 그룹 간 비교가 성립한다. 원자료 중앙값으로
    비교하면 '그 그룹에 큰 평형이 많아서' 비싼 것과 '실제로 비싼' 것이 뒤섞인다.

    잔차 중앙값이 핵심이다. 도보거리·연식·면적·층·구를 전부 통제한 뒤에도 그 그룹이
    평균보다 높다면, 그건 모델에 없는 무언가(노선 가치, 신도시 계획, 학군)가 있다는 뜻이다.

    ## 왜 line_umd 가 필요한가
    같은 법정동에 서로 다른 노선이 걸치는 경우가 있다. 수원 원천동이 그렇다 —
    신분당선 쪽 단지와 수인분당선 쪽 단지의 보정 평당가가 2배 차이난다.
    구 FE 는 물론 법정동 FE 로도 이 차이를 구분할 수 없어서, 노선을 함께 묶는다.
    """
    alpha = fit["alpha"]
    resid = {r["complex_id"]: r for r in fit["residuals"]}
    stations = {s.id: s for s in db.execute(select(Station)).scalars().all()}
    complexes = {c.id: c for c in db.execute(select(Complex)).scalars().all()}

    def key_of(cx, st):
        if by == "sgg":
            return cx.sgg_name or "?"
        if by == "umd":
            return f"{cx.sgg_name} {cx.umd_nm}".strip()
        if by == "line":
            return st.line if st else "정보없음"
        if by == "station":
            return f"{st.name}({st.line})" if st else "정보없음"
        return f"{cx.umd_nm} · {st.line}" if st else f"{cx.umd_nm} · 정보없음"

    groups: dict[str, list] = {}
    for _, row in alpha.iterrows():
        cid = int(row["complex_id"])
        cx = complexes.get(cid)
        if cx is None:
            continue
        st = stations.get(cx.nearest_station_id)
        groups.setdefault(key_of(cx, st), []).append((row, cx, st, resid.get(cid, {})))

    def med(vals):
        xs = sorted(v for v in vals if v is not None)
        return xs[len(xs) // 2] if xs else None

    def q(vals, p):
        xs = sorted(v for v in vals if v is not None)
        return xs[int(p * (len(xs) - 1))] if xs else None

    items = []
    for name, members in groups.items():
        ppps = [math.exp(float(r["alpha"])) for r, _, _, _ in members]
        items.append(
            {
                "group": name,
                "complex_count": len(members),
                "trade_count": int(sum(int(r["trade_count"]) for r, _, _, _ in members)),
                "normalized_ppp": round(med(ppps) or 0, 1),
                "p25": round(q(ppps, 0.25) or 0, 1),
                "p75": round(q(ppps, 0.75) or 0, 1),
                "walk_min": round(med([float(r["walk_min"]) for r, _, _, _ in members]) or 0, 1),
                "age": round(med([float(r["age"]) for r, _, _, _ in members]) or 0, 1),
                "gangnam_min": med(
                    [st.minutes_to_gangnam for _, _, st, _ in members if st]
                ),
                "residual_pct": round(
                    med([d.get("residual_shrunk_pct") for _, _, _, d in members]) or 0, 2
                ),
            }
        )

    items.sort(key=lambda d: -d["normalized_ppp"])
    return {
        "by": by,
        "label": GROUP_BY.get(by, by),
        "options": [{"key": k, "label": v} for k, v in GROUP_BY.items()],
        "count": len(items),
        "note": (
            "보정 평당가는 전용 84㎡·중층·최신월 기준으로 환산한 값입니다. "
            "잔차는 도보거리·연식·면적·층·구를 통제한 뒤에도 남는 차이입니다."
        ),
        "items": items,
    }


def station_payload(db) -> dict:
    per_station: dict[int, int] = {}
    for cx in db.execute(select(Complex)).scalars().all():
        if cx.nearest_station_id:
            per_station[cx.nearest_station_id] = per_station.get(cx.nearest_station_id, 0) + 1

    items = []
    for s in db.execute(select(Station)).scalars().all():
        items.append(
            {
                "id": s.id,
                "name": s.name,
                "line": s.line,
                "lat": s.lat,
                "lng": s.lng,
                "minutes_to_gangnam": s.minutes_to_gangnam,
                "transfers": s.transfers_to_gangnam,
                "complex_count": per_station.get(s.id, 0),
            }
        )
    items.sort(key=lambda d: (-d["complex_count"], d["name"]))
    return {"count": len(items), "items": items}


def walk_path(db, complex_id: int, station_id: int | None = None) -> dict | None:
    cx = db.get(Complex, complex_id)
    if cx is None:
        return None
    target = station_id or cx.nearest_station_id
    if target is None:
        return None
    cs = db.execute(
        select(ComplexStation).where(
            ComplexStation.complex_id == complex_id,
            ComplexStation.station_id == target,
        )
    ).scalar_one_or_none()
    if cs is None:
        return None

    st = db.get(Station, target)
    return {
        "complex_id": complex_id,
        "complex_name": cx.name,
        "complex_lat": cx.lat,
        "complex_lng": cx.lng,
        "station_id": target,
        "station_name": st.name if st else None,
        "station_lat": st.lat if st else None,
        "station_lng": st.lng if st else None,
        "walk_distance_m": cs.walk_distance_m,
        "walk_seconds": cs.walk_seconds,
        "straight_distance_m": cs.straight_distance_m,
        "source": cs.walk_source,
        # estimate 모드에는 경로 지오메트리가 없다 — 프론트가 점선 직선으로 폴백한다.
        "path": json.loads(cs.path_geojson) if cs.path_geojson else None,
    }
