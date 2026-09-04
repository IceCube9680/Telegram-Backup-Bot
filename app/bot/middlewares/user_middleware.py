"""User registration and dependency injection middleware for aiogram."""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import get_logger
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.backup_task_repo import BackupTaskRepository
from app.database.repositories.folder_repo import FolderRepository
from app.database.repositories.settings_repo import SettingsRepository
from app.database.repositories.storage_usage_repo import StorageUsageRepository
from app.database.repositories.tag_repo import TagRepository
from app.database.repositories.user_repo import UserRepository
from app.services.backup_service import BackupService

logger = get_logger(__name__)


class UserMiddleware(BaseMiddleware):
    """Middleware to automatically register/update Telegram users and inject services."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.item_repo = BackupItemRepository(db)
        self.task_repo = BackupTaskRepository(db)
        self.folder_repo = FolderRepository(db)
        self.tag_repo = TagRepository(db)
        self.settings_repo = SettingsRepository(db)
        self.storage_usage_repo = StorageUsageRepository(db)
        self.backup_service = BackupService(db)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Process update, upsert user, and inject repositories."""
        telegram_user: Optional[User] = data.get("event_from_user")

        user_doc: Optional[Dict[str, Any]] = None
        if telegram_user:
            try:
                user_doc = await self.user_repo.upsert_user(
                    telegram_user_id=telegram_user.id,
                    first_name=telegram_user.first_name,
                    last_name=telegram_user.last_name,
                    username=telegram_user.username,
                )
            except Exception as e:
                logger.error(f"Error registering/updating user {telegram_user.id}: {e}")

        # Inject context dependencies into handler data
        data["db"] = self.db
        data["user"] = user_doc
        data["user_repo"] = self.user_repo
        data["item_repo"] = self.item_repo
        data["task_repo"] = self.task_repo
        data["folder_repo"] = self.folder_repo
        data["tag_repo"] = self.tag_repo
        data["settings_repo"] = self.settings_repo
        data["storage_usage_repo"] = self.storage_usage_repo
        data["backup_service"] = self.backup_service

        return await handler(event, data)
