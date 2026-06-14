"""
core/monitoring.py — Sentry SDK integrado con FastAPI
Captura: errores, performance, transacciones, alertas custom
"""
import os, logging
from datetime import datetime

logger = logging.getLogger(__name__)

SENTRY_DSN = os.getenv("SENTRY_DSN", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
RELEASE = os.getenv("APP_VERSION", "investiq@1.0.0")

def init_sentry(app=None):
    """
    Inicializa Sentry. Llamar una sola vez al arrancar FastAPI.
    Sin SENTRY_DSN configurado, solo loggea en consola (modo demo).
    """
    if not SENTRY_DSN:
        logger.info("[Sentry] SENTRY_DSN no configurado — modo demo (sin telemetría real)")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            release=RELEASE,
            # Performance tracing
            traces_sample_rate=0.2,           # 20% de requests trackeados
            profiles_sample_rate=0.1,         # 10% de profiling
            # Integraciones
            integrations=[
                FastApiIntegration(
                    transaction_style="endpoint",
                    failed_request_status_codes=[400, 401, 403, 404, 429, 500, 502, 503],
                ),
                SqlalchemyIntegration(),
                RedisIntegration(),
                LoggingIntegration(
                    level=logging.WARNING,
                    event_level=logging.ERROR,
                ),
            ],
            # Filtros de datos sensibles
            before_send=_filtrar_datos_sensibles,
            # Ignorar errores esperados
            ignore_errors=[
                KeyboardInterrupt,
            ],
            # Tags globales
            initial_scope={
                "tags": {
                    "plataforma": "InvestIQ",
                    "broker": "alpaca_paper",
                    "pais": "CO/PE",
                }
            }
        )
        logger.info(f"[Sentry] Inicializado — env:{ENVIRONMENT} release:{RELEASE}")
        return True
    except ImportError:
        logger.warning("[Sentry] sentry-sdk no instalado: pip install sentry-sdk[fastapi]")
        return False
    except Exception as e:
        logger.error(f"[Sentry] Error inicializando: {e}")
        return False


def _filtrar_datos_sensibles(event, hint):
    """
    Filtra datos sensibles antes de enviar a Sentry.
    NUNCA enviar: passwords, tokens, API keys, datos bancarios.
    """
    # Eliminar headers sensibles
    if "request" in event:
        headers = event["request"].get("headers", {})
        for key in ["authorization", "x-api-key", "cookie", "stripe-signature"]:
            headers.pop(key, None)
            headers.pop(key.upper(), None)
        # Limpiar body de pagos
        body = event["request"].get("data", "")
        if isinstance(body, dict):
            for field in ["password", "card_number", "cvv", "pin", "secret", "mfa_token"]:
                body.pop(field, None)

    # Limpiar extra data
    if "extra" in event:
        extra = event.get("extra", {})
        for field in ["password_hash", "firma_ecdsa", "mfa_secret"]:
            extra.pop(field, None)
    return event


# ── Funciones helper para usar en el código ───────────────────────────────

def capturar_error(error: Exception, contexto: dict = None, usuario_id: int = None):
    """Captura un error con contexto adicional."""
    if not SENTRY_DSN:
        logger.error(f"[ERROR] {type(error).__name__}: {error} | ctx={contexto}")
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if usuario_id:
                scope.user = {"id": str(usuario_id)}
            if contexto:
                for k, v in contexto.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(error)
    except Exception:
        pass


def capturar_mensaje(mensaje: str, nivel: str = "info", extras: dict = None):
    """Envía un mensaje/evento a Sentry."""
    if not SENTRY_DSN:
        logger.info(f"[SENTRY MSG] {nivel}: {mensaje}")
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if extras:
                for k, v in extras.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_message(mensaje, level=nivel)
    except Exception:
        pass


def set_usuario_sentry(usuario_id: int, email: str = None):
    """Asocia el usuario actual al scope de Sentry."""
    if not SENTRY_DSN:
        return
    try:
        import sentry_sdk
        sentry_sdk.set_user({"id": str(usuario_id), "email": email or ""})
    except Exception:
        pass


def iniciar_transaccion(nombre: str, operacion: str = "http.request"):
    """Inicia una transacción de performance en Sentry."""
    if not SENTRY_DSN:
        return None
    try:
        import sentry_sdk
        return sentry_sdk.start_transaction(name=nombre, op=operacion)
    except Exception:
        return None


# ── Alertas custom por tipo de evento financiero ──────────────────────────

def alerta_orden_sospechosa(orden_id: int, ticker: str, monto: float, razon: str):
    capturar_mensaje(
        f"Orden sospechosa #{orden_id}: {ticker} ${monto} — {razon}",
        nivel="warning",
        extras={"orden_id": orden_id, "ticker": ticker, "monto": monto, "razon": razon}
    )

def alerta_aml_blocked(usuario_id: int, entidad: str, score: float):
    capturar_mensaje(
        f"AML BLOQUEADO: usuario #{usuario_id} — {entidad} (score: {score})",
        nivel="error",
        extras={"usuario_id": usuario_id, "entidad": entidad, "score": score}
    )

def alerta_pago_fallido(usuario_id: int, monto: float, gateway: str, error: str):
    capturar_mensaje(
        f"Pago fallido: usuario #{usuario_id} ${monto} vía {gateway}",
        nivel="warning",
        extras={"usuario_id": usuario_id, "monto": monto, "gateway": gateway, "error": error}
    )

def alerta_broker_error(ticker: str, monto: float, error: str):
    capturar_mensaje(
        f"Error broker Alpaca: {ticker} ${monto} — {error}",
        nivel="error",
        extras={"ticker": ticker, "monto": monto, "error": error}
    )
