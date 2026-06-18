"""
backtesting_routes.py — Brecha C: Backtesting y Calibración de Agentes.

POST /api/v1/backtesting/cerrar-partido   → registrar resultado real y calcular Brier Scores
GET  /api/v1/backtesting/reporte          → panel de rendimiento por agente
POST /api/v1/backtesting/recalibrar       → disparar recalibración manual de pesos
GET  /api/v1/backtesting/pesos-actuales   → ver pesos actuales del Master AI
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime

from core.database import get_db
from models.models import BacktestingLog, AgentWeight, Prediction
from master_ai.feedback_loop import (
    calcular_brier_score_multiclase,
    generar_reporte_calibracion,
    recalibrador,
)
from master_ai.master_ai import master_ai

router = APIRouter(prefix="/api/v1/backtesting", tags=["backtesting"])


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class CerrarPartidoRequest(BaseModel):
    match_id: int
    resultado_real: str = Field(..., pattern="^(local|empate|visitante)$")


class RecalibrarResponse(BaseModel):
    brier_score_antes: float
    brier_score_tras: float
    desplegado: bool
    pesos_finales: dict
    brier_por_agente: dict
    timestamp: str


# ─── HELPERS ─────────────────────────────────────────────────────────────────

async def _cargar_logs_por_agente(
    db: AsyncSession,
    semanas: int = 12,
) -> dict[str, list[dict]]:
    """Carga logs de las últimas N semanas agrupados por agente."""
    from datetime import timedelta
    desde = datetime.utcnow() - timedelta(weeks=semanas)
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
            "brier_score":        log.brier_score,
            "prediccion_correcta":log.prediccion_correcta,
            "semana_iso":         log.semana_iso,
        })
    return por_agente


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/cerrar-partido")
async def cerrar_partido(req: CerrarPartidoRequest, db: AsyncSession = Depends(get_db)):
    """
    Registra el resultado real de un partido y calcula Brier Scores por agente.
    Cierra todos los BacktestingLog pendientes para ese match_id.
    """
    result = await db.execute(
        select(BacktestingLog).where(
            BacktestingLog.match_id == req.match_id,
            BacktestingLog.resultado_real.is_(None),
        )
    )
    logs = result.scalars().all()
    if not logs:
        raise HTTPException(404, f"No hay predicciones abiertas para match_id={req.match_id}")

    for log in logs:
        bs = calcular_brier_score_multiclase(
            log.prob_local,
            log.prob_empate,
            log.prob_visitante,
            req.resultado_real,
        )
        # Determinar qué predijo el agente
        probs = {
            "local":     log.prob_local,
            "empate":    log.prob_empate,
            "visitante": log.prob_visitante,
        }
        prediccion_campo = max(probs, key=lambda k: probs[k])

        log.resultado_real      = req.resultado_real
        log.prediccion_correcta = (prediccion_campo == req.resultado_real)
        log.brier_score         = bs

    await db.commit()

    aciertos = sum(1 for l in logs if l.prediccion_correcta)
    return {
        "match_id":        req.match_id,
        "resultado_real":  req.resultado_real,
        "logs_cerrados":   len(logs),
        "aciertos":        aciertos,
        "brier_promedio":  round(sum(l.brier_score for l in logs) / len(logs), 5),
    }


@router.get("/reporte")
async def reporte_calibracion(semanas: int = 12, db: AsyncSession = Depends(get_db)):
    """
    Panel de rendimiento por agente:
    acierto %, Brier Score, Skill Score, y señal de alerta si peor que azar.
    """
    logs_por_agente = await _cargar_logs_por_agente(db, semanas)
    if not logs_por_agente:
        return {"mensaje": "Sin datos suficientes para generar reporte", "agentes": {}}

    reporte = generar_reporte_calibracion(logs_por_agente)
    return {
        "semanas_analizadas": semanas,
        "generado":           datetime.utcnow().isoformat(),
        "agentes":            reporte,
        "pesos_actuales":     master_ai.pesos,
    }


@router.post("/recalibrar", response_model=RecalibrarResponse)
async def recalibrar_pesos(semanas: int = 12, db: AsyncSession = Depends(get_db)):
    """
    Dispara recalibración manual del Master AI.
    Walk-forward validation: solo aplica nuevos pesos si mejoran el Brier Score.
    """
    logs_por_agente = await _cargar_logs_por_agente(db, semanas)
    if not logs_por_agente:
        raise HTTPException(400, "Datos insuficientes para recalibrar (<30 predicciones por agente)")

    nuevos_pesos, reporte = recalibrador.recalibrar(logs_por_agente, master_ai.pesos)

    if reporte.get("desplegado"):
        # Actualizar pesos en BD
        for agente_id, peso in nuevos_pesos.items():
            result = await db.execute(
                select(AgentWeight).where(AgentWeight.agente_id == agente_id)
            )
            aw = result.scalar_one_or_none()
            if aw:
                historial = aw.historial_pesos or []
                historial.append({"fecha": datetime.utcnow().isoformat(), "peso": aw.peso_actual})
                aw.peso_actual    = peso
                aw.historial_pesos= historial
                aw.actualizado    = datetime.utcnow()
            else:
                db.add(AgentWeight(
                    agente_id      = agente_id,
                    peso_actual    = peso,
                    historial_pesos= [],
                ))

        # Actualizar pesos en memoria del Master AI en vivo
        master_ai.pesos.update(nuevos_pesos)
        await db.commit()

    return RecalibrarResponse(
        brier_score_antes = reporte["brier_score_antes"],
        brier_score_tras  = reporte["brier_score_tras"],
        desplegado        = reporte["desplegado"],
        pesos_finales     = reporte["pesos_finales"],
        brier_por_agente  = reporte["brier_por_agente"],
        timestamp         = reporte["timestamp"],
    )


@router.get("/pesos-actuales")
async def pesos_actuales(db: AsyncSession = Depends(get_db)):
    """Devuelve los pesos actuales del Master AI con historial de cambios."""
    result = await db.execute(select(AgentWeight))
    registros = result.scalars().all()

    pesos_bd = {r.agente_id: {"peso": r.peso_actual, "historial": r.historial_pesos}
                for r in registros}

    # Mezclar con pesos en memoria (en caso de no estar en BD todavía)
    salida = {}
    for agente_id, peso_mem in master_ai.pesos.items():
        if agente_id in pesos_bd:
            salida[agente_id] = pesos_bd[agente_id]
        else:
            salida[agente_id] = {"peso": peso_mem, "historial": []}

    return {
        "pesos": salida,
        "total_agentes": len(salida),
        "fuente": "master_ai_live + bd",
    }
