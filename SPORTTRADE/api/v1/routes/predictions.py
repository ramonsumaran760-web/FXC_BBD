"""
predictions.py — Ruta FastAPI para el pipeline completo del Master AI.

GET  /api/v1/predictions/{ticker}     → predicción completa con Kelly y EV
POST /api/v1/predictions/analizar     → análisis on-demand con datos custom
GET  /api/v1/predictions/live         → todas las predicciones de partidos en vivo
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from core.database import get_db
from models.models import Match, Odds as OddsModel, Prediction, BankrollSettings as BankrollDB
from master_ai.master_ai import master_ai, SalidaAgente, OutputMasterAI
from master_ai.agentes.agent_1_estadistica import EstadisticaEquipo, calcular as calc_estadistica
from master_ai.agentes.agent_2_racha import FormaReciente, calcular as calc_racha
from master_ai.agentes.agent_3_lesiones import ReporteLesiones, calcular as calc_lesiones
from master_ai.agentes.agent_4_noticias import SentimientoEquipo, calcular as calc_noticias
from master_ai.agentes.agent_5_arbitro import PerfilArbitro, calcular as calc_arbitro
from master_ai.agentes.agent_6_clima import CondicionesPartido, calcular as calc_clima
from master_ai.agentes.agent_7_odds import MovimientoMercado, SnapshotOdds, calcular as calc_odds
from master_ai.agentes.agent_8_montecarlo import InputMonteCarlo, calcular as calc_mc
from odds import CuotasMercado
from finanzas import BankrollSettings
import time

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class PredictionRequest(BaseModel):
    ticker: str
    # Estadísticas
    pj_local: int = 20; pg_local: int = 10; pe_local: int = 5; pp_local: int = 5
    gf_local: int = 30; gc_local: int = 20; xg_prom_local: float = 1.4; xgc_prom_local: float = 1.1
    pos_local: int = 5
    pj_visit: int = 20; pg_visit: int = 8; pe_visit: int = 6; pp_visit: int = 6
    gf_visit: int = 25; gc_visit: int = 22; xg_prom_visit: float = 1.2; xgc_prom_visit: float = 1.3
    pos_visit: int = 8
    # Racha (W/D/L más reciente primero)
    racha_local: str = "WDWLW"; racha_visit: str = "LWDWL"
    # Clima
    temperatura: float = 18.0; condicion_clima: str = "soleado"
    # Cuotas actuales
    cuota_back_local: float = 1.85; cuota_back_empate: float = 3.40; cuota_back_visit: float = 4.20
    cuota_lay_local: Optional[float] = None; cuota_lay_empate: Optional[float] = None
    cuota_lay_visit: Optional[float] = None
    # xG para Monte Carlo
    goles_prom_local_at: float = 1.6; goles_prom_local_def: float = 1.1
    goles_prom_visit_at: float = 1.2; goles_prom_visit_def: float = 1.3
    # Bankroll (opcional — activa Kelly)
    saldo: Optional[float] = None; perfil_riesgo: str = "moderado"


class PredictionResponse(BaseModel):
    ticker: str
    local: float; empate: float; visitante: float
    confianza: float; valor: str
    meta_metrics: dict
    kelly: Optional[dict] = None
    contribuciones: Optional[dict] = None


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/analizar", response_model=PredictionResponse)
async def analizar_partido(req: PredictionRequest):
    """
    Pipeline completo del Master AI on-demand.
    No requiere datos en BD — ideal para análisis previos y testing.
    """
    # ── 1. Ejecutar los 8 agentes ─────────────────────────────────────────
    salidas = []

    # Agente 1 — Estadística
    s1 = calc_estadistica(
        EstadisticaEquipo(req.ticker.split("-")[0], req.pj_local, req.pg_local, req.pe_local,
                          req.pp_local, req.gf_local, req.gc_local, req.xg_prom_local,
                          req.xgc_prom_local, req.pos_local),
        EstadisticaEquipo(req.ticker.split("-")[1] if "-" in req.ticker else "VISIT",
                          req.pj_visit, req.pg_visit, req.pe_visit, req.pp_visit,
                          req.gf_visit, req.gc_visit, req.xg_prom_visit, req.xgc_prom_visit, req.pos_visit),
    )
    salidas.append(SalidaAgente(**{k: s1[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 2 — Racha
    s2 = calc_racha(
        FormaReciente(req.ticker.split("-")[0], list(req.racha_local[:5]), [1]*5, [1]*5),
        FormaReciente(req.ticker.split("-")[-1], list(req.racha_visit[:5]), [1]*5, [1]*5),
    )
    salidas.append(SalidaAgente(**{k: s2[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 3 — Lesiones (sin datos → impacto neutro)
    s3 = calc_lesiones(ReporteLesiones(req.ticker.split("-")[0]), ReporteLesiones(req.ticker.split("-")[-1]))
    salidas.append(SalidaAgente(**{k: s3[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 4 — Noticias (neutro)
    s4 = calc_noticias(
        SentimientoEquipo(req.ticker.split("-")[0], 0.0, 0),
        SentimientoEquipo(req.ticker.split("-")[-1], 0.0, 0),
    )
    salidas.append(SalidaAgente(**{k: s4[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 5 — Árbitro (sin datos)
    s5 = calc_arbitro(PerfilArbitro("Desconocido", 0, 4.2, 0.3, 0.8, 0.44, 0.27))
    salidas.append(SalidaAgente(**{k: s5[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 6 — Clima
    from master_ai.agentes.agent_6_clima import CondicionClima
    condicion = req.condicion_clima if req.condicion_clima in ("soleado","nublado","lluvia_ligera","lluvia_fuerte","nieve","calor_extremo","viento_fuerte") else "soleado"
    s6 = calc_clima(CondicionesPartido(req.temperatura, condicion))
    salidas.append(SalidaAgente(**{k: s6[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 7 — Odds Movement (apertura ≈ cuotas actuales ± 2%)
    apertura = SnapshotOdds(time.time()-3600, req.cuota_back_local*1.02, req.cuota_back_empate*1.02, req.cuota_back_visit*1.02)
    actual   = SnapshotOdds(time.time(), req.cuota_back_local, req.cuota_back_empate, req.cuota_back_visit)
    s7 = calc_odds(MovimientoMercado(req.ticker, apertura, actual))
    salidas.append(SalidaAgente(**{k: s7[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 8 — Monte Carlo
    s8 = calc_mc(InputMonteCarlo(req.goles_prom_local_at, req.goles_prom_local_def,
                                  req.goles_prom_visit_at, req.goles_prom_visit_def))
    salidas.append(SalidaAgente(**{k: s8[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # ── 2. Cuotas actuales ───────────────────────────────────────────────────
    cuotas = CuotasMercado(
        match_id=0, ticker=req.ticker, fuente="manual",
        back_local=req.cuota_back_local, back_empate=req.cuota_back_empate,
        back_visitante=req.cuota_back_visit,
        lay_local=req.cuota_lay_local, lay_empate=req.cuota_lay_empate,
        lay_visitante=req.cuota_lay_visit,
        datos_frescos=True,
    )

    # ── 3. Bankroll (Brecha A) ────────────────────────────────────────────────
    bankroll = None
    if req.saldo and req.saldo > 0:
        bankroll = BankrollSettings(saldo_declarado=req.saldo, perfil_riesgo=req.perfil_riesgo)

    # ── 4. Master AI ─────────────────────────────────────────────────────────
    output: OutputMasterAI = master_ai.procesar(req.ticker, salidas, cuotas, bankroll)

    kelly_data = None
    if output.kelly_fraccion is not None:
        kelly_data = {
            "fraccion": output.kelly_fraccion,
            "monto_pct": output.monto_sugerido_pct,
            "resultado_rec": output.resultado_recomendado,
            "monto_moneda": round(output.kelly_fraccion * (req.saldo or 0), 2),
        }

    return PredictionResponse(
        ticker=output.ticker,
        local=output.local, empate=output.empate, visitante=output.visitante,
        confianza=output.confianza, valor=output.valor,
        meta_metrics=output.meta_metrics,
        kelly=kelly_data,
        contribuciones=output.contribuciones,
    )


@router.get("/live", response_model=list[dict])
async def predicciones_live(db: AsyncSession = Depends(get_db)):
    """Devuelve las últimas predicciones de partidos en vivo."""
    result = await db.execute(
        select(Prediction)
        .where(Prediction.es_live == True)
        .order_by(Prediction.creado.desc())
        .limit(20)
    )
    preds = result.scalars().all()
    return [
        {
            "ticker": p.ticker,
            "local": p.prob_local * 100,
            "empate": p.prob_empate * 100,
            "visitante": p.prob_visitante * 100,
            "confianza": p.confianza,
            "valor": p.valor,
            "ev": p.ev_local or p.ev_empate or p.ev_visitante,
            "kelly_pct": p.monto_sugerido_pct,
            "creado": p.creado.isoformat(),
        }
        for p in preds
    ]
