"""
Models — SQLAlchemy ORM completo
PostgreSQL en prod (con TimescaleDB para series de tiempo)
SQLite en desarrollo
"""
from sqlalchemy import (Column, Integer, String, Float, Boolean, DateTime,
                        ForeignKey, Text, Index, UniqueConstraint, Enum)
from sqlalchemy.orm import relationship
from core.database import Base
from datetime import datetime
import enum

# ── Enums ─────────────────────────────────────────────────
class RolUsuario(str, enum.Enum):
    admin = "admin"
    investor = "investor"
    readonly = "readonly"

class EstadoOrden(str, enum.Enum):
    pending = "pending"
    filled = "filled"
    partially_filled = "partially_filled"
    cancelled = "cancelled"
    rejected = "rejected"

class TipoOrden(str, enum.Enum):
    buy = "buy"
    sell = "sell"

class TipoActivo(str, enum.Enum):
    stock = "stock"
    etf = "etf"
    crypto = "crypto"
    bond = "bond"

class NivelKYC(str, enum.Enum):
    none = "none"
    basic = "basic"
    full = "full"
    biometric = "biometric"

class EstadoAML(str, enum.Enum):
    pending = "pending"
    clear = "clear"
    alert = "alert"
    blocked = "blocked"

# ── Usuario ───────────────────────────────────────────────
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    password_hash = Column(String(256), nullable=False)
    rol = Column(String(20), default=RolUsuario.investor)
    activo = Column(Boolean, default=True)
    # KYC
    kyc_nivel = Column(String(20), default=NivelKYC.none)
    kyc_verificado = Column(Boolean, default=False)
    kyc_fecha = Column(DateTime)
    biometria_hash = Column(String(128))
    # AML
    aml_status = Column(String(20), default=EstadoAML.pending)
    aml_score = Column(Float, default=0.0)
    aml_fecha = Column(DateTime)
    # MFA
    mfa_secret = Column(String(64))
    mfa_activo = Column(Boolean, default=False)
    # Perfil inversor
    edad = Column(Integer)
    ingresos_anuales_usd = Column(Float, default=0)
    tolerancia_riesgo = Column(String(20), default="media")  # baja, media, alta
    perfil_ia = Column(String(20))  # conservador, moderado, agresivo
    # Cuenta
    saldo_usd = Column(Float, default=0.0)
    saldo_reservado = Column(Float, default=0.0)  # en órdenes pendientes
    # Sesión
    ultimo_login = Column(DateTime)
    creado = Column(DateTime, default=datetime.utcnow)
    # Relaciones
    portafolio = relationship("PosicionPortafolio", back_populates="usuario", lazy="select")
    ordenes = relationship("Orden", back_populates="usuario", lazy="select")

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "email": self.email,
                "rol": self.rol, "kyc_nivel": self.kyc_nivel, "kyc_verificado": self.kyc_verificado,
                "aml_status": self.aml_status, "mfa_activo": self.mfa_activo,
                "saldo_usd": round(self.saldo_usd or 0, 2),
                "tolerancia_riesgo": self.tolerancia_riesgo, "perfil_ia": self.perfil_ia,
                "creado": self.creado.isoformat() if self.creado else None}

# ── Activo (instrumento financiero) ──────────────────────
class Activo(Base):
    __tablename__ = "activos"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(12), unique=True, nullable=False, index=True)
    nombre = Column(String(120))
    tipo = Column(String(20), default=TipoActivo.stock)
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
    intervalo = Column(String(10), default="1m")  # 1m,5m,1h,1d

    __table_args__ = (Index("ix_precio_ticker_ts", "ticker", "timestamp"),)

    def to_dict(self):
        return {"ticker": self.ticker, "timestamp": self.timestamp.isoformat(),
                "open": self.open, "high": self.high, "low": self.low,
                "close": self.close, "volume": self.volume}

# ── Orden ─────────────────────────────────────────────────
class Orden(Base):
    __tablename__ = "ordenes"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ticker = Column(String(12), nullable=False, index=True)
    tipo = Column(String(10), nullable=False)          # buy / sell
    tipo_orden = Column(String(20), default="market")  # market, limit, stop
    monto_usd = Column(Float, nullable=False)          # dólares invertidos
    acciones = Column(Float)                           # fracción resultante
    precio_solicitado = Column(Float)                  # limit price
    precio_ejecucion = Column(Float)                   # filled price
    estado = Column(String(30), default=EstadoOrden.pending)
    # Broker
    broker_order_id = Column(String(100))              # ID en Alpaca
    broker = Column(String(30), default="alpaca_paper")
    # Seguridad
    firma_ecdsa = Column(String(256))                  # hex de firma P-256
    firma_verificada = Column(Boolean, default=False)
    nonce = Column(String(64))                         # anti-replay
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

