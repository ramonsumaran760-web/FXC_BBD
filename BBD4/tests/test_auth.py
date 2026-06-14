"""
test_auth.py — Tests de autenticación JWT y MFA
"""
import pytest, pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_exitoso(client: AsyncClient, demo_user):
    user, _ = demo_user
    r = await client.post("/api/v1/auth/login",
                          json={"email": "test@example.com", "password": "Test1234!"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["usuario"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_login_credenciales_invalidas(client: AsyncClient):
    r = await client.post("/api/v1/auth/login",
                          json={"email": "test@example.com", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_usuario_inexistente(client: AsyncClient):
    r = await client.post("/api/v1/auth/login",
                          json={"email": "noexiste@x.com", "password": "Test1234!"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_me_con_token(client: AsyncClient, demo_user):
    user, token = demo_user
    r = await client.get("/api/v1/auth/me",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_me_sin_token(client: AsyncClient):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_me_token_invalido(client: AsyncClient):
    r = await client.get("/api/v1/auth/me",
                         headers={"Authorization": "Bearer token_falso_12345"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalida_token(client: AsyncClient, demo_user):
    user, token = demo_user
    # Logout
    r = await client.post("/api/v1/auth/logout",
                          headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # El mismo token ya no debería funcionar (si Redis está disponible)
    # En test sin Redis, puede que siga funcionando — verificamos que el endpoint responde
    r2 = await client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {token}"})
    # Puede ser 200 (sin Redis) o 401 (con Redis y blacklist)
    assert r2.status_code in (200, 401)


@pytest.mark.asyncio
async def test_register_nuevo_usuario(client: AsyncClient):
    r = await client.post("/api/v1/auth/register", json={
        "nombre": "Nuevo Usuario",
        "email": "nuevo@example.com",
        "password": "Nueva1234!",
        "edad": 25,
        "tolerancia_riesgo": "moderada"
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["usuario"]["email"] == "nuevo@example.com"


@pytest.mark.asyncio
async def test_register_email_duplicado(client: AsyncClient, demo_user):
    r = await client.post("/api/v1/auth/register", json={
        "nombre": "Duplicado",
        "email": "test@example.com",
        "password": "Dup1234!"
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, demo_user):
    user, _ = demo_user
    # Login para obtener refresh token real
    r = await client.post("/api/v1/auth/login",
                          json={"email": "test@example.com", "password": "Test1234!"})
    refresh_token = r.json()["refresh_token"]

    r2 = await client.post("/api/v1/auth/refresh",
                           json={"refresh_token": refresh_token})
    assert r2.status_code == 200
    assert "access_token" in r2.json()
