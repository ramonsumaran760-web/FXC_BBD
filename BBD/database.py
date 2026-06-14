"""
Database — SQLAlchemy async con soporte PostgreSQL + TimescaleDB / SQLite dev
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from core.config import settings
import logging

logger = logging.getLogger(__name__)

# Motor async
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE if "postgresql" in settings.DATABASE_URL else 1,
    max_overflow=settings.DB_MAX_OVERFLOW if "postgresql" in settings.DATABASE_URL else 0,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession,
    expire_on_commit=False, autoflush=False, autocommit=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Crea todas las tablas. En PostgreSQL usar Alembic para migraciones."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✓ Base de datos inicializada")
