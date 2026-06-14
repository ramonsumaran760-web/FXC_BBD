"""
Tax Engine — Cálculo de ganancias de capital FIFO / LIFO
Conforme con estándares contables internacionales.
"""
from datetime import datetime, timedelta
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


def calcular_ganancias_capital(
    tax_lots: list,
    ventas: list,
    metodo: str = "FIFO",
    tax_rate_st: float = 0.30,
    tax_rate_lt: float = 0.20
) -> dict:
    """
    Calcula ganancias/pérdidas de capital usando FIFO o LIFO.

    Parámetros:
        tax_lots: lista de dicts {"ticker", "acciones_restantes", "precio_costo", "fecha_compra"}
        ventas:   lista de dicts {"ticker", "acciones", "precio_venta", "fecha_venta"}
        metodo:   "FIFO" (primero en entrar, primero en salir) o "LIFO"
        tax_rate_st: tasa impositiva corto plazo (< 1 año)
        tax_rate_lt: tasa impositiva largo plazo (≥ 1 año)

    Retorna:
        dict con detalle de operaciones, totales y estimado de impuesto.
    """
    # Agrupar lotes por ticker, ordenados según el método
    lotes_por_ticker: dict[str, list] = {}
    for lot in tax_lots:
        t = lot["ticker"]
        lotes_por_ticker.setdefault(t, []).append({
            "acciones": float(lot["acciones_restantes"]),
            "costo": float(lot["precio_costo"]),
            "fecha": lot["fecha_compra"] if isinstance(lot["fecha_compra"], datetime)
                     else datetime.fromisoformat(str(lot["fecha_compra"]))
        })

    for ticker, lotes in lotes_por_ticker.items():
        lotes.sort(key=lambda x: x["fecha"], reverse=(metodo == "LIFO"))

    transacciones = []
    total_ganancias = 0.0
    total_perdidas = 0.0
    ganancias_st = 0.0
    ganancias_lt = 0.0

    for venta in ventas:
        ticker = venta["ticker"]
        acciones_vender = float(venta["acciones"])
        precio_venta = float(venta["precio_venta"])
        fecha_venta = (venta["fecha_venta"] if isinstance(venta["fecha_venta"], datetime)
                       else datetime.fromisoformat(str(venta["fecha_venta"])))

        lotes = lotes_por_ticker.get(ticker, [])
        acciones_pendientes = acciones_vender

        for lote in lotes:
            if acciones_pendientes <= 0 or lote["acciones"] <= 0:
                continue

            usadas = min(lote["acciones"], acciones_pendientes)
            ganancia = (precio_venta - lote["costo"]) * usadas
            dias = (fecha_venta - lote["fecha"]).days
            es_largo_plazo = dias >= 365

            transacciones.append({
                "ticker": ticker,
                "acciones": round(usadas, 8),
                "costo_base": round(lote["costo"], 4),
                "precio_venta": round(precio_venta, 4),
                "ganancia_perdida": round(ganancia, 2),
                "dias_tenencia": dias,
                "largo_plazo": es_largo_plazo,
                "fecha_compra": lote["fecha"].isoformat(),
                "fecha_venta": fecha_venta.isoformat(),
            })

            if ganancia >= 0:
                total_ganancias += ganancia
                if es_largo_plazo:
                    ganancias_lt += ganancia
                else:
                    ganancias_st += ganancia
            else:
                total_perdidas += abs(ganancia)

            lote["acciones"] -= usadas
            acciones_pendientes -= usadas

        if acciones_pendientes > 0.0001:
            logger.warning(f"Tax lot insuficiente para {ticker}: faltan {acciones_pendientes:.8f} acc")

    ganancia_neta = total_ganancias - total_perdidas
    impuesto_estimado = max(ganancias_st * tax_rate_st + ganancias_lt * tax_rate_lt, 0)

    return {
        "metodo": metodo,
        "total_ganancias": round(total_ganancias, 2),
        "total_perdidas": round(total_perdidas, 2),
        "ganancia_neta": round(ganancia_neta, 2),
        "ganancias_corto_plazo": round(ganancias_st, 2),
        "ganancias_largo_plazo": round(ganancias_lt, 2),
        "impuesto_estimado": round(impuesto_estimado, 2),
        "tasa_st": tax_rate_st,
        "tasa_lt": tax_rate_lt,
        "transacciones": transacciones,
    }


def generar_lotes_desde_ordenes(ordenes: list) -> list:
    """
    Convierte órdenes de compra en lotes fiscales.
    Cada compra crea un lote independiente para rastrear el costo base.
    """
    lotes = []
    for o in ordenes:
        if o.get("tipo") == "buy" and o.get("estado") == "filled":
            acciones = float(o.get("acciones", 0))
            precio = float(o.get("precio_ejecucion", 0))
            if acciones > 0 and precio > 0:
                lotes.append({
                    "ticker": o["ticker"],
                    "acciones_restantes": acciones,
                    "precio_costo": precio,
                    "fecha_compra": o.get("ejecutado") or o.get("creado"),
                    "orden_id": o.get("id"),
                })
    return lotes


def calcular_tax_report_anual(ordenes: list, año: int, metodo: str = "FIFO") -> dict:
    """
    Calcula el reporte fiscal completo de un año dado.
    Separa compras (lotes) de ventas y aplica FIFO/LIFO.
    """
    compras = [o for o in ordenes if o.get("tipo") == "buy" and o.get("estado") == "filled"
               and _año_orden(o) <= año]
    ventas = [o for o in ordenes if o.get("tipo") == "sell" and o.get("estado") == "filled"
              and _año_orden(o) == año]

    tax_lots = generar_lotes_desde_ordenes(compras)
    ventas_norm = [{
        "ticker": o["ticker"],
        "acciones": float(o.get("acciones", 0)),
        "precio_venta": float(o.get("precio_ejecucion", 0)),
        "fecha_venta": o.get("ejecutado") or o.get("creado"),
    } for o in ventas]

    return calcular_ganancias_capital(tax_lots, ventas_norm, metodo)


def _año_orden(orden: dict) -> int:
    ts = orden.get("ejecutado") or orden.get("creado", "")
    if isinstance(ts, datetime):
        return ts.year
    try:
        return datetime.fromisoformat(str(ts)).year
    except Exception:
        return 0
