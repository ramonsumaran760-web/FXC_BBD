"""
Notifications routes — gestión de suscripciones push (Web Push / FCM)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.models import Usuario, PushSubscription
from services.notification_service import registrar_push_subscription

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


class PushSubscriptionSchema(BaseModel):
    endpoint: str
    p256dh: Optional[str] = None
    auth: Optional[str] = None
    fcm_token: Optional[str] = None
    plataforma: str = "web"

class TestPushSchema(BaseModel):
    titulo: str = "InvestIQ — prueba"
    mensaje: str = "Notificación de prueba"


@router.post("/push/subscribe")
async def subscribe_push(data: PushSubscriptionSchema,
                          current_user: Usuario = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Registra suscripción Web Push o FCM del usuario."""
    # Guardar en BD
    res = await db.execute(select(PushSubscription).where(
        PushSubscription.usuario_id == current_user.id,
        PushSubscription.endpoint == data.endpoint))
    existing = res.scalar_one_or_none()

    if existing:
        existing.p256dh = data.p256dh
        existing.auth = data.auth
        existing.fcm_token = data.fcm_token
        existing.activa = True
    else:
        db.add(PushSubscription(
            usuario_id=current_user.id,
            endpoint=data.endpoint,
            p256dh=data.p256dh, auth=data.auth,
            fcm_token=data.fcm_token,
            plataforma=data.plataforma
        ))

    # Registrar en memoria también (para envío inmediato)
    if data.p256dh and data.auth:
        registrar_push_subscription(current_user.id, {
            "endpoint": data.endpoint,
            "keys": {"p256dh": data.p256dh, "auth": data.auth}
        })

    await db.commit()
    return {"ok": True, "mensaje": "Suscripción push registrada"}


@router.delete("/push/unsubscribe")
async def unsubscribe_push(endpoint: str,
                            current_user: Usuario = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PushSubscription).where(
        PushSubscription.usuario_id == current_user.id,
        PushSubscription.endpoint == endpoint))
    sub = res.scalar_one_or_none()
    if sub:
        sub.activa = False
        await db.commit()
    return {"ok": True}


@router.post("/push/test")
async def test_push(data: TestPushSchema,
                     current_user: Usuario = Depends(get_current_user)):
    from services.notification_service import send_push
    ok = send_push(current_user.id, data.titulo, data.mensaje, "info", "/")
    return {"ok": ok, "mensaje": "Push enviado" if ok else "Sin suscripción activa"}


@router.get("/vapid-public-key")
async def get_vapid_key():
    import os
    key = os.getenv("VAPID_PUBLIC_KEY", "")
    if not key:
        return {"vapid_public_key": None, "modo": "demo"}
    return {"vapid_public_key": key, "modo": "production"}
