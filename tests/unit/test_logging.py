"""Unit tests for logging configuration."""

import logging
from app.core.logging import get_logger, setup_logging


def test_setup_logging_and_get_logger():
    """Test logger creation and formatting setup."""
    setup_logging("DEBUG")
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"
