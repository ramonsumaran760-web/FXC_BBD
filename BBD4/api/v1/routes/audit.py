"""
Audit routes — log de auditoría (solo admin ve todo; usuario solo ve el suyo)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user, require_admin
from models.models import Usuario, AuditLog

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@router.get("")
async def get_auditoria(
    limit: int = Query(50, le=200),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin ve todos los logs; usuario regular solo los suyos."""
    query = select(AuditLog).order_by(AuditLog.fecha.desc()).limit(limit)
    if current_user.rol != "admin":
        query = select(AuditLog).where(AuditLog.usuario_id == current_user.id)\
                                .order_by(AuditLog.fecha.desc()).limit(limit)
    res = await db.execute(query)
    return [l.to_dict() for l in res.scalars().all()]
