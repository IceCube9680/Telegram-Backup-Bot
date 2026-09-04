"""Tests for health check endpoints (/health, /health/live, /health/ready, /api/health)."""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_probe_returns_alive(async_client: AsyncClient):
    """Test /health/live returns 200 and alive status regardless of DB status."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_probe_healthy_when_db_connected(async_client: AsyncClient):
    """Test /health/ready returns 200 and ready status when MongoDB ping succeeds."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True

        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_probe_unavailable_when_db_disconnected(async_client: AsyncClient):
    """Test /health/ready returns 503 and not_ready status when MongoDB ping fails."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = False

        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "disconnected"
        assert "details" in data


@pytest.mark.asyncio
async def test_combined_health_check_healthy(async_client: AsyncClient):
    """Test /health returns 200 and healthy status when MongoDB is connected."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True

        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["app"] == "Telegram Backup Bot"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_combined_health_check_degraded(async_client: AsyncClient):
    """Test /health returns 503 and degraded status when MongoDB is disconnected."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = False

        response = await async_client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"


@pytest.mark.asyncio
async def test_api_health_alias(async_client: AsyncClient):
    """Test /api/health alias matches /health behavior."""
    with patch("app.database.mongo.mongo_manager.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True

        response = await async_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
