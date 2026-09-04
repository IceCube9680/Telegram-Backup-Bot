"""Statistics REST API routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_management_service, require_authenticated_user
from app.api.schemas.common import ApiResponse
from app.api.schemas.stats import StatsResponse
from app.core.logging import get_logger
from app.services.backup_management_service import BackupManagementService

logger = get_logger(__name__)
router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("", response_model=ApiResponse[StatsResponse])
async def get_user_stats(
    current_user: dict = Depends(require_authenticated_user),
    management_service: BackupManagementService = Depends(get_management_service),
) -> ApiResponse[StatsResponse]:
    """Get cumulative storage usage and active items breakdown for authenticated user."""
    user_id = current_user["telegram_user_id"]
    stats = await management_service.get_user_stats(user_id=user_id)

    return ApiResponse(
        data=StatsResponse(
            user_id=stats.user_id,
            total_files=stats.total_files,
            total_size_bytes=stats.total_size_bytes,
            completed_count=stats.completed_count,
            processing_count=stats.processing_count,
            pending_count=stats.pending_count,
            failed_count=stats.failed_count,
        )
    )
