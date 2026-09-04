"""Configuration settings using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings schema and environment variable loader."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Telegram Backup Bot"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Telegram Bot
    BOT_TOKEN: str = ""

    # MongoDB Connection
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "telegram_backup"
    MONGODB_TIMEOUT_MS: int = 5000

    # Security & Secrets
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production"
    JWT_SECRET: str = "default-insecure-jwt-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Storage Configuration
    STORAGE_TYPE: str = "local"  # "local" or "s3"
    STORAGE_PATH: str = "./storage"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB default

    # S3 Compatible Storage (Optional)
    S3_ENDPOINT: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_REGION: str = "us-east-1"

    @property
    def is_production(self) -> bool:
        """Check if environment is set to production."""
        return self.ENVIRONMENT.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
