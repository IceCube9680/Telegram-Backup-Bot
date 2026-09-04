"""Backup management service for file browsing, details, safe deletion, retry, and statistics."""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.models.backup_item import ItemStatus, MediaType
from app.database.models.backup_task import TaskStatus
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.backup_task_repo import BackupTaskRepository
from app.database.repositories.folder_repo import FolderRepository
from app.database.repositories.storage_usage_repo import StorageUsageRepository
from app.database.repositories.tag_repo import TagRepository
from app.services.storage_service import StorageService, get_storage_service

logger = get_logger(__name__)


class PaginatedFilesResult(BaseModel):
    """Paginated list of backup items."""

    items: List[Dict[str, Any]] = Field(default_factory=list, description="List of file records")
    total: int = Field(..., ge=0, description="Total active files matching filter")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total pages")


class FileDetails(BaseModel):
    """Detailed metadata for a single backed-up item."""

    item_id: str = Field(..., description="Unique BackupItem ID")
    original_filename: str = Field(..., description="Display filename")
    media_type: str = Field(..., description="Categorized media type")
    file_size: Optional[int] = Field(default=None, description="Size in bytes")
    mime_type: Optional[str] = Field(default=None, description="MIME content type")
    caption: Optional[str] = Field(default=None, description="Message caption if provided")
    transfer_method: Optional[str] = Field(default="bot_api", description="Transfer provider method")
    status: str = Field(..., description="Processing status")
    created_at: datetime = Field(..., description="Upload timestamp")
    sha256_short: Optional[str] = Field(default=None, description="Shortened display SHA-256")
    folder_id: Optional[str] = Field(default=None, description="Folder ID")
    folder_name: Optional[str] = Field(default=None, description="Display folder name")
    tags: List[str] = Field(default_factory=list, description="Attached tag names")
    task_progress: Optional[float] = Field(default=None, description="Progress percentage if in-progress")
    task_error: Optional[str] = Field(default=None, description="Error reason if failed")


class DeleteResult(BaseModel):
    """Result of file deletion operation."""

    success: bool = Field(..., description="True if deletion succeeded")
    item_id: str = Field(..., description="Item ID")
    filename: str = Field(..., description="Deleted filename")
    file_size: Optional[int] = Field(default=None, description="Freed size in bytes")
    storage_deleted: bool = Field(default=False, description="True if physical storage file was deleted")
    message: str = Field(..., description="Human-readable outcome summary")


class RetryResult(BaseModel):
    """Result of retrying a failed backup task."""

    success: bool = Field(..., description="True if task was re-queued")
    task_id: str = Field(..., description="Task ID")
    item_id: str = Field(..., description="Item ID")
    message: str = Field(..., description="Human-readable message")


class UserStatsResult(BaseModel):
    """Cumulative and breakdown statistics for user's backups."""

    user_id: int = Field(..., description="Telegram user ID")
    total_files: int = Field(..., ge=0, description="Total active files")
    total_size_bytes: int = Field(..., ge=0, description="Total stored bytes")
    completed_count: int = Field(default=0, ge=0, description="Completed backups")
    processing_count: int = Field(default=0, ge=0, description="Processing backups")
    pending_count: int = Field(default=0, ge=0, description="Pending queue backups")
    failed_count: int = Field(default=0, ge=0, description="Failed backups")


