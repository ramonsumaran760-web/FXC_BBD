"""
live.py — Módulo de datos en vivo FXC_BBD.

Brecha D implementada:
  • OddsStreamListener   — cliente WebSocket con reconexión automática y heartbeat
  • LatencyTracker       — mide y registra latencia con SLA < 500ms
  • Degradación controlada — marca cuotas como "posiblemente desactualizadas" si falla
  • Fallback a polling HTTP cuando el WS no está disponible
  • circuit_breaker_status integrado con odds.py
"""
from __future__ import annotations
import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, AsyncGenerator

from odds import CuotasMercado, odds_monitor
from core.config import settings

logger = logging.getLogger("fxcbbd.live")

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

_SLA_MS               = settings.LATENCY_SLA_MS           # 500ms
_ALERT_THRESHOLD_MS   = settings.LATENCY_ALERT_THRESHOLD_MS  # 1000ms
_HEARTBEAT_INTERVAL   = 30    # segundos entre heartbeats WS
_RECONNECT_BASE_DELAY = 1     # delay inicial de reconexión
_RECONNECT_MAX_DELAY  = 60    # delay máximo (backoff exponencial)
_STALE_TIMEOUT        = 10    # segundos sin update → datos stale


# ─── LATENCY TRACKER ─────────────────────────────────────────────────────────

@dataclass
class LatencyRecord:
    timestamp:  float
    fuente:     str
    latencia_ms: int
    estado:     str    # "ok" | "degradado" | "desconectado"
    match_id:   Optional[int] = None
    superó_sla: bool = False


class LatencyTracker:
    """
    Registra la latencia de cada evento recibido y mantiene métricas en memoria.
    Los registros se persisten en DB a través del worker Celery.
    """

    def __init__(self):
        self._registros:   list[LatencyRecord] = []
        self._p99_ms:      int = 0
        self._total:       int = 0
        self._sobre_sla:   int = 0

    def registrar(
        self,
        fuente: str,
        event_timestamp: float,    # timestamp del evento en la fuente
        match_id: Optional[int] = None,
    ) -> LatencyRecord:
        ahora = time.time()
        latencia_ms = int((ahora - event_timestamp) * 1000)
        superó_sla  = latencia_ms > _SLA_MS

        if superó_sla:
            estado = "degradado" if latencia_ms < _ALERT_THRESHOLD_MS else "desconectado"
        else:
            estado = "ok"

        rec = LatencyRecord(
            timestamp=ahora,
            fuente=fuente,
            latencia_ms=latencia_ms,
            estado=estado,
            match_id=match_id,
            superó_sla=superó_sla,
        )
        self._registros.append(rec)
        if len(self._registros) > 1000:
            self._registros = self._registros[-500:]   # ventana deslizante

        self._total += 1
        if superó_sla:
            self._sobre_sla += 1
            logger.warning("Latencia alta: %dms (fuente=%s, match=%s)", latencia_ms, fuente, match_id)

        return rec

    @property
    def sla_compliance_pct(self) -> float:
        if self._total == 0:
            return 100.0
        return round((1 - self._sobre_sla / self._total) * 100, 1)

    def sla_cumplimiento_pct(self) -> float:
        """Alias en espanol conservado para los endpoints publicos."""
        return self.sla_compliance_pct

    def estadisticas(self) -> dict:
        """Resume la ventana de latencias usando el contrato de la API live."""
        latencias = sorted(rec.latencia_ms for rec in self._registros)
        if not latencias:
            return {
                "promedio_ms": 0.0,
                "p95_ms": 0,
                "p99_ms": 0,
                "cumplimiento_pct": self.sla_compliance_pct,
                "total": 0,
            }

        def percentil(p: float) -> int:
            indice = min(len(latencias) - 1, max(0, math.ceil(len(latencias) * p) - 1))
            return latencias[indice]

        return {
            "promedio_ms": round(sum(latencias) / len(latencias), 1),
            "p95_ms": percentil(0.95),
            "p99_ms": percentil(0.99),
            "cumplimiento_pct": self.sla_compliance_pct,
            "total": len(latencias),
        }

    def ultimos(self, n: int = 20) -> list[LatencyRecord]:
        return self._registros[-n:]


