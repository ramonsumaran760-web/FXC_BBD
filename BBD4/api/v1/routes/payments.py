"""
Payments routes — Stripe + MercadoPago con autenticación JWT real
"""
import os, logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.models import Usuario, Transaccion, AuditLog
from services.notification_service import notificar_deposito

router = APIRouter(prefix="/pagos", tags=["pagos"])
logger = logging.getLogger(__name__)


class DepositoStripeSchema(BaseModel):
    monto_usd: float
    metodo: str = "stripe"

class DepositoMPSchema(BaseModel):
    monto_usd: float
    descripcion: Optional[str] = "Depósito InvestIQ"


@router.get("/config")
async def config_pagos():
    mp_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    mp_modo = "no_configurado"
    if mp_token.startswith("APP_USR-"):
        mp_modo = "PRODUCCION"
    elif mp_token.startswith("TEST-"):
        mp_modo = "PRUEBA_TEST"
    elif mp_token:
        mp_modo = "token_desconocido"
    return {
        "stripe": {"activo": bool(os.getenv("STRIPE_SECRET_KEY")), "moneda": "usd"},
        "mercadopago": {
            "activo": bool(mp_token),
            "moneda": "pen",
            "modo": mp_modo,
            "token_prefix": mp_token[:12] + "..." if mp_token else "vacío"
        },
        "crypto": {"activo": False},
        "monto_minimo": 1.0, "monto_maximo": 200000.0
    }


