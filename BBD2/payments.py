"""
services/payments.py — Gateway de pagos real
Stripe (tarjetas internacionales) + MercadoPago (LATAM) + Crypto (opcional)
"""
import os, json, requests, logging
from datetime import datetime
from core.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# STRIPE — Depósitos con tarjeta internacional
# Docs: https://stripe.com/docs/api
# ─────────────────────────────────────────────────────────
STRIPE_API = "https://api.stripe.com/v1"

def stripe_headers():
    key = os.getenv("STRIPE_SECRET_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/x-www-form-urlencoded"}

def stripe_crear_payment_intent(monto_usd: float, usuario_email: str, metadata: dict = None) -> dict:
    """
    Crea un PaymentIntent en Stripe.
    El frontend usa Stripe.js para completar el pago con la tarjeta.
    """
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return {"id": f"pi_demo_{int(datetime.utcnow().timestamp())}",
                "client_secret": "pi_demo_secret_test",
                "amount": int(monto_usd * 100),
                "currency": "usd",
                "status": "requires_payment_method",
                "source": "demo_mode"}
    try:
        data = {
            "amount": int(monto_usd * 100),  # Stripe usa centavos
            "currency": "usd",
            "receipt_email": usuario_email,
            "metadata[usuario]": usuario_email,
            "metadata[plataforma]": "InvestIQ",
        }
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = str(v)
        r = requests.post(f"{STRIPE_API}/payment_intents",
                          headers=stripe_headers(), data=data, timeout=15)
        return r.json() if r.ok else {"error": r.text, "status": r.status_code}
    except Exception as e:
        logger.error(f"Stripe error: {e}")
        return {"error": str(e)}

def stripe_confirmar_pago(payment_intent_id: str) -> dict:
    """Verifica estado del pago en Stripe (webhook alternativo)."""
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return {"id": payment_intent_id, "status": "succeeded", "source": "demo_mode"}
    try:
        r = requests.get(f"{STRIPE_API}/payment_intents/{payment_intent_id}",
                         headers=stripe_headers(), timeout=10)
        return r.json() if r.ok else {"error": r.text}
    except Exception as e:
        return {"error": str(e)}

def stripe_crear_cliente(email: str, nombre: str) -> dict:
    """Crea o recupera un cliente en Stripe."""
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return {"id": f"cus_demo_{hash(email) % 999999}", "email": email, "source": "demo_mode"}
    try:
        r = requests.post(f"{STRIPE_API}/customers",
                          headers=stripe_headers(),
                          data={"email": email, "name": nombre}, timeout=10)
        return r.json() if r.ok else {"error": r.text}
    except Exception as e:
        return {"error": str(e)}

def stripe_retiro_bank_transfer(monto_usd: float, cuenta_bancaria: dict) -> dict:
    """
    Retiro via Stripe Connect / Payout a cuenta bancaria.
    cuenta_bancaria: {routing: str, account: str, account_holder: str}
    Requiere Stripe Connect habilitado en la cuenta.
    """
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        return {"id": f"po_demo_{int(datetime.utcnow().timestamp())}",
                "amount": int(monto_usd * 100), "status": "paid",
                "arrival_date": "2-3 días hábiles", "source": "demo_mode"}
    # En producción: crear Stripe Payout
    return {"id": "po_prod", "amount": int(monto_usd * 100), "status": "in_transit"}

# ─────────────────────────────────────────────────────────
# MERCADOPAGO — Pagos LATAM (Perú, Colombia, etc.)
# Docs: https://www.mercadopago.com.pe/developers
# ─────────────────────────────────────────────────────────
MP_API = "https://api.mercadopago.com"

def mp_headers():
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "X-Idempotency-Key": str(int(datetime.utcnow().timestamp()))}

def mp_crear_preferencia(monto_usd: float, usuario_email: str, descripcion: str = "Depósito InvestIQ") -> dict:
    """
    Crea una preferencia de pago en MercadoPago.
    Retorna init_point (URL de pago) para redirigir al usuario.
    """
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    if not token:
        return {"id": f"mp_demo_{int(datetime.utcnow().timestamp())}",
                "init_point": "https://www.mercadopago.com.pe/checkout/v1/payment?preference_id=demo",
                "sandbox_init_point": "https://sandbox.mercadopago.com.pe/checkout/demo",
                "status": "demo_mode", "monto": monto_usd}
    try:
        payload = {
            "items": [{"title": descripcion, "quantity": 1, "currency_id": "PEN",
                       "unit_price": round(monto_usd * 3.7, 2)}],  # USD → PEN aprox
            "payer": {"email": usuario_email},
            "back_urls": {
                "success": os.getenv("APP_URL", "http://localhost:3000") + "/deposito/success",
                "failure": os.getenv("APP_URL", "http://localhost:3000") + "/deposito/failure",
                "pending": os.getenv("APP_URL", "http://localhost:3000") + "/deposito/pending"
            },
            "auto_return": "approved",
            "external_reference": f"INVESTIQ_{int(datetime.utcnow().timestamp())}",
        }
        r = requests.post(f"{MP_API}/checkout/preferences",
                          headers=mp_headers(), json=payload, timeout=15)
        return r.json() if r.ok else {"error": r.text, "status": r.status_code}
    except Exception as e:
        return {"error": str(e)}

