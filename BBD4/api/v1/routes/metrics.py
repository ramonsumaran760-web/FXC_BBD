"""
Metrics routes — indicadores del dashboard
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.models import Usuario, PosicionPortafolio, Orden, Alerta, Dividendo
from services.services import get_market_prices

router = APIRouter(prefix="/metricas", tags=["metricas"])


@router.get("")
async def get_metricas(current_user: Usuario = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == current_user.id,
        PosicionPortafolio.acciones > 0))
    posiciones = pos_res.scalars().all()

    prices = get_market_prices([p.ticker for p in posiciones])
    valor_port = sum(
        (prices.get(p.ticker, {}).get("price", p.precio_actual) or p.precio_actual) * p.acciones
        for p in posiciones)
    gp_total = sum(
        ((prices.get(p.ticker, {}).get("price", p.precio_actual) or p.precio_actual)
         - p.precio_promedio_compra) * p.acciones
        for p in posiciones)

    ord_res = await db.execute(
        select(func.count(Orden.id)).where(Orden.usuario_id == current_user.id))
    n_ord = ord_res.scalar() or 0

    al_res = await db.execute(
        select(func.count(Alerta.id)).where(
            Alerta.usuario_id == current_user.id, Alerta.leida == False))
    n_alertas = al_res.scalar() or 0

    div_res = await db.execute(
        select(func.sum(Dividendo.monto_usd)).where(Dividendo.usuario_id == current_user.id))
    total_div = div_res.scalar() or 0

    costo_base = valor_port - gp_total
    return {
        "valor_portafolio": round(valor_port, 2),
        "ganancia_total": round(gp_total, 2),
        "ganancia_pct": round(gp_total / max(costo_base, 1) * 100, 3),
        "saldo_disponible": round(current_user.saldo_usd or 0, 2),
        "posiciones": len(posiciones),
        "ordenes_total": n_ord,
        "alertas_nuevas": n_alertas,
        "dividendos_total": round(total_div, 4),
    }
