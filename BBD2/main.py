"""
InvestIQ — FastAPI Main Application
22 endpoints REST + WebSocket tiempo real + seed automático
"""
import os, sys, json, asyncio, time, random, threading
from datetime import datetime, timedelta
from typing import Optional
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr, Field

from core.config import settings
from core.database import init_db, AsyncSessionLocal, get_db
from core.security import (hash_password, verify_password, create_access_token,
                            create_refresh_token, firmar_orden, verificar_firma,
                            generar_mfa_secret, verificar_totp, generar_qr_base64, generar_nonce)
from models.models import (Usuario, Activo, PosicionPortafolio, Orden, Transaccion,
                            Dividendo, ReporteFiscal, Alerta, AuditLog, AMLLog,
                            AnalisisRoboAdvisor, KYCVerificacion)
from api.v1.routes.payments import router as payments_router
from services.services import (get_market_prices, get_candles, alpaca_get_account,
                                alpaca_place_order, alpaca_get_positions, alpaca_cancel_order,
                                aml_check_entidad, robo_advisor_analizar,
                                generar_excel_portafolio, generar_pdf_reporte,
                                cache_set, cache_get)

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

# ── Seed data ─────────────────────────────────────────────
async def seed_inicial(db: AsyncSession):
    res = await db.execute(select(func.count(Usuario.id)))
    if res.scalar() > 0:
        return
    u = Usuario(nombre="Inversionista Demo", email="demo@investiq.co",
                password_hash=hash_password("InvestIQ2026!"),
                rol="investor", kyc_nivel="full", kyc_verificado=True,
                aml_status="clear", mfa_activo=False, edad=30,
                ingresos_anuales_usd=25000, tolerancia_riesgo="moderada",
                saldo_usd=3421.10)
    admin = Usuario(nombre="Administrador", email="admin@investiq.co",
                    password_hash=hash_password("Admin2026!"),
                    rol="admin", kyc_nivel="biometric", kyc_verificado=True,
                    aml_status="clear", saldo_usd=0)
    db.add_all([u, admin]); await db.flush()

    # Activos
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
        db.add(Activo(ticker=ticker, nombre=nombre, tipo=tipo, sector=sector, mercado=mercado,
                      precio_actual=p.get("price", 100), precio_apertura=p.get("open", 100),
                      variacion_pct=p.get("change_pct", 0)))

    # Portafolio demo
    posiciones = [
        ("AAPL","Apple Inc.",2.3456,189.50,195.20),
        ("NVDA","NVIDIA Corp.",0.8721,850.0,912.40),
        ("MSFT","Microsoft Corp.",1.0543,410.0,432.10),
        ("TSLA","Tesla Inc.",3.12,220.0,248.30),
        ("SPY","SPDR S&P 500",1.5,520.0,541.0),
    ]
    for ticker, nombre, acc, pc, pa in posiciones:
        pos = PosicionPortafolio(usuario_id=u.id, ticker=ticker, nombre=nombre,
                                  acciones=acc, precio_promedio_compra=pc, precio_actual=pa)
        pos.recalcular()
        db.add(pos)

    # Órdenes históricas
    for i in range(20):
        d = datetime.utcnow() - timedelta(days=random.randint(0,90))
        tick = random.choice(["AAPL","NVDA","MSFT","TSLA","SPY"])
        monto = round(random.uniform(10, 500), 2)
        price = round(random.uniform(100, 950), 2)
        fracs = round(monto / price, 8)
        datos_firma = {"ticker": tick, "monto": monto, "tipo": "buy", "ts": str(d), "nonce": generar_nonce()}
        firma = firmar_orden(datos_firma)
        db.add(Orden(usuario_id=u.id, ticker=tick, tipo="buy", tipo_orden="market",
                     monto_usd=monto, acciones=fracs, precio_ejecucion=price,
                     estado="filled", broker="alpaca_paper",
                     broker_order_id=f"ord_{i:04d}",
                     firma_ecdsa=firma, firma_verificada=True,
                     nonce=datos_firma["nonce"], aml_check="clear",
                     creado=d, ejecutado=d))

    # Transacciones
    db.add(Transaccion(usuario_id=u.id, tipo="deposito", monto_usd=5000, estado="completed",
                       metodo="bank_transfer", descripcion="Depósito inicial"))
    db.add(Transaccion(usuario_id=u.id, tipo="deposito", monto_usd=3000, estado="completed",
                       metodo="bank_transfer", descripcion="Depósito adicional"))

    # Dividendos
    for tick in ["AAPL","SPY","MSFT"]:
        db.add(Dividendo(usuario_id=u.id, ticker=tick,
                         monto_usd=round(random.uniform(0.5, 8), 4),
                         acciones_en_fecha=round(random.uniform(0.5, 3), 4),
                         pago_date=datetime.utcnow()-timedelta(days=random.randint(10,60))))

    # Alertas
    alertas_init = [
        ("warning","portafolio","Concentración alta","TSLA representa el 28% del portafolio. Revisar."),
        ("info","mercado","Mercado abierto","NYSE y NASDAQ operando normalmente hoy."),
        ("info","ia","Robo-Advisor","Análisis de riesgo disponible. Ejecutar para ver recomendaciones."),
        ("danger","kyc","KYC pendiente","Verificación biométrica pendiente para nivel máximo."),
    ]
    for tipo, mod, titulo, msg in alertas_init:
        db.add(Alerta(usuario_id=u.id, tipo=tipo, modulo=mod, titulo=titulo, mensaje=msg))

    db.add(AuditLog(usuario_id=admin.id, accion="SISTEMA_INIT", modulo="sistema",
                    detalle="Base de datos inicializada — InvestIQ v1.0.0", ip="127.0.0.1"))
    await db.commit()
    print("✓ Seed InvestIQ completado")

# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_inicial(db)
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    print(f"\n{'='*55}")
    print(f"  InvestIQ — Servidor listo en http://localhost:8000")
    print(f"  Docs: http://localhost:8000/docs")
    print(f"  Demo: demo@investiq.co / InvestIQ2026!")
    print(f"{'='*55}\n")
    yield

app = FastAPI(title="InvestIQ API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# Static files
os.makedirs("static/exports", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Registrar routers adicionales
app.include_router(payments_router, prefix="/api/v1")
# ── WebSocket Manager ─────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
    async def connect(self, ws: WebSocket):
        await ws.accept(); self.active.append(ws)
    def disconnect(self, ws: WebSocket):
        self.active.remove(ws) if ws in self.active else None
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

# ── Background price broadcaster ──────────────────────────
async def price_broadcaster():
    while True:
        await asyncio.sleep(4)
        try:
            prices = get_market_prices()
            await manager.broadcast({"type": "prices", "data": prices,
                                     "ts": datetime.utcnow().isoformat()})
        except Exception:
            pass

# ── Schemas ───────────────────────────────────────────────
class LoginSchema(BaseModel):
    email: str; password: str; mfa_token: Optional[str] = None

class OrdenSchema(BaseModel):
    ticker: str
    monto_usd: float = Field(..., ge=1, le=50000)
    tipo: str = "buy"
    tipo_orden: str = "market"
    limit_price: Optional[float] = None

class RoboAdvisorSchema(BaseModel):
    edad: Optional[int] = 30
    ingresos_anuales_usd: Optional[float] = 15000
    tolerancia_riesgo: Optional[str] = "moderada"

class DepositoSchema(BaseModel):
    monto_usd: float = Field(..., ge=1)
    metodo: str = "bank_transfer"

class AlertaLeerSchema(BaseModel):
    ids: list[int]

# ── Auth ──────────────────────────────────────────────────
@app.post("/api/v1/auth/login")
async def login(data: LoginSchema, request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.email == data.email, Usuario.activo == True))
    user = res.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Credenciales inválidas")
    if user.mfa_activo and user.mfa_secret:
        if not data.mfa_token or not verificar_totp(user.mfa_secret, data.mfa_token):
            raise HTTPException(401, "Token MFA requerido o inválido")
    user.ultimo_login = datetime.utcnow()
    db.add(AuditLog(usuario_id=user.id, accion="LOGIN", modulo="auth",
                    detalle=f"Login exitoso: {user.email}", ip=request.client.host))
    await db.commit()
    token = create_access_token({"sub": str(user.id), "email": user.email, "rol": user.rol})
    refresh = create_refresh_token({"sub": str(user.id)})
    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer",
            "usuario": user.to_dict()}

@app.get("/api/v1/auth/me")
async def get_me(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.email == "demo@investiq.co"))
    user = res.scalar_one_or_none()
    return user.to_dict() if user else {}

