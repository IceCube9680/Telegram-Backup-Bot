"""Backup orchestration service for validating and enqueuing Telegram media backups."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.database.models.backup_item import BackupItemModel, ItemStatus
from app.database.models.backup_task import BackupTaskModel, TaskStatus, TaskType
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.backup_task_repo import BackupTaskRepository
from app.database.repositories.settings_repo import SettingsRepository
from app.database.repositories.user_repo import UserRepository
from app.services.telegram_media_service import TelegramMediaInfo

logger = get_logger(__name__)


class BackupResult(BaseModel):
    """Result summary of an enqueued backup task."""

    task_id: str = Field(..., description="Unique task identifier")
    item_id: str = Field(..., description="Unique backup item identifier")
    original_filename: str = Field(..., description="Normalized display filename")
    file_size_formatted: str = Field(..., description="Human-readable file size string")
    media_type: str = Field(..., description="Media category")
    is_duplicate: bool = Field(default=False, description="True if update was already processed")


def format_bytes(size: Optional[int]) -> str:
    """Format byte size into human readable string (KB, MB, GB)."""
    if size is None or size <= 0:
        return "Unknown size"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024.0
    return "0 B"


class BackupService:
    """Orchestrates validation, BackupItem creation, and BackupTask queueing."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.item_repo = BackupItemRepository(db)
        self.task_repo = BackupTaskRepository(db)
        self.settings_repo = SettingsRepository(db)

    async def enqueue_backup(
        self,
        media_info: TelegramMediaInfo,
        user_data: Optional[Dict[str, Any]] = None,
    ) -> BackupResult:
        """Validate incoming media, enforce quotas, and atomically enqueue backup item and task."""
        user_id = media_info.user_id

        # 1. User active status validation
        if user_data and not user_data.get("is_active", True):
            logger.warning(f"Rejected backup for inactive user {user_id}")
            raise ValidationError(
                message="Your account is currently disabled. Please contact the administrator.",
                details={"user_id": user_id},
            )

        # 2. Settings and max file size quota validation
        user_settings = await self.settings_repo.get_or_create_settings(user_id)
        max_size = user_settings.get("max_file_size", 4294967296)

        # Exact 4 GiB hard platform limit (4,294,967,296 bytes)
        HARD_LIMIT_4_GIB = 4294967296
        if media_info.file_size is not None:
            if media_info.file_size < 0:
                raise ValidationError(
                    message="Invalid negative file size.",
                    details={"file_size": media_info.file_size},
                )
            if media_info.file_size > HARD_LIMIT_4_GIB:
                file_formatted = format_bytes(media_info.file_size)
                raise ValidationError(
                    message=f"File size ({file_formatted}) exceeds maximum supported limit of 4 GiB (4,294,967,296 bytes).",
                    details={"file_size": media_info.file_size, "max_allowed": HARD_LIMIT_4_GIB},
                )
            if media_info.file_size > max_size:
                max_formatted = format_bytes(max_size)
                file_formatted = format_bytes(media_info.file_size)
                logger.warning(
                    f"Rejected oversized file for user {user_id}: {file_formatted} > limit {max_formatted}"
                )
                raise ValidationError(
                    message=f"File size ({file_formatted}) exceeds your allowed limit of {max_formatted}.",
                    details={"file_size": media_info.file_size, "max_allowed": max_size},
                )

        # 3. Idempotency verification: check if this message was already enqueued
        existing_item = await self.item_repo.get_by_message_id(
            user_id=user_id,
            telegram_message_id=media_info.telegram_message_id,
        )
        if existing_item:
            logger.info(
                f"Duplicate Telegram update received for user {user_id}, msg {media_info.telegram_message_id}"
            )
            # Find associated task or return duplicate result
            task_doc = await self.task_repo.collection.find_one({"backup_item_id": existing_item["id"]})
            task_id = str(task_doc["_id"]) if task_doc else existing_item["id"]
            return BackupResult(
                task_id=task_id,
                item_id=existing_item["id"],
                original_filename=existing_item.get("original_filename", media_info.original_filename),
                file_size_formatted=format_bytes(existing_item.get("file_size")),
                media_type=existing_item.get("media_type", media_info.media_type.value),
                is_duplicate=True,
            )

        # 4. Determine initial transfer method
        transfer_method = "mtproto" if (media_info.file_size and media_info.file_size > 20 * 1024 * 1024) else "bot_api"

        # 5. Create BackupItem
        default_folder_id = user_settings.get("default_folder_id")
        item_model = BackupItemModel(
            user_id=user_id,
            chat_id=media_info.chat_id,
            telegram_message_id=media_info.telegram_message_id,
            telegram_file_id=media_info.file_id,
            telegram_file_unique_id=media_info.file_unique_id,
            media_type=media_info.media_type,
            original_filename=media_info.original_filename,
            mime_type=media_info.mime_type,
            file_size=media_info.file_size,
            caption=media_info.caption,
            transfer_method=transfer_method,
            folder_id=default_folder_id,
            status=ItemStatus.PENDING,
        )

        try:
            created_item = await self.item_repo.create_item(item_model)
        except DuplicateKeyError:
            # Race condition duplicate check
            existing = await self.item_repo.get_by_message_id(user_id, media_info.telegram_message_id)
            return BackupResult(
                task_id=existing["id"] if existing else "duplicate",
                item_id=existing["id"] if existing else "duplicate",
                original_filename=media_info.original_filename,
                file_size_formatted=format_bytes(media_info.file_size),
                media_type=media_info.media_type.value,
                is_duplicate=True,
            )

        item_id = created_item["id"]

        # 5. Create BackupTask
        task_model = BackupTaskModel(
            user_id=user_id,
            backup_item_id=item_id,
            task_type=TaskType.DOWNLOAD_AND_STORE,
            status=TaskStatus.PENDING,
            progress=0.0,
            attempts=0,
        )
        created_task = await self.task_repo.create_task(task_model)
        task_id = created_task["id"]

        logger.info(
            f"Successfully queued backup task {task_id} for item {item_id} (user={user_id}, file='{media_info.original_filename}')"
        )

        return BackupResult(
            task_id=task_id,
            item_id=item_id,
            original_filename=media_info.original_filename,
            file_size_formatted=format_bytes(media_info.file_size),
            media_type=media_info.media_type.value,
            is_duplicate=False,
        )
