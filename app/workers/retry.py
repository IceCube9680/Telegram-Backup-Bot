"""Worker error classification and exponential backoff retry utilities."""

import asyncio
import random
from typing import Any, Optional
import aiohttp
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

from app.core.exceptions import (
    AppException,
    ResourceNotFoundError,
    StoragePermissionError,
    StorageProcessingError,
    StorageValidationError,
    TaskProcessingError,
    TelegramDownloadError,
    TelegramFileRefExpiredError,
    TelegramFloodWaitError,
    TelegramPermanentError,
    ValidationError,
)


def is_retryable_error(exc: Exception) -> bool:
    """Classify an exception as retryable (transient) or permanent.

    Returns:
        bool: True if the operation should be retried, False for permanent failures.
    """
    # 1. Explicit permanent exceptions
    if isinstance(
        exc,
        (
            TelegramPermanentError,
            StorageValidationError,
            StoragePermissionError,
            ResourceNotFoundError,
            ValidationError,
            ValueError,
            TypeError,
            KeyError,
        ),
    ):
        return False

    # 2. Telegram Unauthorized (invalid token) is permanent
    if isinstance(exc, TelegramUnauthorizedError):
        return False

    # 3. Telegram Bad Request checks (invalid file_id or oversized file for standard Bot API)
    if isinstance(exc, TelegramBadRequest):
        msg = str(exc).lower()
        if (
            "file is too big" in msg
            or "wrong file_id" in msg
            or "wrong remote file identifier" in msg
            or "file_reference_expired" in msg
            or "file not found" in msg
        ):
            return False
        # Other BadRequests are generally client/data errors
        return False

    # 4. Telegram Rate Limiting (FloodWait / RetryAfter) and Server errors are retryable
    if isinstance(exc, (TelegramRetryAfter, TelegramServerError, TelegramNetworkError)):
        return True

    # 5. Network / Transport level errors are retryable
    if isinstance(
        exc,
        (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            TimeoutError,
            ConnectionError,
            TelegramDownloadError,
        ),
    ):
        return True

    # 6. Generic Telegram API error fallback
    if isinstance(exc, TelegramAPIError):
        return True

    # 7. Other general exceptions: allow retry for transient I/O, unless explicitly non-retryable
    if isinstance(exc, (StorageProcessingError, OSError)):
        return True

    # Default to False for unexpected programming exceptions to avoid futile retry loops
    return False


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """Calculate bounded exponential backoff delay with optional random jitter.

    Formula: min(max_delay, base_delay * 2^(attempt - 1)) + jitter
    """
    safe_attempt = max(1, attempt)
    # Exponential factor: 2^(safe_attempt - 1)
    factor = 2 ** min(safe_attempt - 1, 10)
    delay = min(max_delay, base_delay * factor)

    if jitter:
        # Add random jitter up to 25% of the delay or 1 second max
        jitter_amount = random.uniform(0.0, min(1.0, delay * 0.25))
        delay += jitter_amount

    return round(delay, 2)
