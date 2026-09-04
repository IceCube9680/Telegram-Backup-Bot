"""Files management and download REST API routes."""

from typing import Any, Dict, List, Optional
from urllib.parse import quote
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    get_folder_service,
    get_management_service,
    get_tag_service,
    require_authenticated_user,
)
from app.api.middleware import rate_limit
from app.api.schemas.common import ApiResponse
from app.api.schemas.files import (
    DeleteFileResponse,
    FileDetailsResponse,
    FileListItem,
    FileListResponse,
    MoveFileRequest,
    RetryFileResponse,
)
from app.api.schemas.tags import AssignTagRequest, TagResponse
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.models.backup_item import ItemStatus, MediaType
from app.services.backup_management_service import BackupManagementService
from app.services.folder_service import FolderService
from app.services.tag_service import TagService

logger = get_logger(__name__)
router = APIRouter(prefix="/files", tags=["Files"])


@router.get("", response_model=ApiResponse[FileListResponse])
async def list_files(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    folder_id: Optional[str] = Query(default=None, description="Filter by folder ID"),
    media_type: Optional[MediaType] = Query(default=None, description="Filter by media type"),
    status_filter: Optional[ItemStatus] = Query(default=None, alias="status", description="Filter by status"),
    current_user: dict = Depends(require_authenticated_user),
    management_service: BackupManagementService = Depends(get_management_service),
) -> ApiResponse[FileListResponse]:
    """Retrieve paginated list of active backup files strictly scoped to current authenticated user."""
    user_id = current_user["telegram_user_id"]
    result = await management_service.list_user_files(
        user_id=user_id,
        page=page,
        page_size=page_size,
        folder_id=folder_id,
        media_type=media_type,
        status=status_filter,
    )

    items = [
        FileListItem(
            id=item["id"],
            original_filename=item.get("original_filename") or "Unnamed File",
            media_type=item.get("media_type") or "document",
            file_size=item.get("file_size"),
            mime_type=item.get("mime_type"),
            status=item.get("status") or "pending",
            created_at=item.get("created_at"),
            folder_id=item.get("folder_id"),
            caption=item.get("caption"),
            sha256=item.get("sha256"),
            transfer_method=item.get("transfer_method") or "bot_api",
        )
        for item in result.items
    ]

    return ApiResponse(
        data=FileListResponse(
            items=items,
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
        )
    )


@router.get("/{file_id}", response_model=ApiResponse[FileDetailsResponse])
async def get_file_details(
    file_id: str,
    current_user: dict = Depends(require_authenticated_user),
    management_service: BackupManagementService = Depends(get_management_service),
) -> ApiResponse[FileDetailsResponse]:
    """Get full metadata details for a single backup file verifying user ownership."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    details = await management_service.get_file_details(user_id=user_id, item_id=file_id)
    if not details:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return ApiResponse(
        data=FileDetailsResponse(
            item_id=details.item_id,
            original_filename=details.original_filename,
            media_type=details.media_type,
            file_size=details.file_size,
            mime_type=details.mime_type,
            caption=details.caption,
            transfer_method=details.transfer_method,
            status=details.status,
            created_at=details.created_at,
            sha256_short=details.sha256_short,
            folder_id=details.folder_id,
            folder_name=details.folder_name,
            tags=details.tags,
            task_progress=details.task_progress,
            task_error=details.task_error,
        )
    )


@router.delete(
    "/{file_id}",
    response_model=ApiResponse[DeleteFileResponse],
    dependencies=[Depends(rate_limit("delete_file", max_requests=30, window_seconds=60))],
)
async def delete_file(
    file_id: str,
    current_user: dict = Depends(require_authenticated_user),
    management_service: BackupManagementService = Depends(get_management_service),
) -> ApiResponse[DeleteFileResponse]:
    """Safely delete a backup file: soft-delete DB record, delete physical storage object, decrement usage."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    try:
        result = await management_service.delete_file(user_id=user_id, item_id=file_id)
        return ApiResponse(
            data=DeleteFileResponse(
                item_id=result.item_id,
                filename=result.filename,
                file_size=result.file_size,
                storage_deleted=result.storage_deleted,
                message=result.message,
            ),
            message=result.message,
        )
    except ResourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found or already deleted")


