"""Integration tests for MongoDB connection and lifecycle."""

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
            timeout_ms=500,
        )
    assert manager.client is not None or manager.db is None
    await manager.disconnect()
