"""Tag management API schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateTagRequest(BaseModel):
    """Payload to create or ensure a tag."""

    name: str = Field(..., min_length=1, max_length=32, description="Tag label name")


class AssignTagRequest(BaseModel):
    """Payload to attach a tag to an item."""

    tag: str = Field(..., min_length=1, max_length=64, description="Tag name or 24-char ObjectId")


class TagResponse(BaseModel):
    """Tag metadata response."""

    id: str = Field(..., description="Unique tag ID")
    user_id: int = Field(..., description="Owning Telegram user ID")
    name: str = Field(..., description="Normalized tag name")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")


class TagListResponse(BaseModel):
    """List of user tags response."""

    tags: List[TagResponse] = Field(default_factory=list, description="User tags")


class TaggedFilesResponse(BaseModel):
    """Files associated with a specific tag."""

    tag: TagResponse = Field(..., description="Tag metadata")
    items: List[Dict[str, Any]] = Field(default_factory=list, description="Tagged file records")
    total: int = Field(..., ge=0, description="Total matching items")