class BackupManagementService:
    """Service for browsing, inspecting, deleting, retrying, and auditing user backups."""

    def __init__(
        self,
        db: AsyncDatabase,
        storage_service: Optional[StorageService] = None,
    ) -> None:
        self.db = db
        self.item_repo = BackupItemRepository(db)
        self.task_repo = BackupTaskRepository(db)
        self.folder_repo = FolderRepository(db)
        self.tag_repo = TagRepository(db)
        self.usage_repo = StorageUsageRepository(db)
        self.storage = storage_service or get_storage_service()

    async def list_user_files(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 10,
        folder_id: Optional[str] = None,
        media_type: Optional[MediaType] = None,
        status: Optional[ItemStatus] = None,
    ) -> PaginatedFilesResult:
        """Retrieve paginated active files scoped strictly to the user."""
        safe_page = max(1, page)
        safe_size = min(100, max(1, page_size))
        offset = (safe_page - 1) * safe_size

        items = await self.item_repo.list_items(
            user_id=user_id,
            folder_id=folder_id,
            media_type=media_type,
            status=status,
            limit=safe_size,
            offset=offset,
            include_deleted=False,
        )

        total = await self.item_repo.count_items(
            user_id=user_id,
            folder_id=folder_id,
            media_type=media_type,
            status=status,
            include_deleted=False,
        )

        total_pages = math.ceil(total / safe_size) if total > 0 else 0

        return PaginatedFilesResult(
            items=items,
            total=total,
            page=safe_page,
            page_size=safe_size,
            total_pages=total_pages,
        )

    async def get_file_details(self, user_id: int, item_id: str) -> Optional[FileDetails]:
        """Fetch full details for a backup item verifying ownership."""
        item = await self.item_repo.get_by_id(user_id=user_id, item_id=item_id, include_deleted=False)
        if not item:
            return None

        # Resolve folder name if assigned
        folder_name: Optional[str] = None
        if item.get("folder_id"):
            folder_doc = await self.folder_repo.get_by_id(user_id=user_id, folder_id=item["folder_id"])
            if folder_doc:
                folder_name = folder_doc.get("name")

        # Resolve tags
        tags_docs = await self.tag_repo.get_tags_for_item(user_id=user_id, item_id=item_id)
        tag_names = [t.get("name", "") for t in tags_docs if t.get("name")]

        # Resolve task status and progress if applicable
        task_doc = await self.task_repo.collection.find_one({"backup_item_id": item_id, "user_id": user_id})
        task_progress = task_doc.get("progress") if task_doc else None
        task_error = task_doc.get("error_message") if task_doc else None

        sha256 = item.get("sha256")
        sha256_short = f"{sha256[:12]}..." if sha256 else None

        return FileDetails(
            item_id=item["id"],
            original_filename=item.get("original_filename") or "Unnamed File",
            media_type=item.get("media_type") or "file",
            file_size=item.get("file_size"),
            mime_type=item.get("mime_type"),
            caption=item.get("caption"),
            transfer_method=item.get("transfer_method") or "bot_api",
            status=item.get("status") or "pending",
            created_at=item.get("created_at") or datetime.now(timezone.utc),
            sha256_short=sha256_short,
            folder_id=item.get("folder_id"),
            folder_name=folder_name,
            tags=tag_names,
            task_progress=task_progress,
            task_error=task_error,
        )

    async def delete_file(self, user_id: int, item_id: str) -> DeleteResult:
        """Safely delete a backup file: soft-delete MongoDB record, delete storage object, decrement usage."""
        item = await self.item_repo.get_by_id(user_id=user_id, item_id=item_id, include_deleted=False)
        if not item:
            raise ResourceNotFoundError(
                "File not found or already deleted",
                details={"item_id": item_id, "user_id": user_id},
            )

        filename = item.get("original_filename") or "Unnamed File"
        file_size = item.get("file_size") or 0
        storage_key = item.get("storage_key")
        is_completed = item.get("status") == ItemStatus.COMPLETED.value

        # 1. Soft-delete item in database
        soft_deleted = await self.item_repo.soft_delete(user_id=user_id, item_id=item_id)
        if not soft_deleted:
            raise ResourceNotFoundError("Failed to soft-delete item or item was already deleted")

        # 2. Delete physical storage object if it exists
        storage_deleted = False
        if storage_key and is_completed:
            try:
                storage_deleted = await self.storage.delete(storage_key)
            except Exception as se:
                logger.warning(f"Storage deletion encountered error for key '{storage_key}': {se}")

        # 3. Atomically decrement user storage accounting (only if item was completed with physical size)
        if is_completed and file_size > 0:
            await self.usage_repo.decrement_usage(
                user_id=user_id,
                file_count=1,
                total_bytes=file_size,
            )

        # 4. Clean up any attached tags for this item
        await self.tag_repo.item_tags_collection.delete_many({"backup_item_id": item_id})

        logger.info(f"Successfully deleted backup item {item_id} (user={user_id}, size={file_size})")

        return DeleteResult(
            success=True,
            item_id=item_id,
            filename=filename,
            file_size=file_size,
            storage_deleted=storage_deleted,
            message=f"Successfully deleted '{filename}'.",
        )

    async def retry_failed_task(self, user_id: int, item_id: str) -> RetryResult:
        """Re-queue a failed backup task for execution with user ownership verification."""
        item = await self.item_repo.get_by_id(user_id=user_id, item_id=item_id, include_deleted=False)
        if not item:
            raise ResourceNotFoundError(
                "Backup item not found or deleted",
                details={"item_id": item_id, "user_id": user_id},
            )

        task_doc = await self.task_repo.collection.find_one({"backup_item_id": item_id, "user_id": user_id})
        if not task_doc:
            raise ResourceNotFoundError("Associated task record not found for this backup item")

        status = task_doc.get("status")
        if status == TaskStatus.COMPLETED.value:
            raise ValidationError("Backup is already completed and cannot be retried")

        if status == TaskStatus.PROCESSING.value:
            raise ValidationError("Backup is currently being processed by a worker")

        # Reset task to pending with attempt budget reset
        now = datetime.now(timezone.utc)
        await self.task_repo.collection.update_one(
            {"_id": task_doc["_id"]},
            {
                "$set": {
                    "status": TaskStatus.PENDING.value,
                    "error_message": None,
                    "worker_id": None,
                    "locked_at": None,
                    "started_at": None,
                    "completed_at": None,
                    "progress": 0.0,
                    "attempts": 0,
                    "updated_at": now,
                }
            },
        )

        # Reset item status to pending
        await self.item_repo.update_status(user_id, item_id, ItemStatus.PENDING)

        task_id = str(task_doc["_id"])
        logger.info(f"User {user_id} re-queued failed backup task {task_id} for item {item_id}")

        return RetryResult(
            success=True,
            task_id=task_id,
            item_id=item_id,
            message="Backup has been re-queued for processing.",
        )

    async def get_user_stats(self, user_id: int) -> UserStatsResult:
        """Fetch cumulative storage accounting and active items breakdown by status."""
        usage = await self.usage_repo.get_usage(user_id)

        completed_count = await self.item_repo.count_items(
            user_id=user_id, status=ItemStatus.COMPLETED, include_deleted=False
        )
        processing_count = await self.item_repo.count_items(
            user_id=user_id, status=ItemStatus.PROCESSING, include_deleted=False
        )
        pending_count = await self.item_repo.count_items(
            user_id=user_id, status=ItemStatus.PENDING, include_deleted=False
        )
        failed_count = await self.item_repo.count_items(
            user_id=user_id, status=ItemStatus.FAILED, include_deleted=False
        )

        total_active_files = completed_count + processing_count + pending_count + failed_count

        return UserStatsResult(
            user_id=user_id,
            total_files=total_active_files,
            total_size_bytes=usage.get("total_size", 0),
            completed_count=completed_count,
            processing_count=processing_count,
            pending_count=pending_count,
            failed_count=failed_count,
        )
