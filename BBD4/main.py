"""
InvestIQ — FastAPI Application v2.0
Arquitectura limpia: main.py es solo factory + lifespan + WebSocket + health.
Toda la lógica de negocio vive en api/v1/routes/*.py y services/*.py
"""
import os, sys, asyncio, json
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
import logging

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.config import settings
from core.database import init_db, AsyncSessionLocal
from core.security import hash_password
from core.monitoring import init_sentry
from core.rate_limit import limiter, rate_limit_handler
from slowapi.errors import RateLimitExceeded

# ── Structured logging (JSON) ─────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Silenciar librerías externas que spamean logs en data centers
# (Yahoo Finance bloquea IPs de hosting — el fallback de precios lo maneja el código)
for _noisy in ("yfinance", "yfinance.base", "yfinance.utils", "yfinance.cache",
               "peewee", "urllib3.connectionpool", "charset_normalizer"):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL)

# ── Seed data ─────────────────────────────────────────────
async def seed_inicial():
    """Crea los usuarios base y los activos registrables. Sin datos inventados."""
    from sqlalchemy import select, func
    from models.models import (Usuario, Activo, Alerta, AuditLog)
    from services.services import get_market_prices

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(func.count(Usuario.id)))
        if res.scalar() > 0:
            return

        # Usuarios base
        u = Usuario(
            nombre="Administrador", email="demo@investiq.co",
            password_hash=hash_password("InvestIQ2026!"),
            rol="admin", kyc_nivel="biometric", kyc_verificado=True,
            aml_status="clear", mfa_activo=False, edad=30,
            ingresos_anuales_usd=25000, tolerancia_riesgo="moderada",
            saldo_usd=0
        )
        admin = Usuario(
            nombre="Administrador", email="admin@investiq.co",
            password_hash=hash_password("Admin2026!"),
            rol="admin", kyc_nivel="biometric", kyc_verificado=True,
            aml_status="clear", saldo_usd=0
        )
        db.add_all([u, admin])
        await db.flush()

        # Activos registrables (catálogo)
        tickers_data = [
            ("AAPL","Apple Inc.","stock","Tecnología","NASDAQ"),
            ("MSFT","Microsoft Corp.","stock","Tecnología","NASDAQ"),
            ("TSLA","Tesla Inc.","stock","Automotriz","NASDAQ"),
            ("NVDA","NVIDIA Corp.","stock","Semiconductores","NASDAQ"),
            ("AMZN","Amazon.com Inc.","stock","E-Commerce","NASDAQ"),
            ("GOOGL","Alphabet Inc.","stock","Tecnología","NASDAQ"),
            ("META","Meta Platforms","stock","Redes Sociales","NASDAQ"),
            ("SPY","SPDR S&P 500 ETF","etf","Índice","NYSE"),
            ("QQQ","Invesco QQQ Trust","etf","Tecnología","NASDAQ"),
            ("BND","Vanguard Bond ETF","etf","Bonos","NYSE"),
            ("VTI","Vanguard Total Market","etf","Índice","NYSE"),
            ("GLD","SPDR Gold Trust","etf","Materias Primas","NYSE"),
        ]
        precios = get_market_prices([t[0] for t in tickers_data])
        for ticker, nombre, tipo, sector, mercado in tickers_data:
            p = precios.get(ticker, {})
            db.add(Activo(ticker=ticker, nombre=nombre, tipo=tipo,
                          sector=sector, mercado=mercado,
                          precio_actual=p.get("price", 0),
                          precio_apertura=p.get("open", 0),
                          variacion_pct=p.get("change_pct", 0)))

        # Alerta de bienvenida del sistema
        db.add(Alerta(usuario_id=u.id, tipo="info", modulo="sistema",
                      titulo="Plataforma lista",
                      mensaje="InvestIQ conectado. Precios en tiempo real vía Alpaca IEX."))

        db.add(AuditLog(usuario_id=admin.id, accion="SISTEMA_INIT", modulo="sistema",
                        detalle="InvestIQ v2.0.0 inicializado", ip="127.0.0.1"))
        await db.commit()
        logger.info("✓ Seed limpio completado — sin datos de prueba")


