"""
test_portfolio.py — Tests de portafolio y equity curve
"""
import pytest
from httpx import AsyncClient
from datetime import datetime
from models.models import PosicionPortafolio, EquityCurve


@pytest.mark.asyncio
async def test_portafolio_vacio(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.get("/api/v1/portafolio",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "posiciones" in data
    assert "total_valor_usd" in data
    assert isinstance(data["posiciones"], list)


@pytest.mark.asyncio
async def test_portafolio_con_posicion(client: AsyncClient, demo_user, db):
    user, token = demo_user
    # Crear posición manualmente
    pos = PosicionPortafolio(
        usuario_id=user.id, ticker="AAPL", nombre="Apple Inc.",
        acciones=2.5, precio_promedio_compra=190.0, precio_actual=195.0,
        valor_total_usd=487.5, ganancia_perdida_usd=12.5, ganancia_perdida_pct=2.63
    )
    db.add(pos)
    await db.commit()

    r = await client.get("/api/v1/portafolio",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["posiciones"]) >= 1
    tickers = [p["ticker"] for p in data["posiciones"]]
    assert "AAPL" in tickers


@pytest.mark.asyncio
async def test_equity_curve_vacia(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.get("/api/v1/portafolio/equity-curve?dias=30",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "puntos" in data
    assert "dias" in data


@pytest.mark.asyncio
async def test_equity_curve_con_datos(client: AsyncClient, demo_user, db):
    user, token = demo_user
    # Insertar puntos de equity curve
    for i in range(5):
        db.add(EquityCurve(
            usuario_id=user.id,
            valor_portafolio_usd=10000.0 + i * 100,
            saldo_disponible_usd=5000.0,
            ganancia_perdida_usd=i * 100,
            ganancia_perdida_pct=i * 1.0
        ))
    await db.commit()

    r = await client.get("/api/v1/portafolio/equity-curve?dias=30",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["puntos"]) >= 5
    assert "rendimiento_pct" in data


@pytest.mark.asyncio
async def test_equity_curve_dias_invalido(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.get("/api/v1/portafolio/equity-curve?dias=400",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422  # Validación Pydantic


@pytest.mark.asyncio
async def test_portafolio_requiere_auth(client: AsyncClient):
    r = await client.get("/api/v1/portafolio")
    assert r.status_code in (401, 403)
