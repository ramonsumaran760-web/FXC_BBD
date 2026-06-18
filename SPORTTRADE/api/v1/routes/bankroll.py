"""
bankroll.py — Brecha A: Gestión de Bankroll con Kelly Criterion.

POST /api/v1/bankroll/configurar     → guardar configuración Kelly del usuario
GET  /api/v1/bankroll/{user_id}      → consultar configuración actual
POST /api/v1/bankroll/recomendar     → calcular apuesta óptima con Kelly
GET  /api/v1/bankroll/resumen/{user_id} → P&L, exposición total, slots activos
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from core.database import get_db
from models.models import BankrollSettings as BankrollDB, ExchangePosition
from finanzas import (
    BankrollSettings,
    calcular_fraccion_kelly,
    bankroll_manager,
    SenalyKelly,
)

router = APIRouter(prefix="/api/v1/bankroll", tags=["bankroll"])


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class BankrollConfig(BaseModel):
    user_id: int
    saldo_declarado: float = Field(..., gt=0, description="Capital total disponible")
    perfil_riesgo: str = Field("moderado", pattern="^(conservador|moderado|agresivo)$")
    max_exp_evento: float = Field(0.08, ge=0.01, le=0.20)
    max_exp_total: float = Field(0.25, ge=0.05, le=0.50)
    kelly_divisor: float = Field(2.0, ge=1.0, le=8.0)


class KellyRequest(BaseModel):
    user_id: int
    ticker: str
    resultado_rec: str = Field(..., pattern="^(local|empate|visitante)$")
    prob_ia: float = Field(..., ge=0.01, le=0.99)
    cuota: float = Field(..., ge=1.01)
    ev: float
    eventos_activos_liga: int = Field(0, ge=0)


class KellyResponse(BaseModel):
    ticker: str
    resultado_rec: str
    prob_ia: float
    cuota: float
    ev: float
    fraccion_kelly: float
    monto_pct: float
    monto_moneda: float
    saldo_base: float
    perfil_riesgo: str
    razon_rechazo: Optional[str] = None
    kelly_puro: float


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/configurar", status_code=201)
async def configurar_bankroll(cfg: BankrollConfig, db: AsyncSession = Depends(get_db)):
    """Guarda o actualiza la configuración de Kelly del usuario."""
    result = await db.execute(
        select(BankrollDB).where(BankrollDB.user_id == cfg.user_id)
    )
    registro = result.scalar_one_or_none()

    if registro:
        registro.saldo_declarado = cfg.saldo_declarado
        registro.perfil_riesgo   = cfg.perfil_riesgo
        registro.max_exp_evento  = cfg.max_exp_evento
        registro.max_exp_total   = cfg.max_exp_total
        registro.kelly_divisor   = cfg.kelly_divisor
        registro.actualizado     = datetime.utcnow()
    else:
        registro = BankrollDB(
            user_id          = cfg.user_id,
            saldo_declarado  = cfg.saldo_declarado,
            perfil_riesgo    = cfg.perfil_riesgo,
            max_exp_evento   = cfg.max_exp_evento,
            max_exp_total    = cfg.max_exp_total,
            kelly_divisor    = cfg.kelly_divisor,
        )
        db.add(registro)

    await db.commit()
    return {"status": "ok", "user_id": cfg.user_id, "perfil_riesgo": cfg.perfil_riesgo}


@router.get("/{user_id}")
async def obtener_bankroll(user_id: int, db: AsyncSession = Depends(get_db)):
    """Consulta la configuración actual de Kelly."""
    result = await db.execute(
        select(BankrollDB).where(BankrollDB.user_id == user_id)
    )
    registro = result.scalar_one_or_none()
    if not registro:
        raise HTTPException(404, f"Bankroll no configurado para user_id={user_id}")

    return {
        "user_id":         registro.user_id,
        "saldo_declarado": registro.saldo_declarado,
        "perfil_riesgo":   registro.perfil_riesgo,
        "max_exp_evento":  registro.max_exp_evento,
        "max_exp_total":   registro.max_exp_total,
        "kelly_divisor":   registro.kelly_divisor,
        "creado":          registro.creado.isoformat(),
    }


@router.post("/recomendar", response_model=KellyResponse)
async def recomendar_apuesta(req: KellyRequest, db: AsyncSession = Depends(get_db)):
    """
    Calcula la apuesta óptima según Kelly Criterion con gestión de riesgos.
    Aplica tope por evento, tope de exposición total, y penalización por correlación.
    """
    result = await db.execute(
        select(BankrollDB).where(BankrollDB.user_id == req.user_id)
    )
    registro = result.scalar_one_or_none()
    if not registro:
        raise HTTPException(
            400,
            "Configure bankroll primero con POST /api/v1/bankroll/configurar"
        )

    bs = BankrollSettings(
        saldo_declarado = registro.saldo_declarado,
        perfil_riesgo   = registro.perfil_riesgo,
        max_exp_evento  = registro.max_exp_evento,
        max_exp_total   = registro.max_exp_total,
        kelly_divisor   = registro.kelly_divisor,
    )

    # Calcular Kelly puro para mostrar al usuario
    b = req.cuota - 1.0
    p = req.prob_ia
    kelly_puro = max(0.0, (b * p - (1 - p)) / b) if b > 0 else 0.0

    senal: SenalyKelly = bankroll_manager(
        ticker              = req.ticker,
        resultado_rec       = req.resultado_rec,
        prob_ia             = req.prob_ia,
        cuota               = req.cuota,
        ev                  = req.ev,
        settings            = bs,
        eventos_activos_liga= req.eventos_activos_liga,
    )

    return KellyResponse(
        ticker         = req.ticker,
        resultado_rec  = senal.resultado_rec,
        prob_ia        = req.prob_ia,
        cuota          = req.cuota,
        ev             = req.ev,
        fraccion_kelly = senal.fraccion_kelly,
        monto_pct      = round(senal.fraccion_kelly * 100, 2),
        monto_moneda   = round(senal.fraccion_kelly * registro.saldo_declarado, 2),
        saldo_base     = registro.saldo_declarado,
        perfil_riesgo  = registro.perfil_riesgo,
        razon_rechazo  = senal.razon_rechazo,
        kelly_puro     = round(kelly_puro * 100, 2),
    )


@router.get("/resumen/{user_id}")
async def resumen_bankroll(user_id: int, db: AsyncSession = Depends(get_db)):
    """P&L actual, exposición total y slots activos de apuestas abiertas."""
    result_cfg = await db.execute(
        select(BankrollDB).where(BankrollDB.user_id == user_id)
    )
    cfg = result_cfg.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, f"Bankroll no configurado para user_id={user_id}")

    # Posiciones abiertas del usuario
    result_pos = await db.execute(
        select(ExchangePosition).where(
            ExchangePosition.user_id == user_id,
            ExchangePosition.estado == "abierta",
        )
    )
    posiciones = result_pos.scalars().all()

    exposicion_total = sum(p.stake for p in posiciones)
    pnl_flotante     = sum(p.pnl_flotante or 0 for p in posiciones)
    slots_activos    = len(posiciones)

    return {
        "user_id":           user_id,
        "saldo_declarado":   cfg.saldo_declarado,
        "perfil_riesgo":     cfg.perfil_riesgo,
        "exposicion_total":  round(exposicion_total, 2),
        "exposicion_pct":    round(exposicion_total / cfg.saldo_declarado * 100, 1),
        "pnl_flotante":      round(pnl_flotante, 2),
        "slots_activos":     slots_activos,
        "max_exp_total_pct": cfg.max_exp_total * 100,
        "margen_disponible": round((cfg.max_exp_total * cfg.saldo_declarado - exposicion_total), 2),
    }
