"""
conftest.py — Fixtures compartidos para todos los tests de InvestIQ.
Usa SQLite en memoria para no afectar producción.
"""
import asyncio, pytest, pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# ── Motor de prueba (SQLite en memoria) ───────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False,
                                   connect_args={"check_same_thread": False})
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession,
                                       expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Crea todas las tablas antes de los tests."""
    from core.database import Base
    # Importar todos los modelos para que SQLAlchemy los registre
    import models.models  # noqa
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db):
    """Cliente HTTP que usa la BD de prueba."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from core.database import get_db

    async def override_get_db():
        yield db

    from main import app
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def demo_user(db):
    """Crea usuario demo y retorna (user, access_token)."""
    from models.models import Usuario
    from core.security import hash_password, create_access_token

    user = Usuario(nombre="Test User", email="test@example.com",
                   password_hash=hash_password("Test1234!"),
                   rol="investor", kyc_nivel="basic", kyc_verificado=True,
                   aml_status="clear", mfa_activo=False, saldo_usd=5000.0)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email, "rol": user.rol})
    return user, token


@pytest_asyncio.fixture
async def admin_user(db):
    from models.models import Usuario
    from core.security import hash_password, create_access_token

    user = Usuario(nombre="Admin", email="admin@example.com",
                   password_hash=hash_password("Admin1234!"),
                   rol="admin", kyc_nivel="biometric", kyc_verificado=True,
                   aml_status="clear", mfa_activo=False, saldo_usd=0.0)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email, "rol": user.rol})
    return user, token
