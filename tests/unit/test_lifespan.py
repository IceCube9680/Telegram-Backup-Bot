"""Unit test for FastAPI application lifespan manager."""

from unittest.mock import AsyncMock, patch
import pytest
from app.api.main import app, lifespan


@pytest.mark.asyncio
async def test_application_lifespan_startup_and_shutdown():
    """Test lifespan connects on startup and disconnects on shutdown."""
    with patch("app.api.main.mongo_manager.connect", new_callable=AsyncMock) as mock_connect, \
         patch("app.api.main.mongo_manager.disconnect", new_callable=AsyncMock) as mock_disconnect:
        
        mock_connect.return_value = None
        mock_disconnect.return_value = None

        async with lifespan(app):
            mock_connect.assert_awaited_once()

        mock_disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_application_lifespan_startup_db_failure_does_not_crash():
    """Test that MongoDB failure on startup logs warning but does not raise unhandled exception."""
    with patch("app.api.main.mongo_manager.connect", new_callable=AsyncMock) as mock_connect, \
         patch("app.api.main.mongo_manager.disconnect", new_callable=AsyncMock) as mock_disconnect:
        
        mock_connect.side_effect = Exception("Connection refused")
        mock_disconnect.return_value = None

        # Should complete successfully without raising exception
        async with lifespan(app):
            mock_connect.assert_awaited_once()

        mock_disconnect.assert_awaited_once()
