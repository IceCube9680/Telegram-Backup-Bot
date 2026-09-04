"""Backup item data model."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class MediaType(str, Enum):
    """Supported Telegram media and content types."""

    DOCUMENT = "document"
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    ANIMATION = "animation"
    VIDEO_NOTE = "video_note"
    TEXT = "text"
    URL = "url"
    OTHER = "other"


class ItemStatus(str, Enum):
    """Processing and lifecycle status of a backup item."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BackupItemModel(BaseModel):
    """Backup Item document model."""

    user_id: int = Field(..., description="Telegram user ID owning this item")
    telegram_message_id: int = Field(..., description="Original Telegram message ID")
    chat_id: Optional[int] = Field(default=None, description="Original Telegram chat ID")
    telegram_file_id: Optional[str] = Field(default=None, description="Telegram file ID for download")
    telegram_file_unique_id: Optional[str] = Field(default=None, description="Telegram unique file ID")
    media_type: MediaType = Field(default=MediaType.DOCUMENT, description="Categorized media type")
    original_filename: Optional[str] = Field(default=None, description="Sanitized original filename")
    mime_type: Optional[str] = Field(default=None, description="MIME content type")
    file_size: Optional[int] = Field(default=None, ge=0, description="File size in bytes")
    sha256: Optional[str] = Field(default=None, description="SHA-256 checksum for deduplication")
    caption: Optional[str] = Field(default=None, description="Message caption or text body")
    storage_provider: str = Field(default="local", description="Storage backend ('local' or 's3')")
    storage_key: Optional[str] = Field(default=None, description="Generated storage path/key")
    transfer_method: str = Field(
        default="bot_api", description="Transfer provider used ('bot_api' or 'mtproto')"
    )
    folder_id: Optional[str] = Field(default=None, description="Parent folder ID if organized")
    status: ItemStatus = Field(default=ItemStatus.PENDING, description="Item processing status")
    deleted_at: Optional[datetime] = Field(
        default=None, description="Timestamp when soft-deleted, None if active"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        data = self.model_dump()
        data["media_type"] = self.media_type.value
        data["status"] = self.status.value
        return data
