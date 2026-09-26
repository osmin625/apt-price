import logging
import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal, engine
from .models import Base, Complex, ComplexStation, Station, Trade
from .routers import analysis, complexes, listings, map as map_router, model
from .services import fit_worker, hedonic, model_view

# 주의: create_all 은 없는 '테이블'만 만들고 기존 테이블에 '컬럼'은 추가하지 않는다.
# 스키마를 바꿨다면 `python -m scripts.seed_demo --recreate-schema` 로 재생성해야 한다.
Base.metadata.create_all(engine)

app = FastAPI(
    title="수도권 아파트 적정 시세 API",
    description="국토교통부 실거래가 기반 전용면적 평당가 분석 (PoC: 수원시)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(complexes.router)
app.include_router(analysis.router)
app.include_router(listings.router)
app.include_router(model.router)
app.include_router(map_router.router)


@app.on_event("startup")
def _warm_fit():
    """적합을 미리 데워 둔다.

    첫 사용자가 14초를 기다릴 이유가 없고, 동 프리미엄처럼 **적합이 있어야 붙는**
    정보(`/complexes/{id}/dongs` 의 premium_pct)가 첫 화면부터 나온다.
    적합이 별도 프로세스로 빠졌기 때문에 이 예열은 API 를 막지 않는다.

    **기본값은 꺼짐이다.** `--reload` 로 개발 중일 때는 파일을 저장할 때마다 서버가
    재시작하고 그때마다 예열이 새로 돌아, 적합이 겹겹이 쌓여 앱이 멎는 일이 생겼다.
    운영처럼 재시작이 드문 환경에서만 `FIT_WARM=1` 로 켠다.
    """
    if os.environ.get("FIT_WARM", "0").strip() not in {"1", "true", "yes"}:
        return

    def go():
        try:
            with SessionLocal() as db:
                model_view.get_fit(db)
            logging.getLogger(__name__).info("적합 예열 완료")
        except Exception:
            logging.getLogger(__name__).exception("적합 예열 실패 — 요청 시 다시 시도합니다")

    threading.Thread(target=go, name="fit-warm", daemon=True).start()


@app.on_event("shutdown")
def _stop_fit_worker():
    # 안 정리하면 --reload 때마다 적합 워커 프로세스가 하나씩 남는다.
    fit_worker.shutdown()


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        complex_count = db.scalar(select(func.count()).select_from(Complex)) or 0
        trade_count = db.scalar(select(func.count()).select_from(Trade)) or 0
        latest = db.scalar(select(func.max(Trade.deal_date)))
        geocoded = db.scalar(
            select(func.count()).select_from(Complex).where(Complex.lat.is_not(None))
        ) or 0
        station_count = db.scalar(select(func.count()).select_from(Station)) or 0
        routed = db.scalar(
            select(func.count()).select_from(Complex).where(Complex.walk_seconds.is_not(None))
        ) or 0
        walk_sources = dict(
            db.execute(
                select(ComplexStation.walk_source, func.count()).group_by(
                    ComplexStation.walk_source
                )
            ).all()
        )
        synthetic = db.scalar(
            select(func.count()).select_from(Trade).where(Trade.source == "seed")
        ) or 0

    return {
        "status": "ok",
        "complex_count": complex_count,
        "trade_count": trade_count,
        "geocoded_count": geocoded,
        "latest_deal_date": latest.isoformat() if latest else None,
        "molit_key_set": bool(settings.molit_service_key),
        "kakao_key_set": bool(settings.kakao_rest_key),
        "tmap_key_set": bool(settings.tmap_app_key),
        "model_available": hedonic.available(),
        "station_count": station_count,
        "routed_count": routed,
        "walk_source_counts": walk_sources,
        "synthetic_trade_count": synthetic,
    }
