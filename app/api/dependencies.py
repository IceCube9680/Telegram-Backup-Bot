"""FastAPI reusable dependency injectors for authentication, database, and service layers."""

from typing import Any, Dict, Optional
from fastapi import Depends, HTTPException, Request, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import SessionManager
from app.database.mongo import get_database
from app.database.repositories.user_repo import UserRepository
from app.services.backup_management_service import BackupManagementService
from app.services.folder_service import FolderService
from app.services.search_service import SearchService
from app.services.storage_service import StorageService, get_storage_service
from app.services.tag_service import TagService

logger = get_logger(__name__)


async def get_db() -> AsyncDatabase:
    """Dependency providing access to the MongoDB async database."""
    return await get_database()


async def get_current_user(
    request: Request,
    db: AsyncDatabase = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    """Extract and verify session token from cookie or Authorization header."""
    settings = get_settings()

    # 1. Try cookie
    raw_token = request.cookies.get(settings.WEB_COOKIE_NAME)

    # 2. Try Authorization: Bearer <token>
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        return None

    # Verify hashed session in MongoDB
    session = await SessionManager.verify_session(db, raw_token)
    if not session:
        return None

    user_id = session.get("user_id")
    if not user_id:
        return None

    user_repo = UserRepository(db)
    user = await user_repo.get_by_telegram_id(user_id)
    if not user or not user.get("is_active", True):
        return None

    return user


async def require_authenticated_user(
    user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Dependency that strictly requires an authenticated and active user, raising 401 otherwise."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_management_service(
    db: AsyncDatabase = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> BackupManagementService:
    """Dependency injecting BackupManagementService."""
    return BackupManagementService(db=db, storage_service=storage)


async def get_search_service(
    db: AsyncDatabase = Depends(get_db),
) -> SearchService:
    """Dependency injecting SearchService."""
    return SearchService(db=db)


async def get_folder_service(
    db: AsyncDatabase = Depends(get_db),
) -> FolderService:
    """Dependency injecting FolderService."""
    return FolderService(db=db)


async def get_tag_service(
    db: AsyncDatabase = Depends(get_db),
) -> TagService:
    """Dependency injecting TagService."""
    return TagService(db=db)
