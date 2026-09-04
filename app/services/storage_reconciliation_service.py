"""Storage reconciliation service for comparing MongoDB backup records with physical storage."""

import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.database.models.backup_item import ItemStatus
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.storage_usage_repo import StorageUsageRepository
from app.database.repositories.user_repo import UserRepository
from app.services.storage_service import LocalStorageService, StorageService, get_storage_service

logger = get_logger(__name__)


class StorageReconciliationReport(BaseModel):
    """Detailed reconciliation report for a single user or entire system."""

    user_id: int = Field(..., description="Target Telegram user ID")
    total_db_items: int = Field(default=0, description="Active completed items in MongoDB")
    total_physical_files: int = Field(default=0, description="Physical files located on disk")
    missing_files: List[str] = Field(default_factory=list, description="DB items missing physical storage files")
    orphan_files: List[str] = Field(default_factory=list, description="Physical files with no matching DB record")
    db_usage_bytes: int = Field(default=0, description="Usage recorded in StorageUsage collection")
    calculated_items_bytes: int = Field(default=0, description="Authoritative sum of active item file sizes")
    physical_disk_bytes: int = Field(default=0, description="Sum of physical file sizes on disk")
    usage_mismatch: bool = Field(default=False, description="True if StorageUsage does not match active items sum")
    repaired_usage: bool = Field(default=False, description="True if StorageUsage accounting was repaired")
    deleted_orphans_count: int = Field(default=0, description="Number of orphan files deleted in repair mode")


