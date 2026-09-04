"""Security, authentication, session management, and cryptographic helpers."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hash of a raw token for secure database storage."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def validate_telegram_webapp_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> Optional[Dict[str, Any]]:
    """Validate Telegram WebApp initData string using HMAC-SHA-256 per Telegram specification.

    Returns the parsed data dictionary including user information if valid, None otherwise.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed_params = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed_params.pop("hash", None)
        if not received_hash:
            return None

        # Build check string: key=value sorted alphabetically joined by newline
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed_params.items())
        )

        # secret_key = HMAC_SHA256(b"WebAppData", bot_token)
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        # expected_hash = HMAC_SHA256(secret_key, data_check_string)
        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(received_hash, expected_hash):
            logger.warning("Telegram WebApp initData hash verification failed")
            return None

        # Validate auth_date to prevent replay attacks
        auth_date_raw = parsed_params.get("auth_date")
        if auth_date_raw:
            try:
                auth_date = int(auth_date_raw)
                if time.time() - auth_date > max_age_seconds:
                    logger.warning("Telegram WebApp initData is expired")
                    return None
            except ValueError:
                return None

        # Parse user JSON if present
        result = dict(parsed_params)
        if "user" in result and isinstance(result["user"], str):
            try:
                result["user"] = json.loads(result["user"])
            except json.JSONDecodeError:
                pass

        return result
    except Exception as e:
        logger.error(f"Error validating Telegram WebApp data: {e}")
        return None


def validate_telegram_widget_data(
    data: Dict[str, Any],
    bot_token: str,
    max_age_seconds: int = 86400,
) -> Optional[Dict[str, Any]]:
    """Validate Telegram Login Widget data dictionary using SHA-256 & HMAC-SHA-256."""
    if not data or not bot_token:
        return None

    try:
        check_dict = {str(k): str(v) for k, v in data.items() if k != "hash" and v is not None}
        received_hash = data.get("hash")
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(check_dict.items())
        )

        # secret_key = SHA256(bot_token)
        secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()

        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(received_hash, expected_hash):
            logger.warning("Telegram Login Widget hash verification failed")
            return None

        auth_date_raw = data.get("auth_date")
        if auth_date_raw:
            try:
                auth_date = int(auth_date_raw)
                if time.time() - auth_date > max_age_seconds:
                    logger.warning("Telegram Login Widget data is expired")
                    return None
            except ValueError:
                return None

        return data
    except Exception as e:
        logger.error(f"Error validating Telegram Widget data: {e}")
        return None


class SessionManager:
    """Manages secure hashed server-side browser sessions in MongoDB."""

    @staticmethod
    async def create_session(
        db: AsyncDatabase,
        user_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[str, datetime]:
        """Create a new session, storing only the hashed token in MongoDB. Returns (raw_token, expires_at)."""
        settings = get_settings()
        raw_token = secrets.token_urlsafe(32)
        token_hashed = hash_token(raw_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.WEB_SESSION_EXPIRE_SECONDS)

        session_doc = {
            "token_hash": token_hashed,
            "user_id": user_id,
            "created_at": now,
            "expires_at": expires_at,
            "last_active_at": now,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }

        await db["web_sessions"].insert_one(session_doc)
        logger.info(f"Created web session for user_id={user_id} (expires={expires_at.isoformat()})")
        return raw_token, expires_at

    @staticmethod
    async def verify_session(db: AsyncDatabase, raw_token: str) -> Optional[Dict[str, Any]]:
        """Verify raw session token against hashed database record. Returns session doc if valid."""
        if not raw_token or not isinstance(raw_token, str):
            return None

        token_hashed = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        doc = await db["web_sessions"].find_one(
            {
                "token_hash": token_hashed,
                "expires_at": {"$gt": now},
            }
        )
        return doc

    @staticmethod
    async def revoke_session(db: AsyncDatabase, raw_token: str) -> bool:
        """Revoke a single session by raw token."""
        if not raw_token:
            return False

        token_hashed = hash_token(raw_token)
        result = await db["web_sessions"].delete_one({"token_hash": token_hashed})
        return result.deleted_count > 0

    @staticmethod
    async def revoke_all_user_sessions(db: AsyncDatabase, user_id: int) -> int:
        """Revoke all active sessions for a given user."""
        result = await db["web_sessions"].delete_many({"user_id": user_id})
        return result.deleted_count


class LoginTokenManager:
    """Manages single-use, hashed one-time login tokens with brute-force attack protection."""

    @staticmethod
    async def create_login_token(
        db: AsyncDatabase,
        user_id: int,
        telegram_user_id: int,
        expire_minutes: int = 10,
    ) -> Tuple[str, datetime]:
        """Generate a 6-digit one-time login code, storing only its hash."""
        # 6-digit numeric code
        code = f"{secrets.randbelow(1000000):06d}"
        token_hashed = hash_token(code)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expire_minutes)

        # Invalidate previous unconsumed tokens for this user
        await db["login_tokens"].delete_many(
            {"telegram_user_id": telegram_user_id, "used_at": None}
        )

        doc = {
            "token_hash": token_hashed,
            "user_id": user_id,
            "telegram_user_id": telegram_user_id,
            "created_at": now,
            "expires_at": expires_at,
            "attempts": 0,
            "max_attempts": 5,
            "used_at": None,
        }

        await db["login_tokens"].insert_one(doc)
        logger.info(f"Generated one-time login token for telegram_user_id={telegram_user_id}")
        return code, expires_at

    @staticmethod
    async def verify_and_consume_token(
        db: AsyncDatabase,
        raw_token: str,
        telegram_user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically verify and consume a one-time token with brute-force protection."""
        if not raw_token or not isinstance(raw_token, str):
            return None

        clean_token = raw_token.strip()
        token_hashed = hash_token(clean_token)
        now = datetime.now(timezone.utc)

        # Query filter for valid unconsumed token with attempt budget
        query_filter: Dict[str, Any] = {
            "token_hash": token_hashed,
            "used_at": None,
            "attempts": {"$lt": 5},
            "expires_at": {"$gt": now},
        }

        if telegram_user_id is not None:
            query_filter["telegram_user_id"] = telegram_user_id

        # Atomically mark as consumed
        doc = await db["login_tokens"].find_one_and_update(
            query_filter,
            {"$set": {"used_at": now}},
            return_document=ReturnDocument.BEFORE,
        )

        if doc:
            logger.info(f"Successfully consumed one-time login token for user {doc.get('telegram_user_id')}")
            return doc

        # If telegram_user_id provided and token mismatch, increment failed attempts on active token
        if telegram_user_id is not None:
            await db["login_tokens"].update_many(
                {
                    "telegram_user_id": telegram_user_id,
                    "used_at": None,
                    "expires_at": {"$gt": now},
                },
                {"$inc": {"attempts": 1}},
            )
            logger.warning(f"Failed login attempt registered for telegram_user_id={telegram_user_id}")

        return None
