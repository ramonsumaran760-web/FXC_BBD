"""
InvestIQ — Configuración de Producción v2.0
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os, secrets


class Settings(BaseSettings):
    # App
    APP_NAME: str = "InvestIQ Microinversión"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = os.getenv("SECRET_KEY", "investiq-prod-secret-xK9mZ2026!@#")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # PII encryption key (Fernet) — generar con: Fernet.generate_key().decode()
    PII_ENCRYPTION_KEY: str = os.getenv("PII_ENCRYPTION_KEY", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./investiq.db")
    DATABASE_URL_SYNC: str = os.getenv("DATABASE_URL_SYNC", "sqlite:///./investiq.db")
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_TTL_PRICES: int = 15
    REDIS_TTL_PORTFOLIO: int = 30
    REDIS_TTL_METRICS: int = 60

    # Alpaca Paper Trading
    ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "DEMO_KEY")
    ALPACA_API_SECRET: str = os.getenv("ALPACA_API_SECRET", "DEMO_SECRET")
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets/v2"
    ALPACA_DATA_URL: str = "https://data.alpaca.markets/v2"
    ALPACA_WS_URL: str = "wss://stream.data.alpaca.markets/v2/iex"
    ALPACA_WEBHOOK_SECRET: str = os.getenv("ALPACA_WEBHOOK_SECRET", "")

    # Claude API — Robo-Advisor
    CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 1000

    # Yahoo Finance fallback
    YF_TICKERS: list = ["AAPL","MSFT","TSLA","NVDA","AMZN","GOOGL","META","SPY","QQQ","BND","VTI","GLD"]

    # OpenSanctions AML
    OPENSANCTIONS_URL: str = "https://api.opensanctions.org/match/default"

    # Notificaciones — Firebase Cloud Messaging
    FCM_SERVER_KEY: str = os.getenv("FCM_SERVER_KEY", "")
    VAPID_PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_EMAIL: str = os.getenv("VAPID_EMAIL", "admin@investiq.co")

    # Notificaciones — Twilio SMS
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # Email — SendGrid
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "noreply@investiq.co")
    APP_URL: str = os.getenv("APP_URL", "http://localhost:3000")

    # Pagos
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    MERCADOPAGO_ACCESS_TOKEN: str = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")

    # Sentry
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # ECDSA / MFA
    ECDSA_CURVE: str = "secp256r1"
    MFA_ISSUER: str = "InvestIQ"

    # Exportes
    EXPORT_DIR: str = "./static/exports"

    # Órdenes
    MIN_ORDER_USD: float = 1.0
    MAX_ORDER_USD: float = 50000.0

    # Fiscalidad
    IVA_RATE: float = 0.19
    RETENCION_RATE: float = 0.035
    TAX_RATE_ST: float = 0.30     # corto plazo (<1 año)
    TAX_RATE_LT: float = 0.20     # largo plazo (≥1 año)

    # Circuit breaker
    CB_FAILURE_THRESHOLD: int = 5
    CB_TIMEOUT_SECONDS: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
