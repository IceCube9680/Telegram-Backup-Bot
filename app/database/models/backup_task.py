"""Backup task queue data model."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Execution status for asynchronous background tasks."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Types of background worker jobs."""

    DOWNLOAD_AND_STORE = "download_and_store"
    REINDEX = "reindex"
    DELETE = "delete"


class BackupTaskModel(BaseModel):
    """Backup Task queue document model."""

    user_id: int = Field(..., description="Telegram user ID owning the task")
    backup_item_id: Optional[str] = Field(default=None, description="Associated BackupItem ID")
    task_type: TaskType = Field(
        default=TaskType.DOWNLOAD_AND_STORE, description="Type of background job"
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task state")
    progress: float = Field(default=0.0, ge=0.0, le=100.0, description="Task execution progress percentage")
    attempts: int = Field(default=0, ge=0, description="Number of execution attempts")
    error_message: Optional[str] = Field(default=None, description="Detailed error information if failed")
    locked_at: Optional[datetime] = Field(
        default=None, description="Timestamp when claimed by worker for lock tracking"
    )
    worker_id: Optional[str] = Field(default=None, description="Identifier of worker instance executing task")
    started_at: Optional[datetime] = Field(default=None, description="Timestamp when execution started")
    completed_at: Optional[datetime] = Field(default=None, description="Timestamp when task finished")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Task submission timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        data = self.model_dump()
        data["task_type"] = self.task_type.value
        data["status"] = self.status.value
        return data
