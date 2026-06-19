"""
live_routes.py — Brecha D: Stream en tiempo real de odds y predicciones.

GET  /api/v1/live/eventos            → partidos en vivo con estado CB
GET  /api/v1/live/odds/{ticker}      → cuotas actuales con latencia y frescura
GET  /api/v1/live/latencia           → métricas de SLA WebSocket (SLA <500ms)
WS   /api/v1/live/ws/{ticker}        → WebSocket stream de odds + predicciones
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from core.database import get_db
from models.models import Match, Odds as OddsModel, LatencyMonitor
from live import latency_tracker, circuit_breaker, polling_fallback

logger = logging.getLogger("fxcbbd.live")
router = APIRouter(prefix="/api/v1/live", tags=["live"])


# ─── WS CONNECTION MANAGER ───────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._activas: dict[str, list[WebSocket]] = {}

    async def conectar(self, ticker: str, ws: WebSocket):
        await ws.accept()
        self._activas.setdefault(ticker, []).append(ws)
        logger.info("WS conectado: %s (total: %d)", ticker, len(self._activas[ticker]))

    def desconectar(self, ticker: str, ws: WebSocket):
        if ticker in self._activas:
            self._activas[ticker].discard(ws) if hasattr(self._activas[ticker], 'discard') else None
            try:
                self._activas[ticker].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, ticker: str, data: dict):
        muertos = []
        for ws in self._activas.get(ticker, []):
            try:
                await ws.send_json(data)
            except Exception:
                muertos.append(ws)
        for ws in muertos:
            self.desconectar(ticker, ws)

    @property
    def total_conexiones(self) -> int:
        return sum(len(v) for v in self._activas.values())


manager = ConnectionManager()


# ─── ENDPOINTS HTTP ───────────────────────────────────────────────────────────

@router.get("/eventos")
async def partidos_en_vivo(db: AsyncSession = Depends(get_db)):
    """Lista de partidos en vivo con estado del circuit breaker."""
    result = await db.execute(
        select(Match).where(Match.status == "live").order_by(Match.fecha.asc())
    )
    partidos = result.scalars().all()
    return {
        "circuit_breaker": circuit_breaker.estado,
        "total_en_vivo":   len(partidos),
        "latencia_sla_pct": latency_tracker.sla_cumplimiento_pct(),
        "partidos": [
            {
                "id":       p.id,
                "ticker":   p.ticker,
                "liga":     p.liga,
                "local":    p.equipo_local,
                "visitante":p.equipo_visitante,
                "fecha":    p.fecha.isoformat(),
            }
            for p in partidos
        ],
    }


@router.get("/odds/{ticker}")
async def cuotas_live(ticker: str, db: AsyncSession = Depends(get_db)):
    """Cuotas actuales de un ticker con metadatos de latencia y frescura."""
    result = await db.execute(
        select(OddsModel)
        .where(OddsModel.ticker == ticker)
        .order_by(desc(OddsModel.actualizado))
        .limit(1)
    )
    odds = result.scalar_one_or_none()
    if not odds:
        raise HTTPException(404, f"Sin odds para ticker={ticker}")

    return {
        "ticker":          ticker,
        "back_local":      odds.back_local,
        "back_empate":     odds.back_empate,
        "back_visitante":  odds.back_visitante,
        "lay_local":       odds.lay_local,
        "lay_empate":      odds.lay_empate,
        "lay_visitante":   odds.lay_visitante,
        "overround":       odds.overround,
        "latencia_ms":     odds.latencia_ms,
        "datos_frescos":   odds.datos_frescos,
        "es_live":         odds.es_live,
        "actualizado":     odds.actualizado.isoformat(),
        "circuit_breaker": circuit_breaker.estado,
    }


@router.get("/latencia")
async def metricas_latencia():
    """
    Métricas de SLA WebSocket (objetivo: <500ms en el 95% de updates).
    Devuelve ventana móvil de los últimos 1000 registros.
    """
    stats = latency_tracker.estadisticas()
    return {
        "sla_ms":          500,
        "promedio_ms":     stats.get("promedio_ms"),
        "p95_ms":          stats.get("p95_ms"),
        "p99_ms":          stats.get("p99_ms"),
        "cumplimiento_pct":stats.get("cumplimiento_pct"),
        "total_mediciones":stats.get("total"),
        "circuit_breaker": circuit_breaker.estado,
    }


# ─── WEBSOCKET ────────────────────────────────────────────────────────────────

@router.websocket("/ws/{ticker}")
async def websocket_odds(ticker: str, ws: WebSocket):
    """
    Stream en tiempo real de odds + predicciones para un ticker.
    El servidor envía updates cada vez que las odds cambian.
    Latencia objetivo: <500ms (Brecha D SLA).
    """
    await manager.conectar(ticker, ws)
    try:
        # Bucle de recepción (heartbeat + control)
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                data = json.loads(msg) if msg else {}
                if data.get("type") == "ping":
                    await ws.send_json({"type": "pong", "ticker": ticker})
            except asyncio.TimeoutError:
                # Timeout 30s → enviar heartbeat
                await ws.send_json({"type": "heartbeat", "ticker": ticker,
                                    "circuit_breaker": circuit_breaker.estado})
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error("WS error %s: %s", ticker, e)
    finally:
        manager.desconectar(ticker, ws)
        logger.info("WS desconectado: %s", ticker)


async def broadcast_odds_update(ticker: str, odds_data: dict):
    """
    Llamado desde el OddsStreamListener cuando llegan nuevas odds.
    Hace broadcast a todos los clientes conectados a ese ticker.
    """
    await manager.broadcast(ticker, {
        "type":            "odds_update",
        "ticker":          ticker,
        "data":            odds_data,
        "circuit_breaker": circuit_breaker.estado,
    })
