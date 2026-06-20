"""
main.py — FXC_BBD FastAPI Application Entry Point.

Arquitectura: Financial Exchange Center BBD
- 9 Agentes (8 especialistas + Master AI supervisor)
- Back/Lay Exchange (Brecha B)
- Kelly Criterion bankroll manager (Brecha A)
- Brier Score + recalibración semanal (Brecha C)
- WebSocket live odds stream <500ms SLA (Brecha D)
- Circuit Breaker + Monte Carlo Poisson
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.database import init_db

# Rutas
from api.v1.routes.predictions    import router as predictions_router
from api.v1.routes.bankroll       import router as bankroll_router
from api.v1.routes.exchange       import router as exchange_router
from api.v1.routes.backtesting_routes import router as backtesting_router
from api.v1.routes.live_routes    import router as live_router

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fxcbbd.main")


# ─── LIFESPAN ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("═══════════════════════════════════════════")
    logger.info("  FXC_BBD — Financial Exchange Center BBD  ")
    logger.info("  Iniciando plataforma de exchange deportivo")
    logger.info("═══════════════════════════════════════════")

    # Inicializar base de datos y tablas
    await init_db()
    logger.info("Base de datos inicializada")

    # Cargar pesos guardados de la BD al Master AI
    try:
        from core.database import AsyncSessionLocal
        from models.models import AgentWeight
        from master_ai.master_ai import master_ai
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AgentWeight))
            pesos_bd = result.scalars().all()
            for aw in pesos_bd:
                if aw.agente_id in master_ai.pesos:
                    master_ai.pesos[aw.agente_id] = aw.peso_actual
        if pesos_bd:
            logger.info("Pesos del Master AI cargados desde BD: %d agentes", len(pesos_bd))
    except Exception as e:
        logger.warning("No se pudieron cargar pesos desde BD: %s", e)

    logger.info("FXC_BBD listo — escuchando en %s", settings.APP_HOST)
    yield

    logger.info("FXC_BBD deteniendo...")


# ─── APP ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "FXC_BBD — Financial Exchange Center BBD",
    description = (
        "Exchange deportivo de alta frecuencia con 9 agentes de IA.\n\n"
        "**Brechas implementadas:**\n"
        "- **Brecha A**: Kelly Criterion con gestión de bankroll\n"
        "- **Brecha B**: Exchange Back/Lay con trading-out\n"
        "- **Brecha C**: Brier Score + recalibración walk-forward\n"
        "- **Brecha D**: WebSocket stream con SLA <500ms y circuit breaker\n\n"
        "**Master AI**: 8 agentes especializados → Matriz de confianza → EV → Kelly"
    ),
    version     = "1.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# ─── CORS ────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.CORS_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─── ROUTERS ─────────────────────────────────────────────────────────────────

app.include_router(predictions_router)
app.include_router(bankroll_router)
app.include_router(exchange_router)
app.include_router(backtesting_router)
app.include_router(live_router)

# ─── ROOT ────────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)


@app.get("/health", tags=["status"])
async def health():
    from live import circuit_breaker, latency_tracker
    stats = latency_tracker.estadisticas()
    return {
        "status":          "ok",
        "circuit_breaker": circuit_breaker.estado,
        "latencia_p95_ms": stats.get("p95_ms"),
        "sla_cumplimiento":stats.get("cumplimiento_pct"),
    }


# ─── EXCEPTION HANDLER ───────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Error no controlado: %s", exc, exc_info=True)
    return JSONResponse(
        status_code = 500,
        content     = {"error": "Error interno del servidor", "detail": str(exc)},
    )


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host    = settings.APP_HOST,
        port    = settings.APP_PORT,
        reload  = settings.DEBUG,
        workers = 1 if settings.DEBUG else 4,
        log_level = "info",
    )
