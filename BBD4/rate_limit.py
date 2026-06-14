"""
core/rate_limit.py — Rate limiting por usuario e IP con slowapi
Protege endpoints críticos: auth, órdenes, pagos, KYC, AML
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import os

# ── Identificador: IP para anónimos, user_id para autenticados ──────────
def get_user_or_ip(request: Request) -> str:
    """
    Clave de rate limit:
    - Si hay header X-User-ID (puesto por auth middleware): user_id
    - Si no: IP real del cliente
    """
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return f"user:{user_id}"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{get_remote_address(request)}"

# ── Limiter global ────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_user_or_ip,
    default_limits=["200/minute"],          # límite global por defecto
    storage_uri=os.getenv("REDIS_URL", "memory://"),  # Redis si disponible
)

# ── Límites por categoría de endpoint ────────────────────────────────────
LIMITS = {
    # Auth — muy restrictivo para prevenir fuerza bruta
    "auth_login":        "5/minute",
    "auth_register":     "3/minute",
    "mfa_verify":        "10/minute",

    # Órdenes — permite actividad normal de trading
    "ordenes_crear":     "30/minute",
    "ordenes_listar":    "60/minute",
    "ordenes_cancelar":  "20/minute",

    # Pagos — moderado para prevenir abuso
    "pagos_stripe":      "10/minute",
    "pagos_mp":          "10/minute",
    "pagos_retiro":      "5/minute",

    # Mercado — más permisivo (datos públicos)
    "mercado_precios":   "120/minute",
    "mercado_candles":   "60/minute",
    "mercado_activos":   "60/minute",

    # KYC / AML — restrictivo (proceso costoso)
    "kyc_submit":        "3/hour",
    "aml_check":         "20/hour",

    # Robo-Advisor — moderado (llama a Claude API)
    "robo_advisor":      "10/minute",

    # Exportes — lento porque genera archivos
    "exportar":          "10/hour",

    # Admin — solo internos
    "admin":             "100/minute",

    # WebSocket — una conexión por usuario
    "websocket":         "5/minute",
}

def get_limit(categoria: str) -> str:
    return LIMITS.get(categoria, "60/minute")

# Handler de errores de rate limit
rate_limit_handler = _rate_limit_exceeded_handler