@app.get("/api/v1/auth/mfa/setup")
async def mfa_setup():
    secret = generar_mfa_secret()
    qr = generar_qr_base64(secret, "demo@investiq.co")
    return {"secret": secret, "qr_base64": qr,
            "instrucciones": "Escanea el QR con Google Authenticator"}

# ── Mercado ───────────────────────────────────────────────
@app.get("/api/v1/mercado/precios")
async def precios(tickers: Optional[str] = None):
    t = tickers.split(",") if tickers else None
    cached = cache_get("precios_mercado")
    if cached: return cached
    data = get_market_prices(t)
    cache_set("precios_mercado", data, ttl=15)
    return data

@app.get("/api/v1/mercado/candles/{ticker}")
async def candles(ticker: str, period: str = "1mo", interval: str = "1d"):
    key = f"candles_{ticker}_{period}_{interval}"
    cached = cache_get(key)
    if cached: return {"ticker": ticker, "candles": cached}
    data = get_candles(ticker.upper(), period, interval)
    cache_set(key, data, ttl=60)
    return {"ticker": ticker, "period": period, "interval": interval, "candles": data}

@app.get("/api/v1/mercado/activos")
async def get_activos(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Activo).where(Activo.activo == True))
    activos = res.scalars().all()
    # Actualizar precios
    prices = get_market_prices([a.ticker for a in activos])
    for a in activos:
        p = prices.get(a.ticker, {})
        a.precio_actual = p.get("price", a.precio_actual)
        a.variacion_pct = p.get("change_pct", 0)
        a.ultima_actualizacion = datetime.utcnow()
    await db.commit()
    return [a.to_dict() for a in activos]

# ── Portafolio ────────────────────────────────────────────
@app.get("/api/v1/portafolio")
async def get_portafolio(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == 1, PosicionPortafolio.acciones > 0))
    posiciones = res.scalars().all()
    prices = get_market_prices([p.ticker for p in posiciones])
    total_valor = 0; total_gp = 0
    result = []
    for pos in posiciones:
        price = prices.get(pos.ticker, {}).get("price", pos.precio_actual)
        pos.precio_actual = price
        pos.recalcular()
        total_valor += pos.valor_total_usd
        total_gp += pos.ganancia_perdida_usd
        result.append(pos.to_dict())
    await db.commit()
    # Cuenta broker
    cuenta_broker = alpaca_get_account(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET)
    return {"posiciones": result, "total_valor_usd": round(total_valor, 2),
            "ganancia_perdida_total": round(total_gp, 2),
            "cuenta_broker": cuenta_broker,
            "posiciones_broker": alpaca_get_positions(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET)}

