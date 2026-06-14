"""
Models — SQLAlchemy ORM completo v2.0
Nuevos modelos: EquityCurve, OrdenAutomatica (stop-loss/take-profit),
TaxLot (FIFO/LIFO), PushSubscription, WebhookLog
"""
from sqlalchemy import (Column, Integer, String, Float, Boolean, DateTime,
                        ForeignKey, Text, Index, UniqueConstraint)
from sqlalchemy.orm import relationship
from core.database import Base
from datetime import datetime, timezone


# ── Usuario ───────────────────────────────────────────────
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    password_hash = Column(String(256), nullable=False)
    rol = Column(String(20), default="investor")
    activo = Column(Boolean, default=True)
    # KYC
    kyc_nivel = Column(String(20), default="none")
    kyc_verificado = Column(Boolean, default=False)
    kyc_fecha = Column(DateTime)
    biometria_hash = Column(String(128))
    # AML
    aml_status = Column(String(20), default="pending")
    aml_score = Column(Float, default=0.0)
    aml_fecha = Column(DateTime)
    # MFA
    mfa_secret = Column(String(64))
    mfa_activo = Column(Boolean, default=False)
    # Perfil inversor
    edad = Column(Integer)
    ingresos_anuales_usd = Column(Float, default=0)
    tolerancia_riesgo = Column(String(20), default="media")
    perfil_ia = Column(String(20))
    # Cuenta
    saldo_usd = Column(Float, default=0.0)
    saldo_reservado = Column(Float, default=0.0)
    # Sesión
    ultimo_login = Column(DateTime)
    creado = Column(DateTime, default=datetime.utcnow)
    # Relaciones
    portafolio = relationship("PosicionPortafolio", back_populates="usuario", lazy="select")
    ordenes = relationship("Orden", back_populates="usuario", lazy="select")
    equity_curve = relationship("EquityCurve", back_populates="usuario", lazy="select")
    ordenes_automaticas = relationship("OrdenAutomatica", back_populates="usuario", lazy="select")

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "email": self.email,
                "rol": self.rol, "kyc_nivel": self.kyc_nivel, "kyc_verificado": self.kyc_verificado,
                "aml_status": self.aml_status, "mfa_activo": self.mfa_activo,
                "saldo_usd": round(self.saldo_usd or 0, 2),
                "tolerancia_riesgo": self.tolerancia_riesgo, "perfil_ia": self.perfil_ia,
                "phone": self.phone,
                "creado": self.creado.isoformat() if self.creado else None}


# ── Activo (instrumento financiero) ──────────────────────
class Activo(Base):
    __tablename__ = "activos"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(12), unique=True, nullable=False, index=True)
    nombre = Column(String(120))
    tipo = Column(String(20), default="stock")
    sector = Column(String(60))
    mercado = Column(String(20), default="NYSE")
    precio_actual = Column(Float, default=0)
    precio_apertura = Column(Float, default=0)
    precio_max_dia = Column(Float, default=0)
    precio_min_dia = Column(Float, default=0)
    variacion_dia = Column(Float, default=0)
    variacion_pct = Column(Float, default=0)
    volumen = Column(Float, default=0)
    market_cap = Column(Float, default=0)
    pe_ratio = Column(Float)
    dividendo_yield = Column(Float, default=0)
    fracciones_disponibles = Column(Boolean, default=True)
    activo = Column(Boolean, default=True)
    ultima_actualizacion = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "ticker": self.ticker, "nombre": self.nombre,
                "tipo": self.tipo, "sector": self.sector, "mercado": self.mercado,
                "precio_actual": round(self.precio_actual or 0, 4),
                "precio_apertura": round(self.precio_apertura or 0, 4),
                "variacion_dia": round(self.variacion_dia or 0, 4),
                "variacion_pct": round(self.variacion_pct or 0, 4),
                "volumen": self.volumen, "market_cap": self.market_cap,
                "fracciones_disponibles": self.fracciones_disponibles,
                "ultima_actualizacion": self.ultima_actualizacion.isoformat() if self.ultima_actualizacion else None}


