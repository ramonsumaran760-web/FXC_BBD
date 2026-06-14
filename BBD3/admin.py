"""
api/v1/routes/admin.py — Owner Portal: gestión usuarios, sistema, push
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

from core.database import get_db
from models.models import Usuario, Orden, PosicionPortafolio, Transaccion, AuditLog, Alerta
from services.push_service import (registrar_suscripcion, broadcast_push,
                                    push_alerta_mercado, generar_vapid_keys)
from services.email_service import email_bienvenida

router = APIRouter(prefix="/admin", tags=["Admin"])

# ── Stats globales ────────────────────────────────────────
@router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)):
    """KPIs globales del sistema para Owner Portal."""
    n_users = (await db.execute(select(func.count(Usuario.id)))).scalar()
    n_kyc = (await db.execute(select(func.count(Usuario.id)).where(Usuario.kyc_verificado == True))).scalar()
    n_ordenes = (await db.execute(select(func.count(Orden.id)))).scalar()
    vol_total = (await db.execute(select(func.sum(Orden.monto_usd)).where(Orden.estado == "filled"))).scalar() or 0
    n_tx = (await db.execute(select(func.count(Transaccion.id)))).scalar()
    dep_total = (await db.execute(select(func.sum(Transaccion.monto_usd)).where(Transaccion.tipo == "deposito", Transaccion.estado == "completed"))).scalar() or 0
    return {
        "usuarios_total": n_users,
        "usuarios_kyc_ok": n_kyc,
        "ordenes_total": n_ordenes,
        "volumen_operado_usd": round(vol_total, 2),
        "transacciones_total": n_tx,
        "depositos_total_usd": round(dep_total, 2),
        "uptime": "OK",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

# ── Usuarios ──────────────────────────────────────────────
@router.get("/usuarios")
async def get_usuarios(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).order_by(Usuario.creado.desc()).limit(100))
    return [u.to_dict() for u in res.scalars().all()]

@router.get("/usuarios/{uid}")
async def get_usuario(uid: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.id == uid))
    u = res.scalar_one_or_none()
    if not u: raise HTTPException(404, "Usuario no encontrado")
    # Portafolio y órdenes del usuario
    pos_res = await db.execute(select(PosicionPortafolio).where(PosicionPortafolio.usuario_id == uid))
    pos = [p.to_dict() for p in pos_res.scalars().all()]
    ord_res = await db.execute(select(Orden).where(Orden.usuario_id == uid).order_by(Orden.creado.desc()).limit(20))
    ords = [o.to_dict() for o in ord_res.scalars().all()]
    return {"usuario": u.to_dict(), "portafolio": pos, "ordenes": ords}

class UpdateUsuarioSchema(BaseModel):
    activo: Optional[bool] = None
    rol: Optional[str] = None
    kyc_nivel: Optional[str] = None
    kyc_verificado: Optional[bool] = None

@router.put("/usuarios/{uid}")
async def update_usuario(uid: int, data: UpdateUsuarioSchema, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.id == uid))
    u = res.scalar_one_or_none()
    if not u: raise HTTPException(404, "Usuario no encontrado")
    if data.activo is not None: u.activo = data.activo
    if data.rol: u.rol = data.rol
    if data.kyc_nivel: u.kyc_nivel = data.kyc_nivel
    if data.kyc_verificado is not None: u.kyc_verificado = data.kyc_verificado
    db.add(AuditLog(usuario_id=1, accion="ADMIN_UPDATE_USER", modulo="admin",
                    detalle=f"Usuario #{uid} actualizado"))
    await db.commit()
    return u.to_dict()

# ── Push notifications ────────────────────────────────────
class PushSubscribeSchema(BaseModel):
    usuario_id: int
    subscription: dict

@router.post("/push/subscribe")
async def push_subscribe(data: PushSubscribeSchema):
    ok = registrar_suscripcion(data.usuario_id, data.subscription)
    return {"ok": ok}

@router.get("/push/vapid-key")
async def push_vapid_key():
    return {"vapid_public_key": os.getenv("VAPID_PUBLIC_KEY", ""),
            "nota": "Configurar VAPID_PUBLIC_KEY en .env para push reales"}

class BroadcastSchema(BaseModel):
    titulo: str
    mensaje: str
    tipo: str = "info"

@router.post("/push/broadcast")
async def push_broadcast(data: BroadcastSchema):
    n = broadcast_push(data.titulo, data.mensaje, data.tipo)
    return {"ok": True, "enviados": n}

@router.get("/push/vapid/generar")
async def generar_vapid():
    return generar_vapid_keys()

# ── Emails ────────────────────────────────────────────────
class TestEmailSchema(BaseModel):
    email: str
    tipo: str = "bienvenida"

@router.post("/email/test")
async def test_email(data: TestEmailSchema):
    ok = email_bienvenida(data.email, "Usuario Test")
    return {"ok": ok, "nota": "Sin SENDGRID_API_KEY solo se loggea en consola"}

# ── Sistema ───────────────────────────────────────────────
@router.get("/sistema/db-size")
async def db_size(db: AsyncSession = Depends(get_db)):
    """Tamaño de cada tabla en la base de datos."""
    tablas = ["usuarios","activos","ordenes","portafolio","transacciones",
              "alertas","audit_log","aml_logs","analisis_robo_advisor","dividendos"]
    resultado = {}
    for tabla in tablas:
        try:
            r = await db.execute(text(f"SELECT COUNT(*) FROM {tabla}"))
            resultado[tabla] = r.scalar()
        except Exception:
            resultado[tabla] = "—"
    return resultado

@router.post("/sistema/seed")
async def re_seed(db: AsyncSession = Depends(get_db)):
    """Re-ejecutar seed (solo desarrollo)."""
    from main import seed_inicial
    await seed_inicial(db)
    return {"ok": True, "mensaje": "Seed ejecutado"}

@router.delete("/sistema/alertas-leidas")
async def limpiar_alertas(db: AsyncSession = Depends(get_db)):
    """Elimina alertas ya leídas."""
    from sqlalchemy import delete
    await db.execute(delete(Alerta).where(Alerta.leida == True))
    await db.commit()
    return {"ok": True}
