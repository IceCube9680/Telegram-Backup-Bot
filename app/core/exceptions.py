"""Custom application exceptions."""

from typing import Any, Optional


class AppException(Exception):
    """Base exception for application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class DatabaseConnectionError(AppException):
    """Raised when database connection fails or ping times out."""

    def __init__(
        self,
        message: str = "Database connection error",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=503, details=details)


class ConfigurationError(AppException):
    """Raised when required configuration is missing or invalid."""

    def __init__(
        self,
        message: str = "Configuration error",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=500, details=details)


class ResourceNotFoundError(AppException):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        message: str = "Resource not found",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=404, details=details)


class ValidationError(AppException):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str = "Validation error",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=400, details=details)


class StorageError(AppException):
    """Raised when storage operation fails."""

    def __init__(
        self,
        message: str = "Storage error",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=500, details=details)


class StorageNotFoundError(StorageError):
    """Raised when a requested file or storage key does not exist."""

    def __init__(
        self,
        message: str = "Storage object not found",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.status_code = 404


class StorageValidationError(StorageError):
    """Raised when a storage key contains illegal characters, path traversal, or format errors."""

    def __init__(
        self,
        message: str = "Invalid storage key",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.status_code = 400


class StoragePermissionError(StorageError):
    """Raised when filesystem permission is denied."""

    def __init__(
        self,
        message: str = "Storage permission denied",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.status_code = 500


class TaskProcessingError(AppException):
    """Base exception for background task processing failures."""

    def __init__(
        self,
        message: str = "Task processing error",
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=status_code, details=details)


class TelegramDownloadError(TaskProcessingError):
    """Transient error downloading file from Telegram Bot API or MTProto."""

    def __init__(
        self,
        message: str = "Telegram file download failed",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=502, details=details)


class TelegramPermanentError(TaskProcessingError):
    """Permanent unrecoverable error with Telegram file reference or API."""

    def __init__(
        self,
        message: str = "Permanent Telegram error",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=400, details=details)


class StorageProcessingError(TaskProcessingError):
    """Error persisting downloaded file to storage service."""

    def __init__(
        self,
        message: str = "Storage processing failed",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message=message, status_code=500, details=details)


class TelegramFloodWaitError(TelegramDownloadError):
    """Raised when Telegram MTProto returns FLOOD_WAIT_X."""

    def __init__(self, wait_seconds: int, message: Optional[str] = None, details: Optional[dict[str, Any]] = None) -> None:
        msg = message or f"Telegram rate limit: FLOOD_WAIT for {wait_seconds} seconds."
        det = details or {}
        det["wait_seconds"] = wait_seconds
        super().__init__(message=msg, details=det)
        self.wait_seconds = wait_seconds


class TelegramFileRefExpiredError(TelegramDownloadError):
    """Raised when Telegram MTProto file reference expires."""

    def __init__(self, message: Optional[str] = None, details: Optional[dict[str, Any]] = None) -> None:
        msg = message or "Telegram file reference expired."
        super().__init__(message=msg, details=details)


