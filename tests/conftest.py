"""Pytest fixtures and test configuration."""

import os
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment before imports
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["MONGODB_DATABASE"] = "telegram_backup_test"

from app.api.main import app
from app.core.config import Settings, get_settings


@pytest.fixture
def test_settings() -> Settings:
    """Return test settings instance."""
    return get_settings()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
