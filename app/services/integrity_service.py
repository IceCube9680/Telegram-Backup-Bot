"""Data referential integrity audit and repair service across MongoDB collections."""

from typing import Any, Dict, List, Optional, Set
from bson import ObjectId
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import get_logger
from app.database.models.backup_item import ItemStatus
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.backup_task_repo import BackupTaskRepository
from app.database.repositories.folder_repo import FolderRepository
from app.database.repositories.storage_usage_repo import StorageUsageRepository
from app.database.repositories.tag_repo import TagRepository
from app.database.repositories.user_repo import UserRepository

logger = get_logger(__name__)


class IntegrityReport(BaseModel):
    """Structured report of referential consistency checks across MongoDB collections."""

    total_items_checked: int = Field(default=0, description="Total backup items scanned")
    total_folders_checked: int = Field(default=0, description="Total folders scanned")
    total_tags_checked: int = Field(default=0, description="Total tags scanned")
    total_users_checked: int = Field(default=0, description="Total users scanned")

    dangling_folder_refs: List[str] = Field(
        default_factory=list,
        description="BackupItems pointing to non-existent folder IDs",
    )
    orphaned_item_tags: List[str] = Field(
        default_factory=list,
        description="ItemTag associations pointing to non-existent items or tags",
    )
    missing_storage_usage_users: List[int] = Field(
        default_factory=list,
        description="User records missing corresponding StorageUsage document",
    )
    ambiguous_anomalies: List[str] = Field(
        default_factory=list,
        description="Complex or ambiguous state anomalies reported for admin review (never auto-deleted)",
    )

    repaired_count: int = Field(default=0, description="Number of safe fixes applied during repair mode")
    is_clean: bool = Field(default=True, description="True if no anomalies or dangling references found")


class DataIntegrityService:
    """Service for checking referential integrity between MongoDB collections."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.item_repo = BackupItemRepository(db)
        self.task_repo = BackupTaskRepository(db)
        self.folder_repo = FolderRepository(db)
        self.tag_repo = TagRepository(db)
        self.usage_repo = StorageUsageRepository(db)
        self.user_repo = UserRepository(db)

    async def check_integrity(self, repair: bool = False) -> IntegrityReport:
        """Audit database referential integrity.

        Args:
            repair: If True, automatically fix safe dangling references (e.g. unassigning
                    non-existent folders, purging orphaned item-tag joins, initializing missing
                    storage usage docs). Ambiguous anomalies are ALWAYS reported only and never deleted.
        """
        report = IntegrityReport()
        repaired_count = 0

        # 1. Audit Users & StorageUsage
        users = await self.user_repo.collection.find({}).to_list(length=None)
        report.total_users_checked = len(users)

        for user in users:
            uid = user.get("telegram_user_id")
            if uid:
                usage_doc = await self.usage_repo.collection.find_one({"user_id": uid})
                if not usage_doc:
                    report.missing_storage_usage_users.append(uid)
                    if repair:
                        await self.usage_repo.set_usage(user_id=uid, file_count=0, total_bytes=0)
                        repaired_count += 1
                        logger.info(f"[integrity_repair] Initialized missing StorageUsage for user {uid}")

        # 2. Audit BackupItems ↔ Folders
        items = await self.item_repo.collection.find({}).to_list(length=None)
        report.total_items_checked = len(items)

        # Build set of all existing folder IDs
        folders = await self.folder_repo.collection.find({}).to_list(length=None)
        report.total_folders_checked = len(folders)
        valid_folder_ids: Set[str] = {str(f["_id"]) for f in folders}

        for item in items:
            folder_id = item.get("folder_id")
            item_id = str(item["_id"])
            user_id = item.get("user_id")

            if folder_id:
                if str(folder_id) not in valid_folder_ids:
                    msg = f"Item {item_id} (user {user_id}) references non-existent folder_id '{folder_id}'"
                    report.dangling_folder_refs.append(msg)
                    if repair:
                        # Safe fix: unassign deleted folder from item
                        await self.item_repo.collection.update_one(
                            {"_id": item["_id"]},
                            {"$set": {"folder_id": None}},
                        )
                        repaired_count += 1
                        logger.info(f"[integrity_repair] Unassigned missing folder_id '{folder_id}' from item {item_id}")

        # 3. Audit ItemTags ↔ Tags and BackupItems
        tags = await self.tag_repo.collection.find({}).to_list(length=None)
        report.total_tags_checked = len(tags)
        valid_tag_ids: Set[str] = {str(t["_id"]) for t in tags}
        valid_item_ids: Set[str] = {str(i["_id"]) for i in items}

        item_tags = await self.tag_repo.item_tags_collection.find({}).to_list(length=None)
        for it in item_tags:
            it_id = str(it["_id"])
            b_item_id = str(it.get("backup_item_id"))
            t_id = str(it.get("tag_id"))

            is_orphaned = False
            reasons = []
            if b_item_id not in valid_item_ids:
                is_orphaned = True
                reasons.append(f"item '{b_item_id}' missing")
            if t_id not in valid_tag_ids:
                is_orphaned = True
                reasons.append(f"tag '{t_id}' missing")

            if is_orphaned:
                msg = f"ItemTag {it_id} references non-existent: {', '.join(reasons)}"
                report.orphaned_item_tags.append(msg)
                if repair:
                    await self.tag_repo.item_tags_collection.delete_one({"_id": it["_id"]})
                    repaired_count += 1
                    logger.info(f"[integrity_repair] Removed orphaned ItemTag {it_id}")

        # 4. Audit Pending/Processing BackupItems ↔ BackupTasks (Ambiguous check - NEVER delete)
        for item in items:
            item_id = str(item["_id"])
            status = item.get("status")
            user_id = item.get("user_id")

            if status in (ItemStatus.PENDING.value, ItemStatus.PROCESSING.value):
                tasks = await self.task_repo.collection.find(
                    {"backup_item_id": item_id, "user_id": user_id}
                ).to_list(length=None)

                if not tasks:
                    # Item is marked pending/processing but has no task record
                    report.ambiguous_anomalies.append(
                        f"Item {item_id} has status='{status}' but no associated BackupTask exists in database."
                    )
                elif len(tasks) > 1:
                    # Multiple tasks for same item
                    report.ambiguous_anomalies.append(
                        f"Item {item_id} has {len(tasks)} duplicate BackupTask records in database."
                    )

        report.repaired_count = repaired_count
        report.is_clean = (
            len(report.dangling_folder_refs) == 0
            and len(report.orphaned_item_tags) == 0
            and len(report.missing_storage_usage_users) == 0
            and len(report.ambiguous_anomalies) == 0
        )

        return report