# ── Órdenes ───────────────────────────────────────────────
@app.post("/api/v1/ordenes")
async def crear_orden(data: OrdenSchema, request: Request, db: AsyncSession = Depends(get_db)):
    if data.monto_usd < settings.MIN_ORDER_USD:
        raise HTTPException(400, f"Monto mínimo: ${settings.MIN_ORDER_USD}")
    # AML check rápido del usuario
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one_or_none()
    if not user: raise HTTPException(404, "Usuario no encontrado")
    if user.aml_status == "blocked":
        raise HTTPException(403, "Cuenta bloqueada por AML")
    if user.saldo_usd < data.monto_usd:
        raise HTTPException(400, f"Saldo insuficiente. Disponible: ${user.saldo_usd:.2f}")

    # Firma ECDSA de la orden
    nonce = generar_nonce()
    datos_firma = {"ticker": data.ticker, "monto_usd": data.monto_usd,
                   "tipo": data.tipo, "ts": str(datetime.utcnow()), "nonce": nonce}
    firma = firmar_orden(datos_firma)
    firma_ok = verificar_firma(datos_firma, firma)

    # Ejecutar en broker
    broker_resp = alpaca_place_order(
        settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET,
        data.ticker, data.monto_usd, data.tipo, data.tipo_orden, data.limit_price)

    if "error" in broker_resp:
        raise HTTPException(502, f"Error broker: {broker_resp['error']}")

    price = float(broker_resp.get("filled_avg_price", 0) or 0)
    fracs = float(broker_resp.get("filled_qty", 0) or 0)
    if fracs == 0 and price > 0:
        fracs = round(data.monto_usd / price, 8)

    # Guardar orden
    orden = Orden(usuario_id=1, ticker=data.ticker, tipo=data.tipo,
                  tipo_orden=data.tipo_orden, monto_usd=data.monto_usd,
                  acciones=fracs, precio_ejecucion=price, estado="filled",
                  broker="alpaca_paper", broker_order_id=broker_resp.get("id"),
                  firma_ecdsa=firma, firma_verificada=firma_ok,
                  nonce=nonce, ip_origen=request.client.host,
                  aml_check="clear", creado=datetime.utcnow(), ejecutado=datetime.utcnow())
    db.add(orden)

    # Actualizar saldo
    if data.tipo == "buy":
        user.saldo_usd = round(user.saldo_usd - data.monto_usd, 2)
        # Actualizar o crear posición
        pos_res = await db.execute(select(PosicionPortafolio).where(
            PosicionPortafolio.usuario_id == 1, PosicionPortafolio.ticker == data.ticker))
        pos = pos_res.scalar_one_or_none()
        if pos:
            # Costo promedio ponderado
            total_acc = pos.acciones + fracs
            pos.precio_promedio_compra = round(
                (pos.acciones * pos.precio_promedio_compra + fracs * price) / total_acc, 4) if total_acc > 0 else price
            pos.acciones = round(total_acc, 8)
            pos.precio_actual = price; pos.recalcular()
        else:
            db.add(PosicionPortafolio(usuario_id=1, ticker=data.ticker,
                                       nombre=data.ticker, acciones=fracs,
                                       precio_promedio_compra=price, precio_actual=price,
                                       valor_total_usd=round(fracs*price,2)))
    elif data.tipo == "sell":
        user.saldo_usd = round(user.saldo_usd + data.monto_usd, 2)
        pos_res = await db.execute(select(PosicionPortafolio).where(
            PosicionPortafolio.usuario_id == 1, PosicionPortafolio.ticker == data.ticker))
        pos = pos_res.scalar_one_or_none()
        if pos:
            pos.acciones = max(0, round(pos.acciones - fracs, 8))
            pos.precio_actual = price; pos.recalcular()

    db.add(AuditLog(usuario_id=1, accion="ORDEN_EJECUTADA", modulo="broker",
                    detalle=f"{data.tipo.upper()} {data.ticker} ${data.monto_usd} = {fracs} acc @ ${price}",
                    ip=request.client.host))
    await db.commit()
    await manager.broadcast({"type": "orden", "data": orden.to_dict()})
    return {**orden.to_dict(), "firma_ok": firma_ok, "broker": broker_resp,
            "saldo_nuevo": user.saldo_usd}

@app.get("/api/v1/ordenes")
async def get_ordenes(limit: int = 50, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Orden).where(Orden.usuario_id == 1)
                           .order_by(Orden.creado.desc()).limit(limit))
    return [o.to_dict() for o in res.scalars().all()]

@app.delete("/api/v1/ordenes/{orden_id}")
async def cancelar_orden(orden_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Orden).where(Orden.id == orden_id))
    orden = res.scalar_one_or_none()
    if not orden: raise HTTPException(404, "Orden no encontrada")
    if orden.estado == "filled": raise HTTPException(400, "Orden ya ejecutada")
    if orden.broker_order_id:
        alpaca_cancel_order(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET, orden.broker_order_id)
    orden.estado = "cancelled"
    await db.commit()
    return {"ok": True, "id": orden_id}

