"""Search API schemas."""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class SearchResponse(BaseModel):
    """Search results response."""

    query: str = Field(..., description="Executed search term")
    total: int = Field(..., ge=0, description="Total matching items")
    page: int = Field(..., ge=1, description="Current page")
    page_size: int = Field(..., ge=1, description="Results per page")
    total_pages: int = Field(..., ge=0, description="Total pages available")
    items: List[Dict[str, Any]] = Field(default_factory=list, description="Matching file records")
