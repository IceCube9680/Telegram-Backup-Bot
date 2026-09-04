"""User data model."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class UserModel(BaseModel):
    """Telegram User data model."""

    telegram_user_id: int = Field(..., description="Unique Telegram user ID")
    username: Optional[str] = Field(default=None, description="Telegram username without @")
    first_name: str = Field(..., description="Telegram first name")
    last_name: Optional[str] = Field(default=None, description="Telegram last name")
    is_active: bool = Field(default=True, description="Account active status")
    is_admin: bool = Field(default=False, description="Admin authorization flag")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="User registration timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp",
    )

    def to_doc(self) -> Dict[str, Any]:
        """Convert model to MongoDB document dictionary."""
        return self.model_dump()