@router.post(
    "/{file_id}/retry",
    response_model=ApiResponse[RetryFileResponse],
    dependencies=[Depends(rate_limit("retry_file", max_requests=30, window_seconds=60))],
)
async def retry_file_task(
    file_id: str,
    current_user: dict = Depends(require_authenticated_user),
    management_service: BackupManagementService = Depends(get_management_service),
) -> ApiResponse[RetryFileResponse]:
    """Re-queue a failed backup file task for processing."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    try:
        result = await management_service.retry_failed_task(user_id=user_id, item_id=file_id)
        return ApiResponse(
            data=RetryFileResponse(
                task_id=result.task_id,
                item_id=result.item_id,
                message=result.message,
            ),
            message=result.message,
        )
    except ResourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File or task not found")
    except ValidationError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ve.message)


@router.post("/{file_id}/move", response_model=ApiResponse[bool])
async def move_file(
    file_id: str,
    payload: MoveFileRequest,
    current_user: dict = Depends(require_authenticated_user),
    folder_service: FolderService = Depends(get_folder_service),
) -> ApiResponse[bool]:
    """Move a backup file to a destination folder or root."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    try:
        success = await folder_service.move_item_to_folder(
            user_id=user_id,
            item_id=file_id,
            folder_id=payload.folder_id,
        )
        return ApiResponse(data=success, message="File moved successfully")
    except ResourceNotFoundError as rne:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=rne.message)


@router.get("/{file_id}/tags", response_model=ApiResponse[List[TagResponse]])
async def get_file_tags(
    file_id: str,
    current_user: dict = Depends(require_authenticated_user),
    tag_service: TagService = Depends(get_tag_service),
) -> ApiResponse[List[TagResponse]]:
    """List all tags attached to a specific backup file."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    tags_docs = await tag_service.get_item_tags(user_id=user_id, item_id=file_id)
    tags = [
        TagResponse(
            id=t["id"],
            user_id=t["user_id"],
            name=t["name"],
            created_at=t.get("created_at"),
        )
        for t in tags_docs
    ]
    return ApiResponse(data=tags)


@router.post("/{file_id}/tags", response_model=ApiResponse[Dict[str, Any]])
async def add_tag_to_file(
    file_id: str,
    payload: AssignTagRequest,
    current_user: dict = Depends(require_authenticated_user),
    tag_service: TagService = Depends(get_tag_service),
) -> ApiResponse[Dict[str, Any]]:
    """Attach a tag to a backup file."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    try:
        assoc = await tag_service.assign_tag_to_item(
            user_id=user_id,
            item_id=file_id,
            tag_name_or_id=payload.tag,
        )
        return ApiResponse(data=assoc, message="Tag attached successfully")
    except ResourceNotFoundError as rne:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=rne.message)
    except ValidationError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ve.message)


@router.delete("/{file_id}/tags/{tag_id}", response_model=ApiResponse[bool])
async def remove_tag_from_file(
    file_id: str,
    tag_id: str,
    current_user: dict = Depends(require_authenticated_user),
    tag_service: TagService = Depends(get_tag_service),
) -> ApiResponse[bool]:
    """Remove a tag from a backup file."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id) or not ObjectId.is_valid(tag_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    try:
        removed = await tag_service.remove_tag_from_item(
            user_id=user_id,
            item_id=file_id,
            tag_id=tag_id,
        )
        return ApiResponse(data=removed, message="Tag detached successfully")
    except ResourceNotFoundError as rne:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=rne.message)


@router.get(
    "/{file_id}/download",
    dependencies=[Depends(rate_limit("download", max_requests=60, window_seconds=60))],
)
async def download_file(
    file_id: str,
    current_user: dict = Depends(require_authenticated_user),
    management_service: BackupManagementService = Depends(get_management_service),
) -> StreamingResponse:
    """Safe streaming download endpoint verifying user ownership and streaming via StorageService."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    item = await management_service.item_repo.get_by_id(user_id=user_id, item_id=file_id, include_deleted=False)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if item.get("status") != ItemStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File cannot be downloaded because status is '{item.get('status')}'.",
        )

    storage_key = item.get("storage_key")
    if not storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage object not found for this backup item.",
        )

    # Check if storage object exists
    if not await management_service.storage.exists(storage_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Underlying file not found in storage.",
        )

    filename = item.get("original_filename") or f"backup_{file_id}.bin"
    mime_type = item.get("mime_type") or "application/octet-stream"
    file_size = item.get("file_size")

    # Sanitize and encode filename for Content-Disposition header
    ascii_filename = "".join(c for c in filename if c.isascii() and c not in r'/\":*?<>|').strip() or "file.bin"
    encoded_filename = quote(filename)

    headers = {
        "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}',
    }
    if file_size is not None and file_size > 0:
        headers["Content-Length"] = str(file_size)

    stream = management_service.storage.download_stream(storage_key)
    return StreamingResponse(stream, media_type=mime_type, headers=headers)
