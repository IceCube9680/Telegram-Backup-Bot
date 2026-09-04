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
