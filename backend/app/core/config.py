"""
Application configuration
"""
from typing import List
from pydantic_settings import BaseSettings
from pydantic import validator


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "IBSS Superstocks Dashboard"
    DEBUG: bool = True
    API_VERSION: str = "v1"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ibss:ibss_password@localhost:5432/ibss_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis Cache
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 300  # 5 minutes default

    # JWT Authentication
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # External APIs
    POLYGON_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    SEC_EDGAR_USER_AGENT: str = "IBSS Dashboard admin@example.com"

    # Screening Parameters
    DEFAULT_SCREEN_LIMIT: int = 100
    MAX_SCREEN_LIMIT: int = 1000

    # Scheduler (in-process APScheduler orchestration)
    ENABLE_SCHEDULER: bool = False  # opt-in; set true in prod/long-running deploys
    SCHEDULER_TIMEZONE: str = "America/New_York"
    DAILY_PRICE_UPDATE_HOUR: int = 16  # 4 PM ET
    DAILY_PRICE_UPDATE_MINUTE: int = 30  # 30 min after close
    WEEKLY_SCAN_DAY: str = "sun"  # cron day_of_week
    WEEKLY_SCAN_HOUR: int = 6
    WEEKLY_SCAN_MODE: str = "standard"  # quick | standard | deep
    WEEKLY_SCAN_MIN_SCORE: float = 50.0

    # Risk Management
    DEFAULT_RISK_PER_TRADE: float = 0.02  # 2%
    MAX_POSITION_SIZE: float = 0.40  # 40%

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
