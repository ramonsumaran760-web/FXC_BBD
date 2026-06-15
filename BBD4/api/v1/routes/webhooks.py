"""
Webhooks routes — recibe eventos de Alpaca, Stripe y MercadoPago en tiempo real.
"""
import hashlib, hmac, json, os, requests as req_lib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.config import settings
from models.models import Orden, WebhookLog, AuditLog, Transaccion, Usuario
from services.notification_service import notificar_orden_ejecutada

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/alpaca")
async def alpaca_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Endpoint para eventos de Alpaca via webhook.
    Actualiza el estado de las órdenes automáticamente cuando se llenan/cancelan.
    """
    body = await request.body()

    # Verificar firma HMAC si está configurado el secret
    if settings.ALPACA_WEBHOOK_SECRET:
        signature = request.headers.get("X-Signature", "")
        expected = hmac.new(
            settings.ALPACA_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, "Firma de webhook inválida")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Payload JSON inválido")

    event_type = event.get("event", "")
    broker_order_id = event.get("order", {}).get("id", "")

    # Registrar el webhook
    log = WebhookLog(
        fuente="alpaca", evento=event_type,
        payload_json=body.decode(),
        broker_order_id=broker_order_id
    )
    db.add(log)

    if event_type in ("fill", "partial_fill", "cancelled", "expired"):
        res = await db.execute(
            select(Orden).where(Orden.broker_order_id == broker_order_id))
        orden = res.scalar_one_or_none()

        if orden:
            mapa_estado = {
                "fill": "filled", "partial_fill": "partially_filled",
                "cancelled": "cancelled", "expired": "cancelled"
            }
            orden.estado = mapa_estado.get(event_type, orden.estado)

            if event_type == "fill":
                filled_price = float(event.get("order", {}).get("filled_avg_price", 0) or 0)
                if filled_price:
                    orden.precio_ejecucion = filled_price
                orden.ejecutado = datetime.now(timezone.utc)

            db.add(AuditLog(
                usuario_id=orden.usuario_id,
                accion=f"WEBHOOK_{event_type.upper()}",
                modulo="webhooks",
                detalle=f"Orden {broker_order_id} — {event_type}"
            ))

            if event_type == "fill" and orden.usuario_id:
                from sqlalchemy import select as sq
                from models.models import Usuario
                u_res = await db.execute(sq(Usuario).where(Usuario.id == orden.usuario_id))
                user = u_res.scalar_one_or_none()
                if user:
                    notificar_orden_ejecutada(
                        user.id, user.email, user.phone or "",
                        orden.ticker, orden.tipo, orden.monto_usd)

            log.procesado = True

    await db.commit()
    return {"ok": True, "evento": event_type}


@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Endpoint para eventos de Stripe (pagos de suscripción).
    Verifica firma con STRIPE_WEBHOOK_SECRET.
    """
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if settings.STRIPE_WEBHOOK_SECRET:
        try:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY
            event = stripe.Webhook.construct_event(body, sig, settings.STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            raise HTTPException(400, f"Webhook Stripe inválido: {e}")
    else:
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(400, "Payload inválido")

    log = WebhookLog(fuente="stripe", evento=event.get("type", ""),
                     payload_json=body.decode(), procesado=True)
    db.add(log)
    await db.commit()
    return {"ok": True, "evento": event.get("type")}


@router.post("/mercadopago")
async def mercadopago_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    IPN/Webhook de MercadoPago. Recibe notificaciones de pago y acredita saldo.
    Configurar en MercadoPago → Notificaciones → URL:
    https://fxc-bbd.onrender.com/api/v1/webhooks/mercadopago
    """
    body = await request.body()
    try:
        event = json.loads(body)
    except Exception:
        raise HTTPException(400, "Payload inválido")

    log = WebhookLog(fuente="mercadopago", evento=event.get("type", "unknown"),
                     payload_json=body.decode())
    db.add(log)

    # Solo procesamos eventos de tipo "payment"
    if event.get("type") != "payment":
        await db.commit()
        return {"ok": True, "ignorado": True}

    payment_id = event.get("data", {}).get("id")
    if not payment_id:
        await db.commit()
        return {"ok": True, "ignorado": True}

    # Verificar el pago con la API de MercadoPago
    mp_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    if not mp_token:
        await db.commit()
        return {"ok": False, "error": "token_not_configured"}

    try:
        resp = req_lib.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {mp_token}"},
            timeout=10,
        )
        if not resp.ok:
            raise Exception(f"MP API {resp.status_code}")
        pago = resp.json()
    except Exception as e:
        log.procesado = False
        await db.commit()
        raise HTTPException(502, f"Error verificando pago MP: {e}")

    status = pago.get("status")
    external_ref = pago.get("external_reference")  # usuario_id
    monto = float(pago.get("transaction_amount", 0))

    if status != "approved" or not external_ref or monto <= 0:
        log.procesado = True
        await db.commit()
        return {"ok": True, "status": status, "procesado": False}

    # Buscar transacción pendiente por preference_id o crear nueva
    pref_id = str(pago.get("order", {}).get("id", ""))
    res_tx = await db.execute(
        select(Transaccion).where(
            Transaccion.referencia_externa == pref_id,
            Transaccion.estado == "pending"
        )
    )
    tx = res_tx.scalar_one_or_none()

    res_u = await db.execute(select(Usuario).where(Usuario.id == int(external_ref)))
    usuario = res_u.scalar_one_or_none()
    if not usuario:
        await db.commit()
        return {"ok": False, "error": "usuario_no_encontrado"}

    # Evitar doble crédito
    res_dup = await db.execute(
        select(Transaccion).where(
            Transaccion.referencia_externa == str(payment_id),
            Transaccion.estado == "completed"
        )
    )
    if res_dup.scalar_one_or_none():
        await db.commit()
        return {"ok": True, "duplicado": True}

    if tx:
        tx.estado = "completed"
        tx.referencia_externa = str(payment_id)
    else:
        tx = Transaccion(
            usuario_id=usuario.id, tipo="deposito", monto_usd=monto,
            estado="completed", metodo="mercadopago",
            referencia_externa=str(payment_id),
            descripcion=f"Depósito MercadoPago #{payment_id}"
        )
        db.add(tx)

    usuario.saldo_usd = round(usuario.saldo_usd + monto, 2)
    db.add(AuditLog(
        usuario_id=usuario.id, accion="PAGO_MP_CONFIRMADO",
        modulo="pagos", detalle=f"MercadoPago #{payment_id} ${monto}"
    ))
    log.procesado = True
    await db.commit()
    return {"ok": True, "acreditado": monto, "saldo_nuevo": usuario.saldo_usd}
