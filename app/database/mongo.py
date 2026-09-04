"""MongoDB asynchronous connection and lifecycle management."""

import asyncio
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.core.config import get_settings
from app.core.exceptions import DatabaseConnectionError
from app.core.logging import get_logger

logger = get_logger(__name__)


class MongoDBManager:
    """Manages the lifecycle of AsyncIOMotorClient and database instances."""

    def __init__(self) -> None:
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

    @property
    def client(self) -> Optional[AsyncIOMotorClient]:
        """Return raw Motor client instance."""
        return self._client

    @property
    def db(self) -> Optional[AsyncIOMotorDatabase]:
        """Return active MongoDB database instance."""
        return self._db

    async def connect(
        self,
        uri: Optional[str] = None,
        database_name: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> AsyncIOMotorDatabase:
        """Initialize Motor client and verify connectivity."""
        settings = get_settings()
        mongo_uri = uri or settings.MONGODB_URI
        db_name = database_name or settings.MONGODB_DATABASE
        server_timeout = timeout_ms or settings.MONGODB_TIMEOUT_MS

        logger.info(f"Connecting to MongoDB at {mongo_uri} (Database: {db_name})...")

        try:
            self._client = AsyncIOMotorClient(
                mongo_uri,
                serverSelectionTimeoutMS=server_timeout,
                connectTimeoutMS=server_timeout,
            )
            # Verify connectivity
            await self._client.admin.command("ping")
            self._db = self._client[db_name]
            logger.info(f"Successfully connected to MongoDB database '{db_name}'")
            return self._db
        except (ConnectionFailure, ServerSelectionTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise DatabaseConnectionError(
                message=f"Could not connect to MongoDB: {str(e)}",
                details={"uri": mongo_uri, "database": db_name},
            ) from e

    async def disconnect(self) -> None:
        """Gracefully close the Motor client connection."""
        if self._client:
            logger.info("Closing MongoDB connection...")
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB connection closed.")

    async def ping(self) -> bool:
        """Check if MongoDB connection is alive."""
        if self._client is None:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning(f"MongoDB ping failed: {e}")
            return False

    def get_database(self) -> AsyncIOMotorDatabase:
        """Return current database or raise DatabaseConnectionError."""
        if self._db is None:
            raise DatabaseConnectionError(
                message="Database is not connected. Call connect() first."
            )
        return self._db


# Global singleton instance
mongo_manager = MongoDBManager()


async def get_database() -> AsyncIOMotorDatabase:
    """Dependency helper to get active database."""
    return mongo_manager.get_database()