latency_tracker = LatencyTracker()


# ─── CIRCUIT BREAKER DE ALERTAS (PDF 2) ──────────────────────────────────────

class CircuitBreakerAlertas:
    """
    Congela alertas si el mercado sufre una anomalía de cuotas o
    si la fuente de datos está degradada.
    """
    CLOSED    = "OPERATIONAL"      # Funcionando normal
    OPEN      = "CIRCUIT_OPEN"     # Alertas congeladas
    HALF_OPEN = "RECOVERING"       # Probando recuperación

    def __init__(self, timeout_s: int = 60):
        self._estado    = self.CLOSED
        self._abierto_en: Optional[float] = None
        self._timeout   = timeout_s
        self._fallos    = 0

    @property
    def estado(self) -> str:
        if self._estado == self.OPEN:
            if time.time() - self._abierto_en > self._timeout:
                self._estado = self.HALF_OPEN
        return self._estado

    def registrar_anomalia(self, motivo: str = ""):
        self._fallos += 1
        logger.warning("Circuit breaker activado: %s (fallos=%d)", motivo, self._fallos)
        self._estado    = self.OPEN
        self._abierto_en = time.time()

    def registrar_exito(self):
        if self._estado == self.HALF_OPEN:
            self._estado = self.CLOSED
            self._fallos = 0
            logger.info("Circuit breaker restaurado → OPERATIONAL")

    def permite_alerta(self) -> bool:
        return self.estado == self.CLOSED


circuit_breaker = CircuitBreakerAlertas(timeout_s=60)


# ─── ODDS STREAM LISTENER (BRECHA D) ─────────────────────────────────────────

