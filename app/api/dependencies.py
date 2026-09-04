"""FastAPI common dependencies."""

from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database.mongo import get_database


async def get_db() -> AsyncIOMotorDatabase:
    """Dependency providing access to the MongoDB database."""
    return await get_database()
