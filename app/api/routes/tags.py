"""Tag management REST API routes."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_tag_service, require_authenticated_user
from app.api.schemas.common import ApiResponse
from app.api.schemas.tags import (
    CreateTagRequest,
    TagListResponse,
    TagResponse,
    TaggedFilesResponse,
)
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.logging import get_logger
from app.services.tag_service import TagService

logger = get_logger(__name__)
router = APIRouter(prefix="/tags", tags=["Tags"])


@router.get("", response_model=ApiResponse[TagListResponse])
async def list_tags(
    current_user: dict = Depends(require_authenticated_user),
    tag_service: TagService = Depends(get_tag_service),
) -> ApiResponse[TagListResponse]:
    """List all tags belonging to the current user."""
    user_id = current_user["telegram_user_id"]
    tag_docs = await tag_service.list_tags(user_id=user_id)

    tags = [
        TagResponse(
            id=t["id"],
            user_id=t["user_id"],
            name=t["name"],
            created_at=t.get("created_at"),
        )
        for t in tag_docs
    ]
    return ApiResponse(data=TagListResponse(tags=tags))


@router.post("", response_model=ApiResponse[TagResponse])
async def create_tag(
    payload: CreateTagRequest,
    current_user: dict = Depends(require_authenticated_user),
    tag_service: TagService = Depends(get_tag_service),
) -> ApiResponse[TagResponse]:
    """Create or ensure a normalized tag for current user."""
    user_id = current_user["telegram_user_id"]
    try:
        tag = await tag_service.create_tag(user_id=user_id, name=payload.name)
        return ApiResponse(
            data=TagResponse(
                id=tag["id"],
                user_id=tag["user_id"],
                name=tag["name"],
                created_at=tag.get("created_at"),
            ),
            message="Tag created successfully",
        )
    except ValidationError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ve.message)


@router.delete("/{tag_id}", response_model=ApiResponse[bool])
async def delete_tag(
    tag_id: str,
    current_user: dict = Depends(require_authenticated_user),
    tag_service: TagService = Depends(get_tag_service),
) -> ApiResponse[bool]:
    """Delete a tag and its item associations."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(tag_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    deleted = await tag_service.delete_tag(user_id=user_id, tag_id=tag_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    return ApiResponse(data=True, message="Tag deleted successfully")


@router.get("/{tag_id}/files", response_model=ApiResponse[TaggedFilesResponse])
async def list_tagged_files(
    tag_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_authenticated_user),
    tag_service: TagService = Depends(get_tag_service),
) -> ApiResponse[TaggedFilesResponse]:
    """List active backup files attached to a specific tag."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(tag_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    try:
        result = await tag_service.list_tagged_files(
            user_id=user_id,
            tag_id=tag_id,
            limit=limit,
            offset=offset,
        )
        tag_data = result["tag"]
        return ApiResponse(
            data=TaggedFilesResponse(
                tag=TagResponse(
                    id=tag_data["id"],
                    user_id=tag_data["user_id"],
                    name=tag_data["name"],
                    created_at=tag_data.get("created_at"),
                ),
                items=result["items"],
                total=result["total"],
            )
        )
    except ResourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    except ValidationError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ve.message)
