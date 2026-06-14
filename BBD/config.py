"""
InvestIQ — Configuración de Producción
Stack: FastAPI + PostgreSQL/SQLite + Redis + Alpaca + Claude API
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    # App
    APP_NAME: str = "InvestIQ Microinversión"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = os.getenv("SECRET_KEY", "investiq-prod-secret-xK9mZ2026!@#")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database — PostgreSQL en prod, SQLite en dev
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./investiq.db"  # cambiar a postgres en prod
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "sqlite:///./investiq.db"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30

    # Redis cache
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_TTL_PRICES: int = 15        # 15s para precios
    REDIS_TTL_PORTFOLIO: int = 30     # 30s para portafolio
    REDIS_TTL_METRICS: int = 60       # 1min para métricas

    # Alpaca Paper Trading (broker real gratuito)
    ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "DEMO_KEY")
    ALPACA_API_SECRET: str = os.getenv("ALPACA_API_SECRET", "DEMO_SECRET")
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets/v2"
    ALPACA_DATA_URL: str = "https://data.alpaca.markets/v2"
    ALPACA_WS_URL: str = "wss://stream.data.alpaca.markets/v2/iex"

    # Claude API — Robo-Advisor
    CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 1000

    # Yahoo Finance fallback (siempre gratis)
    YF_TICKERS: list = ["AAPL","MSFT","TSLA","NVDA","AMZN","GOOGL","META","SPY","QQQ","BND","VTI","GLD"]

    # OpenSanctions AML
    OPENSANCTIONS_URL: str = "https://api.opensanctions.org/match/default"

    # ECDSA Crypto
    ECDSA_CURVE: str = "secp256r1"

    # MFA
    MFA_ISSUER: str = "InvestIQ"

    # Exportes
    EXPORT_DIR: str = "./static/exports"

    # Fraccionamiento mínimo
    MIN_ORDER_USD: float = 1.0
    MAX_ORDER_USD: float = 50000.0

    # IVA Colombia
    IVA_RATE: float = 0.19
    RETENCION_RATE: float = 0.035

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