# ── Posición en portafolio ────────────────────────────────
class PosicionPortafolio(Base):
    __tablename__ = "portafolio"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ticker = Column(String(12), nullable=False)
    nombre = Column(String(120))
    acciones = Column(Float, default=0)                # cantidad total (fraccionada)
    precio_promedio_compra = Column(Float, default=0)  # costo promedio ponderado
    precio_actual = Column(Float, default=0)
    valor_total_usd = Column(Float, default=0)
    ganancia_perdida_usd = Column(Float, default=0)
    ganancia_perdida_pct = Column(Float, default=0)
    primera_compra = Column(DateTime, default=datetime.utcnow)
    ultima_actualizacion = Column(DateTime, default=datetime.utcnow)
    # Relación
    usuario = relationship("Usuario", back_populates="portafolio")
    __table_args__ = (UniqueConstraint("usuario_id", "ticker", name="uq_user_ticker"),)

    def recalcular(self):
        if self.precio_promedio_compra and self.precio_promedio_compra > 0:
            self.valor_total_usd = round(self.acciones * self.precio_actual, 2)
            self.ganancia_perdida_usd = round(self.valor_total_usd - (self.acciones * self.precio_promedio_compra), 2)
            self.ganancia_perdida_pct = round(
                (self.precio_actual - self.precio_promedio_compra) / self.precio_promedio_compra * 100, 4)

    def to_dict(self):
        return {"id": self.id, "ticker": self.ticker, "nombre": self.nombre,
                "acciones": round(self.acciones or 0, 8),
                "precio_promedio_compra": round(self.precio_promedio_compra or 0, 4),
                "precio_actual": round(self.precio_actual or 0, 4),
                "valor_total_usd": round(self.valor_total_usd or 0, 2),
                "ganancia_perdida_usd": round(self.ganancia_perdida_usd or 0, 2),
                "ganancia_perdida_pct": round(self.ganancia_perdida_pct or 0, 4)}

# ── Análisis Robo-Advisor IA ──────────────────────────────
class AnalisisRoboAdvisor(Base):
    __tablename__ = "analisis_robo_advisor"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    perfil = Column(String(20))              # conservador, moderado, agresivo
    score_riesgo = Column(Integer)           # 0-100
    alerta_riesgo = Column(Boolean, default=False)
    concentracion_max_ticker = Column(String(10))
    concentracion_max_pct = Column(Float)
    sugerencia_rebalanceo = Column(Text)
    acciones_recomendadas = Column(Text)     # JSON
    explicacion_voz = Column(Text)
    prompt_json_enviado = Column(Text)       # JSON completo enviado a Claude
    respuesta_json = Column(Text)            # JSON respuesta de Claude
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
    tipo_doc = Column(String(30))        # cedula, pasaporte, DNI
    num_doc = Column(String(50))
    pais_emision = Column(String(30))
    selfie_hash = Column(String(128))    # hash del documento (nunca guardar imagen raw)
    doc_hash = Column(String(128))
    nivel_alcanzado = Column(String(20), default=NivelKYC.none)
    proveedor = Column(String(30), default="local")  # local, jumio, truora
    resultado = Column(String(20))       # approved, rejected, pending
    fecha = Column(DateTime, default=datetime.utcnow)

# ── AML Log ───────────────────────────────────────────────
class AMLLog(Base):
    __tablename__ = "aml_logs"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    entidad = Column(String(120))
    tipo_check = Column(String(30))      # ofac, onu, opensanctions, pep
    resultado = Column(String(20))       # clear, alert, blocked
    score = Column(Float, default=0)
    detalle = Column(Text)
    fuente = Column(String(50))          # opensanctions, local_list
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
    tipo = Column(String(20))            # deposito, retiro, dividendo, fee
    monto_usd = Column(Float, nullable=False)
    estado = Column(String(20), default="pending")
    metodo = Column(String(30))          # bank_transfer, card, crypto
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
    ganancias_capital = Column(Float, default=0)
    perdidas_capital = Column(Float, default=0)
    dividendos_recibidos = Column(Float, default=0)
    impuesto_estimado = Column(Float, default=0)
    archivo_pdf_path = Column(String(200))
    archivo_excel_path = Column(String(200))
    generado = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "año": self.año,
                "ganancias_capital": self.ganancias_capital,
                "perdidas_capital": self.perdidas_capital,
                "dividendos_recibidos": self.dividendos_recibidos,
                "impuesto_estimado": self.impuesto_estimado,
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

# ── Alerta / Notificación ─────────────────────────────────
class Alerta(Base):
    __tablename__ = "alertas"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    tipo = Column(String(20))      # danger, warning, info, success
    modulo = Column(String(30))
    titulo = Column(String(100))
    mensaje = Column(String(500))
    leida = Column(Boolean, default=False)
    fecha = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "tipo": self.tipo, "modulo": self.modulo,
                "titulo": self.titulo, "mensaje": self.mensaje, "leida": self.leida,
                "fecha": self.fecha.isoformat() if self.fecha else None}
