"""User-scoped Search Service across backed up files and metadata."""

import math
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.database.repositories.backup_item_repo import BackupItemRepository

logger = get_logger(__name__)


class SearchResult(BaseModel):
    """Result summary of a search operation."""

    query: str = Field(..., description="Sanitized search term")
    total: int = Field(..., ge=0, description="Total matching active items")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of results per page")
    total_pages: int = Field(..., ge=0, description="Total pages available")
    items: List[Dict[str, Any]] = Field(default_factory=list, description="Matching backup items")


class SearchService:
    """Service to search files scoped strictly to the authenticated user."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.item_repo = BackupItemRepository(db)

    async def search_files(
        self,
        user_id: int,
        query: str,
        page: int = 1,
        page_size: int = 10,
    ) -> SearchResult:
        """Search active files belonging to user by filename, caption, or MIME type with regex safety."""
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValidationError("Search query cannot be empty", details={"field": "query"})

        if len(clean_query) > 100:
            raise ValidationError(
                "Search query exceeds maximum length of 100 characters",
                details={"field": "query", "length": len(clean_query)},
            )

        safe_page = max(1, page)
        safe_page_size = min(100, max(1, page_size))
        offset = (safe_page - 1) * safe_page_size

        # Escape special regex characters to prevent pathological queries or injection
        escaped_query = re.escape(clean_query)

        search_filter: Dict[str, Any] = {
            "user_id": user_id,
            "deleted_at": None,
            "$or": [
                {"original_filename": {"$regex": escaped_query, "$options": "i"}},
                {"caption": {"$regex": escaped_query, "$options": "i"}},
                {"mime_type": {"$regex": escaped_query, "$options": "i"}},
            ],
        }

        total = await self.item_repo.collection.count_documents(search_filter)
        total_pages = math.ceil(total / safe_page_size) if total > 0 else 0

        cursor = (
            self.item_repo.collection.find(search_filter)
            .sort("created_at", -1)
            .skip(offset)
            .limit(safe_page_size)
        )
        docs = [doc async for doc in cursor]
        items = self.item_repo.format_docs(docs)

        logger.debug(f"Search user={user_id} query='{clean_query}' matched {total} items (page {safe_page})")

        return SearchResult(
            query=clean_query,
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            total_pages=total_pages,
            items=items,
        )
