"""FastAPI Application setup, lifecycle, and middleware configuration."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.api.routes import auth, files, folders, health, search, stats, tags
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import get_logger, setup_logging
from app.database.mongo import mongo_manager

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")

    # Connect to MongoDB on startup (allow retry/fallback if starting up before DB in dev/tests)
    try:
        db = await mongo_manager.connect()
        from app.database.indexes import ensure_indexes
        await ensure_indexes(db)
    except Exception as e:
        logger.warning(
            f"Could not connect to MongoDB on startup ({e}). Will retry on health check / requests."
        )

    yield

    # Clean disconnect on shutdown
    await mongo_manager.disconnect()
    logger.info("Application shutdown complete.")


def create_app() -> FastAPI:
    """Factory function to create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="FastAPI backend and Web Dashboard for Telegram Backup Bot",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # Security Headers and Request Correlation ID Middlewares
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # Safe CORS configuration with explicit origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.WEB_ALLOWED_ORIGINS or ["http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    # Centralized exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "success": False,
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                },
            },
        )

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.error(f"Application error: {exc.message} | Details: {exc.details}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.__class__.__name__,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled server error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                },
            },
        )

    # Mount health routers
    app.include_router(health.router)
    app.include_router(health.router, prefix="/api")

    # Mount API feature routers
    app.include_router(auth.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(folders.router, prefix="/api")
    app.include_router(tags.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")

    # Mount static frontend
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def root():
            index_file = frontend_dir / "index.html"
            if index_file.exists():
                return FileResponse(str(index_file))
            return JSONResponse({"status": "running"})

        @app.get("/login", include_in_schema=False)
        async def login_page():
            login_file = frontend_dir / "login.html"
            if login_file.exists():
                return FileResponse(str(login_file))
            return JSONResponse({"status": "login"})

        @app.get("/dashboard", include_in_schema=False)
        async def dashboard_page():
            index_file = frontend_dir / "index.html"
            if index_file.exists():
                return FileResponse(str(index_file))
            return JSONResponse({"status": "dashboard"})

    return app


app = create_app()
