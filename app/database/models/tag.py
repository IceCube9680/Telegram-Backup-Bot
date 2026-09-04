"""Tag and Item-Tag relationship data models."""

from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, Field


class TagModel(BaseModel):
    """User-defined Tag document model."""

    user_id: int = Field(..., description="Telegram user ID owning the tag")
    name: str = Field(..., min_length=1, max_length=64, description="Normalized tag name")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Tag creation timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        return self.model_dump()


class ItemTagModel(BaseModel):
    """Many-to-Many mapping document between BackupItem and Tag."""

    backup_item_id: str = Field(..., description="BackupItem ID string")
    tag_id: str = Field(..., description="Tag ID string")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Association creation timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        return self.model_dump()