# ── Precio histórico (TimescaleDB hypertable en prod) ─────
class PrecioHistorico(Base):
    __tablename__ = "precios_historicos"
    id = Column(Integer, primary_key=True)
    ticker = Column(String(12), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float); high = Column(Float); low = Column(Float)
    close = Column(Float); volume = Column(Float)
    intervalo = Column(String(10), default="1d")

    __table_args__ = (Index("ix_precio_ticker_ts", "ticker", "timestamp"),)

    def to_dict(self):
        return {"ticker": self.ticker, "timestamp": self.timestamp.isoformat(),
                "open": self.open, "high": self.high, "low": self.low,
                "close": self.close, "volume": self.volume}


# ── Equity Curve — historial de valor del portafolio ─────
class EquityCurve(Base):
    """Serie temporal del valor del portafolio por usuario. Registra una entrada diaria."""
    __tablename__ = "equity_curve"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    valor_portafolio_usd = Column(Float, nullable=False, default=0)
    saldo_disponible_usd = Column(Float, default=0)
    ganancia_perdida_usd = Column(Float, default=0)
    ganancia_perdida_pct = Column(Float, default=0)

    usuario = relationship("Usuario", back_populates="equity_curve")
    __table_args__ = (Index("ix_equity_user_ts", "usuario_id", "timestamp"),)

    def to_dict(self):
        return {"timestamp": self.timestamp.isoformat() if self.timestamp else None,
                "valor_portafolio_usd": round(self.valor_portafolio_usd or 0, 2),
                "saldo_disponible_usd": round(self.saldo_disponible_usd or 0, 2),
                "ganancia_perdida_usd": round(self.ganancia_perdida_usd or 0, 2),
                "ganancia_perdida_pct": round(self.ganancia_perdida_pct or 0, 4)}


# ── Orden ─────────────────────────────────────────────────
class Orden(Base):
    __tablename__ = "ordenes"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ticker = Column(String(12), nullable=False, index=True)
    tipo = Column(String(10), nullable=False)
    tipo_orden = Column(String(20), default="market")
    monto_usd = Column(Float, nullable=False)
    acciones = Column(Float)
    precio_solicitado = Column(Float)
    precio_ejecucion = Column(Float)
    estado = Column(String(30), default="pending")
    # Broker
    broker_order_id = Column(String(100))
    broker = Column(String(30), default="alpaca_paper")
    # Seguridad
    firma_ecdsa = Column(String(256))
    firma_verificada = Column(Boolean, default=False)
    nonce = Column(String(64))
    ip_origen = Column(String(45))
    device_fingerprint = Column(String(128))
    # AML
    aml_check = Column(String(20), default="pending")
    # Timestamps
    creado = Column(DateTime, default=datetime.utcnow)
    ejecutado = Column(DateTime)
    # Relaciones
    usuario = relationship("Usuario", back_populates="ordenes")

    def to_dict(self):
        return {"id": self.id, "usuario_id": self.usuario_id, "ticker": self.ticker,
                "tipo": self.tipo, "tipo_orden": self.tipo_orden,
                "monto_usd": round(self.monto_usd or 0, 2),
                "acciones": round(self.acciones or 0, 8),
                "precio_ejecucion": round(self.precio_ejecucion or 0, 4),
                "estado": self.estado, "broker": self.broker,
                "broker_order_id": self.broker_order_id,
                "firma_verificada": self.firma_verificada,
                "aml_check": self.aml_check,
                "creado": self.creado.isoformat() if self.creado else None,
                "ejecutado": self.ejecutado.isoformat() if self.ejecutado else None}


