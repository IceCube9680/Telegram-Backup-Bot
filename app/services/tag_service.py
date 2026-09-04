"""Tag management service for classifying and searching backup items by labels."""

import re
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.tag_repo import TagRepository

logger = get_logger(__name__)


class TagService:
    """Service to create tags and manage item-tag associations."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.tag_repo = TagRepository(db)
        self.item_repo = BackupItemRepository(db)

    def normalize_tag_name(self, name: str) -> str:
        """Validate and sanitize tag name."""
        clean = (name or "").strip().lower()
        if not clean:
            raise ValidationError("Tag name cannot be empty", details={"field": "name"})

        if len(clean) > 32:
            raise ValidationError(
                "Tag name cannot exceed 32 characters",
                details={"field": "name", "length": len(clean)},
            )

        # Allow alphanumeric, underscore, hyphen, and common Unicode characters
        if not re.match(r"^[\w\-]+$", clean, re.UNICODE):
            raise ValidationError(
                "Tag name contains invalid characters (use letters, numbers, hyphens, or underscores)",
                details={"name": clean},
            )

        return clean

    async def create_tag(self, user_id: int, name: str) -> Dict[str, Any]:
        """Create or fetch existing tag scoped to user."""
        clean_name = self.normalize_tag_name(name)
        tag = await self.tag_repo.get_or_create_tag(user_id=user_id, name=clean_name)
        logger.info(f"Tag '{clean_name}' (id={tag['id']}) ensured for user {user_id}")
        return tag

    async def list_tags(
        self,
        user_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List all tags belonging to user."""
        return await self.tag_repo.list_user_tags(user_id=user_id, limit=limit, offset=offset)

    async def delete_tag(self, user_id: int, tag_id: str) -> bool:
        """Delete tag and its item associations."""
        return await self.tag_repo.delete_tag(user_id=user_id, tag_id=tag_id)

    async def assign_tag_to_item(
        self,
        user_id: int,
        item_id: str,
        tag_name_or_id: str,
    ) -> Dict[str, Any]:
        """Assign tag to backup item verifying user ownership of both."""
        item = await self.item_repo.get_by_id(user_id=user_id, item_id=item_id)
        if not item:
            raise ResourceNotFoundError(
                "Backup item not found or ownership mismatch",
                details={"item_id": item_id, "user_id": user_id},
            )

        # Check if tag_name_or_id is a 24-char hex ObjectId or a name string
        if ObjectId.is_valid(tag_name_or_id):
            tag = await self.tag_repo.collection.find_one(
                {"_id": ObjectId(tag_name_or_id), "user_id": user_id}
            )
            if not tag:
                raise ResourceNotFoundError(
                    "Tag not found or ownership mismatch",
                    details={"tag_id": tag_name_or_id, "user_id": user_id},
                )
            tag_id = str(tag["_id"])
        else:
            tag = await self.create_tag(user_id=user_id, name=tag_name_or_id)
            tag_id = tag["id"]

        assoc = await self.tag_repo.add_tag_to_item(user_id=user_id, item_id=item_id, tag_id=tag_id)
        return assoc

    async def remove_tag_from_item(
        self,
        user_id: int,
        item_id: str,
        tag_id: str,
    ) -> bool:
        """Remove tag from backup item verifying item ownership."""
        item = await self.item_repo.get_by_id(user_id=user_id, item_id=item_id)
        if not item:
            raise ResourceNotFoundError(
                "Backup item not found or ownership mismatch",
                details={"item_id": item_id, "user_id": user_id},
            )

        return await self.tag_repo.remove_tag_from_item(item_id=item_id, tag_id=tag_id)

    async def get_item_tags(self, user_id: int, item_id: str) -> List[Dict[str, Any]]:
        """List all tags attached to a specific backup item."""
        return await self.tag_repo.get_tags_for_item(user_id=user_id, item_id=item_id)

    async def list_tagged_files(
        self,
        user_id: int,
        tag_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List active backup items associated with a specific tag."""
        # Verify tag belongs to user
        if not ObjectId.is_valid(tag_id):
            raise ValidationError("Invalid tag identifier", details={"tag_id": tag_id})

        tag = await self.tag_repo.collection.find_one({"_id": ObjectId(tag_id), "user_id": user_id})
        if not tag:
            raise ResourceNotFoundError("Tag not found", details={"tag_id": tag_id, "user_id": user_id})

        # Get item IDs
        item_ids = await self.tag_repo.get_item_ids_by_tag(tag_id=tag_id, limit=limit, offset=offset)
        if not item_ids:
            return {"tag": self.tag_repo.format_doc(tag), "items": [], "total": 0}

        obj_ids = [ObjectId(iid) for iid in item_ids if ObjectId.is_valid(iid)]
        cursor = self.item_repo.collection.find(
            {"_id": {"$in": obj_ids}, "user_id": user_id, "deleted_at": None}
        ).sort("created_at", -1)

        docs = [doc async for doc in cursor]
        items = self.item_repo.format_docs(docs)
        total = await self.tag_repo.item_tags_collection.count_documents({"tag_id": tag_id})

        return {
            "tag": self.tag_repo.format_doc(tag),
            "items": items,
            "total": total,
        }
