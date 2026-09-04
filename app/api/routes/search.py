"""Search REST API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_search_service, require_authenticated_user
from app.api.middleware import rate_limit
from app.api.schemas.common import ApiResponse
from app.api.schemas.search import SearchResponse
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.services.search_service import SearchService

logger = get_logger(__name__)
router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=ApiResponse[SearchResponse],
    dependencies=[Depends(rate_limit("search", max_requests=60, window_seconds=60))],
)
async def search_files(
    q: str = Query(..., min_length=1, max_length=100, description="Search query string"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=100, description="Page size"),
    current_user: dict = Depends(require_authenticated_user),
    search_service: SearchService = Depends(get_search_service),
) -> ApiResponse[SearchResponse]:
    """Execute safe regex-escaped search across user's backup files."""
    user_id = current_user["telegram_user_id"]
    try:
        result = await search_service.search_files(
            user_id=user_id,
            query=q,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(
            data=SearchResponse(
                query=result.query,
                total=result.total,
                page=result.page,
                page_size=result.page_size,
                total_pages=result.total_pages,
                items=result.items,
            )
        )
    except ValidationError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ve.message)
