"""Health check endpoints (Liveness, Readiness, Combined)."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse
from app.core.config import get_settings
from app.database.mongo import mongo_manager

router = APIRouter(tags=["Health"])


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness Probe",
    description="Verifies that the application process is running and accepting requests.",
)
async def liveness_probe() -> JSONResponse:
    """Liveness probe: confirms application process is running."""
    data = LivenessResponse(status="alive")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data.model_dump(mode="json"),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    description="Verifies MongoDB connectivity. Returns HTTP 200 when connected, HTTP 503 when disconnected.",
)
async def readiness_probe() -> JSONResponse:
    """Readiness probe: verifies MongoDB connectivity."""
    db_connected = await mongo_manager.ping()
    if db_connected:
        data = ReadinessResponse(
            status="ready",
            database="connected",
            details={"database_name": get_settings().MONGODB_DATABASE},
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=data.model_dump(mode="json"),
        )
    else:
        data = ReadinessResponse(
            status="not_ready",
            database="disconnected",
            details={"error": "MongoDB is not reachable or ping timed out"},
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=data.model_dump(mode="json"),
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Combined Application Health Check",
    description="Returns combined application health and MongoDB connectivity status.",
)
async def health_check() -> JSONResponse:
    """Combined health check: returns overall health and database connectivity."""
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
                "error": "MongoDB is disconnected or unreachable",
            },
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data.model_dump(mode="json"),
        )
