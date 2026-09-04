"""User repository for managing Telegram users in MongoDB."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.database.models.user import UserModel
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """Repository for User collection operations."""

    ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "first_name", "telegram_user_id"}

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, "users")

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """Find a user by unique Telegram user ID."""
        doc = await self.collection.find_one({"telegram_user_id": telegram_user_id})
        return self.format_doc(doc)

    async def upsert_user(
        self,
        telegram_user_id: int,
        first_name: str,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
        is_admin: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Atomically insert or update user profile details on incoming message."""
        now = datetime.now(timezone.utc)
        update_doc: Dict[str, Any] = {
            "$set": {
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "updated_at": now,
            },
            "$setOnInsert": {
                "telegram_user_id": telegram_user_id,
                "is_active": True,
                "is_admin": is_admin if is_admin is not None else False,
                "created_at": now,
            },
        }

        if is_admin is not None:
            update_doc["$set"]["is_admin"] = is_admin

        doc = await self.collection.find_one_and_update(
            {"telegram_user_id": telegram_user_id},
            update_doc,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)  # type: ignore

    async def list_users(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_desc: bool = True,
    ) -> List[Dict[str, Any]]:
        """Paginated list of users (Admin)."""
        limit_val, offset_val = self.sanitize_pagination(limit, offset)
        sort_spec = self.sanitize_sort(sort_by, sort_desc, self.ALLOWED_SORT_FIELDS)

        cursor = self.collection.find({}).sort(sort_spec).skip(offset_val).limit(limit_val)
        docs = [doc async for doc in cursor]
        return self.format_docs(docs)

    async def set_active_status(self, telegram_user_id: int, is_active: bool) -> Optional[Dict[str, Any]]:
        """Update account active status."""
        doc = await self.collection.find_one_and_update(
            {"telegram_user_id": telegram_user_id},
            {"$set": {"is_active": is_active, "updated_at": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def count_users(self) -> int:
        """Return total registered users."""
        return await self.collection.count_documents({})
