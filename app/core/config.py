import re
from functools import lru_cache
from typing import Optional
from pydantic import Field, model_validator
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
    MAX_REQUEST_BODY_SIZE: int = 10 * 1024 * 1024  # 10 MB limit for JSON/Payloads

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    BOT_TOKEN: str = ""
    TELEGRAM_MODE: str = "polling"

    @property
    def telegram_token(self) -> str:
        """Return the active Telegram Bot Token from TELEGRAM_BOT_TOKEN or BOT_TOKEN."""
        return (self.TELEGRAM_BOT_TOKEN or self.BOT_TOKEN or "").strip()

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
    MAX_FILE_SIZE: int = 4294967296  # 4 GiB default (4,294,967,296 bytes)

    # MTProto Large File Configuration (Phase 10)
    MT_PROTO_ENABLED: bool = False
    MT_PROTO_API_ID: Optional[int] = None
    MT_PROTO_API_HASH: Optional[str] = None
    MT_PROTO_SESSION_PATH: str = "./secrets/telegram_mtproto.session"
    MT_PROTO_CHUNK_SIZE: int = 1048576  # 1 MiB chunk size
    MT_PROTO_CONCURRENCY: int = 1
    MT_PROTO_MAX_ATTEMPTS: int = 5
    MT_PROTO_RETRY_BASE_DELAY: float = 2.0  # seconds
    MT_PROTO_RETRY_MAX_DELAY: float = 60.0  # seconds
    LARGE_FILE_THRESHOLD: int = 20 * 1024 * 1024  # 20 MiB (20,971,520 bytes)
    LARGE_FILE_RESUME_ENABLED: bool = True
    LARGE_FILE_DISK_SAFETY_MARGIN: int = 1073741824  # 1 GiB safety headroom

    # Disk Space Health Thresholds (%)
    DISK_WARNING_THRESHOLD_PCT: float = 80.0
    DISK_CRITICAL_THRESHOLD_PCT: float = 90.0

    # S3 Compatible Storage (Optional)
    S3_ENDPOINT: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    S3_REGION: str = "us-east-1"

    # Worker Configuration
    WORKER_ENABLED: bool = True
    WORKER_ID: Optional[str] = None
    WORKER_CONCURRENCY: int = 2
    WORKER_POLL_INTERVAL: float = 2.0  # seconds
    WORKER_LOCK_TIMEOUT: int = 300  # seconds
    WORKER_MAX_ATTEMPTS: int = 3
    WORKER_RETRY_BASE_DELAY: float = 2.0  # seconds
    WORKER_RETRY_MAX_DELAY: float = 60.0  # seconds
    WORKER_DOWNLOAD_CHUNK_SIZE: int = 65536  # 64 KiB
    WORKER_HEARTBEAT_INTERVAL: float = 30.0  # seconds

    # Web Dashboard & Sessions
    WEB_ENABLED: bool = True
    WEB_SESSION_SECRET: Optional[str] = None
    WEB_SESSION_EXPIRE_SECONDS: int = 7 * 24 * 3600  # 7 days
    WEB_COOKIE_NAME: str = "backup_bot_session"
    WEB_COOKIE_SECURE: Optional[bool] = None
    WEB_COOKIE_SAMESITE: str = "lax"
    WEB_BASE_URL: str = "http://localhost:8000"
    WEB_ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"]
    )

    # Rate Limiting (Single-instance in-memory baseline)
    RATE_LIMIT_ENABLED: bool = True

    @property
    def is_production(self) -> bool:
        """Check if environment is set to production."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development_or_test(self) -> bool:
        """Check if environment is set to development or test."""
        return self.ENVIRONMENT.lower() in ("development", "test", "dev")

    @property
    def dev_login_allowed(self) -> bool:
        """Check if instant dev-login is allowed in current environment."""
        return self.is_development_or_test

    @property
    def cookie_secure(self) -> bool:
        """Return whether session cookies must have Secure flag."""
        if self.WEB_COOKIE_SECURE is not None:
            return self.WEB_COOKIE_SECURE
        return self.is_production

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        """Enforce strict security requirements when running in production."""
        # 0. MTProto Validation when enabled in any environment
        if self.MT_PROTO_ENABLED:
            if not self.MT_PROTO_API_ID or self.MT_PROTO_API_ID <= 0:
                raise ValueError("MT_PROTO_API_ID must be a valid positive integer when MT_PROTO_ENABLED=true.")
            if not self.MT_PROTO_API_HASH or len(self.MT_PROTO_API_HASH.strip()) < 10:
                raise ValueError("MT_PROTO_API_HASH is required when MT_PROTO_ENABLED=true.")
            if not self.MT_PROTO_SESSION_PATH:
                raise ValueError("MT_PROTO_SESSION_PATH is required when MT_PROTO_ENABLED=true.")

        if not self.is_production:
            return self

        # 1. Automatically force DEBUG off in production
        object.__setattr__(self, "DEBUG", False)

        # 2. Distinct BOT_TOKEN Validation (Telegram token format: <digits>:<string>)
        token = self.telegram_token
        if not token:
            raise ValueError("BOT_TOKEN (or TELEGRAM_BOT_TOKEN) is strictly required in production.")

        token_lower = token.lower()
        known_token_placeholders = {
            "your_telegram_bot_token_here",
            "change_me",
            "your-bot-token",
            "bot_token_here",
            "placeholder",
        }
        if token_lower in known_token_placeholders or any(p in token_lower for p in ["your_telegram", "change_me"]):
            raise ValueError(
                f"Insecure placeholder Telegram BOT_TOKEN detected in production: '{token}'."
            )

        # Telegram bot token regex format: digits:token_secret
        if not re.match(r"^\d{6,14}:[A-Za-z0-9_-]{20,50}$", token):
            raise ValueError(
                "Invalid Telegram BOT_TOKEN format in production. Expected '<bot_id>:<token_secret>' format."
            )

        # 3. Generic Secret Strength Validation for WEB_SESSION_SECRET
        if not self.WEB_SESSION_SECRET:
            raise ValueError("WEB_SESSION_SECRET is strictly required in production.")

        session_secret = self.WEB_SESSION_SECRET.strip()
        if len(session_secret) < 32:
            raise ValueError(
                f"WEB_SESSION_SECRET is too short ({len(session_secret)} chars). Production requires >= 32 characters."
            )

        insecure_patterns = [
            "change-this",
            "change_me",
            "changeme",
            "secret",
            "default",
            "insecure",
            "password",
            "123456",
            "test",
            "dev",
            "your-secret",
        ]
        sec_lower = session_secret.lower()
        if any(pat in sec_lower for pat in insecure_patterns) and len(set(sec_lower)) < 12:
            raise ValueError(
                "WEB_SESSION_SECRET contains known weak/placeholder substrings in production."
            )

        # 4. Insecure defaults for SECRET_KEY / JWT_SECRET
        if self.SECRET_KEY.startswith("default-insecure") or "change-in-production" in self.SECRET_KEY:
            raise ValueError("SECRET_KEY must be changed from default placeholder in production.")

        if self.JWT_SECRET.startswith("default-insecure") or "change-in-production" in self.JWT_SECRET:
            raise ValueError("JWT_SECRET must be changed from default placeholder in production.")

        # 5. Database URI validation
        if not self.MONGODB_URI or not self.MONGODB_URI.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("A valid MONGODB_URI is required in production.")

        # 6. Ensure default cookie_secure is True if not set
        if self.WEB_COOKIE_SECURE is None:
            object.__setattr__(self, "WEB_COOKIE_SECURE", True)

        return self


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()

