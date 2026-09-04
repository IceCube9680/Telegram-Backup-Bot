"""Storage Usage repository with atomic $inc updates and concurrency safety."""

from datetime import datetime, timezone
from typing import Any, Dict
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.database.models.settings import StorageUsageModel
from app.database.repositories.base import BaseRepository


class StorageUsageRepository(BaseRepository):
    """Repository for managing User cumulative storage accounting via atomic MongoDB $inc."""

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, "storage_usage")

    async def get_usage(self, user_id: int) -> Dict[str, Any]:
        """Fetch cumulative storage accounting for user or return initialized zero values."""
        doc = await self.collection.find_one({"user_id": user_id})
        if doc is None:
            now = datetime.now(timezone.utc)
            default_model = StorageUsageModel(user_id=user_id, total_files=0, total_size=0, updated_at=now)
            default_doc = default_model.to_doc()
            doc = await self.collection.find_one_and_update(
                {"user_id": user_id},
                {"$setOnInsert": default_doc},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        return self.format_doc(doc)  # type: ignore

    async def increment_usage(
        self,
        user_id: int,
        file_count: int = 1,
        total_bytes: int = 0,
    ) -> Dict[str, Any]:
        """Atomically increment stored file count and byte size using MongoDB $inc.

        Ensures atomic execution without read-modify-write lost update race conditions.
        """
        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {
                "$inc": {
                    "total_files": max(0, file_count),
                    "total_size": max(0, total_bytes),
                },
                "$set": {
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "user_id": user_id,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)  # type: ignore

    async def decrement_usage(
        self,
        user_id: int,
        file_count: int = 1,
        total_bytes: int = 0,
    ) -> Dict[str, Any]:
        """Atomically decrement stored file count and byte size.

        Uses atomic $inc with negative values and clamps negative values to zero.
        """
        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {
                "$inc": {
                    "total_files": -max(0, file_count),
                    "total_size": -max(0, total_bytes),
                },
                "$set": {
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "user_id": user_id,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        # Floor protection: if either counter went below zero, correct it atomically
        if doc and (doc.get("total_files", 0) < 0 or doc.get("total_size", 0) < 0):
            doc = await self.collection.find_one_and_update(
                {"user_id": user_id},
                {
                    "$set": {
                        "total_files": max(0, doc.get("total_files", 0)),
                        "total_size": max(0, doc.get("total_size", 0)),
                        "updated_at": now,
                    }
                },
                return_document=ReturnDocument.AFTER,
            )

        return self.format_doc(doc)  # type: ignore

    async def reset_usage(
        self,
        user_id: int,
        total_files: int,
        total_bytes: int,
    ) -> Dict[str, Any]:
        """Explicitly set audited counters."""
        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {
                "$set": {
                    "total_files": max(0, total_files),
                    "total_size": max(0, total_bytes),
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "user_id": user_id,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)  # type: ignore
