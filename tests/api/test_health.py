"""Tests for health check endpoints."""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_healthy(async_client: AsyncClient):
    """Test health endpoint when MongoDB is connected."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True

        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "timestamp" in data
        assert data["app"] == "Telegram Backup Bot"
        assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_api_health_check_healthy(async_client: AsyncClient):
    """Test /api/health route alias."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True

        response = await async_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_health_check_degraded_when_db_down(async_client: AsyncClient):
    """Test health endpoint when MongoDB is disconnected/unreachable."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = False

        response = await async_client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
        assert "details" in data
