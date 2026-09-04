"""Health check endpoints."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.schemas.health import HealthResponse
from app.core.config import get_settings
from app.database.mongo import mongo_manager

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application and Database Health Check",
    description="Returns current status of application services and MongoDB connectivity.",
)
async def health_check() -> JSONResponse:
    """Check connectivity to MongoDB and system health."""
    settings = get_settings()
    db_connected = await mongo_manager.ping()

    if db_connected:
        response_data = HealthResponse(
            status="healthy",
            app=settings.APP_NAME,
            version=settings.APP_VERSION,
            database="connected",
            details={
                "environment": settings.ENVIRONMENT,
                "storage_type": settings.STORAGE_TYPE,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_data.model_dump(mode="json"),
        )
    else:
        response_data = HealthResponse(
            status="degraded",
            app=settings.APP_NAME,
            version=settings.APP_VERSION,
            database="disconnected",
            details={
                "environment": settings.ENVIRONMENT,
                "error": "Database ping failed or connection not established",
            },
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data.model_dump(mode="json"),
        )
