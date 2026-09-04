"""Health check response schemas."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(..., description="Overall health status: healthy, degraded, or unhealthy")
    app: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    database: str = Field(..., description="Database connectivity status: connected or disconnected")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current server timestamp in UTC",
    )
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional health diagnostic details")
