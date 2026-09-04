"""Folder management API schemas."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CreateFolderRequest(BaseModel):
    """Payload to create a new folder."""

    name: str = Field(..., min_length=1, max_length=64, description="Folder display name")
    parent_id: Optional[str] = Field(default=None, description="Optional parent folder ID for nesting")


class FolderResponse(BaseModel):
    """Folder metadata response."""

    id: str = Field(..., description="Unique folder ID")
    user_id: int = Field(..., description="Owning Telegram user ID")
    name: str = Field(..., description="Folder display name")
    parent_id: Optional[str] = Field(default=None, description="Parent folder ID")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")


class FolderListResponse(BaseModel):
    """List of folders response."""

    folders: List[FolderResponse] = Field(default_factory=list, description="User folders")