# ── Orden Automática — Stop-Loss / Take-Profit ────────────
class OrdenAutomatica(Base):
    """
    Órdenes automáticas que se ejecutan cuando el precio alcanza el trigger.
    tipo: stop_loss | take_profit | trailing_stop
    """
    __tablename__ = "ordenes_automaticas"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ticker = Column(String(12), nullable=False, index=True)
    tipo = Column(String(20), nullable=False)         # stop_loss, take_profit, trailing_stop
    precio_trigger = Column(Float, nullable=False)    # precio en USD que activa la orden
    precio_trail_pct = Column(Float)                  # % para trailing stop
    monto_usd = Column(Float)                         # monto a vender; None = 100%
    porcentaje_pos = Column(Float, default=100.0)     # % de la posición a liquidar
    activa = Column(Boolean, default=True, index=True)
    ejecutada = Column(Boolean, default=False)
    orden_id = Column(Integer, ForeignKey("ordenes.id"))
    creado = Column(DateTime, default=datetime.utcnow)
    ejecutado_ts = Column(DateTime)

    usuario = relationship("Usuario", back_populates="ordenes_automaticas")
    __table_args__ = (Index("ix_ord_auto_user_ticker", "usuario_id", "ticker", "activa"),)

    def to_dict(self):
        return {"id": self.id, "ticker": self.ticker, "tipo": self.tipo,
                "precio_trigger": round(self.precio_trigger, 4),
                "porcentaje_pos": self.porcentaje_pos,
                "activa": self.activa, "ejecutada": self.ejecutada,
                "orden_id": self.orden_id,
                "creado": self.creado.isoformat() if self.creado else None,
                "ejecutado_ts": self.ejecutado_ts.isoformat() if self.ejecutado_ts else None}


# ── Posición en portafolio ────────────────────────────────
class PosicionPortafolio(Base):
    __tablename__ = "portafolio"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ticker = Column(String(12), nullable=False)
    nombre = Column(String(120))
    acciones = Column(Float, default=0)
    precio_promedio_compra = Column(Float, default=0)
    precio_actual = Column(Float, default=0)
    valor_total_usd = Column(Float, default=0)
    ganancia_perdida_usd = Column(Float, default=0)
    ganancia_perdida_pct = Column(Float, default=0)
    primera_compra = Column(DateTime, default=datetime.utcnow)
    ultima_actualizacion = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="portafolio")
    __table_args__ = (UniqueConstraint("usuario_id", "ticker", name="uq_user_ticker"),)

    def recalcular(self):
        if self.precio_promedio_compra and self.precio_promedio_compra > 0:
            self.valor_total_usd = round(self.acciones * self.precio_actual, 2)
            self.ganancia_perdida_usd = round(
                self.valor_total_usd - (self.acciones * self.precio_promedio_compra), 2)
            self.ganancia_perdida_pct = round(
                (self.precio_actual - self.precio_promedio_compra) / self.precio_promedio_compra * 100, 4)
            self.ultima_actualizacion = datetime.now(timezone.utc)

    def to_dict(self):
        return {"id": self.id, "ticker": self.ticker, "nombre": self.nombre,
                "acciones": round(self.acciones or 0, 8),
                "precio_promedio_compra": round(self.precio_promedio_compra or 0, 4),
                "precio_actual": round(self.precio_actual or 0, 4),
                "valor_total_usd": round(self.valor_total_usd or 0, 2),
                "ganancia_perdida_usd": round(self.ganancia_perdida_usd or 0, 2),
                "ganancia_perdida_pct": round(self.ganancia_perdida_pct or 0, 4)}