async def ensure_usuario_personal():
    """
    Garantiza que el usuario personal del propietario exista siempre.
    Se ejecuta en cada arranque — idempotente.
    """
    from sqlalchemy import select
    from models.models import Usuario, AuditLog

    PERSONAL_EMAIL    = "edwinsumaran3@gmail.com"
    PERSONAL_PASSWORD = "Fxcbbd2026*"
    PERSONAL_NOMBRE   = "Edwin Sumaran"

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Usuario).where(Usuario.email == PERSONAL_EMAIL)
        )
        user = res.scalar_one_or_none()

        if not user:
            user = Usuario(
                nombre           = PERSONAL_NOMBRE,
                email            = PERSONAL_EMAIL,
                password_hash    = hash_password(PERSONAL_PASSWORD),
                rol              = "admin",
                kyc_nivel        = "biometric",
                kyc_verificado   = True,
                aml_status       = "clear",
                mfa_activo       = False,
                edad             = 30,
                ingresos_anuales_usd = 50000,
                tolerancia_riesgo    = "moderada",
                saldo_usd        = 0,
                activo           = True,
            )
            db.add(user)
            await db.flush()
            db.add(AuditLog(
                usuario_id = user.id,
                accion     = "USUARIO_CREADO",
                modulo     = "sistema",
                detalle    = f"Usuario personal {PERSONAL_EMAIL} creado automáticamente",
                ip         = "127.0.0.1",
            ))
            await db.commit()
            logger.info("✓ Usuario personal %s creado", PERSONAL_EMAIL)
        else:
            # Siempre garantizar rol admin y contraseña actualizada
            user.rol           = "admin"
            user.password_hash = hash_password(PERSONAL_PASSWORD)
            user.activo        = True
            await db.commit()
            logger.info("✓ Usuario personal %s verificado", PERSONAL_EMAIL)


async def limpiar_datos_demo():
    """
    Elimina datos de prueba generados por seed antiguo en deployments existentes.
    Identifica órdenes demo por broker_order_id='ord_XXXX', posiciones sin
    origen real (broker_order_id NULL), transacciones de seed y dividendos inventados.
    """
    from sqlalchemy import select, delete, update
    from models.models import (Usuario, PosicionPortafolio, Orden,
                                Transaccion, Dividendo, Alerta, TaxLot)

    async with AsyncSessionLocal() as db:
        # Obtener usuario demo
        res = await db.execute(select(Usuario).where(Usuario.email == "demo@investiq.co"))
        u = res.scalar_one_or_none()
        if not u:
            return

        uid = u.id

        # Órdenes con ID de seed (ord_0000 … ord_0019)
        await db.execute(
            delete(Orden).where(
                Orden.usuario_id == uid,
                Orden.broker_order_id.like("ord_%")
            )
        )

        # Posiciones: eliminar las que vinieron del seed (precio_promedio_compra exacto a los valores del seed)
        seed_pc = {189.50, 850.0, 410.0, 220.0, 520.0}
        res2 = await db.execute(
            select(PosicionPortafolio).where(PosicionPortafolio.usuario_id == uid)
        )
        for pos in res2.scalars().all():
            if round(pos.precio_promedio_compra, 2) in seed_pc:
                await db.execute(
                    delete(TaxLot).where(
                        TaxLot.usuario_id == uid,
                        TaxLot.ticker == pos.ticker,
                        TaxLot.precio_costo == pos.precio_promedio_compra
                    )
                )
                await db.delete(pos)

        # Transacciones de seed (descripción exacta)
        await db.execute(
            delete(Transaccion).where(
                Transaccion.usuario_id == uid,
                Transaccion.descripcion.in_(["Depósito inicial", "Depósito adicional"])
            )
        )

        # Dividendos inventados del seed (los tres tickers exactos)
        await db.execute(
            delete(Dividendo).where(Dividendo.usuario_id == uid)
        )

        # Alerta de concentración falsa
        await db.execute(
            delete(Alerta).where(
                Alerta.usuario_id == uid,
                Alerta.titulo == "Concentración alta"
            )
        )

        # Resetear saldo ficticio a 0
        if u.saldo_usd == 3421.10:
            await db.execute(
                update(Usuario).where(Usuario.id == uid).values(saldo_usd=0)
            )

        # Asegurar rol admin en demo@investiq.co
        if u.rol != "admin":
            await db.execute(
                update(Usuario).where(Usuario.id == uid).values(rol="admin")
            )

        await db.commit()
        logger.info("✓ Datos de prueba eliminados y rol admin aplicado")

# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # init_db DEBE ir antes del yield (crea las tablas)
    await init_db()
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    init_sentry(app)
    # seed e yfinance corren en background para no bloquear el port binding
    asyncio.create_task(seed_inicial())
    asyncio.create_task(limpiar_datos_demo())
    asyncio.create_task(ensure_usuario_personal())
    asyncio.create_task(price_broadcaster())
    logger.info("InvestIQ v2.0 listo — seed y broadcaster arrancando en background")
    yield

