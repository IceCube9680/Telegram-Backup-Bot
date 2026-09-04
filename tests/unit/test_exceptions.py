"""Unit tests for custom exception hierarchy."""

from app.core.exceptions import (
    AppException,
    DatabaseConnectionError,
    ConfigurationError,
    ResourceNotFoundError,
    ValidationError,
    StorageError,
)


def test_base_app_exception():
    """Test base AppException attributes."""
    exc = AppException(message="Custom error", status_code=418, details={"k": "v"})
    assert exc.message == "Custom error"
    assert exc.status_code == 418
    assert exc.details == {"k": "v"}
    assert str(exc) == "Custom error"


def test_domain_exceptions_status_codes():
    """Test standard HTTP status codes of domain exceptions."""
    assert DatabaseConnectionError().status_code == 503
    assert ConfigurationError().status_code == 500
    assert ResourceNotFoundError().status_code == 404
    assert ValidationError().status_code == 400
    assert StorageError().status_code == 500
