"""Integration and lifecycle tests for MongoDB connection manager."""

from unittest.mock import AsyncMock, patch
import pytest
from app.core.exceptions import DatabaseConnectionError
from app.database.mongo import MongoDBManager


@pytest.mark.asyncio
async def test_mongo_manager_unconnected_state():
    """Test manager behavior prior to connection."""
    manager = MongoDBManager()
    assert manager.client is None
    assert manager.db is None
    assert await manager.ping() is False

    with pytest.raises(DatabaseConnectionError):
        manager.get_database()


@pytest.mark.asyncio
async def test_mongo_manager_invalid_connection():
    """Test manager behavior with unreachable host and short timeout."""
    manager = MongoDBManager()
    with pytest.raises(DatabaseConnectionError):
        await manager.connect(
            uri="mongodb://non-existent-host:27017",
            database_name="test_db",
            timeout_ms=300,
        )
    await manager.disconnect()


@pytest.mark.asyncio
async def test_mongo_manager_mocked_successful_lifecycle():
    """Test manager connect, get_database, ping, and disconnect with mocked AsyncMongoClient."""
    manager = MongoDBManager()
    with patch("app.database.mongo.AsyncMongoClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.admin.command = AsyncMock(return_value={"ok": 1.0})
        mock_client_instance.close = AsyncMock()
        mock_client_instance.__getitem__.return_value = AsyncMock()
        mock_client_cls.return_value = mock_client_instance

        db = await manager.connect(uri="mongodb://localhost:27017", database_name="test_db")
        assert db is not None
        assert manager.client is not None
        assert manager.get_database() is db
        assert await manager.ping() is True

        await manager.disconnect()
        assert manager.client is None
        assert manager.db is None
