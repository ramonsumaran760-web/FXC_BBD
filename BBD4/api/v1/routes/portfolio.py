"""
Portfolio routes — posiciones actuales + equity curve (historial de rendimiento)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.models import Usuario, PosicionPortafolio, EquityCurve
from services.services import get_market_prices, alpaca_get_account, alpaca_get_positions
from core.config import settings

router = APIRouter(prefix="/portafolio", tags=["portafolio"])


@router.get("")
async def get_portafolio(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == current_user.id,
        PosicionPortafolio.acciones > 0))
    posiciones = res.scalars().all()

    prices = get_market_prices([p.ticker for p in posiciones])
    total_valor = 0.0; total_gp = 0.0
    result = []
    for pos in posiciones:
        price = prices.get(pos.ticker, {}).get("price", pos.precio_actual)
        pos.precio_actual = price
        pos.recalcular()
        total_valor += pos.valor_total_usd
        total_gp += pos.ganancia_perdida_usd
        result.append(pos.to_dict())

    await db.commit()

    # Registrar punto en equity curve
    await _registrar_equity_point(
        db, current_user.id, total_valor,
        current_user.saldo_usd, total_gp
    )

    cuenta_broker = alpaca_get_account(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET)
    return {
        "posiciones": result,
        "total_valor_usd": round(total_valor, 2),
        "ganancia_perdida_total": round(total_gp, 2),
        "saldo_disponible": round(current_user.saldo_usd, 2),
        "cuenta_broker": cuenta_broker,
        "posiciones_broker": alpaca_get_positions(settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET)
    }


@router.get("/equity-curve")
async def get_equity_curve(
    dias: int = Query(30, ge=1, le=365, description="Días de historial (1-365)"),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Historial de valor del portafolio. Permite graficar la evolución del capital.
    """
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    res = await db.execute(
        select(EquityCurve)
        .where(EquityCurve.usuario_id == current_user.id,
               EquityCurve.timestamp >= desde)
        .order_by(EquityCurve.timestamp.asc())
    )
    puntos = res.scalars().all()

    # Si no hay datos, generar serie simulada (demo)
    if not puntos:
        return {"dias": dias, "puntos": _generar_equity_demo(dias)}

    return {
        "dias": dias,
        "puntos": [p.to_dict() for p in puntos],
        "valor_inicio": puntos[0].valor_portafolio_usd if puntos else 0,
        "valor_actual": puntos[-1].valor_portafolio_usd if puntos else 0,
        "rendimiento_pct": round(
            (puntos[-1].valor_portafolio_usd / max(puntos[0].valor_portafolio_usd, 1) - 1) * 100, 4
        ) if len(puntos) >= 2 else 0
    }


async def _registrar_equity_point(db: AsyncSession, usuario_id: int,
                                   valor: float, saldo: float, gp: float):
    """Registra un punto de equity curve (máximo 1 por hora para evitar spam)."""
    hace_1h = datetime.now(timezone.utc) - timedelta(hours=1)
    res = await db.execute(
        select(func.count(EquityCurve.id)).where(
            EquityCurve.usuario_id == usuario_id,
            EquityCurve.timestamp >= hace_1h
        )
    )
    if res.scalar() == 0:
        costo_base = valor - gp
        pct = round(gp / max(costo_base, 1) * 100, 4) if costo_base else 0
        db.add(EquityCurve(usuario_id=usuario_id, valor_portafolio_usd=round(valor, 2),
                           saldo_disponible_usd=round(saldo, 2),
                           ganancia_perdida_usd=round(gp, 2),
                           ganancia_perdida_pct=pct))
        await db.flush()


def _generar_equity_demo(dias: int) -> list:
    return []  # No datos simulados — solo curva real de EquityCurve en DB
