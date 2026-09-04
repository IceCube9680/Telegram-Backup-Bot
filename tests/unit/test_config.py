"""Unit tests for configuration management."""

import os
from unittest.mock import patch
import pytest

from app.core.config import Settings, get_settings


def test_default_settings():
    """Test default values of Settings."""
    settings = Settings()
    assert settings.APP_NAME == "Telegram Backup Bot"
    assert settings.STORAGE_TYPE == "local"
    assert settings.API_PORT == 8000
    assert settings.MONGODB_DATABASE == "telegram_backup_test"  # from conftest env


def test_settings_environment_override():
    """Test overriding settings with environment variables."""
    with patch.dict(
        os.environ,
        {
            "APP_NAME": "Custom Backup Bot",
            "API_PORT": "9000",
            "LOG_LEVEL": "DEBUG",
            "ENVIRONMENT": "production",
        },
    ):
        settings = Settings()
        assert settings.APP_NAME == "Custom Backup Bot"
        assert settings.API_PORT == 9000
        assert settings.LOG_LEVEL == "DEBUG"
        assert settings.is_production is True


def test_get_settings_cached():
    """Test get_settings() returns cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
