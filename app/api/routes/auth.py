"""Authentication and session management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.dependencies import get_current_user, get_db, require_authenticated_user
from app.api.middleware import rate_limit
from app.api.schemas.auth import (
    AuthSuccessResponse,
    DevLoginRequest,
    TelegramAuthRequest,
    TokenLoginRequest,
    UserResponse,
)
from app.api.schemas.common import ApiResponse
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    LoginTokenManager,
    SessionManager,
    validate_telegram_webapp_data,
    validate_telegram_widget_data,
)
from app.database.repositories.user_repo import UserRepository

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    """Attach secure HttpOnly session cookie to response."""
    settings = get_settings()
    response.set_cookie(
        key=settings.WEB_COOKIE_NAME,
        value=raw_token,
        max_age=settings.WEB_SESSION_EXPIRE_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.WEB_COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    """Clear session cookie from response."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.WEB_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.WEB_COOKIE_SAMESITE,
        path="/",
    )


@router.post(
    "/telegram",
    response_model=ApiResponse[AuthSuccessResponse],
    dependencies=[Depends(rate_limit("auth_telegram", max_requests=15, window_seconds=60))],
)
async def auth_telegram(
    payload: TelegramAuthRequest,
    response: Response,
    request: Request,
    db: AsyncDatabase = Depends(get_db),
) -> ApiResponse[AuthSuccessResponse]:
    """Authenticate via Telegram WebApp initData or Telegram Login Widget signature."""
    settings = get_settings()
    bot_token = settings.telegram_token

    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telegram Bot Token is not configured on server",
        )

    validated_user: dict = {}

    if payload.init_data:
        data = validate_telegram_webapp_data(payload.init_data, bot_token)
        if not data or "user" not in data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Telegram WebApp authentication data",
            )
        validated_user = data["user"]
    elif payload.widget_data:
        data = validate_telegram_widget_data(payload.widget_data, bot_token)
        if not data or "id" not in data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Telegram Login Widget data",
            )
        validated_user = {
            "id": data["id"],
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name"),
            "username": data.get("username"),
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Telegram authentication payload",
        )

    telegram_user_id = int(validated_user["id"])
    first_name = validated_user.get("first_name") or "Telegram User"
    last_name = validated_user.get("last_name")
    username = validated_user.get("username")

    # Upsert user record
    user_repo = UserRepository(db)
    user = await user_repo.upsert_user(
        telegram_user_id=telegram_user_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
    )

    # Issue session
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    raw_token, expires_at = await SessionManager.create_session(
        db=db,
        user_id=telegram_user_id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    _set_session_cookie(response, raw_token)

    return ApiResponse(
        data=AuthSuccessResponse(
            user=UserResponse(
                telegram_user_id=user["telegram_user_id"],
                first_name=user["first_name"],
                last_name=user.get("last_name"),
                username=user.get("username"),
                is_active=user.get("is_active", True),
                is_admin=user.get("is_admin", False),
                created_at=user.get("created_at"),
            ),
            expires_at=expires_at,
        ),
        message="Authentication successful",
    )


@router.post(
    "/token",
    response_model=ApiResponse[AuthSuccessResponse],
    dependencies=[Depends(rate_limit("auth_token", max_requests=10, window_seconds=60))],
)
async def auth_token(
    payload: TokenLoginRequest,
    response: Response,
    request: Request,
    db: AsyncDatabase = Depends(get_db),
) -> ApiResponse[AuthSuccessResponse]:
    """Authenticate using single-use 6-digit one-time login code generated from Telegram bot."""
    consumed = await LoginTokenManager.verify_and_consume_token(
        db=db,
        raw_token=payload.code,
        telegram_user_id=payload.telegram_user_id,
    )

    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or already used login code.",
        )

    telegram_user_id = consumed["telegram_user_id"]
    user_repo = UserRepository(db)
    user = await user_repo.get_by_telegram_id(telegram_user_id)

    if not user:
        user = await user_repo.upsert_user(
            telegram_user_id=telegram_user_id,
            first_name=f"User {telegram_user_id}",
        )

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    raw_token, expires_at = await SessionManager.create_session(
        db=db,
        user_id=telegram_user_id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    _set_session_cookie(response, raw_token)

    return ApiResponse(
        data=AuthSuccessResponse(
            user=UserResponse(
                telegram_user_id=user["telegram_user_id"],
                first_name=user["first_name"],
                last_name=user.get("last_name"),
                username=user.get("username"),
                is_active=user.get("is_active", True),
                is_admin=user.get("is_admin", False),
                created_at=user.get("created_at"),
            ),
            expires_at=expires_at,
        ),
        message="Authentication successful",
    )


@router.post(
    "/dev-login",
    response_model=ApiResponse[AuthSuccessResponse],
    dependencies=[Depends(rate_limit("auth_dev_login", max_requests=20, window_seconds=60))],
)
async def auth_dev_login(
    payload: DevLoginRequest,
    response: Response,
    request: Request,
    db: AsyncDatabase = Depends(get_db),
) -> ApiResponse[AuthSuccessResponse]:
    """Development and automated test login endpoint (strictly disabled in production)."""
    settings = get_settings()
    if not settings.dev_login_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development login is strictly disabled in production environments",
        )

    user_repo = UserRepository(db)
    user = await user_repo.upsert_user(
        telegram_user_id=payload.telegram_user_id,
        first_name=payload.first_name,
        username=payload.username,
    )

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    raw_token, expires_at = await SessionManager.create_session(
        db=db,
        user_id=payload.telegram_user_id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    _set_session_cookie(response, raw_token)

    return ApiResponse(
        data=AuthSuccessResponse(
            user=UserResponse(
                telegram_user_id=user["telegram_user_id"],
                first_name=user["first_name"],
                last_name=user.get("last_name"),
                username=user.get("username"),
                is_active=user.get("is_active", True),
                is_admin=user.get("is_admin", False),
                created_at=user.get("created_at"),
            ),
            expires_at=expires_at,
        ),
        message="Dev login successful",
    )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_me(
    current_user: dict = Depends(require_authenticated_user),
) -> ApiResponse[UserResponse]:
    """Retrieve current authenticated user profile."""
    return ApiResponse(
        data=UserResponse(
            telegram_user_id=current_user["telegram_user_id"],
            first_name=current_user["first_name"],
            last_name=current_user.get("last_name"),
            username=current_user.get("username"),
            is_active=current_user.get("is_active", True),
            is_admin=current_user.get("is_admin", False),
            created_at=current_user.get("created_at"),
        )
    )


@router.post("/logout", response_model=ApiResponse[None])
async def logout(
    request: Request,
    response: Response,
    db: AsyncDatabase = Depends(get_db),
) -> ApiResponse[None]:
    """Invalidate active session and clear session cookie."""
    settings = get_settings()
    raw_token = request.cookies.get(settings.WEB_COOKIE_NAME)
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if raw_token:
        await SessionManager.revoke_session(db, raw_token)

    _clear_session_cookie(response)
    return ApiResponse(data=None, message="Logged out successfully")
