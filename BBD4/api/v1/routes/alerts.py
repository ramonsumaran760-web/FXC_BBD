"""
Alerts routes — gestión de alertas internas del usuario
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.models import Usuario, Alerta

router = APIRouter(prefix="/alertas", tags=["alertas"])


class AlertaLeerSchema(BaseModel):
    ids: list[int]


@router.get("")
async def get_alertas(limit: int = 30,
                       current_user: Usuario = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Alerta).where(Alerta.usuario_id == current_user.id)
        .order_by(Alerta.fecha.desc()).limit(limit))
    return [a.to_dict() for a in res.scalars().all()]


@router.put("/leer")
async def leer_alertas(data: AlertaLeerSchema,
                        current_user: Usuario = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Alerta)
        .where(Alerta.id.in_(data.ids), Alerta.usuario_id == current_user.id)
        .values(leida=True)
    )
    await db.commit()
    return {"ok": True, "marcadas": len(data.ids)}


@router.put("/leer-todas")
async def leer_todas(current_user: Usuario = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Alerta)
        .where(Alerta.usuario_id == current_user.id, Alerta.leida == False)
        .values(leida=True)
    )
    await db.commit()
    return {"ok": True}
