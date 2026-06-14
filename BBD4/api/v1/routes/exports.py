"""
Exports routes — Excel y PDF con generación asíncrona via Celery.
Si Celery no está disponible, genera síncronamente (timeout ~10s en reportes grandes).
"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from core.rate_limit import limiter, get_limit
from core.config import settings
from models.models import Usuario, PosicionPortafolio, Orden, Dividendo
from services.services import get_market_prices, generar_excel_portafolio, generar_pdf_reporte
from fastapi import Request

router = APIRouter(prefix="/exportar", tags=["exportes"])


@router.get("/excel")
@limiter.limit(get_limit("exportar"))
async def exportar_excel(request: Request,
                          current_user: Usuario = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == current_user.id))
    posiciones = [p.to_dict() for p in pos_res.scalars().all()]

    ord_res = await db.execute(select(Orden).where(Orden.usuario_id == current_user.id)
                               .order_by(Orden.creado.desc()).limit(100))
    ordenes = [o.to_dict() for o in ord_res.scalars().all()]

    div_res = await db.execute(select(Dividendo).where(Dividendo.usuario_id == current_user.id))
    divs = [d.to_dict() for d in div_res.scalars().all()]

    nombre = f"investiq_portafolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    ruta = os.path.join(settings.EXPORT_DIR, nombre)
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)

    # Intentar via Celery primero (asíncrono)
    try:
        from workers.celery_worker import generar_excel_task
        result = generar_excel_task.delay(
            current_user.to_dict(), posiciones, ordenes, divs, ruta)
        # Devolver job id para polling (evita timeout en reportes grandes)
        return {"job_id": result.id, "estado": "procesando",
                "descarga_url": f"/api/v1/exportar/resultado/{result.id}"}
    except Exception:
        pass

    # Fallback síncrono
    generar_excel_portafolio(current_user.to_dict(), posiciones, ordenes, divs, ruta)
    return FileResponse(ruta, filename=nombre,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/pdf")
@limiter.limit(get_limit("exportar"))
async def exportar_pdf(request: Request,
                        current_user: Usuario = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == current_user.id,
        PosicionPortafolio.acciones > 0))
    posiciones = [p.to_dict() for p in pos_res.scalars().all()]

    prices = get_market_prices([p["ticker"] for p in posiciones])
    for p in posiciones:
        p["precio_actual"] = prices.get(p["ticker"], {}).get("price", p["precio_actual"])

    from sqlalchemy import func
    from models.models import Orden, Alerta, Dividendo
    valor_port = sum(p["precio_actual"] * p["acciones"] for p in posiciones)
    gp_total = sum((p["precio_actual"] - p["precio_promedio_compra"]) * p["acciones"] for p in posiciones)
    n_ord = (await db.execute(select(func.count(Orden.id)).where(
        Orden.usuario_id == current_user.id))).scalar() or 0
    total_div = (await db.execute(select(func.sum(Dividendo.monto_usd)).where(
        Dividendo.usuario_id == current_user.id))).scalar() or 0

    metricas = {
        "valor_portafolio": round(valor_port, 2),
        "ganancia_total": round(gp_total, 2),
        "saldo_disponible": round(current_user.saldo_usd, 2),
        "posiciones": len(posiciones),
        "ordenes_total": n_ord,
        "dividendos_total": round(total_div, 4),
    }

    nombre = f"investiq_reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    ruta = os.path.join(settings.EXPORT_DIR, nombre)
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)

    try:
        from workers.celery_worker import generar_pdf_task
        result = generar_pdf_task.delay(current_user.to_dict(), posiciones, metricas, ruta)
        return {"job_id": result.id, "estado": "procesando",
                "descarga_url": f"/api/v1/exportar/resultado/{result.id}"}
    except Exception:
        pass

    generar_pdf_reporte(current_user.to_dict(), posiciones, metricas, ruta)
    return FileResponse(ruta, filename=nombre, media_type="application/pdf")


@router.get("/resultado/{job_id}")
async def resultado_export(job_id: str,
                            current_user: Usuario = Depends(get_current_user)):
    """Polling del estado de un job de exportación asíncrono."""
    try:
        from celery.result import AsyncResult
        result = AsyncResult(job_id)
        if result.ready():
            ruta = result.result
            if ruta and os.path.exists(ruta):
                nombre = os.path.basename(ruta)
                ext = nombre.split(".")[-1]
                media = ("application/pdf" if ext == "pdf"
                         else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                return FileResponse(ruta, filename=nombre, media_type=media)
            return JSONResponse({"estado": "error", "mensaje": "Archivo no encontrado"}, 500)
        return {"estado": result.status.lower(), "job_id": job_id}
    except Exception as e:
        raise HTTPException(404, f"Job no encontrado: {e}")
