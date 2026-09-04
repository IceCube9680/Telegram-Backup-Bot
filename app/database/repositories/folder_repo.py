"""Folder repository for directory organization and hierarchical tree navigation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.database.models.folder import FolderModel
from app.database.repositories.base import BaseRepository


class FolderRepository(BaseRepository):
    """Repository for managing User Folder hierarchies."""

    ALLOWED_SORT_FIELDS: Set[str] = {"name", "created_at", "updated_at"}

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, "folders")

    async def create_folder(
        self,
        user_id: int,
        name: str,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new folder scoped to the user."""
        parent_id_clean = None
        if parent_id:
            # Validate parent folder exists and belongs to user
            self.validate_object_id(parent_id, "parent_id")
            parent_id_clean = parent_id

        folder = FolderModel(user_id=user_id, parent_id=parent_id_clean, name=name.strip())
        doc = folder.to_doc()
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        if "_id" in doc:
            del doc["_id"]
        return doc

    async def get_by_id(self, user_id: int, folder_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve folder ensuring user ownership."""
        obj_id = self.validate_object_id(folder_id, "folder_id")
        doc = await self.collection.find_one({"_id": obj_id, "user_id": user_id})
        return self.format_doc(doc)

    async def list_folders(
        self,
        user_id: int,
        parent_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[str] = "name",
        sort_desc: bool = False,
    ) -> List[Dict[str, Any]]:
        """List folders for a user, optionally filtered by parent folder."""
        query: Dict[str, Any] = {"user_id": user_id}
        if parent_id is not None:
            query["parent_id"] = parent_id

        limit_val, offset_val = self.sanitize_pagination(limit, offset)
        sort_spec = self.sanitize_sort(sort_by, sort_desc, self.ALLOWED_SORT_FIELDS, default_field="name")

        cursor = self.collection.find(query).sort(sort_spec).skip(offset_val).limit(limit_val)
        docs = [doc async for doc in cursor]
        return self.format_docs(docs)

    async def rename_folder(
        self,
        user_id: int,
        folder_id: str,
        new_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Rename an existing folder with user ownership check."""
        obj_id = self.validate_object_id(folder_id, "folder_id")
        doc = await self.collection.find_one_and_update(
            {"_id": obj_id, "user_id": user_id},
            {
                "$set": {
                    "name": new_name.strip(),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def delete_folder(self, user_id: int, folder_id: str) -> bool:
        """Delete a folder scoped to user."""
        obj_id = self.validate_object_id(folder_id, "folder_id")
        result = await self.collection.delete_one({"_id": obj_id, "user_id": user_id})
        return result.deleted_count > 0
