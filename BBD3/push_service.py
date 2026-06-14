"""
services/push_service.py — Notificaciones push web (Web Push API)
Compatible con: Chrome, Firefox, Edge, Safari 16+
"""
import os, json, logging
from datetime import datetime
logger = logging.getLogger(__name__)

VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "admin@investiq.co")

# Suscripciones en memoria (en prod: guardar en DB)
_subscriptions: dict = {}  # usuario_id -> subscription_dict

def registrar_suscripcion(usuario_id: int, subscription: dict) -> bool:
    """Guarda la suscripción push de un usuario."""
    _subscriptions[str(usuario_id)] = subscription
    logger.info(f"Push subscription registrada para usuario {usuario_id}")
    return True

def enviar_push(usuario_id: int, titulo: str, mensaje: str,
                tipo: str = "info", url: str = "/") -> bool:
    """
    Envía notificación push a un usuario.
    En producción usar pywebpush:
    pip install pywebpush
    """
    sub = _subscriptions.get(str(usuario_id))
    if not sub:
        logger.debug(f"Sin suscripción push para usuario {usuario_id}")
        return False

    payload = json.dumps({
        "titulo": titulo,
        "mensaje": mensaje,
        "tipo": tipo,
        "url": url,
        "ts": datetime.utcnow().isoformat()
    })

    if not VAPID_PRIVATE:
        logger.info(f"[PUSH DEMO] User {usuario_id}: {titulo} — {mensaje}")
        return True

    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info=sub,
            data=payload,
            vapid_private_key=VAPID_PRIVATE,
            vapid_claims={"sub": f"mailto:{VAPID_EMAIL}"}
        )
        return True
    except Exception as e:
        logger.error(f"Push error usuario {usuario_id}: {e}")
        return False

def broadcast_push(titulo: str, mensaje: str, tipo: str = "info") -> int:
    """Envía push a todos los usuarios suscritos."""
    count = 0
    for uid in list(_subscriptions.keys()):
        if enviar_push(int(uid), titulo, mensaje, tipo):
            count += 1
    return count

# Tipos de notificaciones predefinidas
def push_orden_ejecutada(usuario_id: int, ticker: str, tipo: str, monto: float) -> bool:
    return enviar_push(usuario_id,
        f"Orden ejecutada: {tipo.upper()} {ticker}",
        f"${monto:.2f} USD procesado exitosamente. Firma ECDSA verificada.",
        tipo="success", url="/ordenes")

def push_alerta_mercado(usuario_id: int, ticker: str, cambio_pct: float) -> bool:
    direccion = "subió" if cambio_pct > 0 else "bajó"
    return enviar_push(usuario_id,
        f"Alerta de mercado: {ticker}",
        f"{ticker} {direccion} {abs(cambio_pct):.2f}% en la última hora.",
        tipo="warning", url="/mercado")

def push_deposito_confirmado(usuario_id: int, monto: float) -> bool:
    return enviar_push(usuario_id,
        "Depósito confirmado",
        f"${monto:.2f} USD acreditados en tu cuenta. Ya puedes invertir.",
        tipo="success", url="/")

def push_robo_advisor_alerta(usuario_id: int, sugerencia: str) -> bool:
    return enviar_push(usuario_id,
        "Robo-Advisor: Alerta de riesgo",
        sugerencia[:100],
        tipo="warning", url="/portafolio")

def generar_vapid_keys() -> dict:
    """Genera par de llaves VAPID para producción."""
    try:
        from py_vapid import Vapid
        vapid = Vapid()
        vapid.generate_keys()
        return {
            "public": vapid.public_key.serialize().decode(),
            "private": vapid.private_key.serialize().decode(),
            "instrucciones": "Guardar en VAPID_PUBLIC_KEY y VAPID_PRIVATE_KEY en .env"
        }
    except ImportError:
        return {
            "error": "Instalar: pip install py-vapid pywebpush",
            "vapid_url": "https://vapidkeys.com/"
        }
