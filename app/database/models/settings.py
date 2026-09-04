"""User settings and storage usage tracking models."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class UserSettingsModel(BaseModel):
    """User preferences and backup configuration document model."""

    user_id: int = Field(..., description="Telegram user ID")
    auto_backup: bool = Field(default=True, description="Automatically queue incoming media for backup")
    duplicate_detection: bool = Field(
        default=True, description="Check SHA-256 to skip duplicate uploads for this user"
    )
    default_folder_id: Optional[str] = Field(default=None, description="Default target folder ID")
    max_file_size: int = Field(
        default=52428800, ge=1024, description="Maximum allowed file size in bytes (default 50MB)"
    )
    notifications_enabled: bool = Field(
        default=True, description="Send Telegram notifications on backup completion/failure"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Settings record creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last settings modification timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        return self.model_dump()


class StorageUsageModel(BaseModel):
    """Cumulative storage accounting document model per user."""

    user_id: int = Field(..., description="Telegram user ID")
    total_files: int = Field(default=0, ge=0, description="Total active files stored")
    total_size: int = Field(default=0, ge=0, description="Total cumulative size stored in bytes")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last recalculation or increment timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        return self.model_dump()