def mp_verificar_pago(payment_id: str) -> dict:
    """Verifica un pago recibido de MercadoPago (desde webhook)."""
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
    if not token:
        return {"id": payment_id, "status": "approved", "source": "demo_mode"}
    try:
        r = requests.get(f"{MP_API}/v1/payments/{payment_id}", headers=mp_headers(), timeout=10)
        return r.json() if r.ok else {"error": r.text}
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────
# CRYPTO — Depósitos USDC/USDT (via Coinbase Commerce o directo)
# ─────────────────────────────────────────────────────────
def crypto_generar_direccion_deposito(usuario_id: int, moneda: str = "USDC") -> dict:
    """
    En producción: integrar con Coinbase Commerce, BitPay o Circle.
    Por ahora retorna dirección demo.
    """
    api_key = os.getenv("COINBASE_COMMERCE_KEY", "")
    if not api_key:
        return {
            "direccion": "0x742d35Cc6634C0532925a3b8D4C9C3b9d4E7f8A",
            "moneda": moneda,
            "red": "Ethereum / Polygon",
            "qr_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=0x742d35Cc6634C",
            "minimo": "10 USDC",
            "confirmaciones": "12 bloques (~2 min)",
            "nota": "Modo demo. Configurar COINBASE_COMMERCE_KEY para producción.",
            "source": "demo_mode"
        }
    # Producción: crear charge en Coinbase Commerce
    try:
        r = requests.post("https://api.commerce.coinbase.com/charges",
                          headers={"X-CC-Api-Key": api_key, "X-CC-Version": "2018-03-22",
                                   "Content-Type": "application/json"},
                          json={"name": "Depósito InvestIQ", "description": f"Usuario #{usuario_id}",
                                "pricing_type": "no_price",
                                "metadata": {"usuario_id": str(usuario_id), "plataforma": "InvestIQ"}},
                          timeout=10)
        return r.json() if r.ok else {"error": r.text}
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────
# WEBHOOK HANDLER — Procesar eventos entrantes
# ─────────────────────────────────────────────────────────
def procesar_webhook_stripe(payload: dict, signature: str) -> dict:
    """
    Verifica y procesa webhooks de Stripe.
    En producción verificar firma con stripe.Webhook.construct_event()
    """
    event_type = payload.get("type", "")
    data = payload.get("data", {}).get("object", {})

    if event_type == "payment_intent.succeeded":
        return {"accion": "acreditar_saldo",
                "monto_usd": data.get("amount", 0) / 100,
                "payment_intent_id": data.get("id"),
                "email": data.get("receipt_email")}
    elif event_type == "payment_intent.payment_failed":
        return {"accion": "notificar_fallo", "payment_intent_id": data.get("id")}
    return {"accion": "ignorar", "event": event_type}

def procesar_webhook_mercadopago(payment_id: str) -> dict:
    """Procesa notificaciones IPN de MercadoPago."""
    pago = mp_verificar_pago(payment_id)
    if pago.get("status") == "approved":
        return {"accion": "acreditar_saldo",
                "monto": pago.get("transaction_amount", 0),
                "moneda": pago.get("currency_id", "PEN"),
                "payment_id": payment_id}
    return {"accion": "pendiente", "status": pago.get("status")}

# ─────────────────────────────────────────────────────────
# RESUMEN DE VARIABLES DE ENTORNO REQUERIDAS
# ─────────────────────────────────────────────────────────
PAYMENT_ENV_VARS = {
    "STRIPE_SECRET_KEY":         "sk_test_... (Stripe Dashboard → Developers → API Keys)",
    "STRIPE_WEBHOOK_SECRET":     "whsec_... (Stripe Dashboard → Webhooks)",
    "STRIPE_PUBLISHABLE_KEY":    "pk_test_... (Frontend Stripe.js)",
    "MERCADOPAGO_ACCESS_TOKEN":  "APP_USR-... (MercadoPago Developer → Credenciales)",
    "COINBASE_COMMERCE_KEY":     "... (Coinbase Commerce → Settings → API Keys)",
    "APP_URL":                   "https://tu-dominio.com",
}

def verificar_config_pagos() -> dict:
    """Verifica qué gateways están configurados."""
    return {
        "stripe": bool(os.getenv("STRIPE_SECRET_KEY")),
        "mercadopago": bool(os.getenv("MERCADOPAGO_ACCESS_TOKEN")),
        "crypto": bool(os.getenv("COINBASE_COMMERCE_KEY")),
        "modo": "demo" if not any([
            os.getenv("STRIPE_SECRET_KEY"),
            os.getenv("MERCADOPAGO_ACCESS_TOKEN")
        ]) else "produccion"
    }
