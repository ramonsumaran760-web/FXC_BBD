"""
services/email_service.py — Emails transaccionales con SendGrid
"""
import os, logging
from datetime import datetime
logger = logging.getLogger(__name__)

SENDGRID_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@investiq.co")
APP_URL = os.getenv("APP_URL", "http://localhost:3000")

def _send(to: str, subject: str, html: str) -> bool:
    if not SENDGRID_KEY:
        logger.info(f"[EMAIL DEMO] To: {to} | Subject: {subject}")
        return True
    try:
        import requests
        r = requests.post("https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_KEY}", "Content-Type": "application/json"},
            json={"personalizations": [{"to": [{"email": to}]}],
                  "from": {"email": FROM_EMAIL, "name": "InvestIQ"},
                  "subject": subject, "content": [{"type": "text/html", "value": html}]},
            timeout=10)
        return r.status_code == 202
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

def _tpl(contenido: str) -> str:
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#0b0f14;color:#dde4f0;margin:0;padding:30px">
<div style="max-width:520px;margin:0 auto;background:#111820;border-radius:12px;padding:28px;border:1px solid #2a3545">
<div style="font-size:22px;font-weight:700;color:#17cc85;margin-bottom:8px">InvestIQ</div>
<div style="height:2px;background:linear-gradient(90deg,#12a068,#2196f3);margin-bottom:24px"></div>
{contenido}
<div style="margin-top:24px;font-size:10px;color:#576880;border-top:1px solid #2a3545;padding-top:16px">
InvestIQ · Plataforma de microinversión · <a href="{APP_URL}" style="color:#2196f3">investiq.co</a>
</div></div></body></html>"""

def email_bienvenida(email: str, nombre: str) -> bool:
    return _send(email, "Bienvenido a InvestIQ", _tpl(f"""
<h2 style="color:#dde4f0;font-size:18px;margin-bottom:12px">¡Hola {nombre}!</h2>
<p style="color:#8fa0b8;line-height:1.7">Tu cuenta de InvestIQ está lista. Ahora puedes:</p>
<ul style="color:#8fa0b8;line-height:2;padding-left:18px">
<li>Invertir desde <b style="color:#17cc85">$1 USD</b> en acciones fraccionadas</li>
<li>Obtener análisis de portafolio con <b style="color:#ab47bc">IA Robo-Advisor</b></li>
<li>Operar en tiempo real vía <b style="color:#2196f3">Alpaca Paper Trading</b></li>
</ul>
<a href="{APP_URL}" style="display:inline-block;margin-top:16px;background:#12a068;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700">Empezar a invertir →</a>"""))

def email_orden_ejecutada(email: str, nombre: str, ticker: str, tipo: str, monto: float, acciones: float, precio: float) -> bool:
    color = "#17cc85" if tipo == "buy" else "#f44336"
    accion = "Compra" if tipo == "buy" else "Venta"
    return _send(email, f"Orden ejecutada: {accion} {ticker}", _tpl(f"""
<h2 style="color:#dde4f0;font-size:16px;margin-bottom:16px">Orden ejecutada exitosamente</h2>
<div style="background:#1E2835;border-radius:8px;padding:16px;margin-bottom:16px">
<div style="display:flex;justify-content:space-between;margin-bottom:8px">
<span style="color:#8fa0b8">Ticker</span><b style="color:{color}">{ticker}</b></div>
<div style="display:flex;justify-content:space-between;margin-bottom:8px">
<span style="color:#8fa0b8">Tipo</span><b style="color:{color}">{accion.upper()}</b></div>
<div style="display:flex;justify-content:space-between;margin-bottom:8px">
<span style="color:#8fa0b8">Monto</span><b style="color:#dde4f0">${monto:.2f} USD</b></div>
<div style="display:flex;justify-content:space-between;margin-bottom:8px">
<span style="color:#8fa0b8">Acciones</span><b style="color:#dde4f0">{acciones:.8f}</b></div>
<div style="display:flex;justify-content:space-between">
<span style="color:#8fa0b8">Precio ejecución</span><b style="color:#17cc85">${precio:.4f}</b></div>
</div>
<p style="color:#576880;font-size:11px">Firma criptográfica ECDSA P-256 aplicada · AML verificado · {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
<a href="{APP_URL}/ordenes" style="display:inline-block;margin-top:10px;background:#1E2835;color:#17cc85;padding:10px 20px;border-radius:7px;text-decoration:none;font-size:12px;border:1px solid #2a3545">Ver mis órdenes →</a>"""))

def email_deposito_confirmado(email: str, nombre: str, monto: float, metodo: str, saldo_nuevo: float) -> bool:
    return _send(email, f"Depósito confirmado: ${monto:.2f} USD", _tpl(f"""
<h2 style="color:#dde4f0;font-size:16px;margin-bottom:16px">Depósito confirmado</h2>
<div style="background:#1E2835;border-radius:8px;padding:16px;margin-bottom:16px">
<div style="display:flex;justify-content:space-between;margin-bottom:8px">
<span style="color:#8fa0b8">Monto depositado</span><b style="color:#17cc85">${monto:.2f} USD</b></div>
<div style="display:flex;justify-content:space-between;margin-bottom:8px">
<span style="color:#8fa0b8">Método</span><b style="color:#dde4f0">{metodo}</b></div>
<div style="display:flex;justify-content:space-between">
<span style="color:#8fa0b8">Nuevo saldo</span><b style="color:#17cc85">${saldo_nuevo:.2f} USD</b></div>
</div>
<a href="{APP_URL}" style="display:inline-block;margin-top:10px;background:#12a068;color:#fff;padding:10px 20px;border-radius:7px;text-decoration:none;font-size:12px">Invertir ahora →</a>"""))

def email_alerta_riesgo(email: str, nombre: str, perfil: str, sugerencia: str) -> bool:
    return _send(email, "Alerta Robo-Advisor: revisar portafolio", _tpl(f"""
<h2 style="color:#f5a623;font-size:16px;margin-bottom:12px">⚠ Alerta de riesgo — Robo-Advisor IA</h2>
<p style="color:#8fa0b8;line-height:1.7">Tu perfil de inversión es <b style="color:#ab47bc">{perfil}</b>.</p>
<div style="background:#1E2835;border-left:4px solid #f5a623;border-radius:0 8px 8px 0;padding:14px;margin:14px 0">
<p style="color:#dde4f0;margin:0">{sugerencia}</p>
</div>
<a href="{APP_URL}/portafolio" style="display:inline-block;margin-top:10px;background:#ab47bc;color:#fff;padding:10px 20px;border-radius:7px;text-decoration:none;font-size:12px">Ver mi portafolio →</a>"""))

def email_kyc_aprobado(email: str, nombre: str, nivel: str) -> bool:
    return _send(email, "KYC aprobado — Nivel " + nivel, _tpl(f"""
<h2 style="color:#17cc85;font-size:16px;margin-bottom:12px">✓ Verificación KYC aprobada</h2>
<p style="color:#8fa0b8;line-height:1.7">Tu identidad ha sido verificada al nivel <b style="color:#17cc85">{nivel}</b>.</p>
<p style="color:#8fa0b8">Ahora tienes acceso completo a todas las funciones de InvestIQ.</p>
<a href="{APP_URL}" style="display:inline-block;margin-top:14px;background:#12a068;color:#fff;padding:10px 20px;border-radius:7px;text-decoration:none;font-size:12px">Ir a mi cuenta →</a>"""))
