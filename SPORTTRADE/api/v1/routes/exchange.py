"""
exchange.py — Brecha B: Exchange Back/Lay + Trading-Out.

POST /api/v1/exchange/abrir         → abrir posición back o lay
POST /api/v1/exchange/trading-out   → calcular y ejecutar cierre de posición
GET  /api/v1/exchange/posiciones    → posiciones abiertas del usuario
GET  /api/v1/exchange/historial     → historial de posiciones cerradas
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from core.database import get_db
from models.models import ExchangePosition, Match, Prediction
from finanzas import calcular_trading_out, TradingOutResult

router = APIRouter(prefix="/api/v1/exchange", tags=["exchange"])


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class AbrirPosicion(BaseModel):
    user_id: int
    match_id: int
    ticker: str
    tipo: str = Field(..., pattern="^(back|lay)$")
    resultado: str = Field(..., pattern="^(local|empate|visitante)$")
    cuota: float = Field(..., ge=1.01)
    stake: float = Field(..., gt=0)


class TradingOutRequest(BaseModel):
    posicion_id: int
    cuota_lay_actual: float = Field(..., ge=1.01, description="Cuota lay actual del mercado")
    comision: float = Field(0.05, ge=0, le=0.15)


class TradingOutResponse(BaseModel):
    posicion_id: int
    ticker: str
    stake_back: float
    cuota_back_entrada: float
    cuota_lay_actual: float
    stake_lay_recomendado: float
    ganancia_garantizada: float
    escenario_back_gana: float
    escenario_lay_gana: float
    ejecutado: bool


class PosicionResponse(BaseModel):
    id: int
    ticker: str
    tipo: str
    resultado: str
    cuota: float
    stake: float
    pnl_flotante: Optional[float]
    estado: str
    creado: str


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/abrir", response_model=PosicionResponse, status_code=201)
async def abrir_posicion(req: AbrirPosicion, db: AsyncSession = Depends(get_db)):
    """Abre una posición back o lay en el exchange."""
    # Verificar que el match existe
    match = await db.get(Match, req.match_id)
    if not match:
        raise HTTPException(404, f"Match {req.match_id} no encontrado")

    posicion = ExchangePosition(
        user_id    = req.user_id,
        match_id   = req.match_id,
        ticker     = req.ticker,
        tipo       = req.tipo,
        resultado  = req.resultado,
        cuota      = req.cuota,
        stake      = req.stake,
        estado     = "abierta",
        pnl_flotante = 0.0,
    )
    db.add(posicion)
    await db.commit()
    await db.refresh(posicion)

    return PosicionResponse(
        id          = posicion.id,
        ticker      = posicion.ticker,
        tipo        = posicion.tipo,
        resultado   = posicion.resultado,
        cuota       = posicion.cuota,
        stake       = posicion.stake,
        pnl_flotante= posicion.pnl_flotante,
        estado      = posicion.estado,
        creado      = posicion.creado.isoformat(),
    )


@router.post("/trading-out", response_model=TradingOutResponse)
async def ejecutar_trading_out(req: TradingOutRequest, db: AsyncSession = Depends(get_db)):
    """
    Calcula y ejecuta trading-out para cerrar una posición back con ganancia garantizada.

    Fórmula: stake_lay = (stake_back × cuota_back_entrada) / cuota_lay_actual
    Ganancia garantizada = stake_lay × (cuota_lay_actual - 1) × (1 - comision) - (stake_back - stake_lay)
    """
    posicion = await db.get(ExchangePosition, req.posicion_id)
    if not posicion:
        raise HTTPException(404, f"Posición {req.posicion_id} no encontrada")
    if posicion.estado != "abierta":
        raise HTTPException(400, f"Posición ya está {posicion.estado}")
    if posicion.tipo != "back":
        raise HTTPException(400, "Trading-out solo aplica a posiciones back")

    resultado: TradingOutResult = calcular_trading_out(
        stake_back           = posicion.stake,
        cuota_back_entrada   = posicion.cuota,
        cuota_lay_actual     = req.cuota_lay_actual,
        comision             = req.comision,
    )

    if resultado.ganancia_garantizada > 0:
        # Marcar como cerrada con trading-out
        posicion.estado                = "cerrada"
        posicion.trading_out_ejecutado = True
        posicion.pnl_flotante          = resultado.ganancia_garantizada
        posicion.cerrada               = datetime.utcnow()
        await db.commit()
        ejecutado = True
    else:
        ejecutado = False  # Ganancia negativa — no conviene, informar al usuario

    return TradingOutResponse(
        posicion_id            = req.posicion_id,
        ticker                 = posicion.ticker,
        stake_back             = posicion.stake,
        cuota_back_entrada     = posicion.cuota,
        cuota_lay_actual       = req.cuota_lay_actual,
        stake_lay_recomendado  = round(resultado.stake_lay, 2),
        ganancia_garantizada   = round(resultado.ganancia_garantizada, 2),
        escenario_back_gana    = round(resultado.escenario_back_gana, 2),
        escenario_lay_gana     = round(resultado.escenario_lay_gana, 2),
        ejecutado              = ejecutado,
    )


@router.get("/posiciones")
async def posiciones_abiertas(user_id: int, db: AsyncSession = Depends(get_db)):
    """Posiciones abiertas del usuario ordenadas por fecha."""
    result = await db.execute(
        select(ExchangePosition).where(
            ExchangePosition.user_id == user_id,
            ExchangePosition.estado == "abierta",
        ).order_by(ExchangePosition.creado.desc())
    )
    posiciones = result.scalars().all()
    return [
        {
            "id":          p.id,
            "ticker":      p.ticker,
            "tipo":        p.tipo,
            "resultado":   p.resultado,
            "cuota":       p.cuota,
            "stake":       p.stake,
            "pnl_flotante":p.pnl_flotante,
            "estado":      p.estado,
            "creado":      p.creado.isoformat(),
        }
        for p in posiciones
    ]


@router.get("/historial")
async def historial_posiciones(
    user_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Historial de posiciones cerradas con P&L realizado."""
    result = await db.execute(
        select(ExchangePosition).where(
            ExchangePosition.user_id == user_id,
            ExchangePosition.estado == "cerrada",
        )
        .order_by(ExchangePosition.cerrada.desc())
        .limit(limit)
    )
    posiciones = result.scalars().all()
    pnl_total = sum(p.pnl_flotante or 0 for p in posiciones)
    return {
        "total_operaciones": len(posiciones),
        "pnl_total_realizado": round(pnl_total, 2),
        "posiciones": [
            {
                "id":            p.id,
                "ticker":        p.ticker,
                "tipo":          p.tipo,
                "resultado":     p.resultado,
                "cuota":         p.cuota,
                "stake":         p.stake,
                "pnl_realizado": p.pnl_flotante,
                "trading_out":   p.trading_out_ejecutado,
                "cerrada":       p.cerrada.isoformat() if p.cerrada else None,
            }
            for p in posiciones
        ],
    }