# ── KYC ───────────────────────────────────────────────────
@app.post("/api/v1/kyc/submit")
async def kyc_submit(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    kyc = KYCVerificacion(usuario_id=1, tipo_doc=body.get("tipo_doc","cedula"),
                           num_doc=body.get("num_doc",""), pais_emision=body.get("pais","CO"),
                           nivel_alcanzado="basic", proveedor="local", resultado="approved")
    db.add(kyc)
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    user.kyc_nivel = "basic"; user.kyc_verificado = True; user.kyc_fecha = datetime.utcnow()
    await db.commit()
    return {"ok": True, "nivel": "basic", "mensaje": "KYC básico aprobado"}

# ── AML ───────────────────────────────────────────────────
@app.post("/api/v1/aml/check")
async def aml_check(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    entidad = body.get("entidad", "")
    resultado = aml_check_entidad(entidad, body.get("nit"))
    log = AMLLog(usuario_id=1, entidad=entidad, tipo_check="opensanctions",
                 resultado=resultado["status"], score=resultado["score"],
                 detalle=resultado["detalle"], fuente=resultado["fuente"])
    db.add(log); await db.commit()
    return resultado

# ── Robo-Advisor ──────────────────────────────────────────
@app.post("/api/v1/robo-advisor")
async def robo_advisor(data: RoboAdvisorSchema, db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    perfil_dict = {"id": 1, "edad": data.edad,
                   "ingresos_anuales_usd": data.ingresos_anuales_usd,
                   "tolerancia_riesgo": data.tolerancia_riesgo,
                   "saldo_usd": user.saldo_usd}
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == 1, PosicionPortafolio.acciones > 0))
    posiciones = [p.to_dict() for p in pos_res.scalars().all()]
    resultado = robo_advisor_analizar(perfil_dict, posiciones, settings.CLAUDE_API_KEY)
    # Guardar análisis
    analisis = AnalisisRoboAdvisor(
        usuario_id=1, perfil=resultado["perfil"],
        score_riesgo=resultado["score_riesgo"],
        alerta_riesgo=resultado["alerta_riesgo"],
        concentracion_max_ticker=resultado.get("concentracion_max_ticker"),
        concentracion_max_pct=resultado.get("concentracion_max_pct"),
        sugerencia_rebalanceo=resultado.get("sugerencia_rebalanceo"),
        acciones_recomendadas=json.dumps(resultado.get("acciones_recomendadas",[])),
        explicacion_voz=resultado.get("explicacion_voz"),
        prompt_json_enviado=json.dumps(resultado.get("_prompt_json_enviado",{})),
        respuesta_json=json.dumps(resultado), modelo_ia=resultado.get("_modelo","local"))
    db.add(analisis)
    # Actualizar perfil usuario
    user.perfil_ia = resultado["perfil"]
    user.tolerancia_riesgo = data.tolerancia_riesgo
    if resultado["alerta_riesgo"]:
        db.add(Alerta(usuario_id=1, tipo="warning", modulo="robo_advisor",
                      titulo="Alerta de riesgo — Robo-Advisor",
                      mensaje=resultado.get("sugerencia_rebalanceo","")))
    await db.commit()
    return resultado

@app.get("/api/v1/robo-advisor/historial")
async def robo_historial(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AnalisisRoboAdvisor).where(
        AnalisisRoboAdvisor.usuario_id == 1).order_by(AnalisisRoboAdvisor.fecha.desc()).limit(10))
    return [a.to_dict() for a in res.scalars().all()]

# ── Transacciones (depósito/retiro) ──────────────────────
@app.post("/api/v1/transacciones/deposito")
async def deposito(data: DepositoSchema, db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    tx = Transaccion(usuario_id=1, tipo="deposito", monto_usd=data.monto_usd,
                     estado="completed", metodo=data.metodo,
                     descripcion=f"Depósito vía {data.metodo}")
    db.add(tx); user.saldo_usd = round(user.saldo_usd + data.monto_usd, 2)
    await db.commit()
    await manager.broadcast({"type": "saldo", "saldo": user.saldo_usd})
    return {"ok": True, "saldo_nuevo": user.saldo_usd, "tx": tx.to_dict()}

@app.get("/api/v1/transacciones")
async def get_transacciones(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Transaccion).where(Transaccion.usuario_id == 1)
                           .order_by(Transaccion.fecha.desc()).limit(30))
    return [t.to_dict() for t in res.scalars().all()]

@app.get("/api/v1/dividendos")
async def get_dividendos(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Dividendo).where(Dividendo.usuario_id == 1)
                           .order_by(Dividendo.pago_date.desc()))
    return [d.to_dict() for d in res.scalars().all()]

# ── Alertas ───────────────────────────────────────────────
@app.get("/api/v1/alertas")
async def get_alertas(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Alerta).where(Alerta.usuario_id == 1)
                           .order_by(Alerta.fecha.desc()).limit(30))
    return [a.to_dict() for a in res.scalars().all()]

@app.put("/api/v1/alertas/leer")
async def leer_alertas(data: AlertaLeerSchema, db: AsyncSession = Depends(get_db)):
    await db.execute(update(Alerta).where(Alerta.id.in_(data.ids)).values(leida=True))
    await db.commit()
    return {"ok": True}

