"""File management API schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FileListItem(BaseModel):
    """File item summary in paginated list."""

    id: str = Field(..., description="Unique BackupItem ID")
    original_filename: str = Field(..., description="Original filename")
    media_type: str = Field(..., description="Media type")
    file_size: Optional[int] = Field(default=None, description="Size in bytes")
    mime_type: Optional[str] = Field(default=None, description="MIME content type")
    status: str = Field(..., description="Processing status")
    created_at: datetime = Field(..., description="Upload timestamp")
    folder_id: Optional[str] = Field(default=None, description="Assigned folder ID")
    caption: Optional[str] = Field(default=None, description="Message caption")
    sha256: Optional[str] = Field(default=None, description="SHA-256 hash")
    transfer_method: Optional[str] = Field(
        default="bot_api", description="Transfer method used ('bot_api' or 'mtproto')"
    )


class FileListResponse(BaseModel):
    """Paginated list of backup files."""

    items: List[FileListItem] = Field(default_factory=list, description="Page file records")
    total: int = Field(..., ge=0, description="Total active files")
    page: int = Field(..., ge=1, description="Current page")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total pages")


class FileDetailsResponse(BaseModel):
    """Detailed file metadata view."""

    item_id: str = Field(..., description="Item ID")
    original_filename: str = Field(..., description="Filename")
    media_type: str = Field(..., description="Media category")
    file_size: Optional[int] = Field(default=None, description="Size in bytes")
    mime_type: Optional[str] = Field(default=None, description="MIME content type")
    caption: Optional[str] = Field(default=None, description="Message caption")
    transfer_method: Optional[str] = Field(
        default="bot_api", description="Transfer provider ('bot_api' or 'mtproto')"
    )
    status: str = Field(..., description="Processing status")
    created_at: datetime = Field(..., description="Upload timestamp")
    sha256_short: Optional[str] = Field(default=None, description="Display hash snippet")
    folder_id: Optional[str] = Field(default=None, description="Assigned folder ID")
    folder_name: Optional[str] = Field(default=None, description="Assigned folder display name")
    tags: List[str] = Field(default_factory=list, description="Attached tags")
    task_progress: Optional[float] = Field(default=None, description="Download progress if active")
    task_error: Optional[str] = Field(default=None, description="Error explanation if failed")


class MoveFileRequest(BaseModel):
    """Request payload to move file to a folder or root."""

    folder_id: Optional[str] = Field(default=None, description="Destination folder ID, or null for root")


class DeleteFileResponse(BaseModel):
    """Response returned upon file deletion."""

    item_id: str = Field(..., description="Deleted item ID")
    filename: str = Field(..., description="Deleted filename")
    file_size: Optional[int] = Field(default=None, description="Freed size in bytes")
    storage_deleted: bool = Field(default=False, description="Whether storage object was deleted")
    message: str = Field(..., description="Outcome message")


class RetryFileResponse(BaseModel):
    """Response returned upon re-queuing a failed task."""

    task_id: str = Field(..., description="Re-queued task ID")
    item_id: str = Field(..., description="Item ID")
    message: str = Field(..., description="Outcome message")
