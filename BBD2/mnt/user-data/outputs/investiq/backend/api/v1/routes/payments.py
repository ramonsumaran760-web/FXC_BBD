"""
api/v1/routes/payments.py — Endpoints de pagos
Stripe + MercadoPago + Crypto + Retiros
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os, logging
from datetime import datetime

from core.database import get_db
from models.models import Usuario, Transaccion, AuditLog
from services.payments import (
    stripe_crear_payment_intent, stripe_confirmar_pago, stripe_crear_cliente,
    mp_crear_preferencia, mp_verificar_pago,
    crypto_generar_direccion_deposito, verificar_config_pagos,
    procesar_webhook_stripe, procesar_webhook_mercadopago,
    stripe_retiro_bank_transfer
)

router = APIRouter(prefix="/pagos", tags=["Pagos"])
logger = logging.getLogger(__name__)

# ── Schemas ───────────────────────────────────────────────
class DepositoStripeSchema(BaseModel):
    monto_usd: float
    metodo: str = "stripe"

class DepositoMPSchema(BaseModel):
    monto_usd: float
    descripcion: Optional[str] = "Depósito InvestIQ"

class RetiroSchema(BaseModel):
    monto_usd: float
    metodo: str = "bank_transfer"
    cuenta_bancaria: Optional[dict] = None

class ConfirmarPagoSchema(BaseModel):
    payment_intent_id: Optional[str] = None
    payment_id: Optional[str] = None
    gateway: str = "stripe"

# ── Config pagos ──────────────────────────────────────────
@router.get("/config")
async def config_pagos():
    """Qué gateways están activos."""
    return verificar_config_pagos()

# ── Stripe ────────────────────────────────────────────────
@router.post("/stripe/intent")
async def crear_stripe_intent(data: DepositoStripeSchema, db: AsyncSession = Depends(get_db)):
    """Crea PaymentIntent en Stripe. El frontend completa con Stripe.js."""
    if data.monto_usd < 1:
        raise HTTPException(400, "Monto mínimo: $1 USD")
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    # Crear/recuperar cliente Stripe
    cliente = stripe_crear_cliente(user.email, user.nombre)
    # Crear PaymentIntent
    intent = stripe_crear_payment_intent(
        data.monto_usd, user.email,
        metadata={"usuario_id": str(user.id), "plataforma": "InvestIQ"})
    if "error" in intent:
        raise HTTPException(502, f"Error Stripe: {intent['error']}")
    # Registrar intento
    tx = Transaccion(usuario_id=user.id, tipo="deposito", monto_usd=data.monto_usd,
                     estado="pending", metodo="stripe",
                     referencia_externa=intent.get("id"),
                     descripcion=f"Depósito Stripe ${data.monto_usd}")
    db.add(tx)
    await db.commit()
    return {"client_secret": intent.get("client_secret"),
            "payment_intent_id": intent.get("id"),
            "monto_usd": data.monto_usd,
            "stripe_publishable_key": os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_demo"),
            "transaccion_id": tx.id}

@router.post("/stripe/confirmar")
async def confirmar_stripe(data: ConfirmarPagoSchema, db: AsyncSession = Depends(get_db)):
    """Confirma pago Stripe y acredita saldo."""
    resultado = stripe_confirmar_pago(data.payment_intent_id)
    if resultado.get("status") in ("succeeded", "demo_mode"):
        user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
        user = user_res.scalar_one()
        # Buscar transacción
        tx_res = await db.execute(select(Transaccion).where(
            Transaccion.referencia_externa == data.payment_intent_id))
        tx = tx_res.scalar_one_or_none()
        if tx and tx.estado == "pending":
            tx.estado = "completed"
            user.saldo_usd = round(user.saldo_usd + tx.monto_usd, 2)
            db.add(AuditLog(usuario_id=user.id, accion="DEPOSITO_STRIPE_OK",
                            modulo="pagos",
                            detalle=f"${tx.monto_usd} acreditado vía Stripe"))
            await db.commit()
            return {"ok": True, "saldo_nuevo": user.saldo_usd, "monto_acreditado": tx.monto_usd}
    return {"ok": False, "status": resultado.get("status"), "detalle": "Pago no confirmado"}

# ── Stripe Webhook ────────────────────────────────────────
@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None),
                         db: AsyncSession = Depends(get_db)):
    """Recibe y procesa webhooks automáticos de Stripe."""
    payload = await request.json()
    resultado = procesar_webhook_stripe(payload, stripe_signature or "")
    if resultado["accion"] == "acreditar_saldo":
        user_res = await db.execute(select(Usuario).where(Usuario.email == resultado.get("email")))
        user = user_res.scalar_one_or_none()
        if user:
            user.saldo_usd = round(user.saldo_usd + resultado["monto_usd"], 2)
            db.add(Transaccion(usuario_id=user.id, tipo="deposito",
                               monto_usd=resultado["monto_usd"], estado="completed",
                               metodo="stripe_webhook",
                               referencia_externa=resultado["payment_intent_id"],
                               descripcion="Depósito confirmado via webhook Stripe"))
            await db.commit()
            logger.info(f"Stripe webhook: ${resultado['monto_usd']} acreditado a {user.email}")
    return {"received": True}

# ── MercadoPago ───────────────────────────────────────────
@router.post("/mercadopago/preferencia")
async def crear_mp_preferencia(data: DepositoMPSchema, db: AsyncSession = Depends(get_db)):
    """Crea preferencia MercadoPago. Retorna URL de pago."""
    if data.monto_usd < 1:
        raise HTTPException(400, "Monto mínimo: $1 USD")
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    pref = mp_crear_preferencia(data.monto_usd, user.email, data.descripcion)
    if "error" in pref:
        raise HTTPException(502, f"Error MercadoPago: {pref['error']}")
    tx = Transaccion(usuario_id=user.id, tipo="deposito", monto_usd=data.monto_usd,
                     estado="pending", metodo="mercadopago",
                     referencia_externa=pref.get("id"),
                     descripcion=data.descripcion)
    db.add(tx); await db.commit()
    return {"preference_id": pref.get("id"),
            "init_point": pref.get("init_point"),
            "sandbox_init_point": pref.get("sandbox_init_point"),
            "transaccion_id": tx.id}

@router.get("/mercadopago/webhook")
@router.post("/mercadopago/webhook")
async def mp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """IPN/Webhook de MercadoPago."""
    params = dict(request.query_params)
    payment_id = params.get("id") or params.get("data.id")
    if not payment_id:
        body = await request.json()
        payment_id = body.get("data", {}).get("id")
    if payment_id:
        resultado = procesar_webhook_mercadopago(str(payment_id))
        if resultado["accion"] == "acreditar_saldo":
            user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
            user = user_res.scalar_one()
            monto_usd = round(resultado["monto"] / 3.7, 2)  # PEN → USD aprox
            user.saldo_usd = round(user.saldo_usd + monto_usd, 2)
            db.add(Transaccion(usuario_id=user.id, tipo="deposito",
                               monto_usd=monto_usd, estado="completed",
                               metodo="mercadopago", referencia_externa=str(payment_id),
                               descripcion="Depósito MercadoPago confirmado"))
            await db.commit()
    return {"ok": True}

# ── Crypto ────────────────────────────────────────────────
@router.get("/crypto/direccion")
async def crypto_direccion(moneda: str = "USDC", db: AsyncSession = Depends(get_db)):
    """Genera dirección de depósito crypto."""
    info = crypto_generar_direccion_deposito(1, moneda)
    return info

# ── Retiros ───────────────────────────────────────────────
@router.post("/retiro")
async def solicitar_retiro(data: RetiroSchema, db: AsyncSession = Depends(get_db)):
    """Procesa solicitud de retiro."""
    user_res = await db.execute(select(Usuario).where(Usuario.id == 1))
    user = user_res.scalar_one()
    if user.saldo_usd < data.monto_usd:
        raise HTTPException(400, f"Saldo insuficiente. Disponible: ${user.saldo_usd:.2f}")
    if data.monto_usd < 10:
        raise HTTPException(400, "Retiro mínimo: $10 USD")
    # Reservar saldo
    user.saldo_usd = round(user.saldo_usd - data.monto_usd, 2)
    tx = Transaccion(usuario_id=user.id, tipo="retiro", monto_usd=data.monto_usd,
                     estado="pending", metodo=data.metodo,
                     descripcion=f"Retiro ${data.monto_usd} vía {data.metodo}")
    db.add(tx)
    db.add(AuditLog(usuario_id=user.id, accion="RETIRO_SOLICITADO",
                    modulo="pagos", detalle=f"${data.monto_usd} vía {data.metodo}"))
    await db.commit()
    # Procesar según método
    resultado = {}
    if data.metodo == "bank_transfer" and data.cuenta_bancaria:
        resultado = stripe_retiro_bank_transfer(data.monto_usd, data.cuenta_bancaria)
    return {"ok": True, "transaccion_id": tx.id, "saldo_nuevo": user.saldo_usd,
            "estado": "pending", "tiempo_estimado": "1-3 días hábiles",
            "resultado_gateway": resultado}

# ── Historial ─────────────────────────────────────────────
@router.get("/historial")
async def historial_pagos(db: AsyncSession = Depends(get_db)):
    """Historial completo de depósitos y retiros."""
    res = await db.execute(select(Transaccion).where(Transaccion.usuario_id == 1)
                           .order_by(Transaccion.fecha.desc()).limit(50))
    return [t.to_dict() for t in res.scalars().all()]
