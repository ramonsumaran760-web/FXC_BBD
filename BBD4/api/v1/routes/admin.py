"""
Admin routes — panel de administración (rol: admin)
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import require_admin
from models.models import Usuario, Orden, Transaccion, AuditLog, AMLLog, WebhookLog

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
async def admin_dashboard(admin=Depends(require_admin),
                           db: AsyncSession = Depends(get_db)):
    total_users = (await db.execute(select(func.count(Usuario.id)))).scalar()
    active_users = (await db.execute(
        select(func.count(Usuario.id)).where(Usuario.activo == True))).scalar()
    total_orders = (await db.execute(select(func.count(Orden.id)))).scalar()
    aml_blocked = (await db.execute(
        select(func.count(Usuario.id)).where(Usuario.aml_status == "blocked"))).scalar()
    total_deposited = (await db.execute(
        select(func.sum(Transaccion.monto_usd)).where(
            Transaccion.tipo == "deposito",
            Transaccion.estado == "completed"))).scalar() or 0
    total_comisiones = (await db.execute(
        select(func.sum(Transaccion.monto_usd)).where(
            Transaccion.metodo == "comision",
            Transaccion.estado == "completed"))).scalar() or 0
    return {
        "usuarios_total": total_users,
        "usuarios_activos": active_users,
        "ordenes_total": total_orders,
        "bloqueados_aml": aml_blocked,
        "depositos_totales_usd": round(total_deposited, 2),
        "comisiones_usd": round(float(total_comisiones), 4),
    }


@router.get("/usuarios")
async def list_usuarios(page: int = 1, limit: int = 50,
                         admin=Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    offset = (page - 1) * limit
    res = await db.execute(select(Usuario).offset(offset).limit(limit))
    return [u.to_dict() for u in res.scalars().all()]


@router.patch("/usuarios/{user_id}/bloquear")
async def bloquear_usuario(user_id: int, admin=Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    user.activo = False
    db.add(AuditLog(usuario_id=admin.id, accion="ADMIN_BLOQUEAR_USUARIO",
                    modulo="admin", detalle=f"Usuario {user_id} bloqueado"))
    await db.commit()
    return {"ok": True, "usuario_id": user_id, "activo": False}


@router.patch("/usuarios/{user_id}/desbloquear")
async def desbloquear_usuario(user_id: int, admin=Depends(require_admin),
                               db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    user.activo = True
    user.aml_status = "clear"
    db.add(AuditLog(usuario_id=admin.id, accion="ADMIN_DESBLOQUEAR_USUARIO",
                    modulo="admin", detalle=f"Usuario {user_id} desbloqueado"))
    await db.commit()
    return {"ok": True, "usuario_id": user_id, "activo": True}


@router.get("/aml/logs")
async def aml_logs(limit: int = 100, admin=Depends(require_admin),
                    db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AMLLog).order_by(AMLLog.fecha.desc()).limit(limit))
    return [l.to_dict() for l in res.scalars().all()]


@router.get("/webhooks/logs")
async def webhook_logs(limit: int = 50, admin=Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(WebhookLog).order_by(WebhookLog.recibido.desc()).limit(limit))
    return [l.to_dict() for l in res.scalars().all()]
