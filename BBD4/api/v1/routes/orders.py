"""
Orders routes — CRUD órdenes + stop-loss / take-profit automáticos
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user, firmar_orden, verificar_firma, generar_nonce
from core.rate_limit import limiter, get_limit
from core.config import settings
from models.models import (Usuario, Orden, PosicionPortafolio, AuditLog, Alerta,
                            OrdenAutomatica, TaxLot)
from services.services import alpaca_place_order, alpaca_cancel_order, get_market_prices
from services.notification_service import notificar_orden_ejecutada

router = APIRouter(prefix="/ordenes", tags=["ordenes"])


class OrdenSchema(BaseModel):
    ticker: str
    monto_usd: float = Field(..., ge=1, le=50000)
    tipo: str = "buy"
    tipo_orden: str = "market"
    limit_price: Optional[float] = None


class StopLossSchema(BaseModel):
    ticker: str
    tipo: str = "stop_loss"       # stop_loss | take_profit | trailing_stop
    precio_trigger: float = Field(..., gt=0)
    porcentaje_pos: float = Field(100.0, ge=1, le=100)
    precio_trail_pct: Optional[float] = None


@router.post("")
@limiter.limit(get_limit("ordenes_crear"))
async def crear_orden(data: OrdenSchema, request: Request,
                      current_user: Usuario = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if data.monto_usd < settings.MIN_ORDER_USD:
        raise HTTPException(400, f"Monto mínimo: ${settings.MIN_ORDER_USD}")
    if current_user.aml_status == "blocked":
        raise HTTPException(403, "Cuenta bloqueada por AML")
    if data.tipo == "buy" and current_user.saldo_usd < data.monto_usd:
        raise HTTPException(400, f"Saldo insuficiente. Disponible: ${current_user.saldo_usd:.2f}")

    # Firma ECDSA
    nonce = generar_nonce()
    datos_firma = {"ticker": data.ticker, "monto_usd": data.monto_usd,
                   "tipo": data.tipo, "ts": str(datetime.utcnow()), "nonce": nonce}
    firma = firmar_orden(datos_firma)
    firma_ok = verificar_firma(datos_firma, firma)

    # Ejecutar en broker
    broker_resp = alpaca_place_order(
        settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET,
        data.ticker, data.monto_usd, data.tipo, data.tipo_orden, data.limit_price)

    if "error" in broker_resp:
        raise HTTPException(502, f"Error broker: {broker_resp['error']}")

    price = float(broker_resp.get("filled_avg_price", 0) or 0)
    fracs = float(broker_resp.get("filled_qty", 0) or 0)
    if fracs == 0 and price > 0:
        fracs = round(data.monto_usd / price, 8)

    orden = Orden(
        usuario_id=current_user.id, ticker=data.ticker,
        tipo=data.tipo, tipo_orden=data.tipo_orden,
        monto_usd=data.monto_usd, acciones=fracs,
        precio_ejecucion=price, estado="filled",
        broker="alpaca_paper", broker_order_id=broker_resp.get("id"),
        firma_ecdsa=firma, firma_verificada=firma_ok,
        nonce=nonce, ip_origen=request.client.host if request.client else "",
        aml_check="clear", creado=datetime.utcnow(), ejecutado=datetime.utcnow()
    )
    db.add(orden)
    await db.flush()

    # Actualizar saldo y posición
    if data.tipo == "buy":
        current_user.saldo_usd = round(current_user.saldo_usd - data.monto_usd, 2)
        await _actualizar_posicion_compra(db, current_user.id, data.ticker, fracs, price)
        # Crear tax lot para FIFO/LIFO
        db.add(TaxLot(usuario_id=current_user.id, ticker=data.ticker,
                      acciones_originales=fracs, acciones_restantes=fracs,
                      precio_costo=price, fecha_compra=datetime.utcnow(),
                      orden_id=orden.id))

    elif data.tipo == "sell":
        current_user.saldo_usd = round(current_user.saldo_usd + data.monto_usd, 2)
        await _actualizar_posicion_venta(db, current_user.id, data.ticker, fracs, price)
        await _consumir_tax_lots_fifo(db, current_user.id, data.ticker, fracs)

    db.add(AuditLog(usuario_id=current_user.id, accion="ORDEN_EJECUTADA",
                    modulo="broker",
                    detalle=f"{data.tipo.upper()} {data.ticker} ${data.monto_usd} = {fracs} acc @ ${price}",
                    ip=request.client.host if request.client else ""))
    await db.commit()

    notificar_orden_ejecutada(current_user.id, current_user.email,
                               current_user.phone or "",
                               data.ticker, data.tipo, data.monto_usd)

    return {**orden.to_dict(), "firma_ok": firma_ok, "broker": broker_resp,
            "saldo_nuevo": current_user.saldo_usd}


@router.get("")
async def get_ordenes(limit: int = 50,
                      current_user: Usuario = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Orden).where(Orden.usuario_id == current_user.id)
                           .order_by(Orden.creado.desc()).limit(limit))
    return [o.to_dict() for o in res.scalars().all()]


@router.delete("/{orden_id}")
async def cancelar_orden(orden_id: int,
                         current_user: Usuario = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Orden).where(
        Orden.id == orden_id, Orden.usuario_id == current_user.id))
    orden = res.scalar_one_or_none()
    if not orden:
        raise HTTPException(404, "Orden no encontrada")
    if orden.estado == "filled":
        raise HTTPException(400, "Orden ya ejecutada, no se puede cancelar")
    if orden.broker_order_id:
        alpaca_cancel_order(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET,
                            orden.broker_order_id)
    orden.estado = "cancelled"
    await db.commit()
    return {"ok": True, "id": orden_id}


# ── Stop-Loss / Take-Profit ───────────────────────────────

@router.post("/automatica")
async def crear_orden_automatica(data: StopLossSchema,
                                  current_user: Usuario = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """Crea una orden automática de Stop-Loss o Take-Profit."""
    # Verificar que el usuario tiene posición en el ticker
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == current_user.id,
        PosicionPortafolio.ticker == data.ticker,
        PosicionPortafolio.acciones > 0))
    pos = pos_res.scalar_one_or_none()
    if not pos:
        raise HTTPException(400, f"Sin posición en {data.ticker}")

    orden_auto = OrdenAutomatica(
        usuario_id=current_user.id, ticker=data.ticker,
        tipo=data.tipo, precio_trigger=data.precio_trigger,
        porcentaje_pos=data.porcentaje_pos,
        precio_trail_pct=data.precio_trail_pct,
        activa=True
    )
    db.add(orden_auto)
    await db.commit()
    return orden_auto.to_dict()


@router.get("/automaticas")
async def get_ordenes_automaticas(current_user: Usuario = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(OrdenAutomatica).where(
        OrdenAutomatica.usuario_id == current_user.id,
        OrdenAutomatica.activa == True))
    return [o.to_dict() for o in res.scalars().all()]


@router.delete("/automatica/{auto_id}")
async def cancelar_orden_automatica(auto_id: int,
                                     current_user: Usuario = Depends(get_current_user),
                                     db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(OrdenAutomatica).where(
        OrdenAutomatica.id == auto_id,
        OrdenAutomatica.usuario_id == current_user.id))
    orden = res.scalar_one_or_none()
    if not orden:
        raise HTTPException(404, "Orden automática no encontrada")
    orden.activa = False
    await db.commit()
    return {"ok": True}


# ── Helpers internos ──────────────────────────────────────

async def _actualizar_posicion_compra(db, usuario_id: int, ticker: str,
                                       fracs: float, price: float):
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == usuario_id,
        PosicionPortafolio.ticker == ticker))
    pos = pos_res.scalar_one_or_none()
    if pos:
        total_acc = pos.acciones + fracs
        pos.precio_promedio_compra = round(
            (pos.acciones * pos.precio_promedio_compra + fracs * price) / total_acc, 4
        ) if total_acc > 0 else price
        pos.acciones = round(total_acc, 8)
        pos.precio_actual = price
        pos.recalcular()
    else:
        db.add(PosicionPortafolio(
            usuario_id=usuario_id, ticker=ticker, nombre=ticker,
            acciones=fracs, precio_promedio_compra=price,
            precio_actual=price, valor_total_usd=round(fracs * price, 2)))


async def _actualizar_posicion_venta(db, usuario_id: int, ticker: str,
                                      fracs: float, price: float):
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == usuario_id,
        PosicionPortafolio.ticker == ticker))
    pos = pos_res.scalar_one_or_none()
    if pos:
        pos.acciones = max(0, round(pos.acciones - fracs, 8))
        pos.precio_actual = price
        pos.recalcular()


async def _consumir_tax_lots_fifo(db, usuario_id: int, ticker: str, acciones: float):
    """Consume lotes fiscales en orden FIFO al vender."""
    from models.models import TaxLot
    res = await db.execute(
        select(TaxLot).where(
            TaxLot.usuario_id == usuario_id,
            TaxLot.ticker == ticker,
            TaxLot.cerrado == False,
            TaxLot.acciones_restantes > 0
        ).order_by(TaxLot.fecha_compra.asc())  # FIFO
    )
    lotes = res.scalars().all()
    pendiente = acciones
    for lote in lotes:
        if pendiente <= 0:
            break
        usar = min(lote.acciones_restantes, pendiente)
        lote.acciones_restantes = round(lote.acciones_restantes - usar, 8)
        if lote.acciones_restantes < 0.00000001:
            lote.cerrado = True
        pendiente -= usar
