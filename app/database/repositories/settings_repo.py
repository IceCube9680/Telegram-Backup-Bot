"""User Settings repository."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.database.models.settings import UserSettingsModel
from app.database.repositories.base import BaseRepository


class SettingsRepository(BaseRepository):
    """Repository for UserSettings document operations."""

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, "user_settings")

    async def get_or_create_settings(self, user_id: int) -> Dict[str, Any]:
        """Fetch user settings or initialize defaults with atomic upsert."""
        now = datetime.now(timezone.utc)
        default_model = UserSettingsModel(user_id=user_id)
        default_doc = default_model.to_doc()

        doc = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {"$setOnInsert": default_doc},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)  # type: ignore

    async def update_settings(
        self,
        user_id: int,
        auto_backup: Optional[bool] = None,
        duplicate_detection: Optional[bool] = None,
        default_folder_id: Optional[str] = None,
        max_file_size: Optional[int] = None,
        notifications_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update specific settings for a user with ownership enforcement."""
        update_fields: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if auto_backup is not None:
            update_fields["auto_backup"] = auto_backup
        if duplicate_detection is not None:
            update_fields["duplicate_detection"] = duplicate_detection
        if default_folder_id is not None:
            update_fields["default_folder_id"] = default_folder_id
        if max_file_size is not None:
            update_fields["max_file_size"] = max_file_size
        if notifications_enabled is not None:
            update_fields["notifications_enabled"] = notifications_enabled

        doc = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {"$set": update_fields},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)  # type: ignore
