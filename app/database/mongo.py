"""MongoDB asynchronous connection and lifecycle management using native PyMongo async API."""

import asyncio
from typing import Optional
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.core.config import get_settings
from app.core.exceptions import DatabaseConnectionError
from app.core.logging import get_logger

logger = get_logger(__name__)


class MongoDBManager:
    """Manages the lifecycle of asynchronous PyMongo client and database instances."""

    def __init__(self) -> None:
        self._client: Optional[AsyncMongoClient] = None
        self._db: Optional[AsyncDatabase] = None

    @property
    def client(self) -> Optional[AsyncMongoClient]:
        """Return raw AsyncMongoClient instance."""
        return self._client

    @property
    def db(self) -> Optional[AsyncDatabase]:
        """Return active MongoDB AsyncDatabase instance."""
        return self._db

    async def connect(
        self,
        uri: Optional[str] = None,
        database_name: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> AsyncDatabase:
        """Initialize AsyncMongoClient and verify connectivity."""
        settings = get_settings()
        mongo_uri = uri or settings.MONGODB_URI
        db_name = database_name or settings.MONGODB_DATABASE
        server_timeout = timeout_ms or settings.MONGODB_TIMEOUT_MS

        logger.info(f"Connecting to MongoDB at {mongo_uri} (Database: {db_name})...")

        client = AsyncMongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=server_timeout,
            connectTimeoutMS=server_timeout,
        )

        try:
            # Verify connectivity with an admin ping command
            await client.admin.command("ping")
            self._client = client
            self._db = self._client[db_name]
            logger.info(f"Successfully connected to MongoDB database '{db_name}'")
            return self._db
        except (ConnectionFailure, ServerSelectionTimeoutError, asyncio.TimeoutError, Exception) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            try:
                await client.close()
            except Exception:
                pass
            self._client = None
            self._db = None
            raise DatabaseConnectionError(
                message=f"Could not connect to MongoDB: {str(e)}",
                details={"uri": mongo_uri, "database": db_name},
            ) from e

    async def disconnect(self) -> None:
        """Gracefully close the AsyncMongoClient connection."""
        if self._client is not None:
            logger.info("Closing MongoDB connection...")
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"Error during MongoDB client close: {e}")
            finally:
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

    def get_database(self) -> AsyncDatabase:
        """Return current database or raise DatabaseConnectionError."""
        if self._db is None:
            raise DatabaseConnectionError(
                message="Database is not connected. Call connect() first."
            )
        return self._db


# Global singleton instance
mongo_manager = MongoDBManager()


async def get_database() -> AsyncDatabase:
    """Dependency helper to get active database."""
    return mongo_manager.get_database()
