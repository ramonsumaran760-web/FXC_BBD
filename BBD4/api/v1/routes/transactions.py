"""
Transactions routes — depósitos, retiros, dividendos
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.models import Usuario, Transaccion, Dividendo, AuditLog
from services.notification_service import notificar_deposito

router = APIRouter(prefix="/transacciones", tags=["transacciones"])


class DepositoSchema(BaseModel):
    monto_usd: float = Field(..., ge=1)
    metodo: str = "bank_transfer"

class RetiroSchema(BaseModel):
    monto_usd: float = Field(..., ge=1)
    metodo: str = "bank_transfer"
    cuenta_destino: str = ""


@router.post("/deposito")
async def deposito(data: DepositoSchema,
                   current_user: Usuario = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    tx = Transaccion(usuario_id=current_user.id, tipo="deposito",
                     monto_usd=data.monto_usd, estado="completed",
                     metodo=data.metodo,
                     descripcion=f"Depósito vía {data.metodo}")
    db.add(tx)
    current_user.saldo_usd = round(current_user.saldo_usd + data.monto_usd, 2)
    db.add(AuditLog(usuario_id=current_user.id, accion="DEPOSITO", modulo="transacciones",
                    detalle=f"${data.monto_usd} vía {data.metodo}"))
    await db.commit()

    notificar_deposito(current_user.id, current_user.email,
                       current_user.phone or "", data.monto_usd)

    return {"ok": True, "saldo_nuevo": current_user.saldo_usd, "tx": tx.to_dict()}


@router.post("/retiro")
async def retiro(data: RetiroSchema,
                 current_user: Usuario = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    if current_user.saldo_usd < data.monto_usd:
        raise HTTPException(400, f"Saldo insuficiente: ${current_user.saldo_usd:.2f}")
    if current_user.kyc_nivel == "none":
        raise HTTPException(403, "KYC requerido para retiros")

    tx = Transaccion(usuario_id=current_user.id, tipo="retiro",
                     monto_usd=data.monto_usd, estado="pending",
                     metodo=data.metodo,
                     descripcion=f"Retiro a cuenta {data.cuenta_destino[:20] or '***'}")
    db.add(tx)
    current_user.saldo_usd = round(current_user.saldo_usd - data.monto_usd, 2)
    db.add(AuditLog(usuario_id=current_user.id, accion="RETIRO", modulo="transacciones",
                    detalle=f"${data.monto_usd} retiro solicitado"))
    await db.commit()
    return {"ok": True, "saldo_nuevo": current_user.saldo_usd, "tx": tx.to_dict()}


@router.get("")
async def get_transacciones(limit: int = 30,
                             current_user: Usuario = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Transaccion).where(Transaccion.usuario_id == current_user.id)
        .order_by(Transaccion.fecha.desc()).limit(limit))
    return [t.to_dict() for t in res.scalars().all()]


@router.get("/dividendos")
async def get_dividendos(current_user: Usuario = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Dividendo).where(Dividendo.usuario_id == current_user.id)
        .order_by(Dividendo.pago_date.desc()))
    return [d.to_dict() for d in res.scalars().all()]
