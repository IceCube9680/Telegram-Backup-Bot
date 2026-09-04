"""Folder organization data model."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class FolderModel(BaseModel):
    """Folder document model for hierarchical file organization."""

    user_id: int = Field(..., description="Telegram user ID owning the folder")
    parent_id: Optional[str] = Field(
        default=None, description="Parent folder ID for nested subfolders, None for root"
    )
    name: str = Field(..., min_length=1, max_length=128, description="Folder display name")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Folder creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        return self.model_dump()
