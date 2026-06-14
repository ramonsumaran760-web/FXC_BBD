"""
Tax routes — cálculo de ganancias de capital FIFO / LIFO y reporte fiscal anual
"""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from core.config import settings
from models.models import Usuario, Orden, TaxLot, Dividendo, ReporteFiscal
from services.tax_engine import calcular_tax_report_anual, calcular_ganancias_capital

router = APIRouter(prefix="/fiscal", tags=["fiscal"])


@router.get("/reporte/{año}")
async def reporte_fiscal(
    año: int,
    metodo: str = Query("FIFO", regex="^(FIFO|LIFO)$"),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Genera el reporte fiscal anual para el año indicado.
    Calcula ganancias/pérdidas de capital usando FIFO o LIFO.
    """
    if año < 2020 or año > datetime.now(timezone.utc).year:
        raise HTTPException(400, f"Año inválido: {año}")

    # Obtener todas las órdenes del usuario
    ord_res = await db.execute(
        select(Orden).where(
            Orden.usuario_id == current_user.id,
            Orden.estado == "filled"
        ).order_by(Orden.creado.asc())
    )
    ordenes = [o.to_dict() for o in ord_res.scalars().all()]

    # Obtener dividendos del año
    div_res = await db.execute(
        select(Dividendo).where(Dividendo.usuario_id == current_user.id))
    dividendos = div_res.scalars().all()
    total_dividendos = sum(
        d.monto_usd for d in dividendos
        if d.pago_date and d.pago_date.year == año
    )

    # Calcular con FIFO/LIFO
    calculo = calcular_tax_report_anual(ordenes, año, metodo)
    calculo["dividendos_recibidos"] = round(total_dividendos, 4)

    impuesto_div = total_dividendos * 0.20
    calculo["impuesto_estimado"] += impuesto_div
    calculo["impuesto_estimado"] = round(calculo["impuesto_estimado"], 2)

    # Guardar/actualizar reporte en BD
    rep_res = await db.execute(select(ReporteFiscal).where(
        ReporteFiscal.usuario_id == current_user.id,
        ReporteFiscal.año == año,
        ReporteFiscal.metodo == metodo))
    reporte = rep_res.scalar_one_or_none()

    if reporte:
        reporte.ganancias_capital = calculo["total_ganancias"]
        reporte.perdidas_capital = calculo["total_perdidas"]
        reporte.ganancias_corto_plazo = calculo["ganancias_corto_plazo"]
        reporte.ganancias_largo_plazo = calculo["ganancias_largo_plazo"]
        reporte.dividendos_recibidos = total_dividendos
        reporte.impuesto_estimado = calculo["impuesto_estimado"]
        reporte.detalle_json = json.dumps(calculo["transacciones"])
        reporte.generado = datetime.now(timezone.utc)
    else:
        db.add(ReporteFiscal(
            usuario_id=current_user.id, año=año, metodo=metodo,
            ganancias_capital=calculo["total_ganancias"],
            perdidas_capital=calculo["total_perdidas"],
            ganancias_corto_plazo=calculo["ganancias_corto_plazo"],
            ganancias_largo_plazo=calculo["ganancias_largo_plazo"],
            dividendos_recibidos=total_dividendos,
            impuesto_estimado=calculo["impuesto_estimado"],
            detalle_json=json.dumps(calculo["transacciones"])
        ))

    await db.commit()

    return {
        "año": año,
        "metodo": metodo,
        "usuario": current_user.nombre,
        **calculo
    }


@router.get("/lotes")
async def get_tax_lots(
    ticker: Optional[str] = None,
    solo_abiertos: bool = True,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lista los lotes fiscales del usuario (base de costo por compra)."""
    query = select(TaxLot).where(TaxLot.usuario_id == current_user.id)
    if ticker:
        query = query.where(TaxLot.ticker == ticker.upper())
    if solo_abiertos:
        query = query.where(TaxLot.cerrado == False)
    query = query.order_by(TaxLot.fecha_compra.asc())

    res = await db.execute(query)
    return [l.to_dict() for l in res.scalars().all()]


@router.get("/reportes")
async def get_reportes(current_user: Usuario = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Lista reportes fiscales generados anteriormente."""
    res = await db.execute(
        select(ReporteFiscal).where(ReporteFiscal.usuario_id == current_user.id)
        .order_by(ReporteFiscal.año.desc())
    )
    return [r.to_dict() for r in res.scalars().all()]
