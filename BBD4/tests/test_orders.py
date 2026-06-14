"""
test_orders.py — Tests de órdenes + Stop-Loss / Take-Profit
"""
import pytest
from httpx import AsyncClient
from models.models import PosicionPortafolio, TaxLot, OrdenAutomatica


@pytest.mark.asyncio
async def test_crear_orden_buy(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.post("/api/v1/ordenes",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"ticker": "AAPL", "monto_usd": 10.0, "tipo": "buy"})
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "AAPL"
    assert data["tipo"] == "buy"
    assert "firma_ok" in data


@pytest.mark.asyncio
async def test_crear_orden_monto_invalido(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.post("/api/v1/ordenes",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"ticker": "AAPL", "monto_usd": 0.5})  # < MIN_ORDER_USD
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_crear_orden_saldo_insuficiente(client: AsyncClient, demo_user, db):
    user, token = demo_user
    user.saldo_usd = 0.5  # sin saldo
    await db.commit()

    r = await client.post("/api/v1/ordenes",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"ticker": "AAPL", "monto_usd": 100.0, "tipo": "buy"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_listar_ordenes(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.get("/api/v1/ordenes",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_tax_lot_creado_en_compra(client: AsyncClient, demo_user, db):
    """Cada compra debe crear un TaxLot para FIFO/LIFO."""
    user, token = demo_user
    await client.post("/api/v1/ordenes",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"ticker": "MSFT", "monto_usd": 50.0, "tipo": "buy"})

    from sqlalchemy import select
    lots = (await db.execute(select(TaxLot).where(
        TaxLot.usuario_id == user.id, TaxLot.ticker == "MSFT"))).scalars().all()
    assert len(lots) >= 1
    assert lots[0].acciones_restantes > 0


@pytest.mark.asyncio
async def test_stop_loss_creacion(client: AsyncClient, demo_user, db):
    user, token = demo_user
    # Primero crear posición
    db.add(PosicionPortafolio(
        usuario_id=user.id, ticker="TSLA", nombre="Tesla",
        acciones=1.0, precio_promedio_compra=200.0, precio_actual=250.0,
        valor_total_usd=250.0))
    await db.commit()

    r = await client.post("/api/v1/ordenes/automatica",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"ticker": "TSLA", "tipo": "stop_loss",
                                "precio_trigger": 180.0, "porcentaje_pos": 100.0})
    assert r.status_code == 200
    data = r.json()
    assert data["tipo"] == "stop_loss"
    assert data["activa"] is True


@pytest.mark.asyncio
async def test_stop_loss_sin_posicion(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.post("/api/v1/ordenes/automatica",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"ticker": "NVDA", "tipo": "stop_loss",
                                "precio_trigger": 800.0, "porcentaje_pos": 50.0})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_listar_ordenes_automaticas(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.get("/api/v1/ordenes/automaticas",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_ordenes_requiere_auth(client: AsyncClient):
    r = await client.post("/api/v1/ordenes",
                          json={"ticker": "AAPL", "monto_usd": 10.0})
    assert r.status_code in (401, 403)