# ── Tax Lot — para cálculo FIFO / LIFO ───────────────────
class TaxLot(Base):
    """
    Cada compra crea un lote fiscal. Al vender, se consumen lotes FIFO/LIFO.
    Necesario para calcular ganancias de capital correctamente.
    """
    __tablename__ = "tax_lots"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ticker = Column(String(12), nullable=False, index=True)
    acciones_originales = Column(Float, nullable=False)
    acciones_restantes = Column(Float, nullable=False)
    precio_costo = Column(Float, nullable=False)   # cost basis por acción
    fecha_compra = Column(DateTime, nullable=False, index=True)
    orden_id = Column(Integer, ForeignKey("ordenes.id"))
    cerrado = Column(Boolean, default=False, index=True)

    __table_args__ = (Index("ix_taxlot_user_ticker_fecha", "usuario_id", "ticker", "fecha_compra"),)

    def to_dict(self):
        return {"id": self.id, "ticker": self.ticker,
                "acciones_originales": round(self.acciones_originales, 8),
                "acciones_restantes": round(self.acciones_restantes, 8),
                "precio_costo": round(self.precio_costo, 4),
                "fecha_compra": self.fecha_compra.isoformat() if self.fecha_compra else None,
                "cerrado": self.cerrado}


# ── Análisis Robo-Advisor IA ──────────────────────────────
class AnalisisRoboAdvisor(Base):
    __tablename__ = "analisis_robo_advisor"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    perfil = Column(String(20))
    score_riesgo = Column(Integer)
    alerta_riesgo = Column(Boolean, default=False)
    concentracion_max_ticker = Column(String(10))
    concentracion_max_pct = Column(Float)
    sugerencia_rebalanceo = Column(Text)
    acciones_recomendadas = Column(Text)
    explicacion_voz = Column(Text)
    prompt_json_enviado = Column(Text)
    respuesta_json = Column(Text)
    modelo_ia = Column(String(40), default="claude-sonnet-4-6")
    fecha = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json as _json
        return {"id": self.id, "perfil": self.perfil, "score_riesgo": self.score_riesgo,
                "alerta_riesgo": self.alerta_riesgo,
                "concentracion_max": f"{self.concentracion_max_ticker} {self.concentracion_max_pct}%",
                "sugerencia_rebalanceo": self.sugerencia_rebalanceo,
                "acciones_recomendadas": _json.loads(self.acciones_recomendadas or "[]"),
                "explicacion_voz": self.explicacion_voz,
                "modelo_ia": self.modelo_ia,
                "fecha": self.fecha.isoformat() if self.fecha else None}


# ── KYC Verificación ──────────────────────────────────────
class KYCVerificacion(Base):
    __tablename__ = "kyc_verificaciones"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo_doc = Column(String(30))
    num_doc_cifrado = Column(String(512))      # cifrado con Fernet
    pais_emision = Column(String(30))
    selfie_hash = Column(String(128))
    doc_hash = Column(String(128))
    nivel_alcanzado = Column(String(20), default="none")
    proveedor = Column(String(30), default="local")
    resultado = Column(String(20))
    fecha = Column(DateTime, default=datetime.utcnow)


# ── AML Log ───────────────────────────────────────────────
class AMLLog(Base):
    __tablename__ = "aml_logs"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    entidad = Column(String(120))
    tipo_check = Column(String(30))
    resultado = Column(String(20))
    score = Column(Float, default=0)
    detalle = Column(Text)
    fuente = Column(String(50))
    fecha = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "entidad": self.entidad, "tipo_check": self.tipo_check,
                "resultado": self.resultado, "score": self.score, "detalle": self.detalle,
                "fecha": self.fecha.isoformat() if self.fecha else None}


# ── Depósito / Retiro ─────────────────────────────────────
class Transaccion(Base):
    __tablename__ = "transacciones"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo = Column(String(20))
    monto_usd = Column(Float, nullable=False)
    estado = Column(String(20), default="pending")
    metodo = Column(String(30))
    referencia_externa = Column(String(100))
    descripcion = Column(String(200))
    fecha = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "tipo": self.tipo, "monto_usd": round(self.monto_usd or 0, 2),
                "estado": self.estado, "metodo": self.metodo,
                "descripcion": self.descripcion,
                "fecha": self.fecha.isoformat() if self.fecha else None}


