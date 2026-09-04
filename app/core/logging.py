"""Structured logging configuration."""

import logging
import sys
from typing import Optional


def setup_logging(log_level: Optional[str] = None) -> None:
    """Configure structured logging for the application."""
    level_str = (log_level or "INFO").upper()
    numeric_level = getattr(logging, level_str, logging.INFO)

    log_format = (
        "[%(asctime)s] [%(levelname)-8s] [%(name)s:%(lineno)d] - %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt=date_format,
        stream=sys.stdout,
        force=True,
    )

    # Set specific third-party library log levels to avoid noisy output
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)