class StorageReconciliationService:
    """Production service for validating and repairing storage consistency between MongoDB and disk."""

    def __init__(
        self,
        db: AsyncDatabase,
        storage_service: Optional[StorageService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.storage = storage_service or get_storage_service()
        self.item_repo = BackupItemRepository(db)
        self.usage_repo = StorageUsageRepository(db)
        self.user_repo = UserRepository(db)

    async def reconcile_user(
        self,
        user_id: int,
        repair: bool = False,
        delete_orphans: bool = False,
        confirm: bool = False,
    ) -> StorageReconciliationReport:
        """Reconcile storage for a specific user.

        Args:
            user_id: The Telegram user ID.
            repair: If True, reconcile StorageUsage collection to authoritative item sum.
            delete_orphans: If True and confirm=True, delete confirmed orphan files on disk.
            confirm: Explicit confirmation required for destructive orphan deletion.
        """
        # 1. Load all active completed items for user from MongoDB
        cursor = self.item_repo.collection.find(
            {
                "user_id": user_id,
                "status": ItemStatus.COMPLETED.value,
                "deleted_at": None,
            }
        )
        db_items: List[Dict[str, Any]] = await cursor.to_list(length=None)

        db_storage_keys: Set[str] = set()
        calculated_bytes = 0
        missing_files: List[str] = []

        for doc in db_items:
            key = doc.get("storage_key")
            size = doc.get("file_size") or 0
            calculated_bytes += size

            if key:
                db_storage_keys.add(key)
                # Verify physical existence
                if not await self.storage.exists(key):
                    missing_files.append(key)
            else:
                # Completed item missing storage_key
                missing_files.append(f"item_{doc.get('_id')}_no_key")

        # 2. Inspect physical files on disk under users/{user_id}/
        user_storage_dir = Path(self.settings.STORAGE_PATH).resolve() / "users" / str(user_id)
        physical_files: List[Path] = []
        physical_keys: Set[str] = set()
        physical_bytes = 0

        if await asyncio.to_thread(user_storage_dir.exists):

            def _scan_disk() -> Tuple[List[Path], Set[str], int]:
                files: List[Path] = []
                keys: Set[str] = []
                total_b = 0
                for root, _, filenames in os.walk(user_storage_dir):
                    for fname in filenames:
                        full_p = Path(root) / fname
                        try:
                            # Relative key inside STORAGE_PATH: users/{user_id}/...
                            rel_key = full_p.relative_to(Path(self.settings.STORAGE_PATH).resolve()).as_posix()
                            files.append(full_p)
                            keys.append(rel_key)
                            total_b += full_p.stat().st_size
                        except Exception as e:
                            logger.warning(f"Error scanning file {full_p}: {e}")
                return files, set(keys), total_b

            physical_files, physical_keys, physical_bytes = await asyncio.to_thread(_scan_disk)

        # 3. Find orphan physical files (files on disk not in DB)
        orphan_keys: List[str] = sorted(list(physical_keys - db_storage_keys))

        # 4. Fetch DB StorageUsage record
        usage_doc = await self.usage_repo.get_usage(user_id)
        db_usage_bytes = usage_doc.get("total_size", 0)
        usage_mismatch = (db_usage_bytes != calculated_bytes) or (usage_doc.get("file_count", 0) != len(db_items))

        repaired_usage = False
        deleted_orphans_count = 0

        # 5. Handle Repair Mode
        if repair:
            # A. Fix StorageUsage accounting if mismatched
            if usage_mismatch:
                await self.usage_repo.set_usage(
                    user_id=user_id,
                    file_count=len(db_items),
                    total_bytes=calculated_bytes,
                )
                repaired_usage = True
                logger.info(
                    f"[reconciliation_repair] Reconciled StorageUsage for user {user_id}: files={len(db_items)}, bytes={calculated_bytes}"
                )

            # B. Extremely conservative orphan file deletion
            if delete_orphans and confirm:
                for orphan_key in orphan_keys:
                    # Double check path safety: must be strictly inside users/{user_id}/
                    orphan_path = (Path(self.settings.STORAGE_PATH).resolve() / orphan_key).resolve()
                    if user_storage_dir in orphan_path.parents or orphan_path.parent == user_storage_dir:
                        try:
                            await asyncio.to_thread(orphan_path.unlink, missing_ok=True)
                            deleted_orphans_count += 1
                            logger.info(f"[reconciliation_orphan_deleted] Deleted orphan physical file: {orphan_key}")
                        except Exception as de:
                            logger.warning(f"Failed to delete orphan file {orphan_key}: {de}")
                    else:
                        logger.error(
                            f"Safety violation: orphan path '{orphan_path}' is outside user directory '{user_storage_dir}'. Skipped."
                        )

        return StorageReconciliationReport(
            user_id=user_id,
            total_db_items=len(db_items),
            total_physical_files=len(physical_files),
            missing_files=missing_files,
            orphan_files=orphan_keys,
            db_usage_bytes=db_usage_bytes,
            calculated_items_bytes=calculated_bytes,
            physical_disk_bytes=physical_bytes,
            usage_mismatch=usage_mismatch,
            repaired_usage=repaired_usage,
            deleted_orphans_count=deleted_orphans_count,
        )

    async def reconcile_all(
        self,
        repair: bool = False,
        delete_orphans: bool = False,
        confirm: bool = False,
    ) -> List[StorageReconciliationReport]:
        """Reconcile storage across all registered users and on-disk user storage directories."""
        # Discover all user IDs from users collection
        user_ids_db = await self.user_repo.collection.distinct("telegram_user_id")
        user_ids: Set[int] = set(int(uid) for uid in user_ids_db if uid is not None)

        # Discover all user directories under storage/users/
        users_dir = Path(self.settings.STORAGE_PATH).resolve() / "users"
        if await asyncio.to_thread(users_dir.exists):

            def _scan_user_dirs() -> Set[int]:
                found = set()
                for item in users_dir.iterdir():
                    if item.is_dir() and item.name.isdigit():
                        found.add(int(item.name))
                return found

            disk_user_ids = await asyncio.to_thread(_scan_user_dirs)
            user_ids.update(disk_user_ids)

        reports: List[StorageReconciliationReport] = []
        for uid in sorted(list(user_ids)):
            report = await self.reconcile_user(
                user_id=uid,
                repair=repair,
                delete_orphans=delete_orphans,
                confirm=confirm,
            )
            reports.append(report)

        return reports