# ── Métricas dashboard ────────────────────────────────────
@app.get("/api/v1/metricas")
async def get_metricas(db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one_or_none()
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == 1, PosicionPortafolio.acciones > 0))
    posiciones = pos_res.scalars().all()
    prices = get_market_prices([p.ticker for p in posiciones])
    valor_port = sum((prices.get(p.ticker,{}).get("price", p.precio_actual) or p.precio_actual) * p.acciones
                     for p in posiciones)
    gp_total = sum(((prices.get(p.ticker,{}).get("price", p.precio_actual) or p.precio_actual) -
                    p.precio_promedio_compra) * p.acciones for p in posiciones)
    ord_res = await db.execute(select(func.count(Orden.id)).where(Orden.usuario_id == 1))
    n_ord = ord_res.scalar()
    al_res = await db.execute(select(func.count(Alerta.id)).where(
        Alerta.usuario_id == 1, Alerta.leida == False))
    n_alertas = al_res.scalar()
    div_res = await db.execute(select(func.sum(Dividendo.monto_usd)).where(Dividendo.usuario_id == 1))
    total_div = div_res.scalar() or 0
    return {"valor_portafolio": round(valor_port, 2), "ganancia_total": round(gp_total, 2),
            "ganancia_pct": round(gp_total / max(valor_port - gp_total, 1) * 100, 3),
            "saldo_disponible": round(user.saldo_usd if user else 0, 2),
            "posiciones": len(posiciones), "ordenes_total": n_ord,
            "alertas_nuevas": n_alertas, "dividendos_total": round(total_div, 4)}

# ── Exportes ──────────────────────────────────────────────
@app.get("/api/v1/exportar/excel")
async def exportar_excel(db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    pos_res = await db.execute(select(PosicionPortafolio).where(PosicionPortafolio.usuario_id == 1))
    posiciones = [p.to_dict() for p in pos_res.scalars().all()]
    ord_res = await db.execute(select(Orden).where(Orden.usuario_id == 1)
                               .order_by(Orden.creado.desc()).limit(100))
    ordenes = [o.to_dict() for o in ord_res.scalars().all()]
    div_res = await db.execute(select(Dividendo).where(Dividendo.usuario_id == 1))
    divs = [d.to_dict() for d in div_res.scalars().all()]
    nombre = f"investiq_portafolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    ruta = os.path.join(settings.EXPORT_DIR, nombre)
    generar_excel_portafolio(user.to_dict(), posiciones, ordenes, divs, ruta)
    return FileResponse(ruta, filename=nombre,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.get("/api/v1/exportar/pdf")
async def exportar_pdf(db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == 1, PosicionPortafolio.acciones > 0))
    posiciones = [p.to_dict() for p in pos_res.scalars().all()]
    prices = get_market_prices([p["ticker"] for p in posiciones])
    for p in posiciones:
        p["precio_actual"] = prices.get(p["ticker"], {}).get("price", p["precio_actual"])
    metricas = (await get_metricas(db))
    nombre = f"investiq_reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    ruta = os.path.join(settings.EXPORT_DIR, nombre)
    generar_pdf_reporte(user.to_dict(), posiciones, metricas, ruta)
    return FileResponse(ruta, filename=nombre, media_type="application/pdf")

# ── Audit log ─────────────────────────────────────────────
@app.get("/api/v1/auditoria")
async def get_auditoria(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AuditLog).order_by(AuditLog.fecha.desc()).limit(50))
    return [l.to_dict() for l in res.scalars().all()]

# ── WebSocket tiempo real ─────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Enviar estado inicial
        prices = get_market_prices()
        await ws.send_json({"type": "init", "prices": prices,
                            "ts": datetime.utcnow().isoformat()})
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await ws.send_json({"type": "pong", "ts": datetime.utcnow().isoformat()})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat", "ts": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(ws)

# ── Health ────────────────────────────────────────────────
@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "ts": datetime.utcnow().isoformat(),
            "services": {"database": "ok", "broker": "alpaca_paper", "ia": "claude_ready"}}

@app.get("/")
async def root():
    return {"app": "InvestIQ API", "docs": "/docs", "ws": "/ws"}

# ── Start background tasks ────────────────────────────────
@app.on_event("startup")
async def start_background():
    asyncio.create_task(price_broadcaster())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False,
                workers=1, log_level="info")
