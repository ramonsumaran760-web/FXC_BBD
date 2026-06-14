"""
workers/celery_worker.py — Tareas asíncronas con Celery
Para producción: pip install celery[redis]
Arrancar: celery -A workers.celery_worker worker --loglevel=info
"""
import os
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
        beat_schedule={
            # Actualizar precios cada 15s
            "actualizar-precios": {
                "task": "workers.celery_worker.actualizar_precios_db",
                "schedule": 15.0,
            },
            # Generar reporte diario a las 6am
            "reporte-diario": {
                "task": "workers.celery_worker.generar_reporte_diario",
                "schedule": {"hour": 6, "minute": 0},
            },
            # Verificar AML de usuarios pendientes cada hora
            "aml-check": {
                "task": "workers.celery_worker.verificar_aml_pendientes",
                "schedule": 3600.0,
            },
        }
    )

    @app.task(name="workers.celery_worker.actualizar_precios_db", bind=True, max_retries=3)
    def actualizar_precios_db(self):
        """Actualiza precios de todos los activos en BD."""
        try:
            from services.services import get_market_prices
            import asyncio
            from core.database import AsyncSessionLocal
            from models.models import Activo
            from sqlalchemy import select
            from datetime import datetime

            prices = get_market_prices()

            async def _update():
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
            return {"ok": True, "activos_actualizados": n}
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5)

    @app.task(name="workers.celery_worker.generar_reporte_diario")
    def generar_reporte_diario():
        """Genera reportes diarios para todos los usuarios activos."""
        try:
            import asyncio
            from core.database import AsyncSessionLocal
            from models.models import Usuario, PosicionPortafolio
            from sqlalchemy import select
            from services.services import generar_pdf_reporte, get_market_prices
            import os

            async def _gen():
                async with AsyncSessionLocal() as db:
                    users_res = await db.execute(select(Usuario).where(Usuario.activo == True))
                    users = users_res.scalars().all()
                    prices = get_market_prices()
                    generated = 0
                    for u in users:
                        pos_res = await db.execute(select(PosicionPortafolio).where(
                            PosicionPortafolio.usuario_id == u.id, PosicionPortafolio.acciones > 0))
                        pos = [p.to_dict() for p in pos_res.scalars().all()]
                        if not pos: continue
                        for p in pos:
                            p["precio_actual"] = prices.get(p["ticker"], {}).get("price", p["precio_actual"])
                        os.makedirs("static/exports", exist_ok=True)
                        generar_pdf_reporte(u.to_dict(), pos,
                            {"valor_portafolio": sum(p["valor_total_usd"] for p in pos),
                             "ganancia_total": sum(p["ganancia_perdida_usd"] for p in pos),
                             "posiciones": len(pos), "ordenes": 0, "saldo": u.saldo_usd,
                             "ganancia_pct": 0, "dividendos_total": 0},
                            f"static/exports/reporte_diario_{u.id}.pdf")
                        generated += 1
                return generated

            n = asyncio.run(_gen())
            return {"ok": True, "reportes_generados": n}
        except Exception as e:
            return {"error": str(e)}

    @app.task(name="workers.celery_worker.verificar_aml_pendientes")
    def verificar_aml_pendientes():
        """Verifica AML de usuarios pendientes."""
        try:
            import asyncio
            from core.database import AsyncSessionLocal
            from models.models import Usuario, AMLLog
            from sqlalchemy import select
            from services.services import aml_check_entidad
            from datetime import datetime

            async def _check():
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

else:
    # Stub para cuando Celery no está instalado
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
    generar_reporte_diario = _FakeTask()
    verificar_aml_pendientes = _FakeTask()

# Uso manual (sin Celery)
def ejecutar_tarea_sync(nombre: str) -> dict:
    """Ejecuta tareas sincrónicamente si Celery no está disponible."""
    if nombre == "precios":
        from services.services import get_market_prices
        prices = get_market_prices()
        return {"ok": True, "precios": len(prices)}
    elif nombre == "aml":
        return {"ok": True, "mensaje": "AML sync no implementado"}
    return {"error": "Tarea desconocida"}
