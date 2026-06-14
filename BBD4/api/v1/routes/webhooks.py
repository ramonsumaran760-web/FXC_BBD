"""
Webhooks routes — recibe eventos de Alpaca y Stripe en tiempo real.

Alpaca envía: fill, partial_fill, cancelled, expired, replaced
Validación: HMAC-SHA256 del body con ALPACA_WEBHOOK_SECRET
"""
import hashlib, hmac, json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.config import settings
from models.models import Orden, WebhookLog, AuditLog
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
