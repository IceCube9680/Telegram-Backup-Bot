"""Common generic API request and response schemas."""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiError(BaseModel):
    """Standardized API error schema."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[Any] = Field(default=None, description="Optional extra error context")


class ApiResponse(BaseModel, Generic[T]):
    """Standardized successful API response wrapper."""

    success: bool = Field(default=True, description="Operation success flag")
    data: Optional[T] = Field(default=None, description="Response payload")
    message: Optional[str] = Field(default=None, description="Optional informational message")


class ApiErrorResponse(BaseModel):
    """Standardized failed API response wrapper."""

    success: bool = Field(default=False, description="Operation failure flag")
    error: ApiError = Field(..., description="Error descriptor")
