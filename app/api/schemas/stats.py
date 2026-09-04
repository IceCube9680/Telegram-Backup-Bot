"""Storage and usage statistics API schemas."""

from pydantic import BaseModel, Field


class StatsResponse(BaseModel):
    """User storage and backup statistics."""

    user_id: int = Field(..., description="Telegram user ID")
    total_files: int = Field(..., ge=0, description="Total active files")
    total_size_bytes: int = Field(..., ge=0, description="Total stored bytes")
    completed_count: int = Field(default=0, ge=0, description="Completed backups")
    processing_count: int = Field(default=0, ge=0, description="Processing backups")
    pending_count: int = Field(default=0, ge=0, description="Pending queue backups")
    failed_count: int = Field(default=0, ge=0, description="Failed backups")
