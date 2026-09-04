"""Authentication and user session schemas."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    """Payload for Telegram WebApp or Login Widget authentication."""

    init_data: Optional[str] = Field(default=None, description="Raw Telegram WebApp initData string")
    widget_data: Optional[Dict[str, Any]] = Field(default=None, description="Telegram Login Widget payload")


class TokenLoginRequest(BaseModel):
    """Payload for logging in using a 6-digit one-time code from the Telegram bot."""

    code: str = Field(..., min_length=4, max_length=64, description="One-time login code / token")
    telegram_user_id: Optional[int] = Field(default=None, description="Optional Telegram User ID")


class DevLoginRequest(BaseModel):
    """Payload for local development and automated testing login."""

    telegram_user_id: int = Field(..., description="Telegram user ID")
    first_name: str = Field(default="Test User", description="Display name")
    username: Optional[str] = Field(default=None, description="Telegram username")


class UserResponse(BaseModel):
    """Safe public user profile schema."""

    telegram_user_id: int = Field(..., description="Unique Telegram User ID")
    first_name: str = Field(..., description="User first name")
    last_name: Optional[str] = Field(default=None, description="User last name")
    username: Optional[str] = Field(default=None, description="Telegram username")
    is_active: bool = Field(default=True, description="Account active status")
    is_admin: bool = Field(default=False, description="Admin authorization status")
    created_at: Optional[datetime] = Field(default=None, description="Registration timestamp")


class AuthSuccessResponse(BaseModel):
    """Response returned upon successful authentication."""

    user: UserResponse = Field(..., description="Authenticated user details")
    expires_at: datetime = Field(..., description="Session expiration timestamp")
