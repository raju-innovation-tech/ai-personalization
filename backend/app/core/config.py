"""
Central application configuration.

All values are sourced from environment variables (.env in local dev,
real environment variables in production). Nothing sensitive is
hardcoded here — see .env.example for the full list of variables.
"""
from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "AI Personalization & Offer Engine"
    APP_ENV: str = "development"  # development | staging | production
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    JWT_SECRET_KEY: str = Field(..., description="Must be set via environment/.env")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Database ---
    DATABASE_URL: str = Field(
        ...,
        description="postgresql+asyncpg://user:pass@host:port/dbname",
    )
    DATABASE_URL_SYNC: str = Field(
        ...,
        description="postgresql+psycopg2://user:pass@host:port/dbname (used by Alembic)",
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL_SECONDS: int = 900

    # --- Celery ---
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- CORS ---
    # NoDecode: stop pydantic-settings from JSON-parsing the env value, so the
    # comma-separated form in .env works (the validator below splits it).
    CORS_ORIGINS: Annotated[List[str], NoDecode] = ["http://localhost", "http://127.0.0.1"]
    # Flutter web (`flutter run -d chrome`) serves from a RANDOM localhost port,
    # so allow any port on localhost / 127.0.0.1 in addition to the list above.
    CORS_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # --- Rate limiting ---
    EVENTS_RATE_LIMIT_PER_MINUTE: int = 600

    # --- Recommendation engine (Phase 2) ---
    RECO_LOOKBACK_DAYS: int = 90  # only events newer than this feed the models
    RECO_HALF_LIFE_DAYS: float = 30.0  # an interaction loses half its weight every N days
    RECO_SNAPSHOT_TTL_SECONDS: int = 300  # in-memory model snapshot is rebuilt after this
    RECO_EXCLUDE_OUT_OF_STOCK: bool = True
    RECO_FBT_MIN_SUPPORT: int = 2  # min. baskets containing both products for "bought together"
    RECO_MAX_LIMIT: int = 50

    # --- Customer intelligence (Phase 3) ---
    CUSTOMER_LOOKBACK_DAYS: int = 365  # behaviour older than this is ignored for RFM
    CUSTOMER_ACTIVE_DAYS: int = 30  # "recently active" window (prospects vs inactive, new customers)
    CUSTOMER_PROFILE_REFRESH_MINUTES: int = 60  # automatic recompute interval; 0 = manual only

    # --- Seed / Admin bootstrap ---
    FIRST_SUPER_ADMIN_EMAIL: str = "admin@example.com"
    FIRST_SUPER_ADMIN_PASSWORD: str = "ChangeMe123!"

    # --- LLM (optional, Phase 19 feature — not used in Phase 1) ---
    ANTHROPIC_API_KEY: str = ""

    # --- Phase 8: Production Hardening ---
    MAX_CONTENT_LENGTH_BYTES: int = 10 * 1024 * 1024  # 10MB maximum request payload size
    ENABLE_SECURITY_HEADERS: bool = True
    DB_POOL_RECYCLE_SECONDS: int = 1800  # recycle connections every 30 mins
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 15  # anti-bruteforce login limit
    METRICS_ENABLED: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