@router.post("/stripe/intent")
async def crear_stripe_intent(data: DepositoStripeSchema,
                               current_user: Usuario = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    if data.monto_usd < 1:
        raise HTTPException(400, "Monto mínimo: $1 USD")

    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        # Demo mode
        return {"client_secret": "pi_demo_secret", "payment_intent_id": "pi_demo",
                "monto_usd": data.monto_usd, "modo": "demo",
                "stripe_publishable_key": "pk_test_demo"}

    try:
        import stripe
        stripe.api_key = stripe_key
        intent = stripe.PaymentIntent.create(
            amount=int(data.monto_usd * 100),
            currency="usd",
            metadata={"usuario_id": str(current_user.id)}
        )
        tx = Transaccion(usuario_id=current_user.id, tipo="deposito",
                         monto_usd=data.monto_usd, estado="pending",
                         metodo="stripe", referencia_externa=intent.id,
                         descripcion=f"Depósito Stripe ${data.monto_usd}")
        db.add(tx)
        await db.commit()
        return {"client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "monto_usd": data.monto_usd,
                "stripe_publishable_key": os.getenv("STRIPE_PUBLISHABLE_KEY", "")}
    except Exception as e:
        raise HTTPException(502, f"Error Stripe: {e}")


@router.post("/stripe/confirmar")
async def confirmar_stripe(payment_intent_id: str,
                            current_user: Usuario = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Confirma un pago exitoso y acredita saldo."""
    from sqlalchemy import select, update
    res = await db.execute(select(Transaccion).where(
        Transaccion.referencia_externa == payment_intent_id,
        Transaccion.usuario_id == current_user.id))
    tx = res.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Transacción no encontrada")
    if tx.estado == "completed":
        return {"ok": True, "mensaje": "Ya procesado", "saldo": current_user.saldo_usd}

    tx.estado = "completed"
    current_user.saldo_usd = round(current_user.saldo_usd + tx.monto_usd, 2)
    db.add(AuditLog(usuario_id=current_user.id, accion="PAGO_CONFIRMADO",
                    modulo="pagos", detalle=f"Stripe ${tx.monto_usd}"))
    await db.commit()

    notificar_deposito(current_user.id, current_user.email,
                       current_user.phone or "", tx.monto_usd)
    return {"ok": True, "saldo_nuevo": current_user.saldo_usd}


@router.post("/mercadopago/preferencia")
async def crear_mp_preferencia(data: DepositoMPSchema,
                                current_user: Usuario = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    mp_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    if not mp_token:
        return {"init_point": "https://sandbox.mercadopago.com/demo",
                "preference_id": "demo_pref", "modo": "demo", "monto_usd": data.monto_usd}
    try:
        import mercadopago
        sdk = mercadopago.SDK(mp_token)

        # PEN para cuentas Perú — back_urls y notification_url obligatorios
        # para que el botón "Pagar" se active en el checkout de MP.
        # El monto se acepta en soles (PEN); el equivalente USD se guarda aparte.
        preference_data = {
            "items": [{
                "title": data.descripcion,
                "quantity": 1,
                "unit_price": float(data.monto_usd),
                "currency_id": "PEN",
            }],
            "external_reference": str(current_user.id),
            "back_urls": {
                "success": "https://fxc-bbd.onrender.com/?dep=ok",
                "failure": "https://fxc-bbd.onrender.com/?dep=fail",
                "pending": "https://fxc-bbd.onrender.com/?dep=pending",
            },
            "auto_return": "approved",
            "notification_url": "https://fxc-bbd.onrender.com/api/v1/webhooks/mercadopago",
            "statement_descriptor": "InvestIQ",
            "payer": {"email": current_user.email},
        }
        result = sdk.preference().create(preference_data)
        pref = result["response"]
        if not pref.get("id"):
            raise Exception(f"MP no devolvió preference_id: {pref}")

        tx = Transaccion(usuario_id=current_user.id, tipo="deposito",
                         monto_usd=data.monto_usd, estado="pending",
                         metodo="mercadopago", referencia_externa=pref.get("id"),
                         descripcion=data.descripcion)
        db.add(tx)
        await db.commit()
        return {"init_point": pref.get("init_point"),
                "preference_id": pref.get("id"),
                "monto": data.monto_usd,
                "currency": "PEN"}
    except Exception as e:
        raise HTTPException(502, f"Error MercadoPago: {e}")


# ── Plin ──────────────────────────────────────────────────

class PlinSolicitudSchema(BaseModel):
    monto_pen: float
    numero_operacion: str

class PlinConfirmarSchema(BaseModel):
    tx_id: int

@router.get("/plin/info")
async def plin_info():
    """Retorna los datos del número Plin del negocio para que el cliente pueda pagar."""
    from core.config import settings
    if not settings.PLIN_PHONE:
        raise HTTPException(503, "Plin no configurado. Agrega PLIN_PHONE en variables de entorno.")
    return {
        "telefono": settings.PLIN_PHONE,
        "titular": settings.PLIN_TITULAR,
        "activo": True,
        "instrucciones": [
            f"Abre tu app bancaria (BBVA, Scotiabank, Interbank o BanBif)",
            f"Selecciona 'Plin' y busca el número {settings.PLIN_PHONE}",
            f"Envía el monto exacto en Soles (S/.)",
            "Copia el número de operación y regístralo aquí",
        ]
    }

@router.post("/plin/solicitud")
async def plin_solicitud(
    data: PlinSolicitudSchema,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """El usuario registra su pago Plin. Queda pendiente hasta que el admin confirme."""
    from core.config import settings
    if not settings.PLIN_PHONE:
        raise HTTPException(503, "Plin no configurado")
    if data.monto_pen < 5:
        raise HTTPException(400, "Monto mínimo S/.5")
    if not data.numero_operacion.strip():
        raise HTTPException(400, "Ingresa el número de operación Plin")

    tx = Transaccion(
        usuario_id=current_user.id,
        tipo="deposito",
        monto_usd=data.monto_pen,          # se guarda en PEN, admin convierte si aplica
        estado="pending",
        metodo="plin",
        referencia_externa=data.numero_operacion.strip(),
        descripcion=f"Depósito Plin S/.{data.monto_pen} — Op.{data.numero_operacion.strip()}"
    )
    db.add(tx)
    db.add(AuditLog(
        usuario_id=current_user.id, accion="PLIN_SOLICITUD",
        modulo="pagos",
        detalle=f"Plin S/.{data.monto_pen} op:{data.numero_operacion}"
    ))
    await db.commit()
    return {
        "ok": True,
        "tx_id": tx.id,
        "estado": "pending",
        "mensaje": "Solicitud recibida. El admin verificará tu pago y acreditará tu saldo en minutos."
    }

@router.post("/plin/confirmar")
async def plin_confirmar(
    data: PlinConfirmarSchema,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin confirma y acredita un depósito Plin pendiente."""
    from sqlalchemy import select
    if current_user.rol != "admin":
        raise HTTPException(403, "Solo administradores")

    res = await db.execute(select(Transaccion).where(
        Transaccion.id == data.tx_id,
        Transaccion.metodo == "plin",
        Transaccion.estado == "pending"
    ))
    tx = res.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Transacción no encontrada o ya procesada")

    res_u = await db.execute(select(Usuario).where(Usuario.id == tx.usuario_id))
    usuario = res_u.scalar_one_or_none()
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")

    tx.estado = "completed"
    usuario.saldo_usd = round(usuario.saldo_usd + tx.monto_usd, 2)
    db.add(AuditLog(
        usuario_id=current_user.id, accion="PLIN_CONFIRMADO",
        modulo="pagos",
        detalle=f"Plin tx#{tx.id} S/.{tx.monto_usd} → usuario {usuario.email}"
    ))
    await db.commit()
    return {"ok": True, "saldo_nuevo": usuario.saldo_usd, "usuario": usuario.email}
