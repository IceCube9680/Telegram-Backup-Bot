"""Folder management service for user directory hierarchy."""

from typing import Any, Dict, List, Optional
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.repositories.backup_item_repo import BackupItemRepository
from app.database.repositories.folder_repo import FolderRepository

logger = get_logger(__name__)


class FolderService:
    """Service to create, organize, and navigate user folder hierarchies."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.folder_repo = FolderRepository(db)
        self.item_repo = BackupItemRepository(db)

    async def create_folder(
        self,
        user_id: int,
        name: str,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new folder ensuring user scoping and validation."""
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValidationError("Folder name cannot be empty", details={"field": "name"})

        if len(clean_name) > 64:
            raise ValidationError(
                "Folder name cannot exceed 64 characters",
                details={"field": "name", "length": len(clean_name)},
            )

        if parent_id:
            parent = await self.folder_repo.get_by_id(user_id=user_id, folder_id=parent_id)
            if not parent:
                raise ResourceNotFoundError(
                    "Parent folder not found or ownership mismatch",
                    details={"parent_id": parent_id, "user_id": user_id},
                )

        try:
            folder = await self.folder_repo.create_folder(
                user_id=user_id,
                name=clean_name,
                parent_id=parent_id,
            )
            logger.info(f"Created folder '{clean_name}' (id={folder['id']}) for user {user_id}")
            return folder
        except DuplicateKeyError:
            raise ValidationError(
                f"A folder named '{clean_name}' already exists in this location",
                details={"name": clean_name, "parent_id": parent_id},
            )

    async def list_folders(
        self,
        user_id: int,
        parent_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List folders belonging to user."""
        return await self.folder_repo.list_folders(
            user_id=user_id,
            parent_id=parent_id,
            limit=limit,
            offset=offset,
        )

    async def get_folder(self, user_id: int, folder_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve folder with user ownership verification."""
        return await self.folder_repo.get_by_id(user_id=user_id, folder_id=folder_id)

    async def move_item_to_folder(
        self,
        user_id: int,
        item_id: str,
        folder_id: Optional[str],
    ) -> bool:
        """Move a backup item to a folder or root."""
        item = await self.item_repo.get_by_id(user_id=user_id, item_id=item_id)
        if not item:
            raise ResourceNotFoundError(
                "Backup item not found or ownership mismatch",
                details={"item_id": item_id, "user_id": user_id},
            )

        if folder_id is not None:
            folder = await self.folder_repo.get_by_id(user_id=user_id, folder_id=folder_id)
            if not folder:
                raise ResourceNotFoundError(
                    "Destination folder not found or ownership mismatch",
                    details={"folder_id": folder_id, "user_id": user_id},
                )

        updated = await self.item_repo.update_folder(user_id=user_id, item_id=item_id, folder_id=folder_id)
        return updated is not None

    async def delete_folder(self, user_id: int, folder_id: str) -> bool:
        """Delete a folder scoped to user."""
        folder = await self.folder_repo.get_by_id(user_id=user_id, folder_id=folder_id)
        if not folder:
            return False

        # Reset item folder_id to None for items inside this folder
        await self.item_repo.collection.update_many(
            {"user_id": user_id, "folder_id": folder_id},
            {"$set": {"folder_id": None}},
        )

        return await self.folder_repo.delete_folder(user_id=user_id, folder_id=folder_id)
