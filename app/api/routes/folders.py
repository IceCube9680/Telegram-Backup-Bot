"""Folder organization REST API routes."""

from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_folder_service, require_authenticated_user
from app.api.schemas.common import ApiResponse
from app.api.schemas.folders import (
    CreateFolderRequest,
    FolderListResponse,
    FolderResponse,
)
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.core.logging import get_logger
from app.services.folder_service import FolderService

logger = get_logger(__name__)
router = APIRouter(prefix="/folders", tags=["Folders"])


@router.get("", response_model=ApiResponse[FolderListResponse])
async def list_folders(
    parent_id: Optional[str] = Query(default=None, description="Filter by parent folder ID"),
    current_user: dict = Depends(require_authenticated_user),
    folder_service: FolderService = Depends(get_folder_service),
) -> ApiResponse[FolderListResponse]:
    """List all folders belonging to the current user."""
    user_id = current_user["telegram_user_id"]
    folder_docs = await folder_service.list_folders(user_id=user_id, parent_id=parent_id)

    folders = [
        FolderResponse(
            id=f["id"],
            user_id=f["user_id"],
            name=f["name"],
            parent_id=f.get("parent_id"),
            created_at=f.get("created_at"),
            updated_at=f.get("updated_at"),
        )
        for f in folder_docs
    ]
    return ApiResponse(data=FolderListResponse(folders=folders))


@router.post("", response_model=ApiResponse[FolderResponse])
async def create_folder(
    payload: CreateFolderRequest,
    current_user: dict = Depends(require_authenticated_user),
    folder_service: FolderService = Depends(get_folder_service),
) -> ApiResponse[FolderResponse]:
    """Create a new folder for the current user."""
    user_id = current_user["telegram_user_id"]
    try:
        folder = await folder_service.create_folder(
            user_id=user_id,
            name=payload.name,
            parent_id=payload.parent_id,
        )
        return ApiResponse(
            data=FolderResponse(
                id=folder["id"],
                user_id=folder["user_id"],
                name=folder["name"],
                parent_id=folder.get("parent_id"),
                created_at=folder.get("created_at"),
                updated_at=folder.get("updated_at"),
            ),
            message="Folder created successfully",
        )
    except ValidationError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ve.message)
    except ResourceNotFoundError as rne:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=rne.message)


@router.get("/{folder_id}", response_model=ApiResponse[FolderResponse])
async def get_folder(
    folder_id: str,
    current_user: dict = Depends(require_authenticated_user),
    folder_service: FolderService = Depends(get_folder_service),
) -> ApiResponse[FolderResponse]:
    """Get single folder details."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(folder_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    folder = await folder_service.get_folder(user_id=user_id, folder_id=folder_id)
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    return ApiResponse(
        data=FolderResponse(
            id=folder["id"],
            user_id=folder["user_id"],
            name=folder["name"],
            parent_id=folder.get("parent_id"),
            created_at=folder.get("created_at"),
            updated_at=folder.get("updated_at"),
        )
    )


@router.delete("/{folder_id}", response_model=ApiResponse[bool])
async def delete_folder(
    folder_id: str,
    current_user: dict = Depends(require_authenticated_user),
    folder_service: FolderService = Depends(get_folder_service),
) -> ApiResponse[bool]:
    """Delete folder and safely unassign contained items to root."""
    user_id = current_user["telegram_user_id"]
    if not ObjectId.is_valid(folder_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    deleted = await folder_service.delete_folder(user_id=user_id, folder_id=folder_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    return ApiResponse(data=True, message="Folder deleted successfully")
