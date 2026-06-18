"""
FXC_BBD — Esquema de base de datos completo.
Tablas originales (matches, odds, predictions) + extensiones de las 4 brechas:
  Brecha A → bankroll_settings
  Brecha B → exchange_positions
  Brecha C → backtesting_logs, agent_weights
  Brecha D → latency_monitor
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    JSON, ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship
from core.database import Base


# ─── TABLA CORE: PARTIDOS ────────────────────────────────────────────────────

class Match(Base):
    __tablename__ = "matches"

    id            = Column(Integer, primary_key=True, index=True)
    ticker        = Column(String(20), unique=True, index=True)   # "RMA-BAR"
    deporte       = Column(String(30), default="futbol")
    liga          = Column(String(100))
    equipo_local  = Column(String(100), nullable=False)
    equipo_visit  = Column(String(100), nullable=False)
    fecha         = Column(DateTime, nullable=False)
    status        = Column(String(20), default="programado")      # programado | en_vivo | finalizado
    minuto        = Column(Integer, nullable=True)
    goles_local   = Column(Integer, nullable=True)
    goles_visit   = Column(Integer, nullable=True)
    resultado     = Column(String(10), nullable=True)             # "local" | "empate" | "visitante"
    estadio       = Column(String(150), nullable=True)
    pais          = Column(String(50), nullable=True)
    temperatura   = Column(Float, nullable=True)
    condicion_wx  = Column(String(50), nullable=True)             # "soleado" | "lluvia" | etc.
    creado        = Column(DateTime, default=datetime.utcnow)
    actualizado   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    odds         = relationship("Odds", back_populates="match", lazy="dynamic")
    predictions  = relationship("Prediction", back_populates="match", lazy="dynamic")

    __table_args__ = (
        Index("idx_matches_status_date", "status", "fecha"),
    )


# ─── TABLA CORE: CUOTAS (BACK + LAY) ─────────────────────────────────────────

class Odds(Base):
    """
    Almacena cuotas back y lay por separado.
    En un exchange real ambas coexisten con spread entre ellas.
    Brecha B: agregados lay_local, lay_empate, lay_visitante.
    """
    __tablename__ = "odds"

    id             = Column(Integer, primary_key=True, index=True)
    match_id       = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    timestamp      = Column(DateTime, default=datetime.utcnow, index=True)

    # Back odds (a favor de que ocurra)
    back_local     = Column(Float)
    back_empate    = Column(Float)
    back_visitante = Column(Float)

    # Lay odds — Brecha B (en contra de que ocurra)
    lay_local      = Column(Float, nullable=True)
    lay_empate     = Column(Float, nullable=True)
    lay_visitante  = Column(Float, nullable=True)

    # Probabilidades implícitas (post overround correction)
    prob_impl_local    = Column(Float)
    prob_impl_empate   = Column(Float)
    prob_impl_visitante = Column(Float)
    overround          = Column(Float)       # suma de (1/cuota) − 1

    fuente         = Column(String(50))      # "bet365" | "betfair" | "sportradar"
    es_live        = Column(Boolean, default=False)
    latencia_ms    = Column(Integer, nullable=True)  # ms desde fuente hasta BD

    match = relationship("Match", back_populates="odds")


# ─── TABLA CORE: PREDICCIONES DEL MASTER AI ──────────────────────────────────

class Prediction(Base):
    """
    Output unificado del Master AI (Agente 9).
    Incluye EV, gap de ineficiencia de mercado y estado del circuit breaker.
    """
    __tablename__ = "predictions"

    id           = Column(Integer, primary_key=True, index=True)
    match_id     = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    ticker       = Column(String(20), index=True)
    creado       = Column(DateTime, default=datetime.utcnow, index=True)
    es_live      = Column(Boolean, default=False)

    # Probabilidades del ensemble
    prob_local      = Column(Float)
    prob_empate     = Column(Float)
    prob_visitante  = Column(Float)
    confianza       = Column(Float)          # 0-100

    # Valor esperado — EV = (P_IA × Cuota_Casa) − 1
    ev_local      = Column(Float, nullable=True)
    ev_empate     = Column(Float, nullable=True)
    ev_visitante  = Column(Float, nullable=True)
    valor         = Column(String(10))       # "ALTO" | "MEDIO" | "BAJO" | "SIN_VALOR"
    resultado_rec = Column(String(20), nullable=True)  # resultado recomendado

    # Ineficiencia de mercado
    market_inefficiency_gap = Column(Float, nullable=True)
    circuit_breaker_status  = Column(String(20), default="OPERATIONAL")

    # Brecha A — Kelly output
    kelly_fraccion     = Column(Float, nullable=True)
    monto_sugerido_pct = Column(Float, nullable=True)

    # Contribuciones individuales de los 8 agentes
    contribuciones_agentes = Column(JSON, nullable=True)
    pesos_usados           = Column(JSON, nullable=True)

    match = relationship("Match", back_populates="predictions")

    __table_args__ = (
        Index("idx_predictions_match_val", "match_id", "valor", "confianza"),
    )


# ─── BRECHA A: GESTIÓN DE BANCA (KELLY) ──────────────────────────────────────

class BankrollSettings(Base):
    """Configuración de capital por usuario — Brecha A."""
    __tablename__ = "bankroll_settings"

    id                    = Column(Integer, primary_key=True, index=True)
    usuario_id            = Column(Integer, nullable=False, unique=True, index=True)
    saldo_declarado       = Column(Float, default=0.0)
    perfil_riesgo         = Column(String(20), default="moderado")  # conservador | moderado | agresivo
    kelly_divisor         = Column(Float, default=2.0)               # 4=cuarto, 2=mitad, 1=completo
    max_exp_evento        = Column(Float, default=0.08)              # 8% max por evento
    max_exp_total         = Column(Float, default=0.25)              # 25% max simultáneo
    max_eventos_simult    = Column(Integer, default=5)
    ajuste_correlacion    = Column(Boolean, default=True)            # reducir por liga/torneo correlacionado
    activo                = Column(Boolean, default=True)
    creado                = Column(DateTime, default=datetime.utcnow)
    actualizado           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── BRECHA B: POSICIONES DE EXCHANGE (BACK / LAY) ───────────────────────────

class ExchangePosition(Base):
    """Posiciones abiertas/cerradas en el mercado back/lay — Brecha B."""
    __tablename__ = "exchange_positions"

    id                   = Column(Integer, primary_key=True, index=True)
    usuario_id           = Column(Integer, nullable=False, index=True)
    match_id             = Column(Integer, ForeignKey("matches.id"), nullable=False)
    ticker               = Column(String(20), index=True)
    tipo                 = Column(String(5))    # "back" | "lay"
    resultado_apostado   = Column(String(15))   # "local" | "empate" | "visitante"
    cuota_entrada        = Column(Float)
    stake                = Column(Float)
    ganancia_potencial   = Column(Float)
    responsabilidad_lay  = Column(Float, nullable=True)  # solo en lay: stake × (cuota−1)
    cuota_actual         = Column(Float, nullable=True)
    pnl_flotante         = Column(Float, default=0.0)
    pnl_realizado        = Column(Float, nullable=True)
    estado               = Column(String(15), default="abierta")  # abierta | cerrada | cancelada
    fecha_apertura       = Column(DateTime, default=datetime.utcnow)
    fecha_cierre         = Column(DateTime, nullable=True)
    kelly_fraccion       = Column(Float, nullable=True)
    trading_out_ejecutado = Column(Boolean, default=False)
    stake_trading_out    = Column(Float, nullable=True)
    metadatos            = Column(JSON, nullable=True)


# ─── BRECHA C: FEEDBACK LOOP — BACKTESTING ───────────────────────────────────

class BacktestingLog(Base):
    """
    Registro de predicción de cada agente vs resultado real.
    Alimenta la recalibración semanal de pesos — Brecha C.
    """
    __tablename__ = "backtesting_logs"

    id                    = Column(Integer, primary_key=True, index=True)
    match_id              = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    agente_id             = Column(String(50), nullable=False, index=True)
    probabilidad_predicha = Column(Float)
    resultado_real        = Column(String(15), nullable=True)   # se llena al finalizar el partido
    confianza_declarada   = Column(Float)
    prediccion_correcta   = Column(Boolean, nullable=True)
    brier_score           = Column(Float, nullable=True)        # (p − outcome)²
    fecha                 = Column(DateTime, default=datetime.utcnow, index=True)
    semana_iso            = Column(Integer)
    features_entrada      = Column(JSON, nullable=True)


class AgentWeight(Base):
    """Pesos dinámicos de los 8 agentes especializados — Brecha C."""
    __tablename__ = "agent_weights"

    id                  = Column(Integer, primary_key=True, index=True)
    agente_id           = Column(String(50), nullable=False, unique=True, index=True)
    peso                = Column(Float, default=1.0)
    acierto_historico   = Column(Float, nullable=True)
    brier_score_avg     = Column(Float, nullable=True)
    total_predicciones  = Column(Integer, default=0)
    ventana_semanas     = Column(Integer, default=12)
    ultima_actualizacion = Column(DateTime, default=datetime.utcnow)
    historial_pesos     = Column(JSON, nullable=True)   # timeseries


# ─── BRECHA D: MONITOR DE LATENCIA ───────────────────────────────────────────

class LatencyMonitor(Base):
    """Registro de latencia del WebSocket de datos en vivo — Brecha D."""
    __tablename__ = "latency_monitor"

    id          = Column(Integer, primary_key=True, index=True)
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)
    fuente      = Column(String(50))       # "sportradar_ws" | "betfair_ws" | "polling_fallback"
    latencia_ms = Column(Integer)
    estado      = Column(String(20))       # "ok" | "degradado" | "desconectado"
    match_id    = Column(Integer, nullable=True)
    mensaje     = Column(String(500), nullable=True)
    superó_sla  = Column(Boolean, default=False)  # True si latencia > 500ms
