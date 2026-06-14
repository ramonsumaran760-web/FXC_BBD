"""
Notification Service — Notificaciones unificadas:
  - Email (SendGrid)
  - Web Push (pywebpush / VAPID)
  - SMS (Twilio)
  - Firebase Cloud Messaging (FCM)
"""
import os, json, logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# EMAIL — SendGrid
# ─────────────────────────────────────────────────────────
def _email_tpl(contenido: str) -> str:
    app_url = os.getenv("APP_URL", "http://localhost:3000")
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#0b0f14;color:#dde4f0;margin:0;padding:30px">
<div style="max-width:520px;margin:0 auto;background:#111820;border-radius:12px;padding:28px;border:1px solid #2a3545">
<div style="font-size:22px;font-weight:700;color:#17cc85;margin-bottom:8px">InvestIQ</div>
<div style="height:2px;background:linear-gradient(90deg,#12a068,#2196f3);margin-bottom:24px"></div>
{contenido}
<div style="margin-top:24px;font-size:10px;color:#576880;border-top:1px solid #2a3545;padding-top:16px">
InvestIQ · <a href="{app_url}" style="color:#2196f3">investiq.co</a></div></div></body></html>"""

def send_email(to: str, subject: str, html: str) -> bool:
    key = os.getenv("SENDGRID_API_KEY", "")
    if not key:
        logger.info(f"[EMAIL DEMO] To: {to} | {subject}")
        return True
    try:
        import requests
        r = requests.post("https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"personalizations": [{"to": [{"email": to}]}],
                  "from": {"email": os.getenv("FROM_EMAIL","noreply@investiq.co"), "name": "InvestIQ"},
                  "subject": subject, "content": [{"type": "text/html", "value": html}]},
            timeout=10)
        return r.status_code == 202
    except Exception as e:
        logger.error(f"Email error: {e}"); return False

def email_bienvenida(email: str, nombre: str) -> bool:
    return send_email(email, "Bienvenido a InvestIQ", _email_tpl(
        f"<h2>¡Hola {nombre}!</h2><p>Tu cuenta está lista. Invierte desde <b>$1 USD</b>.</p>"))

def email_orden_ejecutada(email: str, nombre: str, ticker: str, tipo: str,
                          monto: float, acciones: float, precio: float) -> bool:
    color = "#17cc85" if tipo == "buy" else "#f44336"
    return send_email(email, f"Orden ejecutada: {tipo.upper()} {ticker}", _email_tpl(
        f"<h2>Orden ejecutada: {tipo.upper()} {ticker}</h2>"
        f"<p>Monto: <b style='color:{color}'>${monto:.2f}</b> | "
        f"Acciones: {acciones:.8f} | Precio: ${precio:.4f}</p>"))

def email_deposito_confirmado(email: str, nombre: str, monto: float,
                              metodo: str, saldo_nuevo: float) -> bool:
    return send_email(email, f"Depósito confirmado: ${monto:.2f} USD", _email_tpl(
        f"<h2>Depósito confirmado</h2>"
        f"<p>Monto: <b style='color:#17cc85'>${monto:.2f}</b> vía {metodo}. "
        f"Nuevo saldo: <b>${saldo_nuevo:.2f}</b></p>"))

def email_alerta_riesgo(email: str, nombre: str, perfil: str, sugerencia: str) -> bool:
    return send_email(email, "Alerta Robo-Advisor: revisar portafolio", _email_tpl(
        f"<h2>⚠ Alerta Robo-Advisor</h2><p>Perfil: {perfil}</p>"
        f"<p style='background:#1E2835;padding:12px;border-left:4px solid #f5a623'>{sugerencia}</p>"))

def email_stop_loss_ejecutado(email: str, nombre: str, ticker: str, precio: float, monto: float) -> bool:
    return send_email(email, f"Stop-Loss ejecutado: {ticker}", _email_tpl(
        f"<h2>Stop-Loss activado: {ticker}</h2>"
        f"<p>Se vendió <b>${monto:.2f}</b> de {ticker} al precio ${precio:.4f} "
        f"por activación automática de Stop-Loss.</p>"))

def email_kyc_aprobado(email: str, nombre: str, nivel: str) -> bool:
    return send_email(email, f"KYC aprobado — Nivel {nivel}", _email_tpl(
        f"<h2 style='color:#17cc85'>✓ KYC aprobado — Nivel {nivel}</h2>"
        f"<p>Acceso completo desbloqueado en InvestIQ.</p>"))


# ─────────────────────────────────────────────────────────
# WEB PUSH — pywebpush + VAPID
# ─────────────────────────────────────────────────────────
_push_subscriptions: dict = {}   # usuario_id -> subscription_dict (en prod: DB)

def registrar_push_subscription(usuario_id: int, subscription: dict) -> bool:
    _push_subscriptions[str(usuario_id)] = subscription
    logger.info(f"Push registrado para usuario {usuario_id}")
    return True

def send_push(usuario_id: int, titulo: str, mensaje: str,
              tipo: str = "info", url: str = "/") -> bool:
    sub = _push_subscriptions.get(str(usuario_id))
    if not sub:
        return False
    payload = json.dumps({"titulo": titulo, "mensaje": mensaje, "tipo": tipo,
                          "url": url, "ts": datetime.now(timezone.utc).isoformat()})
    vapid_private = os.getenv("VAPID_PRIVATE_KEY", "")
    vapid_email = os.getenv("VAPID_EMAIL", "admin@investiq.co")
    if not vapid_private:
        logger.info(f"[PUSH DEMO] {usuario_id}: {titulo} — {mensaje}")
        return True
    try:
        from pywebpush import webpush, WebPushException
        webpush(subscription_info=sub, data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": f"mailto:{vapid_email}"})
        return True
    except Exception as e:
        logger.error(f"Push error {usuario_id}: {e}"); return False


# ─────────────────────────────────────────────────────────
# FIREBASE CLOUD MESSAGING
# ─────────────────────────────────────────────────────────
def send_fcm(fcm_token: str, titulo: str, mensaje: str, data: dict = None) -> bool:
    server_key = os.getenv("FCM_SERVER_KEY", "")
    if not server_key:
        logger.info(f"[FCM DEMO] {fcm_token[:20]}...: {titulo}")
        return True
    try:
        import requests
        payload = {
            "to": fcm_token,
            "notification": {"title": titulo, "body": mensaje, "sound": "default"},
            "data": data or {}
        }
        r = requests.post("https://fcm.googleapis.com/fcm/send",
                          headers={"Authorization": f"key={server_key}",
                                   "Content-Type": "application/json"},
                          json=payload, timeout=10)
        return r.ok
    except Exception as e:
        logger.error(f"FCM error: {e}"); return False


# ─────────────────────────────────────────────────────────
# SMS — Twilio
# ─────────────────────────────────────────────────────────
def send_sms(to_number: str, mensaje: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")
    if not sid or not token:
        logger.info(f"[SMS DEMO] To: {to_number}: {mensaje}")
        return True
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(body=mensaje, from_=from_number, to=to_number)
        return True
    except Exception as e:
        logger.error(f"SMS error: {e}"); return False


# ─────────────────────────────────────────────────────────
# NOTIFICACIÓN UNIFICADA — envía por todos los canales disponibles
# ─────────────────────────────────────────────────────────
def notificar_usuario(usuario_id: int, email: str, phone: str,
                      titulo: str, mensaje: str,
                      tipo: str = "info", url: str = "/",
                      canales: list = None) -> dict:
    """
    Envía notificación por email, push y/o SMS según canales disponibles.
    canales = ["email", "push", "sms"]  — None = todos los disponibles.
    """
    canales = canales or ["email", "push", "sms"]
    resultados = {}

    if "email" in canales and email:
        resultados["email"] = send_email(email, titulo,
            _email_tpl(f"<h2>{titulo}</h2><p>{mensaje}</p>"))

    if "push" in canales:
        resultados["push"] = send_push(usuario_id, titulo, mensaje, tipo, url)

    if "sms" in canales and phone:
        resultados["sms"] = send_sms(phone, f"InvestIQ: {titulo}. {mensaje}")

    return resultados


def notificar_stop_loss(usuario_id: int, email: str, phone: str,
                        ticker: str, precio: float, monto: float) -> dict:
    return notificar_usuario(
        usuario_id, email, phone,
        titulo=f"Stop-Loss activado: {ticker}",
        mensaje=f"Se vendió ${monto:.2f} de {ticker} @ ${precio:.4f} por Stop-Loss automático.",
        tipo="danger", url="/portafolio"
    )

def notificar_orden_ejecutada(usuario_id: int, email: str, phone: str,
                               ticker: str, tipo: str, monto: float) -> dict:
    return notificar_usuario(
        usuario_id, email, phone,
        titulo=f"Orden ejecutada: {tipo.upper()} {ticker}",
        mensaje=f"${monto:.2f} procesado exitosamente.",
        tipo="success", url="/ordenes"
    )

def notificar_deposito(usuario_id: int, email: str, phone: str, monto: float) -> dict:
    return notificar_usuario(
        usuario_id, email, phone,
        titulo="Depósito confirmado",
        mensaje=f"${monto:.2f} USD acreditados en tu cuenta.",
        tipo="success", url="/"
    )

def notificar_aml_bloqueado(usuario_id: int, email: str, phone: str) -> dict:
    return notificar_usuario(
        usuario_id, email, phone,
        titulo="Cuenta bloqueada — Revisión AML",
        mensaje="Tu cuenta ha sido marcada para revisión AML. Contacta soporte.",
        tipo="danger", url="/soporte",
        canales=["email", "sms"]
    )
