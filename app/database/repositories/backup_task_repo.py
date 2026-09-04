"""Backup Task repository with atomic claiming and lock timeout recovery."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.database.models.backup_task import BackupTaskModel, TaskStatus, TaskType
from app.database.repositories.base import BaseRepository


class BackupTaskRepository(BaseRepository):
    """Repository for managing the MongoDB-backed asynchronous task queue."""

    ALLOWED_SORT_FIELDS: Set[str] = {"created_at", "updated_at", "status", "attempts"}

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, "backup_tasks")

    async def create_task(self, task: BackupTaskModel) -> Dict[str, Any]:
        """Insert a new task into the pending task queue."""
        doc = task.to_doc()
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        if "_id" in doc:
            del doc["_id"]
        return doc

    async def claim_next_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Atomically claim the oldest pending task for the specified worker using find_one_and_update.

        Ensures no two workers can claim the same task simultaneously.
        """
        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one_and_update(
            {"status": TaskStatus.PENDING.value},
            {
                "$set": {
                    "status": TaskStatus.PROCESSING.value,
                    "worker_id": worker_id,
                    "locked_at": now,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )

        if doc and not doc.get("started_at"):
            await self.collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"started_at": now}},
            )
            doc["started_at"] = now

        return self.format_doc(doc)

    async def recover_stale_tasks(
        self,
        lock_timeout_seconds: int = 300,
        max_attempts: int = 3,
    ) -> int:
        """Identify crashed worker tasks with expired locks and reset them or mark failed.

        Tasks with attempts < max_attempts are transitioned back to 'pending'.
        Tasks with attempts >= max_attempts are transitioned to 'failed'.
        """
        now = datetime.now(timezone.utc)
        stale_threshold = now - timedelta(seconds=lock_timeout_seconds)

        # 1. Fail tasks exceeding max attempts
        await self.collection.update_many(
            {
                "status": TaskStatus.PROCESSING.value,
                "locked_at": {"$lt": stale_threshold},
                "attempts": {"$gte": max_attempts},
            },
            {
                "$set": {
                    "status": TaskStatus.FAILED.value,
                    "error_message": f"Task execution timed out and exceeded {max_attempts} attempts",
                    "locked_at": None,
                    "updated_at": now,
                }
            },
        )

        # 2. Reset recoverable tasks back to pending
        result = await self.collection.update_many(
            {
                "status": TaskStatus.PROCESSING.value,
                "locked_at": {"$lt": stale_threshold},
                "attempts": {"$lt": max_attempts},
            },
            {
                "$set": {
                    "status": TaskStatus.PENDING.value,
                    "worker_id": None,
                    "locked_at": None,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count

    async def update_progress(
        self,
        task_id: str,
        progress: float,
        worker_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update current percentage progress for an executing task."""
        obj_id = self.validate_object_id(task_id, "task_id")
        query: Dict[str, Any] = {"_id": obj_id, "status": TaskStatus.PROCESSING.value}
        if worker_id:
            query["worker_id"] = worker_id

        doc = await self.collection.find_one_and_update(
            query,
            {
                "$set": {
                    "progress": min(100.0, max(0.0, progress)),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def complete_task(
        self,
        task_id: str,
        worker_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark task as successfully completed."""
        obj_id = self.validate_object_id(task_id, "task_id")
        now = datetime.now(timezone.utc)
        query: Dict[str, Any] = {"_id": obj_id}
        if worker_id:
            query["worker_id"] = worker_id

        doc = await self.collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": TaskStatus.COMPLETED.value,
                    "progress": 100.0,
                    "completed_at": now,
                    "locked_at": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def fail_task(
        self,
        task_id: str,
        error_message: str,
        worker_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark task as failed with reason."""
        obj_id = self.validate_object_id(task_id, "task_id")
        now = datetime.now(timezone.utc)
        query: Dict[str, Any] = {"_id": obj_id}
        if worker_id:
            query["worker_id"] = worker_id

        doc = await self.collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": TaskStatus.FAILED.value,
                    "error_message": error_message,
                    "locked_at": None,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.format_doc(doc)

    async def renew_lock(
        self,
        task_id: str,
        worker_id: str,
    ) -> bool:
        """Atomically refresh locked_at timestamp for an actively executing task claimed by worker."""
        obj_id = self.validate_object_id(task_id, "task_id")
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {
                "_id": obj_id,
                "status": TaskStatus.PROCESSING.value,
                "worker_id": worker_id,
            },
            {
                "$set": {
                    "locked_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count > 0

    async def release_task_for_retry(
        self,
        task_id: str,
        error_message: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> bool:
        """Release a task back to pending state for subsequent retry attempts."""
        obj_id = self.validate_object_id(task_id, "task_id")
        now = datetime.now(timezone.utc)
        query: Dict[str, Any] = {"_id": obj_id, "status": TaskStatus.PROCESSING.value}
        if worker_id:
            query["worker_id"] = worker_id

        update_set: Dict[str, Any] = {
            "status": TaskStatus.PENDING.value,
            "worker_id": None,
            "locked_at": None,
            "updated_at": now,
        }
        if error_message:
            update_set["error_message"] = error_message

        result = await self.collection.update_one(
            query,
            {"$set": update_set},
        )
        return result.modified_count > 0

    async def get_by_id(
        self,
        task_id: str,
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get task by ID with optional user ownership enforcement."""
        obj_id = self.validate_object_id(task_id, "task_id")
        query: Dict[str, Any] = {"_id": obj_id}
        if user_id is not None:
            query["user_id"] = user_id

        doc = await self.collection.find_one(query)
        return self.format_doc(doc)

    async def list_user_tasks(
        self,
        user_id: int,
        status: Optional[TaskStatus] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_desc: bool = True,
    ) -> List[Dict[str, Any]]:
        """List tasks scoped to a specific user."""
        query: Dict[str, Any] = {"user_id": user_id}
        if status:
            query["status"] = status.value

        limit_val, offset_val = self.sanitize_pagination(limit, offset)
        sort_spec = self.sanitize_sort(sort_by, sort_desc, self.ALLOWED_SORT_FIELDS)

        cursor = self.collection.find(query).sort(sort_spec).skip(offset_val).limit(limit_val)
        docs = [doc async for doc in cursor]
        return self.format_docs(docs)
