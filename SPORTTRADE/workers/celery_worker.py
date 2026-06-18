"""
celery_worker.py — Jobs asíncronos de FXC_BBD.

Tareas programadas (Celery beat):
  - recalibrar_pesos_semanal  → cada lunes a las 02:00 UTC (Brecha C)
  - actualizar_odds_cache     → cada 5 minutos
  - cerrar_partidos_finalizados → cada hora
  - limpiar_latency_monitor   → cada domingo a las 03:00 UTC

Para ejecutar:
  celery -A workers.celery_worker worker --loglevel=info
  celery -A workers.celery_worker beat --loglevel=info
"""
import asyncio
import logging
from datetime import datetime, timedelta
from celery import Celery
from celery.schedules import crontab

from core.config import settings

logger = logging.getLogger("fxcbbd.workers")

# ─── CELERY APP ───────────────────────────────────────────────────────────────

celery_app = Celery(
    "fxcbbd",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer       = "json",
    accept_content        = ["json"],
    result_serializer     = "json",
    timezone              = "UTC",
    enable_utc            = True,
    task_track_started    = True,
    task_acks_late        = True,
    worker_prefetch_multiplier = 1,
)

# ─── BEAT SCHEDULE ────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    # Brecha C — Recalibración semanal de pesos de agentes
    "recalibrar-pesos-semanal": {
        "task":     "workers.celery_worker.recalibrar_pesos_semanal",
        "schedule": crontab(hour=2, minute=0, day_of_week="monday"),
        "kwargs":   {"semanas": 12},
    },
    # Limpiar latency monitor (ventana móvil ya lo hace, esto limpia BD)
    "limpiar-latency-monitor": {
        "task":     "workers.celery_worker.limpiar_latency_monitor",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
    },
}


# ─── HELPERS ASYNC ────────────────────────────────────────────────────────────

def _run_async(coro):
    """Ejecuta una coroutine desde un contexto síncrono Celery."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── TAREAS CELERY ────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="workers.celery_worker.recalibrar_pesos_semanal",
                 max_retries=3, default_retry_delay=300)
def recalibrar_pesos_semanal(self, semanas: int = 12):
    """
    Brecha C: Recalibración semanal de pesos del Master AI.
    Walk-forward validation — solo aplica si mejora el Brier Score.
    """
    async def _recalibrar():
        from core.database import AsyncSessionLocal
        from models.models import BacktestingLog, AgentWeight
        from master_ai.feedback_loop import generar_reporte_calibracion, recalibrador
        from master_ai.master_ai import master_ai
        from sqlalchemy import select

        desde = datetime.utcnow() - timedelta(weeks=semanas)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(BacktestingLog).where(
                    BacktestingLog.fecha >= desde,
                    BacktestingLog.brier_score.is_not(None),
                ).order_by(BacktestingLog.fecha.asc())
            )
            logs = result.scalars().all()

        por_agente: dict[str, list[dict]] = {}
        for log in logs:
            aid = log.agente_id
            if aid not in por_agente:
                por_agente[aid] = []
            por_agente[aid].append({
                "brier_score":         log.brier_score,
                "prediccion_correcta": log.prediccion_correcta,
                "semana_iso":          log.semana_iso,
            })

        if not por_agente:
            logger.info("Recalibración semanal: sin datos suficientes, saltando.")
            return {"skipped": True}

        nuevos_pesos, reporte = recalibrador.recalibrar(por_agente, master_ai.pesos)

        if reporte.get("desplegado"):
            async with AsyncSessionLocal() as db:
                for agente_id, peso in nuevos_pesos.items():
                    result = await db.execute(
                        select(AgentWeight).where(AgentWeight.agente_id == agente_id)
                    )
                    aw = result.scalar_one_or_none()
                    if aw:
                        hist = aw.historial_pesos or []
                        hist.append({"fecha": datetime.utcnow().isoformat(), "peso": aw.peso_actual})
                        aw.peso_actual     = peso
                        aw.historial_pesos = hist
                        aw.actualizado     = datetime.utcnow()
                    else:
                        db.add(AgentWeight(
                            agente_id       = agente_id,
                            peso_actual     = peso,
                            historial_pesos = [],
                        ))
                await db.commit()

            master_ai.pesos.update(nuevos_pesos)
            logger.info("Pesos actualizados: %s", nuevos_pesos)

        return reporte

    try:
        return _run_async(_recalibrar())
    except Exception as exc:
        logger.error("Error en recalibración semanal: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(name="workers.celery_worker.limpiar_latency_monitor")
def limpiar_latency_monitor():
    """Elimina registros de latencia de más de 30 días."""
    async def _limpiar():
        from core.database import AsyncSessionLocal
        from models.models import LatencyMonitor
        from sqlalchemy import delete

        limite = datetime.utcnow() - timedelta(days=30)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(LatencyMonitor).where(LatencyMonitor.timestamp < limite)
            )
            await db.commit()
            return {"eliminados": result.rowcount}

    return _run_async(_limpiar())
