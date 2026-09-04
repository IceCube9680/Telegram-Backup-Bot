"""Backup Item repository with user ownership isolation, soft delete, and deduplication lookups."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.database.models.backup_item import BackupItemModel, ItemStatus, MediaType
from app.database.repositories.base import BaseRepository


class BackupItemRepository(BaseRepository):
    """Repository for managing BackupItem documents."""

    ALLOWED_SORT_FIELDS: Set[str] = {
        "created_at",
        "updated_at",
        "file_size",
        "original_filename",
        "media_type",
    }

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, "backup_items")

    async def create_item(self, item: BackupItemModel) -> Dict[str, Any]:
        """Insert a new backup item record."""
        doc = item.to_doc()
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        if "_id" in doc:
            del doc["_id"]
        return doc

    async def get_by_message_id(
        self,
        user_id: int,
        telegram_message_id: int,
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find an item by Telegram message ID scoped to the user (for update idempotency)."""
        query: Dict[str, Any] = {"user_id": user_id, "telegram_message_id": telegram_message_id}
        if not include_deleted:
            query["deleted_at"] = None
        doc = await self.collection.find_one(query)
        return self.format_doc(doc)

    async def get_by_id(
        self,
        user_id: int,
        item_id: str,
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find a backup item by ID enforcing user ownership and soft-delete filtering."""
        obj_id = self.validate_object_id(item_id, "item_id")
        query: Dict[str, Any] = {"_id": obj_id, "user_id": user_id}
        if not include_deleted:
            query["deleted_at"] = None

        doc = await self.collection.find_one(query)
        return self.format_doc(doc)

    async def find_by_sha256(
        self,
        user_id: int,
        sha256: str,
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find an existing item by SHA-256 hash strictly scoped to the user (for deduplication)."""
        if not sha256:
            return None
        query: Dict[str, Any] = {
            "user_id": user_id,
            "sha256": sha256,
            "status": ItemStatus.COMPLETED.value,
        }
        if not include_deleted:
            query["deleted_at"] = None

        doc = await self.collection.find_one(query)
        return self.format_doc(doc)

    async def update_storage_info(
        self,
        user_id: int,
        item_id: str,
        storage_key: str,
        sha256: str,
        file_size: int,
        mime_type: Optional[str] = None,
        original_filename: Optional[str] = None,
        transfer_method: Optional[str] = None,
        status: ItemStatus = ItemStatus.COMPLETED,
    ) -> Optional[Dict[str, Any]]:
        """Update file storage details after worker completion with user ownership check."""
        obj_id = self.validate_object_id(item_id, "item_id")
        now = datetime.now(timezone.utc)
        update_fields: Dict[str, Any] = {
            "storage_key": storage_key,
            "sha256": sha256,
            "file_size": file_size,
            "status": status.value,
            "updated_at": now,
        }
        if mime_type:
            update_fields["mime_type"] = mime_type
        if original_filename:
            update_fields["original_filename"] = original_filename
        if transfer_method:
            update_fields["transfer_method"] = transfer_method

        doc = await self.collection.find_one_and_update(
            {"_id": obj_id, "user_id": user_id},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def update_status(
        self,
        user_id: int,
        item_id: str,
        status: ItemStatus,
    ) -> Optional[Dict[str, Any]]:
        """Update processing status for a backup item."""
        obj_id = self.validate_object_id(item_id, "item_id")
        doc = await self.collection.find_one_and_update(
            {"_id": obj_id, "user_id": user_id},
            {
                "$set": {
                    "status": status.value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def update_folder(
        self,
        user_id: int,
        item_id: str,
        folder_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Move item to a folder or root."""
        obj_id = self.validate_object_id(item_id, "item_id")
        doc = await self.collection.find_one_and_update(
            {"_id": obj_id, "user_id": user_id},
            {
                "$set": {
                    "folder_id": folder_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def soft_delete(self, user_id: int, item_id: str) -> Optional[Dict[str, Any]]:
        """Soft delete item by recording deleted_at timestamp with user ownership check."""
        obj_id = self.validate_object_id(item_id, "item_id")
        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {"_id": obj_id, "user_id": user_id, "deleted_at": None},
            {"$set": {"deleted_at": now, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def hard_delete(self, user_id: int, item_id: str) -> bool:
        """Permanently remove document from collection."""
        obj_id = self.validate_object_id(item_id, "item_id")
        result = await self.collection.delete_one({"_id": obj_id, "user_id": user_id})
        return result.deleted_count > 0

    async def list_items(
        self,
        user_id: int,
        media_type: Optional[MediaType] = None,
        folder_id: Optional[str] = None,
        status: Optional[ItemStatus] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_desc: bool = True,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """Retrieve paginated and filtered items scoped strictly to the user."""
        query: Dict[str, Any] = {"user_id": user_id}
        if not include_deleted:
            query["deleted_at"] = None
        if media_type:
            query["media_type"] = media_type.value
        if folder_id is not None:
            query["folder_id"] = folder_id
        if status:
            query["status"] = status.value

        limit_val, offset_val = self.sanitize_pagination(limit, offset)
        sort_spec = self.sanitize_sort(sort_by, sort_desc, self.ALLOWED_SORT_FIELDS)

        cursor = self.collection.find(query).sort(sort_spec).skip(offset_val).limit(limit_val)
        docs = [doc async for doc in cursor]
        return self.format_docs(docs)

    async def count_items(
        self,
        user_id: int,
        media_type: Optional[MediaType] = None,
        folder_id: Optional[str] = None,
        status: Optional[ItemStatus] = None,
        include_deleted: bool = False,
    ) -> int:
        """Count active items belonging to a user with given filters."""
        query: Dict[str, Any] = {"user_id": user_id}
        if not include_deleted:
            query["deleted_at"] = None
        if media_type:
            query["media_type"] = media_type.value
        if folder_id is not None:
            query["folder_id"] = folder_id
        if status:
            query["status"] = status.value

        return await self.collection.count_documents(query)
