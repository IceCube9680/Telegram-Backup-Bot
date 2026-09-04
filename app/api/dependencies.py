"""FastAPI common dependencies."""

from pymongo.asynchronous.database import AsyncDatabase
from app.database.mongo import get_database


async def get_db() -> AsyncDatabase:
    """Dependency providing access to the MongoDB async database."""
    return await get_database()
