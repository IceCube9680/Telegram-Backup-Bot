"""Health check response schemas."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Liveness probe response schema."""

    status: str = Field(default="alive", description="Liveness status of the application process")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current server timestamp in UTC",
    )


class ReadinessResponse(BaseModel):
    """Readiness probe response schema."""

    status: str = Field(..., description="Readiness status: 'ready' or 'not_ready'")
    database: str = Field(..., description="Database status: 'connected' or 'disconnected'")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current server timestamp in UTC",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Diagnostic details regarding service readiness"
    )


class HealthResponse(BaseModel):
    """Combined health check response schema."""

    status: str = Field(..., description="Overall status: 'healthy' or 'degraded'")
    app: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    database: str = Field(..., description="Database connectivity status: 'connected' or 'disconnected'")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current server timestamp in UTC",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional health diagnostic details"
    )
