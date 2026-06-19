from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "FXC_BBD"
    APP_VERSION: str = "1.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8001
    DEBUG: bool = False
    SECRET_KEY: str = "changeme-in-production"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./sporttrade.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Exchange provider (Betfair / Matchbook)
    EXCHANGE_API_URL: str = ""
    EXCHANGE_API_KEY: str = ""
    EXCHANGE_API_SECRET: str = ""
    EXCHANGE_WS_URL: str = ""

    # Sports data provider (Sportradar / API-Football)
    SPORTS_DATA_API_URL: str = "https://v3.football.api-sports.io"
    SPORTS_DATA_API_KEY: str = ""
    SPORTS_DATA_WS_URL: str = ""

    # Latency SLA (ms)
    LATENCY_SLA_MS: int = 500
    LATENCY_ALERT_THRESHOLD_MS: int = 1000

    # Kelly defaults
    KELLY_DEFAULT_DIVISOR: float = 2.0          # Half-Kelly by default
    MAX_EXPOSICION_EVENTO: float = 0.08          # 8% max per event
    MAX_EXPOSICION_TOTAL: float = 0.25           # 25% max simultaneous
    MAX_EVENTOS_SIMULTANEOS: int = 5

    # Agent recalibration
    RECALIBRACION_VENTANA_SEMANAS: int = 12
    RECALIBRACION_MIN_PREDICCIONES: int = 30     # Min predictions before recalibrating

    # Monitoring
    SENTRY_DSN: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
