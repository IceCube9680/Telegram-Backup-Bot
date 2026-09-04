"""Tag repository for managing user tags and item-tag associations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.database.models.tag import ItemTagModel, TagModel
from app.database.repositories.base import BaseRepository


class TagRepository(BaseRepository):
    """Repository for managing Tags and Item-Tag associations."""

    ALLOWED_SORT_FIELDS: Set[str] = {"name", "created_at"}

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, "tags")
        self.item_tags_collection = db["item_tags"]

    async def get_or_create_tag(self, user_id: int, name: str) -> Dict[str, Any]:
        """Get an existing tag or atomically create one scoped to user."""
        normalized_name = name.strip().lower()
        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {"user_id": user_id, "name": normalized_name},
            {"$setOnInsert": {"user_id": user_id, "name": normalized_name, "created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)  # type: ignore

    async def list_user_tags(
        self,
        user_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List all tags belonging to user."""
        limit_val, offset_val = self.sanitize_pagination(limit, offset)
        cursor = self.collection.find({"user_id": user_id}).sort("name", 1).skip(offset_val).limit(limit_val)
        docs = [doc async for doc in cursor]
        return self.format_docs(docs)

    async def delete_tag(self, user_id: int, tag_id: str) -> bool:
        """Delete a tag and clean up its item associations."""
        obj_id = self.validate_object_id(tag_id, "tag_id")
        tag_doc = await self.collection.find_one_and_delete({"_id": obj_id, "user_id": user_id})
        if tag_doc:
            await self.item_tags_collection.delete_many({"tag_id": str(obj_id)})
            return True
        return False

    async def add_tag_to_item(self, user_id: int, item_id: str, tag_id: str) -> Dict[str, Any]:
        """Associate a tag with a backup item with user ownership verification."""
        self.validate_object_id(item_id, "item_id")
        self.validate_object_id(tag_id, "tag_id")

        # Verify tag belongs to user
        tag = await self.collection.find_one({"_id": self.validate_object_id(tag_id), "user_id": user_id})
        if not tag:
            raise BaseRepository.validate_object_id("invalid", "tag_id")

        now = datetime.now(timezone.utc)
        doc = await self.item_tags_collection.find_one_and_update(
            {"backup_item_id": item_id, "tag_id": tag_id},
            {"$setOnInsert": {"backup_item_id": item_id, "tag_id": tag_id, "created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)  # type: ignore

    async def remove_tag_from_item(self, item_id: str, tag_id: str) -> bool:
        """Remove a tag association from a backup item."""
        result = await self.item_tags_collection.delete_one(
            {"backup_item_id": item_id, "tag_id": tag_id}
        )
        return result.deleted_count > 0

    async def get_tags_for_item(self, user_id: int, item_id: str) -> List[Dict[str, Any]]:
        """Retrieve all tags associated with a specific backup item."""
        cursor = self.item_tags_collection.find({"backup_item_id": item_id})
        tag_ids = [self.validate_object_id(doc["tag_id"]) async for doc in cursor]
        if not tag_ids:
            return []

        tag_cursor = self.collection.find({"_id": {"$in": tag_ids}, "user_id": user_id})
        tags = [t async for t in tag_cursor]
        return self.format_docs(tags)

    async def get_item_ids_by_tag(
        self,
        tag_id: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[str]:
        """Retrieve item IDs tagged with a specific tag."""
        limit_val, offset_val = self.sanitize_pagination(limit, offset)
        cursor = (
            self.item_tags_collection.find({"tag_id": tag_id})
            .skip(offset_val)
            .limit(limit_val)
        )
        return [doc["backup_item_id"] async for doc in cursor]
