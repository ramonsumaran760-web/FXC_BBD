"""
tests/test_core.py — Tests unitarios InvestIQ
Ejecutar: pytest tests/ -v
"""
import pytest, asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Security tests ─────────────────────────────────────
def test_hash_password():
    from core.security import hash_password, verify_password
    h = hash_password("MiPassword123!")
    assert verify_password("MiPassword123!", h)
    assert not verify_password("WrongPassword", h)

def test_jwt_tokens():
    from core.security import create_access_token, decode_token
    tok = create_access_token({"sub": "1", "email": "test@test.com"})
    data = decode_token(tok)
    assert data["sub"] == "1"
    assert data["email"] == "test@test.com"

def test_ecdsa_firma():
    from core.security import firmar_orden, verificar_firma
    datos = {"ticker": "AAPL", "monto": 100.0, "tipo": "buy"}
    firma = firmar_orden(datos)
    assert verificar_firma(datos, firma)
    datos_alt = {"ticker": "AAPL", "monto": 200.0, "tipo": "buy"}
    assert not verificar_firma(datos_alt, firma)

def test_mfa_secret():
    from core.security import generar_mfa_secret, verificar_totp
    import pyotp
    secret = generar_mfa_secret()
    assert len(secret) >= 16
    totp = pyotp.TOTP(secret)
    token = totp.now()
    assert verificar_totp(secret, token)
    assert not verificar_totp(secret, "000000")

def test_nonce():
    from core.security import generar_nonce
    n1 = generar_nonce(); n2 = generar_nonce()
    assert len(n1) == 32
    assert n1 != n2

# ── Services tests ─────────────────────────────────────
def test_market_prices():
    from services.services import get_market_prices
    prices = get_market_prices(["AAPL", "NVDA"])
    assert "AAPL" in prices
    assert prices["AAPL"]["price"] > 0
    assert "source" in prices["AAPL"]

def test_alpaca_demo():  # noqa
    from services.services import alpaca_get_account, alpaca_get_positions, alpaca_place_order
    acc = alpaca_get_account("DEMO_KEY", "DEMO_SECRET")
    assert "equity" in acc
    pos = alpaca_get_positions("DEMO_KEY", "DEMO_SECRET")
    assert isinstance(pos, list)
    # positions list can be empty in sandbox

def test_aml_clear():
    from services.services import aml_check_entidad
    r = aml_check_entidad("Empresa Limpia S.A.S")
    assert r["status"] == "clear"

def test_aml_blocked():
    from services.services import aml_check_entidad
    r = aml_check_entidad("FARC Colombia")
    assert r["status"] == "blocked"
    assert r["score"] == 1.0

def test_robo_advisor_local():
    from services.services import robo_advisor_analizar
    perfil = {"edad": 25, "ingresos_anuales_usd": 20000, "tolerancia_riesgo": "alta", "saldo_usd": 5000}
    port = [{"ticker": "NVDA", "valor_total_usd": 4500}, {"ticker": "SPY", "valor_total_usd": 500}]
    r = robo_advisor_analizar(perfil, port)
    assert r["perfil"] in ["conservador", "moderado", "agresivo"]
    assert 0 <= r["score_riesgo"] <= 100
    assert isinstance(r["alerta_riesgo"], bool)
    assert "_prompt_json_enviado" in r
    assert len(r["acciones_recomendadas"]) > 0

def test_candles():
    from services.services import get_candles
    c = get_candles("AAPL", "1mo", "1d")
    assert isinstance(c, list)
    assert len(c) > 0
    assert all(k in c[0] for k in ["t","o","h","l","c","v"])

def test_cache():
    from services.services import cache_set, cache_get, cache_delete
    cache_set("test_pytest", {"valor": 42}, ttl=60)
    val = cache_get("test_pytest")
    assert val == {"valor": 42}
    cache_delete("test_pytest")
    assert cache_get("test_pytest") is None

# ── Payments tests ─────────────────────────────────────
def test_payments_config():
    from services.payments import verificar_config_pagos
    config = verificar_config_pagos()
    assert "stripe" in config
    assert "mercadopago" in config
    assert "modo" in config

def test_stripe_demo():
    from services.payments import stripe_crear_payment_intent
    r = stripe_crear_payment_intent(100.0, "test@test.com")
    assert "id" in r
    assert "source" in r

def test_mp_demo():
    from services.payments import mp_crear_preferencia
    r = mp_crear_preferencia(100.0, "test@test.com")
    assert "id" in r

def test_crypto_demo():
    from services.payments import crypto_generar_direccion_deposito
    r = crypto_generar_direccion_deposito(1, "USDC")
    assert "direccion" in r
    assert "moneda" in r

# ── Excel + PDF ───────────────────────────────────────
def test_generar_excel(tmp_path):
    from services.services import generar_excel_portafolio
    pos = [{"ticker":"AAPL","nombre":"Apple","acciones":2.3,"precio_promedio_compra":189,
            "precio_actual":195,"valor_total_usd":448,"ganancia_perdida_usd":13,"ganancia_perdida_pct":3.0}]
    ruta = str(tmp_path / "test.xlsx")
    resultado = generar_excel_portafolio({"nombre":"Test","email":"t@t.co"}, pos, [], [], ruta)
    assert os.path.exists(resultado)
    assert os.path.getsize(resultado) > 1000

def test_generar_pdf(tmp_path):
    from services.services import generar_pdf_reporte
    pos = [{"ticker":"AAPL","nombre":"Apple","acciones":2.3,"precio_promedio_compra":189,
            "precio_actual":195,"valor_total_usd":448,"ganancia_perdida_usd":13,"ganancia_perdida_pct":3.0}]
    ruta = str(tmp_path / "test.pdf")
    resultado = generar_pdf_reporte({"nombre":"Test","email":"t@t.co"}, pos,
        {"valor_portafolio":448,"ganancia_total":13,"ganancia_pct":3,"posiciones":1,"saldo":5000,"ordenes":1,"dividendos_total":0},
        ruta)
    assert os.path.exists(resultado)
    assert os.path.getsize(resultado) > 500

# ── DB async tests ────────────────────────────────────
@pytest.mark.asyncio
async def test_db_tablas():
    from core.database import init_db, AsyncSessionLocal
    from sqlalchemy import text
    await init_db()
    async with AsyncSessionLocal() as db:
        r = await db.execute(text('SELECT name FROM sqlite_master WHERE type="table"'))
        tables = [row[0] for row in r.fetchall()]
    assert len(tables) >= 13
    assert "usuarios" in tables
    assert "ordenes" in tables
    assert "portafolio" in tables

@pytest.mark.asyncio
async def test_seed():
    from core.database import init_db, AsyncSessionLocal
    from models.models import Usuario, PosicionPortafolio, Orden
    from sqlalchemy import select, func
    await init_db()
    async with AsyncSessionLocal() as db:
        from main import seed_inicial
        await seed_inicial(db)
        n_u = (await db.execute(select(func.count(Usuario.id)))).scalar()
        n_p = (await db.execute(select(func.count(PosicionPortafolio.id)))).scalar()
        n_o = (await db.execute(select(func.count(Orden.id)))).scalar()
    assert n_u >= 1
    assert n_p >= 3
    assert n_o >= 10