# ── Dividendos ────────────────────────────────────────────
class Dividendo(Base):
    __tablename__ = "dividendos"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    ticker = Column(String(12))
    monto_usd = Column(Float)
    acciones_en_fecha = Column(Float)
    ex_dividend_date = Column(DateTime)
    pago_date = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "ticker": self.ticker, "monto_usd": round(self.monto_usd or 0, 4),
                "pago_date": self.pago_date.isoformat() if self.pago_date else None}


# ── Reporte fiscal ────────────────────────────────────────
class ReporteFiscal(Base):
    __tablename__ = "reportes_fiscales"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    año = Column(Integer)
    metodo = Column(String(10), default="FIFO")    # FIFO o LIFO
    ganancias_capital = Column(Float, default=0)
    perdidas_capital = Column(Float, default=0)
    ganancias_corto_plazo = Column(Float, default=0)
    ganancias_largo_plazo = Column(Float, default=0)
    dividendos_recibidos = Column(Float, default=0)
    impuesto_estimado = Column(Float, default=0)
    detalle_json = Column(Text)                    # array de transacciones fiscales
    archivo_pdf_path = Column(String(200))
    archivo_excel_path = Column(String(200))
    generado = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json as _json
        return {"id": self.id, "año": self.año, "metodo": self.metodo,
                "ganancias_capital": self.ganancias_capital,
                "perdidas_capital": self.perdidas_capital,
                "ganancias_corto_plazo": self.ganancias_corto_plazo,
                "ganancias_largo_plazo": self.ganancias_largo_plazo,
                "dividendos_recibidos": self.dividendos_recibidos,
                "impuesto_estimado": self.impuesto_estimado,
                "detalle": _json.loads(self.detalle_json or "[]"),
                "generado": self.generado.isoformat() if self.generado else None}


# ── Audit Log ─────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    accion = Column(String(80), nullable=False)
    modulo = Column(String(40))
    detalle = Column(Text)
    ip = Column(String(45))
    user_agent = Column(String(200))
    fecha = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "accion": self.accion, "modulo": self.modulo,
                "detalle": self.detalle, "ip": self.ip,
                "fecha": self.fecha.isoformat() if self.fecha else None}


# ── Alerta / Notificación interna ────────────────────────
class Alerta(Base):
    __tablename__ = "alertas"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    tipo = Column(String(20))
    modulo = Column(String(30))
    titulo = Column(String(100))
    mensaje = Column(String(500))
    leida = Column(Boolean, default=False)
    fecha = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "tipo": self.tipo, "modulo": self.modulo,
                "titulo": self.titulo, "mensaje": self.mensaje, "leida": self.leida,
                "fecha": self.fecha.isoformat() if self.fecha else None}


# ── Push Subscription ─────────────────────────────────────
class PushSubscription(Base):
    """Suscripciones Web Push / FCM por usuario."""
    __tablename__ = "push_subscriptions"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    endpoint = Column(String(500), nullable=False)
    p256dh = Column(String(200))
    auth = Column(String(100))
    fcm_token = Column(String(300))        # Firebase Cloud Messaging token
    plataforma = Column(String(20))        # web, android, ios
    activa = Column(Boolean, default=True)
    creada = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("usuario_id", "endpoint", name="uq_push_user_endpoint"),)


# ── Webhook Log — notificaciones de Alpaca ───────────────
class WebhookLog(Base):
    """Registro de eventos recibidos por webhook de Alpaca."""
    __tablename__ = "webhook_logs"
    id = Column(Integer, primary_key=True)
    fuente = Column(String(30), default="alpaca")  # alpaca, stripe
    evento = Column(String(60))                    # fill, cancel, partial_fill
    payload_json = Column(Text)
    broker_order_id = Column(String(100), index=True)
    procesado = Column(Boolean, default=False)
    error = Column(String(200))
    recibido = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "fuente": self.fuente, "evento": self.evento,
                "broker_order_id": self.broker_order_id,
                "procesado": self.procesado, "error": self.error,
                "recibido": self.recibido.isoformat() if self.recibido else None}