# ── App ───────────────────────────────────────────────────
app = FastAPI(
    title="InvestIQ API",
    version="2.0.0",
    description="Plataforma de microinversión con IA Robo-Advisor, KYC/AML y broker real",
    lifespan=lifespan
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# Archivos estáticos
os.makedirs("static/exports", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ───────────────────────────────────────────────
from api.v1.routes.auth import router as auth_router
from api.v1.routes.market import router as market_router
from api.v1.routes.portfolio import router as portfolio_router
from api.v1.routes.orders import router as orders_router
from api.v1.routes.kyc import router as kyc_router
from api.v1.routes.aml import router as aml_router
from api.v1.routes.robo_advisor import router as robo_router
from api.v1.routes.transactions import router as transactions_router
from api.v1.routes.alerts import router as alerts_router
from api.v1.routes.metrics import router as metrics_router
from api.v1.routes.exports import router as exports_router
from api.v1.routes.audit import router as audit_router
from api.v1.routes.webhooks import router as webhooks_router
from api.v1.routes.notifications import router as notifications_router
from api.v1.routes.tax import router as tax_router
from api.v1.routes.payments import router as payments_router
from api.v1.routes.admin import router as admin_router

PREFIX = "/api/v1"
app.include_router(auth_router, prefix=PREFIX)
app.include_router(market_router, prefix=PREFIX)
app.include_router(portfolio_router, prefix=PREFIX)
app.include_router(orders_router, prefix=PREFIX)
app.include_router(kyc_router, prefix=PREFIX)
app.include_router(aml_router, prefix=PREFIX)
app.include_router(robo_router, prefix=PREFIX)
app.include_router(transactions_router, prefix=PREFIX)
app.include_router(alerts_router, prefix=PREFIX)
app.include_router(metrics_router, prefix=PREFIX)
app.include_router(exports_router, prefix=PREFIX)
app.include_router(audit_router, prefix=PREFIX)
app.include_router(webhooks_router, prefix=PREFIX)
app.include_router(notifications_router, prefix=PREFIX)
app.include_router(tax_router, prefix=PREFIX)
app.include_router(payments_router, prefix=PREFIX)
app.include_router(admin_router, prefix=PREFIX)

# ── WebSocket Manager ─────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()


async def price_broadcaster():
    """Difunde precios de mercado a todos los clientes WebSocket cada 4 segundos."""
    from services.services import get_market_prices
    while True:
        await asyncio.sleep(4)
        try:
            prices = get_market_prices()
            await manager.broadcast({"type": "prices", "data": prices,
                                     "ts": datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        from services.services import get_market_prices
        prices = get_market_prices()
        await ws.send_json({"type": "init", "prices": prices,
                            "ts": datetime.now(timezone.utc).isoformat()})
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await ws.send_json({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})
                elif data.get("type") == "subscribe":
                    await ws.send_json({"type": "subscribed",
                                        "tickers": data.get("tickers", [])})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "ts": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(ws)

# ── Health ────────────────────────────────────────────────
@app.get("/api/v1/health", tags=["health"])
async def health():
    from services.services import cache_set, cache_get
    redis_ok = False
    try:
        cache_set("_health", 1, ttl=5)
        redis_ok = cache_get("_health") is not None
    except Exception:
        pass

    from core.circuit_breaker import cb_alpaca, cb_claude, cb_opensanctions
    return {
        "status": "ok",
        "version": "2.0.0",
        "ts": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database": "ok",
            "redis": "ok" if redis_ok else "memory_fallback",
            "broker": "alpaca_paper",
            "ia": "claude_ready" if settings.CLAUDE_API_KEY else "local_mode",
            "sentry": "active" if settings.SENTRY_DSN else "not_configured",
            "stripe": "active" if settings.STRIPE_SECRET_KEY else "demo_mode",
            "mercadopago": "active" if settings.MERCADOPAGO_ACCESS_TOKEN else "demo_mode",
            "twilio": "active" if settings.TWILIO_ACCOUNT_SID else "demo_mode",
            "firebase": "active" if settings.FCM_SERVER_KEY else "demo_mode",
            "push_vapid": "active" if settings.VAPID_PUBLIC_KEY else "demo_mode",
        },
        "circuit_breakers": {
            "alpaca": cb_alpaca.get_state(),
            "claude": cb_claude.get_state(),
            "opensanctions": cb_opensanctions.get_state(),
        }
    }


@app.get("/", tags=["root"])
async def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False,
                workers=1, log_level="info")