class OddsStreamListener:
    """
    Cliente WebSocket de baja latencia para datos de cuotas en vivo.
    Implementa:
      • Reconexión automática con backoff exponencial
      • Heartbeat periódico
      • Marcado de datos stale si la conexión falla
      • Integración con LatencyTracker y CircuitBreaker
    """

    def __init__(
        self,
        ws_url: str,
        on_odds_update: Callable[[CuotasMercado], None],
        fuente: str = "ws_provider",
    ):
        self._ws_url         = ws_url
        self._on_update      = on_odds_update
        self._fuente         = fuente
        self._running        = False
        self._retry_delay    = _RECONNECT_BASE_DELAY
        self._last_update:   dict[str, float] = {}   # ticker → timestamp último update

    async def start(self):
        """Inicia el listener con reconexión automática."""
        self._running = True
        while self._running:
            try:
                await self._conectar()
                self._retry_delay = _RECONNECT_BASE_DELAY   # reset delay en éxito
            except Exception as e:
                logger.error("WS desconectado (%s): %s. Reconectando en %ds...",
                             self._fuente, e, self._retry_delay)
                await self._marcar_datos_stale()
                await asyncio.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, _RECONNECT_MAX_DELAY)

    async def stop(self):
        self._running = False

    async def _conectar(self):
        """Abre la conexión WS. Requiere websockets instalado y credenciales."""
        try:
            import websockets
        except ImportError:
            logger.warning("websockets no instalado — usando modo simulación")
            await self._modo_simulacion()
            return

        async with websockets.connect(
            self._ws_url,
            ping_interval=_HEARTBEAT_INTERVAL,
            ping_timeout=10,
            extra_headers={"Authorization": f"Bearer {settings.EXCHANGE_API_KEY}"},
        ) as ws:
            logger.info("WS conectado: %s", self._ws_url)
            circuit_breaker.registrar_exito()
            async for mensaje in ws:
                await self._procesar_mensaje(mensaje)

    async def _procesar_mensaje(self, raw: str):
        """Parsea el mensaje WS y lo convierte a CuotasMercado."""
        try:
            data = json.loads(raw)
            event_ts = data.get("timestamp", time.time())

            cuotas = CuotasMercado(
                match_id       = data.get("match_id", 0),
                ticker         = data.get("ticker", ""),
                fuente         = self._fuente,
                timestamp      = event_ts,
                es_live        = data.get("is_live", False),
                minuto         = data.get("minute"),
                back_local     = data.get("back_home", 0.0),
                back_empate    = data.get("back_draw", 0.0),
                back_visitante = data.get("back_away", 0.0),
                lay_local      = data.get("lay_home"),
                lay_empate     = data.get("lay_draw"),
                lay_visitante  = data.get("lay_away"),
                datos_frescos  = True,
            )

            # Registrar latencia
            rec = latency_tracker.registrar(self._fuente, event_ts, cuotas.match_id)

            # Verificar anomalía de cuota → circuit breaker
            if odds_monitor.registrar(cuotas):
                circuit_breaker.registrar_anomalia("variación de cuota > 20%")

            self._last_update[cuotas.ticker] = time.time()
            self._on_update(cuotas)

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Error parseando mensaje WS: %s", e)

    async def _marcar_datos_stale(self):
        """Notifica que los datos actuales pueden estar desactualizados."""
        logger.warning("Datos marcados como STALE — conexión perdida con %s", self._fuente)
        # En producción: publicar evento en Redis para que el frontend muestre
        # "cuotas posiblemente desactualizadas"
        circuit_breaker.registrar_anomalia("conexión WS perdida")

    async def _modo_simulacion(self):
        """
        Modo fallback: genera cuotas simuladas para desarrollo sin proveedor B2B.
        Simula un partido RMA-BAR con cuotas cambiantes cada 3 segundos.
        """
        import random
        logger.info("Iniciando modo simulación de cuotas en vivo")

        base_local = 1.85
        base_empate = 3.40
        base_visit = 4.20

        while self._running:
            # Simular variación de mercado ±3%
            variacion = lambda b: round(b * (1 + random.uniform(-0.03, 0.03)), 2)

            cuotas = CuotasMercado(
                match_id=1,
                ticker="RMA-BAR",
                fuente="simulacion",
                timestamp=time.time(),
                es_live=True,
                minuto=random.randint(1, 90),
                back_local=variacion(base_local),
                back_empate=variacion(base_empate),
                back_visitante=variacion(base_visit),
                lay_local=variacion(base_local + 0.02),
                lay_empate=variacion(base_empate + 0.05),
                lay_visitante=variacion(base_visit + 0.08),
                datos_frescos=True,
            )

            latency_tracker.registrar("simulacion", cuotas.timestamp - 0.1, 1)
            if odds_monitor.registrar(cuotas):
                circuit_breaker.registrar_anomalia("simulación - anomalía detectada")

            self._on_update(cuotas)
            await asyncio.sleep(3)


# ─── FALLBACK POLLING ────────────────────────────────────────────────────────

async def polling_fallback(
    url: str,
    ticker: str,
    match_id: int,
    on_update: Callable[[CuotasMercado], None],
    intervalo_s: int = 5,
):
    """
    Fallback HTTP polling cuando el WebSocket no está disponible.
    Las cuotas se marcan como datos_frescos=False para indicar latencia mayor.
    """
    import aiohttp
    logger.info("Iniciando polling HTTP fallback para %s", ticker)

    async with aiohttp.ClientSession() as session:
        while True:
            t0 = time.time()
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status == 200:
                        data = await r.json()
                        cuotas = CuotasMercado(
                            match_id=match_id,
                            ticker=ticker,
                            fuente="polling_http",
                            timestamp=t0,
                            es_live=data.get("is_live", False),
                            back_local=data.get("odds_home", 0),
                            back_empate=data.get("odds_draw", 0),
                            back_visitante=data.get("odds_away", 0),
                            datos_frescos=False,   # ← STALE: latencia > SLA
                        )
                        latency_tracker.registrar("polling_http", t0, match_id)
                        on_update(cuotas)
            except Exception as e:
                logger.warning("Polling falló: %s", e)

            await asyncio.sleep(intervalo_s)
