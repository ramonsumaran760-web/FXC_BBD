"""
Workers v2.0 — Celery tasks para operaciones asíncronas pesadas:
  - actualizar_precios_db        → cada 15s
  - verificar_stop_loss          → cada 30s (nuevo)
  - registrar_equity_diario      → cada hora (nuevo)
  - generar_reporte_diario       → cada día a las 6am
  - verificar_aml_pendientes     → cada hora
  - generar_excel_task           → bajo demanda (nuevo)
  - generar_pdf_task             → bajo demanda (nuevo)
  - sincronizar_tax_lots         → cada noche (nuevo)

Arrancar: celery -A workers.celery_worker worker -B --loglevel=info
"""
import os, asyncio, logging

logger = logging.getLogger(__name__)

try:
    from celery import Celery
    CELERY_OK = True
except ImportError:
    CELERY_OK = False

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

if CELERY_OK:
    app = Celery("investiq", broker=REDIS_URL, backend=REDIS_URL)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="America/Bogota",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        result_expires=3600,
        beat_schedule={
            "actualizar-precios": {
                "task": "workers.celery_worker.actualizar_precios_db",
                "schedule": 15.0,
            },
            "verificar-stop-loss": {
                "task": "workers.celery_worker.verificar_stop_loss",
                "schedule": 30.0,
            },
            "registrar-equity": {
                "task": "workers.celery_worker.registrar_equity_diario",
                "schedule": 3600.0,
            },
            "reporte-diario": {
                "task": "workers.celery_worker.generar_reporte_diario",
                "schedule": {"hour": 6, "minute": 0},
            },
            "aml-check": {
                "task": "workers.celery_worker.verificar_aml_pendientes",
                "schedule": 3600.0,
            },
            "sincronizar-tax-lots": {
                "task": "workers.celery_worker.sincronizar_tax_lots",
                "schedule": {"hour": 2, "minute": 0},
            },
        }
    )

    # ── Actualizar precios ────────────────────────────────
    @app.task(name="workers.celery_worker.actualizar_precios_db", bind=True, max_retries=3)
    def actualizar_precios_db(self):
        try:
            from services.services import get_market_prices
            from models.models import Activo
            from sqlalchemy import select
            from datetime import datetime

            prices = get_market_prices()

            async def _update():
                from core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    res = await db.execute(select(Activo))
                    activos = res.scalars().all()
                    for a in activos:
                        if a.ticker in prices:
                            a.precio_actual = prices[a.ticker]["price"]
                            a.variacion_pct = prices[a.ticker]["change_pct"]
                            a.ultima_actualizacion = datetime.utcnow()
                    await db.commit()
                return len(activos)

            n = asyncio.run(_update())
            return {"ok": True, "activos": n}
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5)

    # ── Verificar Stop-Loss / Take-Profit ─────────────────
    @app.task(name="workers.celery_worker.verificar_stop_loss")
    def verificar_stop_loss():
        """
        Comprueba si algún precio ha cruzado el trigger de stop-loss o take-profit.
        Si es así, ejecuta la venta automáticamente.
        """
        try:
            from services.services import get_market_prices, alpaca_place_order
            from services.notification_service import notificar_stop_loss
            from models.models import OrdenAutomatica, PosicionPortafolio, Orden, Usuario, AuditLog
            from core.security import firmar_orden, generar_nonce
            from core.config import settings
            from sqlalchemy import select
            from datetime import datetime

            async def _check():
                from core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    res = await db.execute(select(OrdenAutomatica).where(
                        OrdenAutomatica.activa == True,
                        OrdenAutomatica.ejecutada == False))
                    ordenes_auto = res.scalars().all()
                    if not ordenes_auto:
                        return 0

                    tickers = list({o.ticker for o in ordenes_auto})
                    prices = get_market_prices(tickers)
                    ejecutadas = 0

                    for oa in ordenes_auto:
                        precio_actual = prices.get(oa.ticker, {}).get("price", 0)
                        if not precio_actual:
                            continue

                        activada = False
                        if oa.tipo == "stop_loss" and precio_actual <= oa.precio_trigger:
                            activada = True
                        elif oa.tipo == "take_profit" and precio_actual >= oa.precio_trigger:
                            activada = True

                        if not activada:
                            continue

                        # Buscar posición
                        pos_res = await db.execute(select(PosicionPortafolio).where(
                            PosicionPortafolio.usuario_id == oa.usuario_id,
                            PosicionPortafolio.ticker == oa.ticker))
                        pos = pos_res.scalar_one_or_none()
                        if not pos or pos.acciones <= 0:
                            oa.activa = False
                            continue

                        # Calcular monto a vender
                        acc_vender = round(pos.acciones * oa.porcentaje_pos / 100, 8)
                        monto_usd = round(acc_vender * precio_actual, 2)

                        if monto_usd < settings.MIN_ORDER_USD:
                            oa.activa = False
                            continue

                        # Ejecutar en broker
                        broker_resp = alpaca_place_order(
                            settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET,
                            oa.ticker, monto_usd, "sell", "market")

                        if "error" not in broker_resp:
                            nonce = generar_nonce()
                            datos = {"ticker": oa.ticker, "monto_usd": monto_usd,
                                     "tipo": "sell", "ts": str(datetime.utcnow()), "nonce": nonce}
                            from core.security import firmar_orden
                            firma = firmar_orden(datos)

                            orden = Orden(
                                usuario_id=oa.usuario_id, ticker=oa.ticker,
                                tipo="sell", tipo_orden="market",
                                monto_usd=monto_usd, acciones=acc_vender,
                                precio_ejecucion=precio_actual,
                                estado="filled", broker="alpaca_paper",
                                broker_order_id=broker_resp.get("id"),
                                firma_ecdsa=firma, firma_verificada=True,
                                nonce=nonce, aml_check="clear",
                                creado=datetime.utcnow(), ejecutado=datetime.utcnow()
                            )
                            db.add(orden)
                            await db.flush()

                            oa.ejecutada = True
                            oa.activa = False
                            oa.orden_id = orden.id
                            oa.ejecutado_ts = datetime.utcnow()

                            # Actualizar posición
                            pos.acciones = max(0, round(pos.acciones - acc_vender, 8))
                            pos.precio_actual = precio_actual
                            pos.recalcular()

                            # Actualizar saldo
                            u_res = await db.execute(select(Usuario).where(
                                Usuario.id == oa.usuario_id))
                            user = u_res.scalar_one_or_none()
                            if user:
                                user.saldo_usd = round(user.saldo_usd + monto_usd, 2)
                                notificar_stop_loss(user.id, user.email,
                                                    user.phone or "",
                                                    oa.ticker, precio_actual, monto_usd)

                            db.add(AuditLog(
                                usuario_id=oa.usuario_id,
                                accion=f"{oa.tipo.upper()}_EJECUTADO",
                                modulo="ordenes_automaticas",
                                detalle=f"{oa.ticker} @ ${precio_actual:.4f} — ${monto_usd:.2f}"))
                            ejecutadas += 1

                    await db.commit()
                    return ejecutadas

            n = asyncio.run(_check())
            return {"ok": True, "ejecutadas": n}
        except Exception as e:
            logger.error(f"verificar_stop_loss error: {e}")
            return {"error": str(e)}

    # ── Registrar Equity Curve ────────────────────────────
    @app.task(name="workers.celery_worker.registrar_equity_diario")
    def registrar_equity_diario():
        """Registra un punto de equity curve para cada usuario activo."""
        try:
            from models.models import Usuario, PosicionPortafolio, EquityCurve
            from services.services import get_market_prices
            from sqlalchemy import select
            from datetime import datetime

            async def _register():
                from core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    u_res = await db.execute(select(Usuario).where(Usuario.activo == True))
                    users = u_res.scalars().all()
                    registrados = 0
                    for u in users:
                        pos_res = await db.execute(select(PosicionPortafolio).where(
                            PosicionPortafolio.usuario_id == u.id,
                            PosicionPortafolio.acciones > 0))
                        posiciones = pos_res.scalars().all()
                        if not posiciones:
                            continue
                        prices = get_market_prices([p.ticker for p in posiciones])
                        valor = sum(prices.get(p.ticker, {}).get("price", p.precio_actual) * p.acciones
                                    for p in posiciones)
                        gp = sum((prices.get(p.ticker, {}).get("price", p.precio_actual) -
                                  p.precio_promedio_compra) * p.acciones for p in posiciones)
                        costo = valor - gp
                        pct = round(gp / max(costo, 1) * 100, 4) if costo else 0
                        db.add(EquityCurve(
                            usuario_id=u.id, valor_portafolio_usd=round(valor, 2),
                            saldo_disponible_usd=round(u.saldo_usd or 0, 2),
                            ganancia_perdida_usd=round(gp, 2),
                            ganancia_perdida_pct=pct))
                        registrados += 1
                    await db.commit()
                    return registrados

            n = asyncio.run(_register())
            return {"ok": True, "registros": n}
        except Exception as e:
            return {"error": str(e)}

    # ── Reporte diario ────────────────────────────────────
    @app.task(name="workers.celery_worker.generar_reporte_diario")
    def generar_reporte_diario():
        try:
            from models.models import Usuario, PosicionPortafolio
            from services.services import generar_pdf_reporte, get_market_prices
            from sqlalchemy import select
            import os

            async def _gen():
                from core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    u_res = await db.execute(select(Usuario).where(Usuario.activo == True))
                    users = u_res.scalars().all()
                    prices = get_market_prices()
                    generated = 0
                    for u in users:
                        pos_res = await db.execute(select(PosicionPortafolio).where(
                            PosicionPortafolio.usuario_id == u.id,
                            PosicionPortafolio.acciones > 0))
                        pos = [p.to_dict() for p in pos_res.scalars().all()]
                        if not pos:
                            continue
                        for p in pos:
                            p["precio_actual"] = prices.get(p["ticker"], {}).get(
                                "price", p["precio_actual"])
                        os.makedirs("static/exports", exist_ok=True)
                        generar_pdf_reporte(u.to_dict(), pos, {
                            "valor_portafolio": sum(p["valor_total_usd"] for p in pos),
                            "ganancia_total": sum(p["ganancia_perdida_usd"] for p in pos),
                            "posiciones": len(pos), "ordenes_total": 0,
                            "saldo_disponible": u.saldo_usd, "dividendos_total": 0
                        }, f"static/exports/reporte_diario_{u.id}.pdf")
                        generated += 1
                    return generated

            n = asyncio.run(_gen())
            return {"ok": True, "reportes": n}
        except Exception as e:
            return {"error": str(e)}

    # ── AML check programado ──────────────────────────────
    @app.task(name="workers.celery_worker.verificar_aml_pendientes")
    def verificar_aml_pendientes():
        try:
            from models.models import Usuario, AMLLog
            from services.services import aml_check_entidad
            from sqlalchemy import select
            from datetime import datetime

            async def _check():
                from core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    res = await db.execute(select(Usuario).where(Usuario.aml_status == "pending"))
                    users = res.scalars().all()
                    for u in users:
                        r = aml_check_entidad(u.nombre)
                        u.aml_status = r["status"]
                        u.aml_score = r["score"]
                        u.aml_fecha = datetime.utcnow()
                        db.add(AMLLog(usuario_id=u.id, entidad=u.nombre,
                                      tipo_check="scheduled", resultado=r["status"],
                                      score=r["score"], detalle=r["detalle"], fuente=r["fuente"]))
                    await db.commit()
                    return len(users)

            n = asyncio.run(_check())
            return {"ok": True, "verificados": n}
        except Exception as e:
            return {"error": str(e)}

    # ── Sincronizar Tax Lots ──────────────────────────────
    @app.task(name="workers.celery_worker.sincronizar_tax_lots")
    def sincronizar_tax_lots():
        """
        Reconstruye los tax lots desde las órdenes si hay inconsistencias.
        Corre cada noche a las 2am.
        """
        try:
            from models.models import Orden, TaxLot
            from sqlalchemy import select
            from datetime import datetime

            async def _sync():
                from core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    # Buscar órdenes de compra sin tax lot asociado
                    ord_res = await db.execute(select(Orden).where(
                        Orden.tipo == "buy", Orden.estado == "filled"))
                    ordenes = ord_res.scalars().all()

                    sincronizados = 0
                    for o in ordenes:
                        lot_res = await db.execute(select(TaxLot).where(
                            TaxLot.orden_id == o.id))
                        if not lot_res.scalar_one_or_none():
                            db.add(TaxLot(
                                usuario_id=o.usuario_id, ticker=o.ticker,
                                acciones_originales=o.acciones or 0,
                                acciones_restantes=o.acciones or 0,
                                precio_costo=o.precio_ejecucion or 0,
                                fecha_compra=o.ejecutado or o.creado,
                                orden_id=o.id, cerrado=False))
                            sincronizados += 1
                    await db.commit()
                    return sincronizados

            n = asyncio.run(_sync())
            return {"ok": True, "sincronizados": n}
        except Exception as e:
            return {"error": str(e)}

    # ── Exportes bajo demanda ─────────────────────────────
    @app.task(name="workers.celery_worker.generar_excel_task")
    def generar_excel_task(usuario: dict, portafolio: list, ordenes: list,
                            dividendos: list, ruta: str) -> str:
        from services.services import generar_excel_portafolio
        return generar_excel_portafolio(usuario, portafolio, ordenes, dividendos, ruta)

    @app.task(name="workers.celery_worker.generar_pdf_task")
    def generar_pdf_task(usuario: dict, portafolio: list, metricas: dict, ruta: str) -> str:
        from services.services import generar_pdf_reporte
        return generar_pdf_reporte(usuario, portafolio, metricas, ruta)

else:
    # ── Stubs cuando Celery no está instalado ─────────────
    class _FakeTask:
        def delay(self, *a, **k): return None
        def apply_async(self, *a, **k): return None
        def __call__(self, *a, **k): return None

    class app:
        @staticmethod
        def task(*a, **k):
            def dec(f): return _FakeTask()
            return dec

    actualizar_precios_db = _FakeTask()
    verificar_stop_loss = _FakeTask()
    registrar_equity_diario = _FakeTask()
    generar_reporte_diario = _FakeTask()
    verificar_aml_pendientes = _FakeTask()
    sincronizar_tax_lots = _FakeTask()
    generar_excel_task = _FakeTask()
    generar_pdf_task = _FakeTask()
